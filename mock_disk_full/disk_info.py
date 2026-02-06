# -*- coding: utf-8 -*-
"""
跨平台磁盘信息获取模块。
列举各分区/盘符的总空间与剩余空间，供用户选择。
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Optional


def _get_mount_point_darwin(path: str) -> Optional[str]:
    """Mac 上用 df 获取路径所在挂载点（与 df $HOME 一致，避免 st_dev 多卷相同）。"""
    path = os.path.abspath(path)
    try:
        out = subprocess.run(
            ["df", "-P", path],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode != 0 or not out.stdout:
            return None
        lines = out.stdout.strip().splitlines()
        if len(lines) < 2:
            return None
        # 最后一行最后一列为挂载点
        return lines[-1].split()[-1]
    except (OSError, IndexError, subprocess.TimeoutExpired):
        return None


@dataclass
class DiskPartition:
    """单个分区/盘符信息"""

    mount_point: str  # 挂载点，如 "C:" 或 "/" 或 "/Users/xxx"
    total_bytes: int
    free_bytes: int
    used_bytes: int
    label: str = ""  # 可选标签，如 "本地磁盘"

    @property
    def total_gb(self) -> float:
        return self.total_bytes / (1024**3)

    @property
    def free_gb(self) -> float:
        return self.free_bytes / (1024**3)

    @property
    def used_gb(self) -> float:
        return self.used_bytes / (1024**3)

    def __str__(self, suffix: str = "") -> str:
        line = (
            f"{self.mount_point}  | "
            f"总空间: {self.total_gb:.2f} GB | "
            f"已用: {self.used_gb:.2f} GB | "
            f"剩余: {self.free_gb:.2f} GB"
        )
        if suffix:
            line += f"  {suffix}"
        return line


def _get_partitions_psutil() -> List[DiskPartition]:
    """使用 psutil 获取所有分区（跨平台）。"""
    import psutil

    result: List[DiskPartition] = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            result.append(
                DiskPartition(
                    mount_point=part.mountpoint,
                    total_bytes=usage.total,
                    free_bytes=usage.free,
                    used_bytes=usage.used,
                    label=getattr(part, "label", "") or "",
                )
            )
        except (PermissionError, OSError):
            continue
    return result


def _get_partitions_stdlib() -> List[DiskPartition]:
    """仅用标准库获取分区（无 psutil 时回退）。"""
    result: List[DiskPartition] = []

    if sys.platform == "win32":
        import string

        for letter in string.ascii_uppercase:
            path = f"{letter}:\\"
            if os.path.exists(path):
                try:
                    if sys.platform != "win32" and hasattr(os, "statvfs"):
                        stat = os.statvfs(path)
                        total = stat.f_frsize * stat.f_blocks
                        free = stat.f_bavail * stat.f_frsize
                        used = total - free
                    else:
                        # Windows：使用 ctypes 调用 GetDiskFreeSpaceExW
                        import ctypes

                        free_bytes = ctypes.c_ulonglong(0)
                        total_bytes = ctypes.c_ulonglong(0)
                        ctypes.windll.kernel32.GetDiskFreeSpaceExW(  # type: ignore[attr-defined]
                            ctypes.c_wchar_p(path),
                            None,
                            ctypes.byref(total_bytes),
                            ctypes.byref(free_bytes),
                        )
                        total = total_bytes.value
                        free = free_bytes.value
                        used = total - free
                    result.append(
                        DiskPartition(
                            mount_point=path.rstrip("\\"),
                            total_bytes=total,
                            free_bytes=free,
                            used_bytes=used,
                        )
                    )
                except (OSError, AttributeError):
                    continue
    else:
        # Unix / macOS：常见挂载点
        for path in ["/", os.path.expanduser("~")]:
            path = os.path.realpath(path)
            if not os.path.isdir(path):
                continue
            try:
                stat = os.statvfs(path)
                total = stat.f_frsize * stat.f_blocks
                free = stat.f_bavail * stat.f_frsize
                used = total - free
                result.append(
                    DiskPartition(
                        mount_point=path,
                        total_bytes=total,
                        free_bytes=free,
                        used_bytes=used,
                    )
                )
            except OSError:
                continue
        # 去重（根与 HOME 可能同一分区）
        seen = set()
        unique = []
        for p in result:
            key = (p.total_bytes, p.free_bytes)
            if key not in seen:
                seen.add(key)
                unique.append(p)
        result = unique

    return result


def get_disk_partitions() -> List[DiskPartition]:
    """获取当前机器上可用的磁盘分区列表（总空间、剩余空间）。"""
    try:
        return _get_partitions_psutil()
    except ImportError:
        return _get_partitions_stdlib()


def get_partition_by_path(path: str) -> Optional[DiskPartition]:
    """根据路径获取其所在分区的信息。Mac 上用 df 获取挂载点（APFS 多卷同 st_dev 时准确）。"""
    path = os.path.abspath(path)
    partitions = get_disk_partitions()
    if sys.platform == "darwin":
        mp_str = _get_mount_point_darwin(path)
        if mp_str is not None:
            for p in partitions:
                if p.mount_point == mp_str or p.mount_point.rstrip(os.sep) == mp_str.rstrip(os.sep):
                    return p
    try:
        path_dev = os.stat(path).st_dev
    except OSError:
        path_dev = None
    if path_dev is not None:
        for p in partitions:
            try:
                if os.stat(p.mount_point).st_dev == path_dev:
                    return p
            except OSError:
                continue
    try:
        path = os.path.realpath(path)
    except OSError:
        pass
    best: Optional[DiskPartition] = None
    best_len = 0
    for p in partitions:
        mp = p.mount_point.rstrip(os.sep) + os.sep
        if path.startswith(mp) and len(mp) > best_len:
            best = p
            best_len = len(mp)
    return best
