# -*- coding: utf-8 -*-
"""
跨平台磁盘信息获取模块。
列举各分区/盘符的总空间与剩余空间，供用户选择。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import List, Optional


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

    def __str__(self) -> str:
        return (
            f"{self.mount_point}  | "
            f"总空间: {self.total_gb:.2f} GB | "
            f"已用: {self.used_gb:.2f} GB | "
            f"剩余: {self.free_gb:.2f} GB"
        )


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
    """根据路径获取其所在分区的信息。"""
    path = os.path.abspath(path)
    partitions = get_disk_partitions()
    # 取最长匹配的挂载点
    best: Optional[DiskPartition] = None
    best_len = 0
    for p in partitions:
        mp = p.mount_point.rstrip(os.sep) + os.sep
        if path.startswith(mp) and len(mp) > best_len:
            best = p
            best_len = len(mp)
    return best
