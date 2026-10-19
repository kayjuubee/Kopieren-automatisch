from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import devices


class EjectTests(unittest.TestCase):
    def test_locks_flushes_dismounts_then_ejects_and_closes(self):
        operations = []
        kernel = SimpleNamespace(
            CreateFileW=Mock(return_value=42),
            DeviceIoControl=Mock(side_effect=lambda handle, code, *_: operations.append(code) or 1),
            FlushFileBuffers=Mock(side_effect=lambda _: operations.append('flush') or 1),
            CloseHandle=Mock())
        with patch.object(devices, 'os', SimpleNamespace(name='nt')), patch.object(devices, 'volume_id', return_value='stick'), patch.object(devices.ctypes, 'WinDLL', return_value=kernel, create=True):
            devices.eject('E:\\', 'stick')
        self.assertEqual(operations, [0x90018, 'flush', 0x90020, 0x2D4808, 0x9001C])
        kernel.CloseHandle.assert_called_once_with(42)

    def test_busy_volume_is_never_dismounted_or_forced(self):
        kernel = SimpleNamespace(CreateFileW=Mock(return_value=42), DeviceIoControl=Mock(return_value=0), FlushFileBuffers=Mock(), CloseHandle=Mock())
        with patch.object(devices, 'os', SimpleNamespace(name='nt')), patch.object(devices, 'volume_id', return_value='stick'), patch.object(devices.ctypes, 'WinDLL', return_value=kernel, create=True), patch.object(devices.ctypes, 'get_last_error', return_value=5, create=True), patch.object(devices.ctypes, 'WinError', side_effect=lambda _: OSError('busy'), create=True):
            with self.assertRaises(OSError):
                devices.eject('E:\\', 'stick')
        self.assertEqual(kernel.DeviceIoControl.call_count, 1)
        self.assertEqual(kernel.DeviceIoControl.call_args.args[1], 0x90018)
        kernel.FlushFileBuffers.assert_not_called()
        kernel.CloseHandle.assert_called_once_with(42)

    def test_wrong_device_is_rejected_before_opening(self):
        with patch.object(devices, 'os', SimpleNamespace(name='nt')), patch.object(devices, 'volume_id', return_value='replacement'), patch.object(devices.ctypes, 'WinDLL', create=True) as dll:
            with self.assertRaises(OSError):
                devices.eject('E:\\', 'original')
            dll.assert_not_called()
