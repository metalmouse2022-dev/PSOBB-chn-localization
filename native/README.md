# PSOBB 4:3 兼容显示增量补丁

这里发布相对上游源码的本地修改，不提供游戏 EXE、DLL、SDK、DDS 纹理、内嵌素材数组或编译产物。

## 来源与适用版本

- 上游：[anzz1/psobb_patches](https://github.com/anzz1/psobb_patches)。
- 固定提交：[`3d487ba5323b66d8795874f4edb0c82991cfbab6`](https://github.com/anzz1/psobb_patches/tree/3d487ba5323b66d8795874f4edb0c82991cfbab6)，子目录 `psobb_widescreen`。
- 游戏构建：MTethVer12513 / 1.25.13，原生地址和指令签名检查保留。此前工程匹配的 `PsoBB.exe` SHA-256 为 `cd82b56e04468bd2270330fbce19f7cbf5586e8957f25b8342608f2507a6dfe6`。本仓库不提供该文件，也不保证其他构建兼容。
- 保留上游 d3d8to9 的 [LICENSE.md](LICENSE.md)。上游其他组件、SDK、NVAPI、SMAA 等仍遵守各自原有声明；这个许可证文件不代表游戏或全部第三方依赖由本项目授权。

## 修改内容

`psobb-4x3-compat.patch` 包含 9 个文件的完整本地源码/项目增量：

1. 从游戏 EXE 同目录的 `launcher_display.ini` 读取显示模式及内部尺寸；限定精确 4:3，范围 640×480 至 7680×5760，无效尺寸回退 1280×960。
2. 为经过窗口模式格式能力检查的内部尺寸补全 Direct3D 模式缓存，避免只改客户端分辨率表后出现 `Can't find DisplayMode`。
3. `borderless` 与 `fullscreen` 共用窗口化兼容呈现，移除窗口框架、等比居中并维护黑边；普通窗口走原窗口路径。这里的 `fullscreen` 不切换显示器独占输出。
4. 兼容呈现使用 COPY、单缓冲和关闭 MSAA，以支持目标矩形；保留上游 HUD 缩放及现有特效。Reset 前释放补丁默认池资源，成功后重建。
5. 删除上游 Debug 配置中向固定本机游戏目录复制 DLL 的 `CustomBuildStep`。除这一发布调整外，源码增量取自工程当前本地版本；原工程没有被修改。

本地新增 helper 为 `display_modes.hpp`、`presentation.hpp`、`presentation_window.h`。其余未修改文件和必需依赖由固定上游提供，不包含在补丁中。

## 应用补丁

准备 Windows Git，并在本目录执行。使用新建的上游副本，先保存自己的已有修改。以下步骤只取得上游源码并应用增量，不启动游戏，也不复制任何 DLL 到游戏目录。

```powershell
$patch = (Resolve-Path -LiteralPath '.\psobb-4x3-compat.patch').Path
git -c core.autocrlf=false clone --no-checkout https://github.com/anzz1/psobb_patches.git psobb_patches
git -C .\psobb_patches config core.autocrlf false
git -C .\psobb_patches checkout --detach 3d487ba5323b66d8795874f4edb0c82991cfbab6
git -C .\psobb_patches apply --directory=psobb_widescreen --check $patch
git -C .\psobb_patches apply --directory=psobb_widescreen $patch
```

`--directory=psobb_widescreen` 必须保留：补丁内部路径相对于该子目录。固定提交和关闭自动换行转换是为保证原始上下文一致；若 `--check` 失败，先核对提交、工作树和换行，不跳过检查强行应用。应用结果的各文件 SHA-256 见 [verification.json](verification.json)。

## Release 构建

需要 Visual Studio Build Tools 2022 的 MSVC v143、Windows 10/11 SDK，以及固定上游包含的构建依赖。上游的 DirectX SDK/NVAPI 库、着色器与查找纹理须保留在原目录；本补丁不能作为完整源码树独立构建。依赖由使用者从其可信来源取得并确认使用条件，本仓库不重新分发这些文件。

```powershell
$msbuild = 'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\MSBuild\Current\Bin\MSBuild.exe'
& $msbuild .\psobb_patches\psobb_widescreen\d3d8to9.vcxproj /p:Configuration=Release /p:Platform=Win32 /p:PlatformToolset=v143 /p:WindowsTargetPlatformVersion=10.0 /verbosity:minimal /nologo
```

输出为 `psobb_patches/psobb_widescreen/bin/Release/d3d8.dll`，目标架构 x86。这里只提供 Release 构建流程；编译成功不代表在所有设备上兼容。

启动器与 DLL 的显示配置接口需要匹配。示例配置应由启动器写到游戏 EXE 同目录，或在独立测试副本中手工准备：

```ini
[Display]
Mode=borderless
Width=1440
Height=1080
```

模式为 `window`、`borderless`、`fullscreen`；客户端自身仍须设置为窗口状态。更新前正常退出游戏并备份旧 DLL 和启动器；本仓库不会自动覆盖游戏文件。

## 验证与限制

本次发布核验从 GitHub 固定提交取得相关原始文件，校验 Git blob SHA-1，并在隔离目录完成 `git apply --check`、实际应用及 9 个目标文件逐字节 SHA-256 比对，均通过。补丁与文件清单见 [verification.json](verification.json)。

本次未重新编译此发布副本，也未启动游戏。工程此前的 Win32 Release 编译、隔离图形接口检查和本机显示确认属于历史证据，不能代替这份公开材料的全新构建或跨设备验收。此增量不提供宽屏视野适配；其他电脑、显示器、游戏内切出返回及所有输入设备仍需各自验证。
