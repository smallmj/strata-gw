"""winjob.py - Windows Job Object glue for spawned backend children.

The gateway spawns one backend process per model; each backend in turn starts
an engine, a vision encoder and whatever else it likes. When the router dies -
Ctrl+C, the console window's X, taskkill, a crash - everything under it must
die too, or orphaned engines keep holding the GPU forever.

Windows solves this natively: attach the child to a Job Object flagged
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, and the kernel tears the whole tree down
when this process' handle to the job closes (which the OS does for us at exit,
no matter how we exit). ctypes only, no dependency on the engine's own
serve/winjob.py: a standalone checkout gets identical lifetime semantics.

On non-Windows platforms contain() is a no-op; there the SIGTERM/SIGBREAK
handlers in main.py are the guarantee.
"""
from __future__ import annotations

import ctypes
import subprocess

_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


_JOB = None
_TRIED = False


def _shared_job():
    """One kill-on-close job per router process, created lazily."""
    global _JOB, _TRIED
    if _TRIED:
        return _JOB
    _TRIED = True
    windll = getattr(ctypes, "windll", None)   # absent on POSIX
    if windll is None:
        return None
    kernel32 = windll.kernel32
    handle = kernel32.CreateJobObjectW(None, None)
    if not handle:
        return None
    info = _ExtendedLimitInformation()
    info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    ok = kernel32.SetInformationJobObject(
        handle, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(info), ctypes.sizeof(info))
    if not ok:
        kernel32.CloseHandle(handle)
        return None
    _JOB = handle
    return _JOB


def contain(proc: subprocess.Popen) -> bool:
    """Tie a freshly spawned child - and its whole descendant tree - to this
    process's lifetime. Returns True when the guarantee is active."""
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return False                       # non-Windows: no-op
    try:
        job = _shared_job()
        if not job:
            return False
        child = getattr(proc, "_handle", None)   # noqa: SLF001 - Popen's OS handle
        if child is None:
            return False
        return bool(windll.kernel32.AssignProcessToJobObject(job, int(child)))
    except (AttributeError, OSError, ValueError):
        return False
