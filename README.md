# mock_disk_full

跨平台模拟磁盘占满工具，用于在 **Windows** 与 **macOS** 上快速制造“磁盘将满”的测试环境（例如验证应用在磁盘空间不足时的行为）。

## 功能说明

- **列举当前磁盘情况**：显示各分区总空间、已用、剩余空间（中文输出）。
- **模拟占满**：在选定分区上创建填充文件，占满剩余空间（默认预留约 510MB，避免系统异常）。
- **释放空间**：删除本工具创建的填充文件，恢复空间。
- **操作前确认**：执行填充或删除前会再次提示并需输入 `y` 确认。

## 环境要求

- **Python**：3.7+（推荐使用 `python3`）
- **操作系统**：Windows 或 macOS

## 项目结构

```
mock_disk_full/
├── README.md                 # 本说明文档
├── requirements.txt           # 依赖（psutil，可选）
└── mock_disk_full/            # 主包
    ├── __init__.py
    ├── __main__.py            # python3 -m mock_disk_full 入口
    ├── cli.py                 # 命令行交互与主流程
    ├── disk_info.py           # 跨平台磁盘信息
    └── filler.py              # 填充/删除逻辑（Win + Mac）
```

## 安装与运行

### 1. 安装依赖（推荐）

```bash
pip install -r requirements.txt
```

未安装 `psutil` 时，脚本会使用标准库回退实现（可能列举的分区较少）。

### 2. 运行方式

在项目根目录下执行：

```bash
# 方式一：模块方式运行（推荐）
python3 -m mock_disk_full

# 方式二：直接运行包内 CLI
python3 mock_disk_full/cli.py
```

也可先安装为可执行包再运行：

```bash
pip install -e .
python3 -m mock_disk_full
```

### 3. 交互流程

1. 启动后显示**当前磁盘情况**（总空间、已用、剩余）。
2. 选择操作：
   - **1**：模拟磁盘占满（先选分区，确认后创建填充文件）。
   - **2**：释放磁盘空间（先选分区，确认后删除填充文件）。
   - **0**：退出。
3. 选择分区时输入对应**序号**。
4. 填充/删除前会再次提示，输入 **y** 确认后执行。

## 各平台说明

### Windows

- 填充文件路径：`<盘符>:\FAKETMP\fakefile.tmp`（例如 `C:\FAKETMP\fakefile.tmp`）。
- 优先使用 `fsutil file createnew` 快速创建大文件；若无 `fsutil`，则用 Python 写入（速度较慢）。
- 释放时会删除该文件；若 `FAKETMP` 为空，会顺带删除该目录。

### macOS

- 填充文件路径：`<所选分区路径>/testfile`（例如选择用户主目录时为 `$HOME/testfile`）。
- 使用 `dd if=/dev/zero` 写入，预留约 500MB + 10MB，与常见脚本行为一致。
- 释放时删除该 `testfile`。

参考的 Mac 指令示例：

```bash
# 占满用户目录（预留约 510MB）
dd if=/dev/zero of="$HOME/testfile" bs=1m count=$(( $(df -m "$HOME" | awk 'NR==2 {print $4}') - 500 - 10 ))

# 删除
rm -f "$HOME/testfile"
```

本工具在 macOS 上会按所选分区计算可写空间并调用 `dd`，实现相同效果。

## 注意事项

1. **仅用于测试环境**：请勿在生产机或重要数据盘上随意执行“占满”操作。
2. **预留空间**：默认预留约 510MB，避免磁盘 100% 导致系统异常；如需修改可在代码中调整 `RESERVE_MB_DEFAULT`（见 `filler.py`）。
3. **网络盘**：Windows 上会列出逻辑盘；请勿选择网络盘进行填充，以免影响他人或挂载点。
4. **权限**：需要对目标分区有写权限；若权限不足，创建或删除文件会报错。
5. **Windows 中文显示**：脚本会尝试将标准输出设为 UTF-8。若仍乱码，可在运行前执行 `chcp 65001` 或使用支持 UTF-8 的终端（如 Windows Terminal）。

## 许可证

按项目仓库约定使用。
