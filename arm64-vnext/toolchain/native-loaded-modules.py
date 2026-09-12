"""Inspect already-running owned native processes without a debugger."""
import ctypes as C
from ctypes import wintypes as W
import hashlib
from pathlib import Path


def modules(pid):
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel.OpenProcess.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.CloseHandle.restype = W.BOOL
    kernel.K32EnumProcessModulesEx.argtypes = [W.HANDLE, C.POINTER(W.HMODULE), W.DWORD,
                                              C.POINTER(W.DWORD), W.DWORD]
    kernel.K32EnumProcessModulesEx.restype = W.BOOL
    kernel.K32GetModuleFileNameExW.argtypes = [W.HANDLE, W.HMODULE, W.LPWSTR, W.DWORD]
    kernel.K32GetModuleFileNameExW.restype = W.DWORD
    handle = kernel.OpenProcess(0x410, False, pid)
    if not handle:
        raise C.WinError(C.get_last_error())
    try:
        array = (W.HMODULE * 2048)()
        needed = W.DWORD()
        if not kernel.K32EnumProcessModulesEx(handle, array, C.sizeof(array), C.byref(needed), 3):
            raise C.WinError(C.get_last_error())
        if needed.value > C.sizeof(array):
            raise ValueError("Owned process module inventory exceeds the explicit bound")
        result = []
        for module in array[:needed.value // C.sizeof(W.HMODULE)]:
            text = C.create_unicode_buffer(32768)
            length = kernel.K32GetModuleFileNameExW(handle, module, text, len(text))
            if not length or length == len(text):
                raise C.WinError(C.get_last_error())
            path = Path(text.value).resolve(strict=True)
            result.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                           "base": module})
        return result
    finally:
        if not kernel.CloseHandle(handle):
            raise C.WinError(C.get_last_error())
