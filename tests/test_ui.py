"""Run with a display (or Xvfb); hardware operations are simulated."""
import os
import gc
import sys
import threading
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import app


@unittest.skipUnless(os.environ.get('DISPLAY') or os.name == 'nt', 'Display required')
class InterfaceTests(unittest.TestCase):
    def setUp(self):
        gc.collect()
        self.previous_exception_hook = sys.excepthook
        self.previous_thread_hook = threading.excepthook
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.parent = root / 'events'
        self.source = self.parent / 'Event'
        (self.source / 'Originals').mkdir(parents=True)
        self.file = self.source / 'Originals/photo.jpg'
        self.file.write_bytes(b'photo')
        os.utime(self.file, (0, 0))
        self.first, self.second = root / 'USB1', root / 'USB2'
        self.first.mkdir()
        self.second.mkdir()
        self.drives = {str(self.first): {'id': 'volume-one', 'label': 'First'}}
        for target, value in [(app, 'CONFIG')]:
            patcher = patch.object(target, value, root / 'settings.json')
            patcher.start()
            self.addCleanup(patcher.stop)
        for patcher in [patch.object(app.App, 'init_tray', lambda _: None),
                        patch.object(app, 'volumes', lambda: dict(self.drives)),
                        patch.object(app, 'volume_id', lambda path: self.drives.get(str(path), {}).get('id'))]:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.window = app.App()
        self.window.parent.set(str(self.parent))
        self.window.refresh()
        self.window.update()
        self.addCleanup(self.destroy_window)

    def destroy_window(self):
        for worker in [getattr(self.window, 'worker_thread', None), getattr(self.window, 'overview_thread', None)]:
            if worker is not None:
                worker.join(timeout=3)
        for token in self.window.tk.call('after', 'info'):
            self.window.after_cancel(token)
        self.window.destroy()
        for handler in self.window.log.handlers[:]:
            handler.close()
            self.window.log.removeHandler(handler)
        sys.excepthook = self.previous_exception_hook
        threading.excepthook = self.previous_thread_hook
        self.window = None
        gc.collect()

    def wait_for_copy(self):
        deadline = time.monotonic() + 3
        while self.window.busy and time.monotonic() < deadline:
            self.window.update()
            time.sleep(0.01)
        self.assertFalse(self.window.busy)

    def test_manual_source_and_immediate_copy(self):
        self.assertEqual(self.window.source.get(), '')
        self.window.tick()
        self.assertFalse((self.first / 'Event').exists())
        self.window.choose_latest()
        self.assertEqual(self.window.source.get(), str(self.source))
        self.window.running = False
        self.window.copy()
        self.wait_for_copy()
        self.assertEqual((self.first / 'Event/Originals/photo.jpg').read_bytes(), b'photo')
        self.assertIn('1 neue Dateien', self.window.status.get())

    def test_full_error_keeps_hidden_and_second_stick_continues(self):
        self.window.choose_latest()
        self.window.withdraw()
        self.window.messages.put(('full', 'USB-Stick voll'))
        self.window.poll()
        self.assertEqual(self.window.state(), 'withdrawn')
        self.assertTrue(self.window.storage_wait)
        self.window.copy()
        self.assertFalse(self.window.busy)
        self.drives.clear()
        self.drives[str(self.second)] = {'id': 'volume-two', 'label': 'Second'}
        self.window.scan_usb()
        self.window.resume_storage()
        self.wait_for_copy()
        self.assertEqual(self.window.state(), 'withdrawn')
        self.assertEqual((self.second / 'Event/Originals/photo.jpg').read_bytes(), b'photo')
        self.window.messages.put(('error', 'USB entfernt'))
        self.window.poll()
        self.assertEqual(self.window.state(), 'withdrawn')

    def test_unhandled_error_does_not_open_window(self):
        self.window.withdraw()
        try:
            raise RuntimeError('simulated callback error')
        except RuntimeError as error:
            self.window.report_callback_exception(type(error), error, error.__traceback__)
        self.window.poll()
        self.assertEqual(self.window.state(), 'withdrawn')
        self.assertIn('Details im Protokoll', self.window.status.get())
        self.assertIn('simulated callback error', (app.CONFIG.parent / 'transfer.log').read_text())

    def test_volume_follows_letter_but_not_replacement(self):
        self.assertEqual(self.window.selected_volume, 'volume-one')
        self.drives.clear()
        self.drives[str(self.second)] = {'id': 'volume-one', 'label': 'First'}
        self.window.scan_usb()
        self.assertEqual(self.window.drive_choices[self.window.target.get()][0], str(self.second))
        self.drives[str(self.second)]['id'] = 'other-volume'
        self.window.scan_usb()
        self.assertEqual(self.window.target.get(), '')

    def test_countdown_and_pause(self):
        self.window.choose_latest()
        with patch('app.time.monotonic', return_value=100):
            self.window.next_check = 342
            self.window.update_countdown()
        self.assertEqual(self.window.countdown.get(), 'Nächste Prüfung in 04:02')
        self.window.toggle()
        self.window.update_countdown()
        self.assertEqual(self.window.countdown.get(), 'Automatik pausiert')

    def test_eject_waits_for_copy_shutdown_and_stays_hidden(self):
        self.window.choose_latest()
        self.window.withdraw()
        self.window.busy = True
        calls = []
        with patch('app.eject', side_effect=lambda root, identity: calls.append((root, identity))):
            self.window.request_eject()
            self.assertTrue(self.window.stop_worker.is_set())
            self.assertEqual(calls, [])
            self.window.messages.put(('done', 'Kopiervorgang beendet.'))
            self.window.poll()
            self.wait_for_copy()
        self.assertEqual(calls, [(str(self.first), 'volume-one')])
        self.assertIsNone(self.window.pending_eject)
        self.assertFalse(self.window.running)
        self.assertEqual(self.window.state(), 'withdrawn')
        self.assertIn('ausgeworfen', self.window.status.get())

    def test_eject_failure_no_popup_or_focus(self):
        self.window.withdraw()
        with patch('app.eject', side_effect=OSError('drive in use')):
            self.window.request_eject()
            self.wait_for_copy()
        self.assertFalse(self.window.running)
        self.assertEqual(self.window.state(), 'withdrawn')
        self.assertIn('nicht auswerfen', self.window.status.get())

    def test_finished_overview_does_not_open_hidden_window(self):
        self.window.withdraw()
        before = len(self.window.winfo_children())
        self.window.messages.put(('overview', {'source': str(self.source)}))
        self.window.poll()
        self.assertEqual(len(self.window.winfo_children()), before)
        self.assertIsNone(self.window.overview_window)
        self.assertEqual(self.window.state(), 'withdrawn')

    def test_five_errors_require_different_stick_and_recopy_complete_event(self):
        import errno
        import json
        from recovery import retry_copy as real_retry
        self.window.choose_latest()
        self.window.copy()
        self.wait_for_copy()
        other = self.file.with_name('second.jpg')
        other.write_bytes(b'second')
        os.utime(other, (0, 0))
        self.window.withdraw()
        fast_retry = lambda operation, stop, notify: real_retry(operation, stop, notify, delay=0)
        with patch('app.copy_new', side_effect=OSError(errno.EIO, 'USB error')) as copying, patch('app.retry_copy', side_effect=fast_retry):
            self.window.copy()
            self.wait_for_copy()
        self.assertEqual(copying.call_count, 5)
        self.assertTrue(self.window.storage_wait)
        self.assertIsNotNone(self.window.recovery_spec)
        self.assertEqual(self.window.state(), 'withdrawn')
        saved = json.loads(app.CONFIG.read_text())
        self.assertEqual(saved['recovery']['volume'], 'volume-one')
        self.window.resume_storage()
        self.assertFalse(self.window.busy)
        self.assertIn('anderen Stick', self.window.status.get())
        self.drives.clear()
        self.drives[str(self.second)] = {'id': 'volume-two', 'label': 'Second'}
        self.window.scan_usb()
        self.window.resume_storage()
        self.wait_for_copy()
        self.assertEqual((self.second / 'Event/Originals/photo.jpg').read_bytes(), b'photo')
        self.assertEqual((self.second / 'Event/Originals/second.jpg').read_bytes(), b'second')
        self.assertIsNone(self.window.recovery_spec)
        self.assertIsNone(json.loads(app.CONFIG.read_text())['recovery'])
        self.assertEqual(self.window.state(), 'withdrawn')

    def test_full_speed_is_explicit_and_skips_rate_field(self):
        self.assertFalse(self.window.full_speed.get())
        self.window.choose_latest()
        self.window.full_speed.set(True)
        self.window.performance_changed()
        self.window.rate.set('invalid but ignored in full speed mode')
        self.window.copy()
        self.wait_for_copy()
        self.assertEqual((self.first / 'Event/Originals/photo.jpg').read_bytes(), b'photo')
        self.assertIn('beeinträchtigen', self.window.performance_hint.get())
