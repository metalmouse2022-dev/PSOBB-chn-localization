# 环境与最小复现

## 环境与输入

本次工具整理环境为 Windows、Python 3.12。启动器使用 `winreg`、`ctypes` 和 `tkinter`，不适用于直接在 Linux 启动。QST/PRS/unitxt 核心工具使用标准库。

自备游戏目录通过 `PSOBB_GAME_ROOT` 指定。先复制到工作目录，再操作；不要直接对唯一底本或正在使用的存档运行回填、倍率修改等功能。

已知匹配输入记录：

| 输入 | SHA-256 / 限制 |
| --- | --- |
| `Client/PsoBB.exe` | `cd82b56e04468bd2270330fbce19f7cbf5586e8957f25b8342608f2507a6dfe6`；原生显示补丁仅针对 MTethVer12513 |
| `Client/data/PlyLevelTbl.bin.default` | `59d29b9c510a39965074c45c29b4a1a0f5f7d78d5b156e9d32798aeb9a8386d6`；29184 字节已知布局 |
| `Server/ship_server.exe` | 既有成长表调查使用 `9c49eb910a1f39ce5de847c47d23186be4fa91958ea0cc3c936adf9bf4a1f84e` |

以上来自既有调查记录，不证明其他版本兼容。仓库没有这些文件，也不提供游戏下载地址。

## 任务文本

从仓库根目录执行：

```powershell
$env:PSOBB_GAME_ROOT = 'D:\PSOBB-work'
python tools/psobb_quest_tool.py --export --output tools/quest_translations/all_quests_text.json
python tools/psobb_batch_tool.py --split
```

导出项以相对任务路径为键，对白有稳定 `id`、`raw_offset`、`raw_len`、`max_chars`、`en`、`cn`。标题、简报、详述各有译文字段和预算。`max_chars` 实际对应 UTF-16 代码单元预算，非所有 Unicode 字符都只占一格。

手工填写 `cn`，或把整理后的批次交给自己选择的翻译流程；人工结果放在 `tools/quest_translations/translated_batches/`。完成后：

```powershell
python tools/psobb_batch_tool.py --merge
python tools/psobb_quest_tool.py --check tools/quest_translations/all_quests_text.json
python tools/psobb_quest_tool.py --import-json tools/quest_translations/all_quests_text.json
```

回填原位修改自备工作目录中的 QST。先审阅检查输出并保留底本；现有 CLI 的退出码不能单独证明每个任务成功。提取器使用启发式 ASCII UTF-16 扫描，不能保证识别任意脚本中的全部字符串。超长会拦截，部分控制码和行宽问题仅预警，仍需人工检查。详见技术说明。

## unitxt 文本表

```powershell
python tools/psobb_unitxt_tool.py export D:\PSOBB-work\Client\data\unitxt_j.prs unitxt-work.txt
python tools/psobb_unitxt_tool.py import unitxt-work.txt unitxt-rebuilt.prs
```

TXT 采用 `[表号:条目号]` 与 `[/entry]` 标记。保持编号与换行关系；输出先写独立文件，人工核验后再替换工作副本。

## 可选依赖与构建

```powershell
python -m pip install -r requirements-optional.txt
```

`GEMINI_API_KEY` 通过环境变量或未提交的 `tools/.env` 配置，不把真实密钥写入脚本。API 脚本保留既有候选模型列表，未在本次验证可用性；使用前自行核对服务端支持。本次已将凭据改为 `x-goog-api-key` 请求头，错误日志仅保留状态码或异常类型，依据 [Gemini API 参考](https://ai.google.dev/api)。运行翻译会向该服务发送所选文本并可能产生费用；手工编辑是无需 API 的替代方式。

如需打包启动器，另安装 PyInstaller，再在 `tools/` 目录运行：

```powershell
python -m PyInstaller --clean PSOBB一键单机启动器.spec
```

公开 spec 使用默认图标，不携带游戏图标；输出 EXE 不由本仓库分发。本次没有重新打包。原生补丁另见 [应用和构建说明](../native/README.md)。

## 原有回归测试

`tools/test_*.py` 保留供自备资源后的维护使用；成长表、ItemPT 和真实红盒表测试依赖本地游戏数据，并非空仓库即可全量运行。真实输入包括 `Server/param/ItemPT.gsl`、`Client/data/PlyLevelTbl.bin.default`、`Server/drop/` 及其原表备份。测试使用 `.ui-review/` 下的隔离副本，已有历史记录为 26 项通过，本次没有重跑整套。
