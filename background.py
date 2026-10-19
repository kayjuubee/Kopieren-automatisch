"""Windows scheduling: foreground booth work takes priority over copying."""
from contextlib import contextmanager
import ctypes
import os


def lower_process_priority():
    if os.name != 'nt':
        return
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    # BELOW_NORMAL_PRIORITY_CLASS keeps the UI responsive without competing
    # with a foreground application running at normal priority.
    if not kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x4000):
        raise ctypes.WinError(ctypes.get_last_error())


def background_copy_thread():
    if os.name != 'nt':
        return
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentThread.restype = ctypes.c_void_p
    kernel.SetThreadPriority.argtypes = [ctypes.c_void_p, ctypes.c_int]
    # THREAD_MODE_BACKGROUND_BEGIN lowers CPU, I/O and memory scheduling
    # priorities for this worker only. The mode ends when the thread exits.
    if not kernel.SetThreadPriority(kernel.GetCurrentThread(), 0x10000):
        raise ctypes.WinError(ctypes.get_last_error())


def suppress_system_error_dialogs():
    """Never let removable-media or process error dialogs interrupt the booth."""
    if os.name == 'nt':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        # SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX
        previous = kernel.SetErrorMode(0x8003)
        kernel.SetErrorMode(previous | 0x8003)


def normal_process_priority():
    """Normal scheduling only; never request high or realtime priority."""
    if os.name == 'nt':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        if not kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x20):
            raise ctypes.WinError(ctypes.get_last_error())


@contextmanager
def copy_priority(full_speed=False):
    if full_speed:
        normal_process_priority()
    else:
        background_copy_thread()
    try:
        yield
    finally:
        if full_speed:
            lower_process_priority()
