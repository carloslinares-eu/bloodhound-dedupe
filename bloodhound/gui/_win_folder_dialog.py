"""The native Windows folder picker, with several folders selectable at once.

Tk's ``askdirectory`` can only return one folder, so on Windows we drive the
system ``IFileOpenDialog`` directly through ctypes (no pywin32 needed) with the
``FOS_PICKFOLDERS | FOS_ALLOWMULTISELECT`` options. Only import this on Windows.
"""

from __future__ import annotations

import ctypes
import os
import uuid
from ctypes import POINTER, byref, c_void_p, c_wchar_p
from ctypes import wintypes


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def parse(cls, text: str) -> _GUID:
        return cls.from_buffer_copy(uuid.UUID(text).bytes_le)


_HRESULT = ctypes.c_long

_ole32 = ctypes.WinDLL("ole32")  # private handles so our argtypes don't affect other code
_shell32 = ctypes.WinDLL("shell32")

_ole32.CoInitializeEx.argtypes = [c_void_p, wintypes.DWORD]
_ole32.CoInitializeEx.restype = _HRESULT
_ole32.CoUninitialize.argtypes = []
_ole32.CoUninitialize.restype = None
_ole32.CoCreateInstance.argtypes = [POINTER(_GUID), c_void_p, wintypes.DWORD, POINTER(_GUID), POINTER(c_void_p)]
_ole32.CoCreateInstance.restype = _HRESULT
_ole32.CoTaskMemFree.argtypes = [c_void_p]
_ole32.CoTaskMemFree.restype = None
_shell32.SHCreateItemFromParsingName.argtypes = [c_wchar_p, c_void_p, POINTER(_GUID), POINTER(c_void_p)]
_shell32.SHCreateItemFromParsingName.restype = _HRESULT

_CLSID_FILE_OPEN_DIALOG = _GUID.parse("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")
_IID_IFILE_OPEN_DIALOG = _GUID.parse("D57C7288-D4AD-4768-BE02-9D969532D960")
_IID_ISHELL_ITEM = _GUID.parse("43826D1E-E718-42EE-BC55-A1E261C37BFE")

_COINIT_APARTMENTTHREADED = 0x2
_CLSCTX_INPROC_SERVER = 0x1
_FOS_NOCHANGEDIR = 0x8
_FOS_PICKFOLDERS = 0x20
_FOS_FORCEFILESYSTEM = 0x40
_FOS_ALLOWMULTISELECT = 0x200
_FOS_PATHMUSTEXIST = 0x800
_SIGDN_FILESYSPATH = 0x80058000
_HRESULT_CANCELLED = ctypes.c_long(0x800704C7).value  # HRESULT_FROM_WIN32(ERROR_CANCELLED)

# Positions of the methods we use in each interface's vtable.
_RELEASE = 2  # IUnknown
_SHOW = 3  # IModalWindow
_SET_OPTIONS, _GET_OPTIONS, _SET_FOLDER, _SET_TITLE = 9, 10, 12, 17  # IFileDialog
_GET_RESULTS = 27  # IFileOpenDialog
_ARRAY_GET_COUNT, _ARRAY_GET_ITEM_AT = 7, 8  # IShellItemArray
_ITEM_GET_DISPLAY_NAME = 5  # IShellItem


def _call(interface: c_void_p, index: int, *args, argtypes: tuple = ()) -> int:
    """Call the method at ``index`` in the vtable of a COM ``interface`` pointer."""
    vtable = ctypes.cast(interface, POINTER(POINTER(c_void_p))).contents
    method = ctypes.cast(vtable[index], ctypes.WINFUNCTYPE(_HRESULT, c_void_p, *argtypes))
    return method(interface, *args)


def _check(hresult: int, what: str) -> None:
    if hresult < 0:
        raise OSError(f"{what} failed (HRESULT 0x{hresult & 0xFFFFFFFF:08X})")


def _release(interface: c_void_p) -> None:
    if interface:
        _call(interface, _RELEASE)


def ask_directories(title: str, initialdir: str | None = None, owner: int | None = None) -> list[str]:
    """Show the dialog and return the chosen folders, or an empty list if the user closes it.

    Raises :class:`OSError` if the dialog can't be created, so callers can fall
    back to another picker.
    """
    init = _ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
    dialog = c_void_p()
    try:
        _check(
            _ole32.CoCreateInstance(
                byref(_CLSID_FILE_OPEN_DIALOG), None, _CLSCTX_INPROC_SERVER, byref(_IID_IFILE_OPEN_DIALOG),
                byref(dialog),
            ),
            "CoCreateInstance",
        )
        options = wintypes.DWORD()
        _check(_call(dialog, _GET_OPTIONS, byref(options), argtypes=(POINTER(wintypes.DWORD),)), "GetOptions")
        options.value |= (
            _FOS_PICKFOLDERS | _FOS_ALLOWMULTISELECT | _FOS_FORCEFILESYSTEM | _FOS_PATHMUSTEXIST | _FOS_NOCHANGEDIR
        )
        _check(_call(dialog, _SET_OPTIONS, options, argtypes=(wintypes.DWORD,)), "SetOptions")
        _check(_call(dialog, _SET_TITLE, title, argtypes=(c_wchar_p,)), "SetTitle")
        if initialdir and os.path.isdir(initialdir):
            _set_folder(dialog, initialdir)

        hresult = _call(dialog, _SHOW, owner, argtypes=(wintypes.HWND,))
        if hresult == _HRESULT_CANCELLED:
            return []
        _check(hresult, "Show")
        return _get_results(dialog)
    finally:
        _release(dialog)
        if init >= 0:  # S_OK or S_FALSE must be balanced; RPC_E_CHANGED_MODE must not
            _ole32.CoUninitialize()


def _set_folder(dialog: c_void_p, path: str) -> None:
    item = c_void_p()
    if _shell32.SHCreateItemFromParsingName(os.path.abspath(path), None, byref(_IID_ISHELL_ITEM), byref(item)) < 0:
        return  # not fatal: the dialog just opens in its default location
    try:
        _call(dialog, _SET_FOLDER, item, argtypes=(c_void_p,))
    finally:
        _release(item)


def _get_results(dialog: c_void_p) -> list[str]:
    results = c_void_p()
    _check(_call(dialog, _GET_RESULTS, byref(results), argtypes=(POINTER(c_void_p),)), "GetResults")
    try:
        count = wintypes.DWORD()
        _check(_call(results, _ARRAY_GET_COUNT, byref(count), argtypes=(POINTER(wintypes.DWORD),)), "GetCount")
        paths = []
        for index in range(count.value):
            item = c_void_p()
            _check(
                _call(results, _ARRAY_GET_ITEM_AT, index, byref(item), argtypes=(wintypes.DWORD, POINTER(c_void_p))),
                "GetItemAt",
            )
            try:
                name = c_void_p()
                _check(
                    _call(
                        item, _ITEM_GET_DISPLAY_NAME, _SIGDN_FILESYSPATH, byref(name),
                        argtypes=(wintypes.DWORD, POINTER(c_void_p)),
                    ),
                    "GetDisplayName",
                )
                try:
                    paths.append(ctypes.wstring_at(name))
                finally:
                    _ole32.CoTaskMemFree(name)
            finally:
                _release(item)
        return paths
    finally:
        _release(results)
