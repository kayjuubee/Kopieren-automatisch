"""Identify Windows volumes independently of their drive letter."""
import ctypes
import os


def volumes():
    if os.name != 'nt':
        return {}
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    result = {}
    for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        root = f'{letter}:\\'
        if kernel.GetDriveTypeW(root) != 2:
            continue
        label = ctypes.create_unicode_buffer(261)
        serial = ctypes.c_ulong()
        if not kernel.GetVolumeInformationW(root, label, len(label), ctypes.byref(serial), None, None, None, 0):
            continue
        guid = ctypes.create_unicode_buffer(261)
        if not kernel.GetVolumeNameForVolumeMountPointW(root, guid, len(guid)):
            continue
        result[root] = {'id': guid.value, 'label': label.value or 'USB-Stick'}
    return result


def volume_id(root):
    if os.name != 'nt':
        return None
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    guid = ctypes.create_unicode_buffer(261)
    return guid.value if kernel.GetVolumeNameForVolumeMountPointW(str(root), guid, len(guid)) else None


def eject(root, expected_volume):
    """Lock, flush and eject only the selected volume. Never force a busy drive."""
    if os.name != 'nt':
        raise OSError('Sicheres Entfernen ist nur unter Windows verfügbar')
    from ctypes import wintypes
    root = str(root)
    if len(root) != 3 or root[1:] != ':\\' or not root[0].isalpha():
        raise ValueError('Ungültiger Laufwerksbuchstabe')
    if volume_id(root) != expected_volume:
        raise OSError('Der ausgewählte USB-Stick ist nicht mehr angeschlossen')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    kernel.FlushFileBuffers.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW('\\\\.\\' + root[:2], 0xC0000000, 3, None, 3, 0, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    returned = wintypes.DWORD()
    locked = False
    def control(code):
        if not kernel.DeviceIoControl(handle, code, None, 0, None, 0, ctypes.byref(returned), None):
            raise ctypes.WinError(ctypes.get_last_error())
    try:
        control(0x90018)  # FSCTL_LOCK_VOLUME; fails if any other process uses it
        locked = True
        if volume_id(root) != expected_volume:
            raise OSError('Der USB-Stick wurde gewechselt')
        if not kernel.FlushFileBuffers(handle):
            raise ctypes.WinError(ctypes.get_last_error())
        control(0x90020)  # FSCTL_DISMOUNT_VOLUME
        control(0x2D4808)  # IOCTL_STORAGE_EJECT_MEDIA
    finally:
        if locked:
            kernel.DeviceIoControl(handle, 0x9001C, None, 0, None, 0, ctypes.byref(returned), None)  # unlock
        kernel.CloseHandle(handle)
