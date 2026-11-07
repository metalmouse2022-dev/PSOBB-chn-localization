# PSOBB《梦幻之星网络版：蓝色脉冲》汉化工具与技术资料

![Uploading 86b02537-ff5b-41e0-9f2a-93e83effe802.png…]()


这里整理 PSOBB 单机汉化工程中的 **Python 工具、启动器源码、4:3 显示兼容补丁和中文排错经验**，供汉化作者与开发者参考、复现和继续维护。

仓库不包含游戏客户端、服务端程序、游戏资源、整合包、存档、账号配置或完整提取文本。运行游戏相关功能前，请自行合法准备匹配版本的输入，并先复制到独立工作目录。

## 有什么

| 目录 | 内容 |
| --- | --- |
| [tools/](tools/) | Tk 启动器、QST/PRS 任务文本工具、unitxt 文本表工具、批次/TM 工具、可选翻译 API 脚本及原有回归测试 |
| [native/](native/) | 基于固定上游提交的 4:3 兼容显示增量补丁、原许可证、应用与构建说明 |
| [docs/technical-notes.md](docs/technical-notes.md) | 成长表越界、显示模式枚举、红盒概率、音频隔离和汉化格式经验 |
| [docs/quickstart.md](docs/quickstart.md) | 环境、最小复现流程、输入版本与工具限制 |
| [docs/provenance.md](docs/provenance.md) | 来源、许可与未公开材料说明 |
| [docs/publication.md](docs/publication.md) | 本次整理范围、导出差异和抽查结果 |
| [docs/history/](docs/history/) | 有日期的既有排错记录，保留当时的验证边界 |

## 快速开始

本次整理使用 Windows、Python 3.12。PRS、QST、unitxt 工具仅依赖 Python 标准库；启动器还需要 Windows API 和 Python 自带的 Tk。可选翻译脚本需要 `requests`，打包启动器另需 PyInstaller。

不需要游戏文件、网络或 API Key 的三项自造样例抽查：

```powershell
python -B tools/smoke_check.py
```

查看工具帮助：

```powershell
python tools/psobb_quest_tool.py --help
python tools/psobb_batch_tool.py --help
python tools/psobb_unitxt_tool.py
```

如需使用启动器或操作自备游戏文件，显式设置运行根目录：

```powershell
$env:PSOBB_GAME_ROOT = 'D:\PSOBB-work'
python tools/launcher.py
```

工作目录应有 `Client/` 与 `Server/`；源码默认使用仓库根目录，冻结 EXE 默认使用 EXE 所在目录。不会向上查找其他工程。实际运行启动器会写入配置，并按所选功能调整游戏数据或启动本地服务，请先备份并关闭正在运行的游戏。

## 当前边界

- 本仓库发布的是工具与经验，不等于可直接运行的完整游戏，也不代表全部剧情和路线已验收。
- 目前显示方案保留 4:3；无边框和兼容全屏使用窗口呈现。原生补丁只针对文档注明的客户端版本。
- 本次只做小样抽查和发布检查，未重新编译原生 DLL、未调用翻译服务、未进行游戏内验证。原始工程和存档保持原位。
- API 脚本作为可选源码保留。使用前自行确认模型、配额和费用；本次没有发送游戏文本。也可以手工翻译或使用批次工具整理人工结果。
- 自有工程文件尚未指定统一开源许可证；公开可读不代表授予任意再分发权。第三方代码按各自声明处理。
