# -*- coding: utf-8 -*-
"""
命令行入口：列举磁盘、确认后执行填充或释放，中文日志输出。
"""

from __future__ import annotations

import sys

# Windows 控制台使用 UTF-8 以正确显示中文
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
from typing import List, Optional

from . import __version__
from .disk_info import DiskPartition, get_disk_partitions
from .filler import (
    RESERVE_MB_DEFAULT,
    fill_disk,
    get_filler_file_path,
    list_existing_filler_files,
    remove_filler_file,
)


def log(msg: str) -> None:
    """统一中文日志输出。"""
    print(msg)
    sys.stdout.flush()


def log_operation_end(operation_name: str = "操作已结束") -> None:
    """输出操作结束分隔块，便于区分「执行完毕」与后续菜单。"""
    log("")
    log("=" * 60)
    log(f"  【{operation_name}】")
    log("=" * 60)
    log("")


def print_header() -> None:
    """打印脚本标题与版本。"""
    log("")
    log("=" * 60)
    log("  模拟磁盘占满工具 (mock_disk_full)")
    log("  跨平台支持: Windows / macOS")
    log(f"  版本: {__version__}")
    log("=" * 60)
    log("")


def print_disk_list(partitions: List[DiskPartition]) -> None:
    """打印当前磁盘情况（总空间、剩余空间）。"""
    log("【当前磁盘情况】")
    log("-" * 60)
    for i, p in enumerate(partitions, 1):
        log(f"  {i}. {p}")
    log("-" * 60)
    log("")


def prompt_choice(
    prompt: str,
    max_index: int,
    allow_zero: bool = False,
) -> Optional[int]:
    """提示用户输入选项编号，返回 1-based 索引，无效则返回 None。"""
    while True:
        try:
            s = input(prompt).strip()
            n = int(s)
            if allow_zero and n == 0:
                return 0
            if 1 <= n <= max_index:
                return n
        except ValueError:
            pass
        log("  无效输入，请重新选择。")


def confirm(prompt: str = "确认执行？(y/N): ") -> bool:
    """要求用户输入 y/yes 确认。"""
    s = input(prompt).strip().lower()
    return s in ("y", "yes")


def run_fill(partitions: List[DiskPartition], reserve_mb: int = RESERVE_MB_DEFAULT) -> None:
    """执行填充流程：选分区 -> 确认 -> 创建填充文件。"""
    print_disk_list(partitions)
    idx = prompt_choice(
        "请选择要填充的分区（输入序号）: ",
        len(partitions),
    )
    if idx is None:
        log("[取消] 未选择有效分区。")
        return

    part = partitions[idx - 1]
    filler_path = get_filler_file_path(part.mount_point)
    free_gb = part.free_gb
    reserve_gb = reserve_mb / 1024
    fill_gb = free_gb - reserve_gb

    log("")
    log("【即将执行】")
    log(f"  分区: {part.mount_point}")
    log(f"  总空间: {part.total_gb:.2f} GB")
    log(f"  当前剩余: {free_gb:.2f} GB")
    log(f"  预留空间: {reserve_gb:.2f} GB")
    log(f"  将创建填充文件约: {fill_gb:.2f} GB")
    log(f"  填充文件路径: {filler_path}")
    log("")
    if not confirm("确认后将在该分区创建大文件以占满磁盘，是否继续？(y/N): "):
        log("[取消] 已取消填充操作。")
        log_operation_end("填充已取消")
        return

    ok, result = fill_disk(part.mount_point, reserve_mb=reserve_mb, log_print=log)
    if ok:
        log("")
        log("[完成] 磁盘填充已完成。")
        # 打印填充后的磁盘情况（输出填充效果）
        partitions_after = get_disk_partitions()
        part_after = next(
            (p for p in partitions_after if p.mount_point == part.mount_point),
            None,
        )
        if part_after:
            log("")
            log("【填充后磁盘情况】")
            log("-" * 60)
            log(f"  {part_after.mount_point}  | "
                f"总空间: {part_after.total_gb:.2f} GB | "
                f"已用: {part_after.used_gb:.2f} GB | "
                f"剩余: {part_after.free_gb:.2f} GB")
            log("-" * 60)
        log_operation_end("填充操作已结束")
    else:
        log(f"[失败] {result}")
        log_operation_end("填充未完成")


def run_remove() -> None:
    """执行释放流程：自动检查 mock 占用 -> 列出并提示确认 -> 删除填充文件。"""
    existing = list_existing_filler_files()
    if not existing:
        log("【当前 mock 占用情况】")
        log("-" * 60)
        log("  当前未检测到本工具创建的填充文件，无需释放。")
        log("-" * 60)
        log_operation_end("释放检查已结束（无待释放文件）")
        return

    log("【当前 mock 占用情况】")
    log("-" * 60)
    for i, (path, size_bytes) in enumerate(existing, 1):
        size_gb = size_bytes / (1024**3)
        log(f"  {i}. {path}")
        log(f"     占用空间: {size_gb:.2f} GB")
    log("-" * 60)
    log("")
    if not confirm("确认删除以上填充文件以释放空间？(y/N): "):
        log("[取消] 已取消释放操作。")
        log_operation_end("释放已取消")
        return

    all_ok = True
    for path, _ in existing:
        ok, result = remove_filler_file(path, log_print=log)
        if not ok:
            log(f"[失败] {result}")
            all_ok = False
    log("")
    if all_ok:
        log("[完成] 磁盘空间已释放。")
    log_operation_end("释放操作已结束" if all_ok else "释放未完全成功")


def main() -> None:
    """主入口：交互式菜单，填充 / 释放 / 退出。"""
    print_header()

    partitions = get_disk_partitions()
    if not partitions:
        log("[错误] 未检测到可用磁盘分区。")
        sys.exit(1)

    while True:
        log("请选择操作：")
        log("  1. 模拟磁盘占满（创建填充文件）")
        log("  2. 释放磁盘空间（删除填充文件）")
        log("  0. 退出")
        log("")
        choice = prompt_choice("请输入选项 (0/1/2): ", 2, allow_zero=True)
        if choice is None:
            continue
        if choice == 0:
            log("再见。")
            break
        if choice == 1:
            run_fill(partitions)
        else:
            run_remove()
        log("")


def main_argv() -> None:
    """支持简单命令行参数：fill / remove，无参数时进入交互模式。"""
    if len(sys.argv) > 1 and sys.argv[1] in ("fill", "remove"):
        # 单命令模式：仍需选分区，但减少一层菜单
        print_header()
        partitions = get_disk_partitions()
        if not partitions:
            log("[错误] 未检测到可用磁盘分区。")
            sys.exit(1)
        if sys.argv[1] == "fill":
            run_fill(partitions)
        else:
            run_remove()
        return
    main()


if __name__ == "__main__":
    main_argv()
