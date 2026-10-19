import errno
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from copier import CopyCancelled, copy_new
from journal import Journal
from recovery import retry_copy, RepeatedCopyError
from background import copy_priority
from transfer_progress import TransferProgress


class RecoveryTests(unittest.TestCase):
    def test_five_identical_errors_stop(self):
        operation = Mock(side_effect=OSError(errno.EIO, 'USB error'))
        notices = Mock()
        with self.assertRaises(RepeatedCopyError):
            retry_copy(operation, threading.Event(), notices, delay=0)
        self.assertEqual(operation.call_count, 5)
        self.assertEqual(notices.call_count, 4)

    def test_transient_error_recovers(self):
        operation = Mock(side_effect=[OSError(errno.EIO, 'USB error'), 3])
        self.assertEqual(retry_copy(operation, threading.Event(), delay=0), 3)
        self.assertEqual(operation.call_count, 2)

    def test_cancel_during_retry(self):
        stop = threading.Event()
        operation = Mock(side_effect=OSError(errno.EIO, 'USB error'))
        with self.assertRaises(CopyCancelled):
            retry_copy(operation, stop, lambda *_: stop.set(), delay=0)
        self.assertEqual(operation.call_count, 1)

    def test_replacement_recopies_whole_event_and_replaces_stale_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, first, second = root/'Event', root/'USB1', root/'USB2'
            (source/'Originals').mkdir(parents=True)
            first.mkdir()
            second.mkdir()
            (source/'Originals/a.jpg').write_bytes(b'photo')
            journal = Journal(root/'history.sqlite3')
            try:
                self.assertEqual(copy_new(source, first, ['Originals'], age=0, journal=journal, volume='first'), 1)
                stale = second/'Event/Originals/a.jpg'
                stale.parent.mkdir(parents=True)
                stale.write_bytes(b'stale')
                session = set()
                self.assertEqual(copy_new(source, second, ['Originals'], age=0, journal=journal, volume='second', ignore_history=True, session_delivered=session), 1)
                self.assertEqual(stale.read_bytes(), b'photo')
                self.assertEqual(journal.delivery(source/'Originals/a.jpg', (source/'Originals/a.jpg').stat())['volume'], 'second')
                self.assertEqual(copy_new(source, second, ['Originals'], age=0, journal=journal, volume='second', ignore_history=True, session_delivered=session), 0)
            finally:
                journal.close()

    def test_full_speed_has_no_delays_and_keeps_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, target = root/'Event', root/'USB'
            (source/'Originals').mkdir(parents=True)
            target.mkdir()
            (source/'Originals/a.jpg').write_bytes(b'photo')
            with patch('copier.time.sleep') as sleep:
                self.assertEqual(copy_new(source, target, ['Originals'], age=0, full_speed=True, verify=True), 1)
                sleep.assert_not_called()

    def test_normal_priority_restored_after_error(self):
        with patch('background.normal_process_priority') as normal, patch('background.lower_process_priority') as lower, patch('background.background_copy_thread') as quiet:
            with self.assertRaises(RuntimeError):
                with copy_priority(True):
                    raise RuntimeError('error')
            normal.assert_called_once()
            lower.assert_called_once()
            quiet.assert_not_called()

    def test_remaining_estimate_includes_verification_work(self):
        with patch('transfer_progress.time.monotonic', return_value=0):
            tracker = TransferProgress({'a': 100, 'b': 100}, verify=True)
            tracker.start('a', 100)
        with patch('transfer_progress.time.monotonic', return_value=2):
            tracker.advance(100)
            value = tracker.snapshot()
            self.assertEqual((value['remaining_files'], value['remaining_bytes']), (2, 100))
            self.assertEqual(value['eta_seconds'], 6)
            tracker.advance(100, checking=True)
            tracker.finish('a', delivered=True)
            self.assertEqual(tracker.snapshot()['remaining_bytes'], 100)
            tracker.start('b', 100)
            tracker.advance(100)
            tracker.advance(100, checking=True)
            tracker.finish('b', delivered=True)
            self.assertEqual(tracker.snapshot()['eta_seconds'], 0)
