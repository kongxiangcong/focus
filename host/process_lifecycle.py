"""Supervise child interpreters and tool processes owned by a runtime."""
import ctypes
import os
import signal
import subprocess


class WindowsJob:
    def __init__(self, process):
        from ctypes import wintypes

        kernel = self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
        kernel.TerminateJobObject.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        self.handle = kernel.CreateJobObjectW(None, None)
        if self.handle and not kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            kernel.CloseHandle(self.handle)
            self.handle = None

    def terminate(self):
        try:
            return bool(self.kernel.TerminateJobObject(self.handle, 1))
        finally:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def stop_process(process, *, isolated=False, job=None):
    if job and job.handle and job.terminate():
        process.wait(timeout=5)
        return
    if isolated and os.name != 'nt':
        _signal_group(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        # The parent may have exited while its MCP child still holds the pipes.
        _signal_group(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
        return
    if process.poll() is not None:
        return
    if os.name == 'nt':
        try:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           capture_output=True, timeout=5, check=False)
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _signal_group(pid, value):
    try:
        os.killpg(pid, value)
    except ProcessLookupError:
        pass
