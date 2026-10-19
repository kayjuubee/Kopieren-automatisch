"""Per-user Windows startup and lightweight booth process watcher."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys
import time

APP_MUTEX = 'Local\\kayjuubeeHotfolderUSB'
WATCH_MUTEX = APP_MUTEX + '-Watcher'
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
RUN_NAME = 'kayjuubeeUSBBoothWatcher'
BOOTH_NAMES = {'dslrbooth.exe', 'lumabooth.exe', 'luma booth.exe'}
# Handles must remain open for the lifetime of the process.
_mutex_handles = []


def kernel32():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.OpenMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    return kernel


def acquire_instance(name=APP_MUTEX):
    if os.name != 'nt':
        return True
    kernel = kernel32()
    handle = kernel.CreateMutexW(None, False, name)
    error = ctypes.get_last_error()
    if not handle:
        raise ctypes.WinError(error)
    if error == 183:  # ERROR_ALREADY_EXISTS
        kernel.CloseHandle(handle)
        return False
    _mutex_handles.append(handle)
    return True


def app_running():
    kernel = kernel32()
    handle = kernel.OpenMutexW(0x100000, False, APP_MUTEX)
    if handle:
        kernel.CloseHandle(handle)
        return True
    return False


def command(*arguments):
    executable = Path(sys.executable)
    if getattr(sys, 'frozen', False):
        return [str(executable), *arguments]
    windowed = executable.with_name('pythonw.exe')
    return [str(windowed if windowed.exists() else executable), str(Path(__file__).parent / 'app.py'), *arguments]


def set_autostart(enabled):
    if os.name != 'nt':
        raise OSError('Autostart ist nur unter Windows verfügbar')
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(command('--watch')))
        else:
            try:
                winreg.DeleteValue(key, RUN_NAME)
            except FileNotFoundError:
                pass


def autostart_enabled():
    if os.name != 'nt':
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            saved, _ = winreg.QueryValueEx(key, RUN_NAME)
            return saved == subprocess.list2cmdline(command('--watch'))
    except FileNotFoundError:
        return False


def process_names():
    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                    ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
                    ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                    ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG),
                    ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260)]
    kernel = kernel32()
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        names = set()
        found = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while found:
            names.add(entry.szExeFile.casefold())
            found = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        error = ctypes.get_last_error()
        if error != 18:  # ERROR_NO_MORE_FILES
            raise ctypes.WinError(error)
        return names
    finally:
        kernel.CloseHandle(snapshot)


class BoothSession:
    def __init__(self):
        self.active = False

    def should_launch(self, names, copier_running):
        active = bool(BOOTH_NAMES.intersection(name.casefold() for name in names))
        launch = active and not self.active and not copier_running
        self.active = active
        return launch


def watch():
    if os.name != 'nt' or not acquire_instance(WATCH_MUTEX):
        return
    session = BoothSession()
    while autostart_enabled():
        try:
            if session.should_launch(process_names(), app_running()):
                subprocess.Popen(command('--background'), creationflags=0x08000000)
        except OSError:
            # Keep the watcher silent, retry after a transient enumeration error.
            session.active = False
        time.sleep(3)


def start_watcher():
    if os.name == 'nt':
        subprocess.Popen(command('--watch'), creationflags=0x08000000)
