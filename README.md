# 自动视频剪辑 V2.1

完全本地运行的 Windows 桌面自动剪辑软件，使用 Python 3.11/3.12、PySide6、FFmpeg 和 FFprobe。素材不会上传，也不依赖在线 API。

## 已实现能力

- 默认批量文件夹模式：一次选择素材总目录，自动扫描其直接子文件夹并逐个生成成片。
- 每个批量子文件夹要求至少 2 个 MP4，以及恰好 1 个 PNG 封面、1 个 SRT 字幕和 1 个 MP3 配乐；视频和子文件夹均按自然文件名排序。
- 批量任务统一手动选择一个 Logo，输出按“前缀1.mp4、前缀2.mp4……”命名；单个目录失败不会阻断后续任务。
- 批量输出目录只交付最终 MP4，封面、任务报告和逐任务诊断日志保存在应用配置目录；界面可将本轮完整日志下载为 UTF-8 文本。
- 可选择导出质量：标准 CRF/CQ 19、高质量 16、超高质量 14，或目标码率 12/16/20 Mbps；CPU 与 NVIDIA 编码均生效。
- 多视频导入、重复素材、拖拽/上移/下移人工排序，最终顺序严格等于列表顺序。
- 固定输出 H.264 MP4、1440×2560、9:16、CFR 60FPS、`yuv420p`。
- 混合横竖比例素材：完整前景等比居中，同画面放大并模糊作为背景，不留纯黑边。
- 默认使用 FFmpeg `minterpolate` 做运动补偿插帧；也可明确选择快速 `fps=60` 模式。
- 相邻片段固定 1 秒交叉叠化；单片段不添加转场。
- 默认将列表中的第 2 段视频水平镜像，可在界面取消。
- 可选封面置于最前方，精确 5 帧且不参与叠化，同时输出独立 `cover.jpg`。
- 可选 Logo 图片；可按 10%–300% 缩放并设置 0%–100% 透明度，前 4 帧不显示，从第 5 帧开始沿对角线由右上角平滑移动至末帧左下角。
- SRT/ASS 硬字幕；界面可选择已安装字体，SRT 还支持字号、颜色、描边与底边距，ASS 保留字体以外的原样式。封面存在时字幕统一偏移 `5/60` 秒。
- 配乐自动截短或循环，默认音量 35%，在成片最后 1 秒淡出。
- 原声默认静音，可选保留；多片原声在视频转场处同步跨淡化，无音轨片段自动补静音。
- NVENC 实际编码探测；不可用或仅初始化失败时回退 `libx264`，不会偷偷把运动补偿降级为快速模式。
- 后台渲染、真实 FFmpeg 进度、可取消、完整日志、失败清理、`.part.mp4` 原子成品保存和同名防覆盖。
- 成片完成前使用 FFprobe 核验编码、尺寸、60FPS、真实帧数、时长和音频参数。

## Windows 安装

要求：Windows 10/11 x64、Python 3.11 或 3.12 x64、FFmpeg 7+（需同时包含 FFprobe 和 libass）。

```bat
git clone https://github.com/NoEnglish1997/Codex.git
cd Codex
py -3.12 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m auto_video_editor
```

### FFmpeg 与 FFprobe

应用按以下顺序查找：

1. 界面中用户指定的 `ffmpeg.exe` 和 `ffprobe.exe`；
2. EXE/项目目录，或其 `ffmpeg\bin` 子目录；
3. 系统 `PATH`。

可从 FFmpeg 官方下载页选择可信 Windows 构建，也可用包管理器安装：

```powershell
winget install --id Gyan.FFmpeg
# 或
choco install ffmpeg
```

安装后在终端验证：

```bat
ffmpeg -version
ffprobe -version
ffmpeg -filters | findstr /I "xfade minterpolate subtitles ass overlay gblur boxblur"
```

本项目不静默下载或捆绑 FFmpeg。若分发 FFmpeg 二进制，请自行确认所选构建的许可证条款。

## 批量文件夹流程（默认）

素材总目录只扫描其第一层子文件夹。建议结构如下：

```text
素材总目录\
├─ 任务1\
│  ├─ 1.mp4
│  ├─ 2.mp4
│  ├─ 封面.png
│  ├─ 字幕.srt
│  └─ 配乐.mp3
└─ 任务2\
   ├─ 片段1.mp4
   ├─ 片段2.mp4
   ├─ cover.png
   ├─ caption.srt
   └─ bgm.mp3
```

1. 启动软件并确认 FFmpeg 环境可用，保持“批量文件夹（默认）”模式。
2. 选择素材总目录，点击“扫描检查”；不合格目录会显示原因，开始后也会写入完整日志。
3. 手动选择本批任务统一使用的 Logo，并调整缩放、透明度、字幕字体、镜像及导出质量等公共设置。
4. 选择一个单独的输出目录并输入文件名前缀，例如 `成片_`。程序会按自然排序生成 `成片_1.mp4`、`成片_2.mp4`……。
5. 点击“开始批量剪辑”。某个目录预检或渲染失败时会跳过并继续；为防止覆盖，如果目标文件名已存在，对应任务会被跳过。
6. 完成后点击“打开输出文件夹”查看 MP4，或点击“下载日志”把本轮界面中的完整记录另存为 UTF-8 文本。

批量输出目录中只会放最终 MP4。逐任务封面、JSON 报告和底层日志默认保存在 `%APPDATA%\AutoVideoEditor\batch_records\`，用于排错，不属于交付文件。

## 手动单任务流程

1. 将“工作模式”切换为“手动单任务”，确认顶部显示“全部必需能力可用”。检测失败时选择正确的两个可执行文件。
2. 添加至少一个视频。拖拽列表或使用“上移/下移”确定最终顺序；手动模式不会按文件名自动排序。
3. 按需选择封面、Logo 图片、SRT/ASS 字幕和配乐。Logo 保持原始比例，可设置缩放和透明度；缩放 100% 表示最大 240×240，透明度 100% 表示不透明。
4. 选择帧率模式：
   - **运动补偿**：默认，使用 `minterpolate` 生成真实中间帧，CPU 负载高；GTX 1060 的 NVENC 只加速编码，不加速该滤镜。
   - **快速 60FPS**：使用 `fps=60` 重复/丢弃帧，速度更快，但不是运动补偿。
5. 按需启用/取消第 2 段镜像、启用原声混合、调整配乐音量，并从“字幕字体”下拉框选择 Windows 已安装字体。固定输出规格不能改成横屏。
6. 选择导出质量。标准档会根据画面复杂度智能控制体积；如果需要接近剪映的文件大小，可先选择“目标 16 Mbps”。
7. 选择输出目录和文件名，点击“开始剪辑”。渲染时可查看阶段、百分比和日志，也可取消。
8. 只有 FFprobe 核验通过后进度才会到 100%。同名文件不会被覆盖，而会自动追加 `_001` 等编号。

手动模式输出目录包含：

- 最终 MP4；
- 有封面时的独立 `cover.jpg`；
- `*.job_report.json`，记录真实帧数、转场位置、编码器和配置；
- 渲染日志，包含安全的参数列表、返回码和 FFmpeg 错误。

## 时间线规则

所有时间线都以 60FPS 整数帧计算。标准化后各片段真实帧数为 `N1...Nk`：

```text
主体帧数 = sum(Ni) - (k - 1) * 60
总帧数   = 主体帧数 + (有封面时 5，否则 0)
```

例如三段各 600 帧、两次叠化并带封面时，成片为 `1800 - 120 + 5 = 1685` 帧。程序不会把转场当成额外的一秒插入。

## 测试

运行全部测试，包括真实 FFmpeg 集成测试：

```bat
call .venv\Scripts\activate.bat
python -m pytest
```

只运行不编码视频的快速单元测试：

```bat
python -m pytest -m "not integration"
```

单独生成三段短测试素材：

```bat
python scripts\create_test_media.py test-media
```

真实集成测试会生成横屏/竖屏、有声/无声视频、封面、字幕和短音乐，执行完整渲染，并用 FFprobe 与解码像素核验尺寸、60FPS、帧数、首部五帧、音轨和非黑边背景。测试产物位于 pytest 临时目录。

## Windows EXE 打包

在 Windows x64 的普通 `cmd.exe` 中运行：

```bat
scripts\build_windows.bat
```

脚本会创建/复用 `.venv`、安装精确版本依赖、先运行测试，再执行：

```bat
python -m PyInstaller --noconfirm --clean --onedir --windowed --name AutoVideoEditor --paths src scripts\windows_entry.py
```

成功后入口为：

```text
dist\AutoVideoEditor\AutoVideoEditor.exe
```

FFmpeg/FFprobe 仍是外部前提。可以在目标电脑加入 `PATH`，通过应用设置选择，或放到 `dist\AutoVideoEditor\ffmpeg\bin\`。仓库同时提供 `.github/workflows/build-windows.yml`；推送到 `main` 或手动运行工作流后，可下载 `AutoVideoEditor-Windows-x64` 构建产物。

## 常见问题

- **FFmpeg 检测失败**：确认 FFmpeg 与 FFprobe 来自同一套构建，且具有 `xfade`、`minterpolate`、`overlay`、模糊滤镜、libass 和 `libx264`。
- **NVENC 名称存在但仍不可用**：编码器列表不代表驱动可初始化。应用会做短时实际编码探测并使用 x264；请更新 NVIDIA 驱动后重新检测。
- **运动补偿很慢**：这是 CPU 滤镜，属于预期行为。可由用户主动切换“快速 60FPS”，程序不会自动降级。
- **字幕不显示**：检查字幕时间码、编码和 FFmpeg 是否启用 libass；中文字体不存在时在界面选择已安装字体。
- **Logo 不显示**：确认图片为 JPG、PNG 或 WebP；Logo 在前 4 帧隐藏，从第 5 帧开始出现。
- **批量目录被跳过**：确认该直接子目录中至少有 2 个 MP4，并且 PNG、SRT、MP3 各恰好 1 个；文件扩展名不区分大小写。
- **批量编号缺少某一项**：为防止覆盖，已有目标 MP4 会导致对应任务被跳过；下载日志可查看具体路径。
- **成片体积比剪映小**：标准档是内容自适应压缩，静态或低运动画面会很小；选择目标 12/16/20 Mbps 可以更直接地控制体积。理论体积约为“时长秒数 × Mbps ÷ 8”。
- **素材短于 2 秒**：V1 会阻止渲染，避免一个片段上的相邻转场重叠。
- **磁盘不足**：逐片标准化会产生高质量中间文件。日志会显示临时空间估计与任务临时目录。
- **取消后没有成片**：这是正确行为；取消或失败会删除 `.part.mp4` 和本任务临时目录，防止把残片当成完成品。
- **超长路径或权限失败**：选择较短且当前用户可写的输出目录；应用不会绕过 Windows 权限。

## 平台说明

开发与自动集成测试可在 Linux 执行，但 Linux 的 PyInstaller 产物不是 Windows EXE。本仓库只把 `scripts\build_windows.bat` 或 Windows GitHub Actions runner 生成的结果视为 Windows 构建；发布前仍应在 Windows 10 x64 上启动 GUI，并用实际素材做一次人工验收。
