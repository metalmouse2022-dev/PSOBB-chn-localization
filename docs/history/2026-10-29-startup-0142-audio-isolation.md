# v2/v3 启动错误 0xc0000142：优先停用附加音频层

反馈：某玩家 v1 能打开但显示左上角小窗口，v2/v3 无法启动，单独运行 PsoBB.exe 也报 0xc0000142。暂时没有其系统、显卡或故障转储，且本地没有可直接比对的完整 v1/v2 原包。不能把此次兼容处理写成已确认解决远端故障。

Microsoft 将该错误定义为 STATUS_DLL_INIT_FAILED：动态链接库初始化失败。它没有指出具体哪个 DLL，不能据此断言显卡故障或缺少某个运行库。

## 优先处理依据

当前包新增的 DSOAL r697 Win32 音频兼容层来自先前音乐卡顿排查；此前未通过实际游戏证明其改善。旧记录指出加入前 Client 没有本地 dsound.dll。附加层并非游戏本体必需，停用即可回到系统 DirectSound 路径，因此是可逆、影响范围小的首轮隔离对象。

实际 PE 导入已核对：

- PsoBB.exe 为 x86，静态导入 dsound.dll 与 d3d8.dll。
- 附加 dsound.dll 导入 MSVCP140.dll、VCRUNTIME140.dll 及 UCRT。
- dsoal-aldrv.dll 另外导入 MSVCP140_ATOMIC_WAIT.dll，且含 CreateFile2 等系统 API 依赖。仅确认依赖存在，没有故障玩家电脑的加载失败证据。
- 图形链为本地 d3d8 → d3d9，仍是后续候选；本轮不同时改动图形链，避免失去单变量测试价值。

## 安全修改

只移动 `Client/dsound.dll` 到 `Client/audio-compat/disabled/dsound.dll`。不改游戏 EXE、注册表、显示配置、成长表或存档；dsoal-aldrv.dll 和 alsoft.ini 留在原处，但游戏不再通过本地 dsound.dll 进入此兼容层。

工具 `tools/audio_compat_toggle.ps1` 提供 Disable / Restore。检查游戏已退出；识别随包 DSOAL 的 SHA256；未知版本拒绝修改；已有目标拒绝覆盖；移动后核对哈希。没有删除 DLL、终止进程或操作系统目录。

先在独立文件夹检查停用、重复停用、恢复与恢复冲突，再应用到本机。故障玩家需先停用后重新运行一次游戏，以判断此次调整是否解决 0xc0000142；若仍报同一错误，应恢复音频后单独隔离图形 DLL。v1 的窗口尺寸问题另行处理。

## 本次完成状态

隔离验证已通过：停用、重复停用、恢复、目标冲突拒绝覆盖、未知 DLL 哈希拒绝修改。测试中发现当前 Windows PowerShell 环境无法使用 Get-FileHash，已改用 .NET SHA256，复测通过，减少对 PowerShell 模块的依赖。

本机未检测到游戏进程后已停用附加层，原 DLL 完整保留在上述 disabled 目录，哈希为 `c304c7c822e885d35d016ef2667ed98bd3c3f688d16c35ce5e412d61749542cf`。其余 Client 根目录文件逐个哈希不变；Server 根目录 12 个 DAT 哈希不变。没有启动游戏进行试听，不能声称远端 0xc0000142 已解决。

交付 `PSOBB_启动兼容处理_停用附加音频_20261029.zip`：包含停用与恢复两个 CMD、一个 PS1、使用说明，CRC 校验通过。该 ZIP 不含 DLL、游戏文件或存档。原完整 v3 ZIP 未修改，分发旧整包时需另行配套本补丁。验证记录：`.ui-review/audio-isolation-receipt.json`。

## 来源

- https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-erref/596a1078-e883-4972-9bbc-49e60bebca55
- https://github.com/kcat/dsoal
- https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist
- 本地既有记录：`tools/docs/BUGFIX_AUDIT_2026-10-28.md`。
