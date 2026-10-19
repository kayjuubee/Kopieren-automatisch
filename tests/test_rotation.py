import errno
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from copier import copy_new, DiskFull, CopyCancelled
from journal import Journal


class RotationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.source = root / 'Event'
        self.first, self.second = root / 'USB1', root / 'USB2'
        self.first.mkdir()
        self.second.mkdir()
        (self.source / 'Originals').mkdir(parents=True)
        self.journal = Journal(root / 'journal.sqlite3')
        self.addCleanup(self.journal.close)
        self.file = self.source / 'Originals' / 'a.jpg'
        self.file.write_bytes(b'first photo')

    def copy(self, target, **kwargs):
        return copy_new(self.source, target, ['Originals'], age=0, journal=self.journal, **kwargs)

    def test_full_then_new_stick_only_gets_remaining_files(self):
        self.assertEqual(self.copy(self.first), 1)
        other = self.file.with_name('b.jpg')
        other.write_bytes(b'second photo')
        with patch('copier.shutil.disk_usage', return_value=SimpleNamespace(free=0)):
            with self.assertRaises(DiskFull):
                self.copy(self.first)
        self.assertFalse((self.first / 'Event/Originals/b.jpg').exists())
        self.assertEqual(self.copy(self.second), 1)
        self.assertFalse((self.second / 'Event/Originals/a.jpg').exists())
        self.assertEqual((self.second / 'Event/Originals/b.jpg').read_bytes(), b'second photo')
        self.assertEqual(self.copy(self.second), 0)

    def test_journal_survives_reopening(self):
        self.assertEqual(self.copy(self.first), 1)
        second_connection = Journal(Path(self.tmp.name) / 'journal.sqlite3')
        try:
            self.assertEqual(copy_new(self.source, self.second, ['Originals'], age=0, journal=second_connection), 0)
        finally:
            second_connection.close()

    def test_full_during_write_leaves_no_partial_file_or_delivery_record(self):
        with patch('copier.os.fsync', side_effect=OSError(errno.ENOSPC, 'disk full')):
            with self.assertRaises(DiskFull):
                self.copy(self.first)
        self.assertEqual(list((self.first / 'Event/Originals').iterdir()), [])
        self.assertFalse(self.journal.contains(self.file, self.file.stat()))
        self.assertEqual(self.copy(self.second), 1)

    def test_cancelled_copy_and_removed_device(self):
        stop = threading.Event()
        def progress(*_):
            stop.set()
        with self.assertRaises(CopyCancelled):
            self.copy(self.first, progress=progress, stop=stop)
        self.assertEqual(list((self.first / 'Event/Originals').iterdir()), [])
        self.assertFalse(self.journal.contains(self.file, self.file.stat()))
        with self.assertRaises(OSError):
            self.copy(self.second, valid_target=lambda: False)

    def test_progress_and_rate_limits(self):
        reports = []
        self.assertEqual(self.copy(self.first, progress=lambda *args: reports.append(args)), 1)
        self.assertEqual(reports[-1], ('Originals/a.jpg', self.file.stat().st_size, self.file.stat().st_size, 1))
        with self.assertRaises(ValueError):
            self.copy(self.second, rate=0)

    def test_changed_source_not_committed(self):
        def mutate(*_):
            self.file.write_bytes(b'photo still changing with new bytes')
        self.assertEqual(self.copy(self.first, progress=mutate), 0)
        self.assertFalse(self.journal.contains(self.file, self.file.stat()))
        self.assertEqual(list((self.first / 'Event/Originals').iterdir()), [])
