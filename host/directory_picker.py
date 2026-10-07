"""Choose a directory on the Host machine without binding a workspace."""
import base64
import json
import os
from pathlib import Path
import subprocess
import threading

_picker_lock = threading.Lock()
_WINDOWS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class FocusFolderPicker {
    [ComImport, Guid("D57C7288-D4AD-4768-BE02-9D969532D960"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IFileOpenDialog {
        [PreserveSig] int Show(IntPtr owner);
        void SetFileTypes(uint count, IntPtr types);
        void SetFileTypeIndex(uint index);
        void GetFileTypeIndex(out uint index);
        void Advise(IntPtr events, out uint cookie);
        void Unadvise(uint cookie);
        void SetOptions(uint options);
        void GetOptions(out uint options);
        void SetDefaultFolder(IntPtr folder);
        void SetFolder(IntPtr folder);
        void GetFolder(out IntPtr folder);
        void GetCurrentSelection(out IntPtr item);
        void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string name);
        void GetFileName(out IntPtr name);
        void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string title);
        void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string text);
        void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string text);
        void GetResult(out IShellItem item);
    }
    [ComImport, Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IShellItem {
        void BindToHandler(IntPtr context, ref Guid handler, ref Guid iid, out IntPtr result);
        void GetParent(out IShellItem parent);
        void GetDisplayName(uint kind, out IntPtr name);
        void GetAttributes(uint mask, out uint attributes);
        void Compare(IShellItem other, uint hint, out int order);
    }
    public static string Select(IntPtr owner) {
        var dialog = (IFileOpenDialog)Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")));
        IShellItem item = null;
        try {
            uint options;
            dialog.GetOptions(out options);
            dialog.SetOptions(options | 0x20u | 0x40u | 0x800u | 0x2000000u);
            dialog.SetTitle("选择 FOCUS 工作区目录");
            dialog.SetOkButtonLabel("选择目录");
            int result = dialog.Show(owner);
            if (result == unchecked((int)0x800704C7)) return null;
            Marshal.ThrowExceptionForHR(result);
            dialog.GetResult(out item);
            IntPtr path;
            item.GetDisplayName(0x80058000u, out path);
            try { return Marshal.PtrToStringUni(path); }
            finally { Marshal.FreeCoTaskMem(path); }
        } finally {
            if (item != null) Marshal.FinalReleaseComObject(item);
            Marshal.FinalReleaseComObject(dialog);
        }
    }
}
'@
$owner = New-Object System.Windows.Forms.Form
$owner.Text = 'FOCUS 工作区目录'
$owner.ShowInTaskbar = $false
$owner.Opacity = 0
$owner.TopMost = $true
try {
    $owner.Show()
    $owner.Activate()
    $selected = [FocusFolderPicker]::Select($owner.Handle)
    @{path = $selected} | ConvertTo-Json -Compress
} finally {
    $owner.Close()
    $owner.Dispose()
}
"""


def choose_directory():
    if not _picker_lock.acquire(blocking=False):
        return {'path': None, 'error': '目录选择窗口已打开，请完成选择或取消。'}
    try:
        if os.name == 'nt':
            executable = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
            command = base64.b64encode(_WINDOWS_SCRIPT.encode('utf-16-le')).decode('ascii')
            result = subprocess.run(
                [str(executable), '-NoProfile', '-NonInteractive', '-STA', '-WindowStyle', 'Hidden', '-EncodedCommand', command],
                capture_output=True, text=True, encoding='utf-8', check=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            value = json.loads(result.stdout)
            path = value['path']
            if path is not None and not isinstance(path, str):
                raise ValueError('Invalid directory selection')
            return {'path': path or None}
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        try:
            return {'path': filedialog.askdirectory(parent=root, title='选择 FOCUS 工作区目录') or None}
        finally:
            root.destroy()
    except Exception:
        return {'path': None, 'error': '目录选择器不可用，请手动输入本机目录。'}
    finally:
        _picker_lock.release()
