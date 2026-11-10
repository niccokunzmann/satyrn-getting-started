"""What this computer offers a model: memory, free disk, CPU cores and a usable GPU."""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .layout import IS_WINDOWS

GB = 1e9


@dataclass(frozen=True)
class Machine:
    memory_gb: float  # total RAM
    free_disk_gb: float  # where .runtime/ lives
    cpu_cores: int
    gpu: str | None  # description, or None when the model will run on the CPU
    gpu_memory_gb: float  # memory a model can use on that GPU (0 without one)

    def describe(self) -> str:
        gpu = self.gpu or "no GPU"
        return (
            f"{self.memory_gb:.0f} GB memory, {self.free_disk_gb:.0f} GB free disk, {self.cpu_cores} CPU cores, {gpu}"
        )


def _memory_bytes() -> int:
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():  # Linux
        for line in meminfo.read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    if IS_WINDOWS:

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))  # type: ignore[attr-defined]
        return int(status.ullTotalPhys)
    out = subprocess.run(["/usr/sbin/sysctl", "-n", "hw.memsize"], capture_output=True, text=True, check=False)
    return int(out.stdout.strip() or 0)  # macOS


def _nvidia() -> tuple[str, float] | None:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return None
    out = subprocess.run(
        [smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    gpus = [line.rsplit(",", 1) for line in out.stdout.strip().splitlines() if "," in line]
    if out.returncode != 0 or not gpus:
        return None
    name, memory_mib = max(gpus, key=lambda gpu: float(gpu[1]))
    return name.strip(), float(memory_mib) * 1024 * 1024 / GB


def detect(disk_path: Path) -> Machine:
    memory = _memory_bytes() / GB
    disk_path = next((p for p in (disk_path, *disk_path.parents) if p.exists()), Path.cwd())
    free_disk = shutil.disk_usage(disk_path).free / GB
    gpu, gpu_memory = None, 0.0
    if nvidia := _nvidia():
        gpu, gpu_memory = f"NVIDIA {nvidia[0]} ({nvidia[1]:.0f} GB)", nvidia[1]
    elif platform.system() == "Darwin" and platform.machine() == "arm64":
        # Apple Silicon: the GPU shares the main memory; macOS lets it use about three quarters.
        gpu, gpu_memory = "Apple GPU (shared memory)", memory * 0.75
    return Machine(memory, free_disk, os.cpu_count() or 1, gpu, gpu_memory)
