# -*- coding: utf-8 -*-
"""
跨平台磁盘填充与释放模块。
Windows: 在目标盘符下创建 FAKETMP\\fakefile.tmp 占满剩余空间。
macOS: 在目标路径下创建 testfile，使用 dd 占满剩余空间（保留约 500MB + 10MB）。
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Optional, Tuple

from .disk_info import DiskPartition, get_disk_partitions, get_partition_by_path


# 预留空间（MB），避免完全占满导致系统异常
RESERVE_MB_DEFAULT = 510  # 500 + 10，与用户提供的 Mac 指令一致

# 填充文件名
FAKE_DIR = "FAKETMP"
FAKE_FILENAME = "fakefile.tmp"
MAC_FILENAME = "testfile"


def _is_windows() -> bool:
    return sys.platform == "win32"


def _is_macos() -> bool:
    return sys.platform == "darwin"


def get_filler_file_path(mount_point: str) -> str:
    """根据挂载点返回将要创建的填充文件路径（用于提示和删除）。"""
    mount_point = os.path.normpath(mount_point).rstrip(os.sep)
    if _is_windows():
        # Windows: X:\FAKETMP\fakefile.tmp
        return os.path.join(mount_point + os.sep, FAKE_DIR, FAKE_FILENAME)
    # macOS / Unix: {mount_point}/testfile
    return os.path.join(mount_point, MAC_FILENAME)


def fill_disk(
    target_path: str,
    reserve_mb: int = RESERVE_MB_DEFAULT,
    log_print=None,
) -> Tuple[bool, str]:
    """
    在目标路径所在分区上创建填充文件，占满剩余空间（保留 reserve_mb MB）。

    :param target_path: 挂载点或任意该分区下的路径，如 "C:\\" 或 "/Users/xxx"
    :param reserve_mb: 预留空间（MB）
    :param log_print: 日志输出函数，签名为 (msg: str) -> None
    :return: (成功与否, 填充文件路径或错误信息)
    """
    if log_print is None:
        log_print = print

    part = get_partition_by_path(target_path)
    if not part:
        return False, f"无法获取路径所在分区信息: {target_path}"

    free_mb = part.free_bytes // (1024 * 1024)
    if free_mb <= reserve_mb:
        return False, f"剩余空间不足 {reserve_mb} MB，当前约 {free_mb} MB，无需填充。"

    fill_mb = free_mb - reserve_mb
    filler_path = get_filler_file_path(part.mount_point)

    if _is_windows():
        return _fill_windows(part.mount_point, filler_path, fill_mb, log_print)
    if _is_macos() or sys.platform != "win32":
        return _fill_unix(part.mount_point, filler_path, fill_mb, log_print)
    return False, "当前操作系统暂不支持自动填充，请手动操作。"


def _fill_windows(
    mount_point: str,
    file_path: str,
    size_mb: int,
    log_print,
) -> Tuple[bool, str]:
    """Windows: 创建 FAKETMP 目录，使用 fsutil 创建大文件。"""
    dir_path = os.path.dirname(file_path)
    try:
        os.makedirs(dir_path, exist_ok=True)
        log_print(f"[信息] 已创建目录: {dir_path}")
    except OSError as e:
        return False, f"创建目录失败: {e}"

    size_bytes = size_mb * 1024 * 1024
    try:
        # fsutil file createnew <path> <length> 可快速创建空洞文件
        ret = subprocess.run(
            ["fsutil", "file", "createnew", file_path, str(size_bytes)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if ret.returncode != 0:
            err = (ret.stderr or ret.stdout or "").strip()
            return False, f"fsutil 执行失败: {err}"
        log_print(f"[信息] 已创建填充文件: {file_path}，大小约 {size_mb} MB")
        return True, file_path
    except FileNotFoundError:
        # 无 fsutil 时回退：用 Python 写文件（较慢）
        log_print("[信息] 未找到 fsutil，使用 Python 写入（可能较慢）...")
        try:
            with open(file_path, "wb") as f:
                f.seek(size_bytes - 1)
                f.write(b"\x00")
            log_print(f"[信息] 已创建填充文件: {file_path}，大小约 {size_mb} MB")
            return True, file_path
        except OSError as e:
            return False, f"创建填充文件失败: {e}"
    except subprocess.TimeoutExpired:
        return False, "创建文件超时。"


def _fill_unix(
    mount_point: str,
    file_path: str,
    size_mb: int,
    log_print,
) -> Tuple[bool, str]:
    """macOS / Unix: 使用 dd 创建填充文件。"""
    # dd if=/dev/zero of=file bs=1m count=N
    try:
        # 1m = 1MB，兼容 macOS (BSD dd) 与 Linux (GNU dd)
        cmd = [
            "dd",
            "if=/dev/zero",
            f"of={file_path}",
            "bs=1m",
            f"count={size_mb}",
        ]
        log_print(f"[信息] 执行: dd 写入约 {size_mb} MB 到 {file_path}")
        ret = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if ret.returncode != 0:
            err = (ret.stderr or ret.stdout or "").strip()
            return False, f"dd 执行失败: {err}"
        if os.path.isfile(file_path):
            size_actual = os.path.getsize(file_path)
            log_print(f"[信息] 已创建填充文件: {file_path}，大小约 {size_actual // (1024*1024)} MB")
            return True, file_path
        return False, "dd 未生成目标文件。"
    except FileNotFoundError:
        return False, "未找到 dd 命令，请确保在 Unix/macOS 环境下运行。"
    except OSError as e:
        return False, f"创建填充文件失败: {e}"


def remove_filler_file(file_path: str, log_print=None) -> Tuple[bool, str]:
    """
    删除之前创建的填充文件。

    :param file_path: 填充文件完整路径
    :param log_print: 日志输出函数
    :return: (成功与否, 说明信息)
    """
    if log_print is None:
        log_print = print

    if not file_path or not os.path.isfile(file_path):
        return False, f"文件不存在或不是文件: {file_path}"

    try:
        os.remove(file_path)
        log_print(f"[信息] 已删除填充文件: {file_path}")
        # Windows: 若 FAKETMP 为空，可顺带删除目录（可选）
        if _is_windows():
            dir_path = os.path.dirname(file_path)
            if os.path.basename(dir_path) == FAKE_DIR and not os.listdir(dir_path):
                try:
                    os.rmdir(dir_path)
                    log_print(f"[信息] 已删除空目录: {dir_path}")
                except OSError:
                    pass
        return True, "已释放磁盘空间。"
    except OSError as e:
        return False, f"删除文件失败: {e}"
