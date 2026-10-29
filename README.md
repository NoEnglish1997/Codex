# 自动视频剪辑 V3.4

完全本地运行的 Windows 桌面自动剪辑软件，使用 Python 3.11/3.12、PySide6、FFmpeg 和 FFprobe。素材不会上传，也不依赖在线 API。

## V3.4 已实现能力

- **完整批量生产**：扫描素材总目录的直接子文件夹；自然/创建时间/修改时间/`config.json`/确定性随机五种排序，可用通配符固定片头片尾。
- **Desert Rose 创作工作台**：依据 Anthropic 官方开源 [`frontend-design`](https://github.com/anthropics/skills/tree/main/skills/frontend-design) 与 [`theme-factory`](https://github.com/anthropics/skills/tree/main/skills/theme-factory) Skills 重写为酒红、陶土和暖沙色的原生桌面界面；批量项目库、9:16 预览、视频/音频时间线、导出检查器和固定任务栏构成真正的三栏剪辑工作流。
- **灵活命名与自动监控**：命名模板支持 `{prefix}`、`{folder}`、`{index}`、`{date}`；可监控新增子目录，连续两次检测文件不再变化后自动处理。
- **目录级配置**：每个子目录可用 `config.json` 指定视频顺序、逐片裁剪、输出名及剪辑参数，且不会影响其他目录。
- **失败隔离**：单任务失败继续队列；“仅重试失败任务”不会重复成功任务；完整日志可下载，批量输出目录只交付 MP4。
- **逐片裁剪**：手动设置每段开始/结束时间，也可统一限制每段最长时长；可检测并裁掉片尾黑帧。
- **可选转场**：无转场、交叉淡化、向左推拉、向左擦除、缩放五种类型，时长可在 0–5 秒内调整。
- **高级封面**：封面帧数、淡入、100%–160% 平缓缩放、居中标题和独立 `cover.jpg` 导出均可设置。
- **三种画布**：模糊背景＋完整前景、放大填满并裁切、纯色背景＋完整前景；支持居中/四边/自定义位置。
- **非 AI 画质增强**：Lanczos 缩放、降噪、锐化、亮度、对比度、饱和度、暗部提升和高光保护，全部是本地 FFmpeg 滤镜。
- **可交互剪辑时间线**：手动模式可在时间线上点击选中片段、拖拽重新排序、拖动左右手柄裁剪、点击刻度或音频轨定位静帧；点击转场标记会直接打开对应设置，所有操作同步到最终 FFmpeg 任务。
- **快速预览与定位**：手动模式按播放头所在源视频时间异步生成静帧，也可在预览区拖动画面位置，不必先编码完整视频。
- **Logo 完整控制**：10%–300% 缩放、0%–100% 透明度、八种轨迹/固定位置、自定义起止坐标、显示帧区间和淡入淡出。
- **字幕排版**：系统字体、字号、颜色、描边、阴影、半透明底板、安全边距、自动换行和关键词着色；内置三种字幕样式预设。
- **音频优化**：配乐循环/截断、音量和淡入淡出；可保留原声、做 LUFS 响度标准化，并在原声出现时自动压低 BGM。
- **预设与预估**：内置“抖音2K高清”“快速预览”“20秒约40MB”等方案，支持自定义预设；实时估算时长、帧数、文件体积和磁盘需求，并提示低清、低帧率及 VFR 素材。
- **固定可交付规格**：H.264 MP4、1440×2560、9:16、CFR 60FPS、`yuv420p`；质量可选 CRF/CQ 19/16/14 或稳定 12/16/20 Mbps。
- **单次最终编码**：裁剪、画布、镜像、60FPS、转场、封面、Logo、增强和字幕在同一个滤镜图中完成，最终只进行一次 H.264 编码，不调用 AI、在线 API 或云端素材处理。
- **可靠完成判定**：后台处理、可取消、`.part.mp4` 原子保存、同名防覆盖、NVENC 实际探测与 x264 回退；完成前用 FFprobe 核验编码、尺寸、帧率、帧数、时长和音轨。

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
ffmpeg -filters | findstr /I "xfade minterpolate subtitles overlay gblur hqdn3d unsharp loudnorm sidechaincompress"
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
2. 选择素材总目录和视频排序方式。默认“自然文件名”会按 `2.mp4`、`10.mp4` 排序；也可按创建/修改时间、`config.json` 或确定性随机顺序。片头/片尾输入框接受 `片头*.mp4` 这类通配符。
3. 点击“扫描检查”；不合格目录会显示原因，开始后也会写入完整日志。批量目录仍要求至少 2 个 MP4，以及 PNG、SRT、MP3 各 1 个。
4. 手动选择本批任务统一使用的 Logo，并调整画面、转场、字幕、音频及导出质量等公共设置；子目录里的 `config.json` 可以只覆盖该任务。
5. 选择一个单独的输出目录，填写前缀及命名模板。默认 `{prefix}{index}.mp4` 生成 `成片_1.mp4`；例如 `{date}_{folder}_{index}.mp4` 会同时带日期、目录名和序号。
6. 点击“开始批量剪辑”。某个目录失败时队列继续；修正素材后可点击“仅重试失败任务”。已有目标文件不会被覆盖。
7. 如果持续向总目录投放任务，可勾选“监控新增子文件夹并自动处理”。程序只处理启用监控后新建、且连续两次轮询大小与修改时间都稳定的目录。
8. 完成后点击“打开成品”查看 MP4，或点击“导出日志”将本轮完整记录另存为 UTF-8 文本。

批量输出目录中只会放最终 MP4。逐任务封面、JSON 报告和底层日志默认保存在 `%APPDATA%\AutoVideoEditor\batch_records\`，用于排错，不属于交付文件。

### 子目录 `config.json`

`config.json` 是可选文件。文件名匹配不区分大小写；`trim.end=0` 表示使用素材结尾。未写的字段继承界面当前设置，固定输出宽高和 60FPS 不能被覆盖。

```json
{
  "video_order": ["片头.mp4", "主体2.mp4", "片尾.mp4"],
  "first_video": "片头*.mp4",
  "last_video": "*片尾.mp4",
  "output_name": "本目录成片.mp4",
  "trims": {
    "主体2.mp4": {"start": 0.5, "end": 8.2}
  },
  "settings": {
    "transition_type": "wipeleft",
    "transition_frames": 30,
    "canvas_mode": "crop",
    "canvas_position": "top",
    "clip_max_duration_seconds": 10,
    "cover_frames": 30,
    "cover_zoom_percent": 108,
    "cover_title": "项目标题",
    "sharpen_amount": 0.6,
    "denoise_strength": 1.5,
    "normalize_audio": true,
    "loudness_target_lufs": -16,
    "duck_music_under_source": true,
    "subtitle_style": {
      "max_chars_per_line": 16,
      "background_opacity_percent": 45,
      "highlight_words": ["安全", "结构"],
      "highlight_color": "#FFD400"
    }
  }
}
```

`transition_type` 可用 `none`、`fade`、`slideleft`、`wipeleft`、`zoomin`；`canvas_mode` 可用 `blur`、`crop`、`solid`。目录配置的 `output_template` 也可单独覆盖界面命名模板。
仓库中的 [`docs/batch-config.example.json`](docs/batch-config.example.json) 可直接复制到素材子目录后修改。

## 手动单任务流程

1. 将顶部工作模式切换为“手动剪辑”，确认显示“FFmpeg 就绪”。检测失败时在“环境”中选择正确的两个可执行文件。
2. 添加至少一个视频。可以直接拖动时间线片段排序，拖动片段左右手柄裁剪；左侧列表及“上移/下移”和裁剪数字框是等价的精确操作入口。手动模式不会按文件名自动排序。
3. 按需选择封面、Logo 图片、SRT/ASS 字幕和配乐。Logo 保持原始比例；缩放 100% 表示最大 240×240，透明度 100% 表示不透明。
4. 选择帧率模式：
   - **运动补偿**：默认，使用 `minterpolate` 生成真实中间帧，CPU 负载高；GTX 1060 的 NVENC 只加速编码，不加速该滤镜。
   - **快速 60FPS**：使用 `fps=60` 重复/丢弃帧，速度更快，但不是运动补偿。
5. 在右侧“画面”中选择画布、非 AI 增强、转场、封面动画、Logo 轨迹、字幕排版和音频处理。点击时间线顶部刻度或音频轨可移动播放头并自动生成对应静帧；点击片段间的转场标记会直接打开转场设置。需要对齐主体时可在预览画面中拖动位置。
6. 可直接应用内置预设，也可把当前全部剪辑参数另存为自定义预设。预设不包含素材路径和输出目录。
7. 选择导出质量。标准档会根据画面复杂度智能控制体积；如需接近剪映的文件大小，可先选择“稳定 16 Mbps”。20 秒视频连同 192 kbps 音频通常约 40 MB，实际封装开销会造成小幅差异。
8. 查看输出区域的预计时长、帧数、体积、磁盘需求及素材警告，再选择输出目录和文件名并开始。渲染时可查看阶段、百分比和日志，也可取消。
9. 只有 FFprobe 核验通过后进度才会到 100%。同名文件不会被覆盖，而会自动追加 `_001` 等编号；渲染失败后可点击“仅重试失败任务”。

手动模式输出目录包含：

- 最终 MP4；
- 有封面时的独立 `cover.jpg`；
- `*.job_report.json`，记录真实帧数、转场位置、编码器和配置；
- 渲染日志，包含安全的参数列表、返回码和 FFmpeg 错误。

## 时间线规则

所有时间线都以 60FPS 整数帧计算。裁剪和全局时长限制后各片段帧数为 `N1...Nk`，转场帧数为 `T`，封面帧数为 `C`：

```text
主体帧数 = sum(Ni) - (k - 1) * T
总帧数   = 主体帧数 + C
```

无转场时 `T=0`；未选择封面或封面帧数为 0 时 `C=0`。默认仍为 60 帧转场、5 帧封面，因此三段各 600 帧时成片为 `1800 - 120 + 5 = 1685` 帧。程序不会把转场当成额外时长插入。

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
- **Logo 不显示**：确认图片为 JPG、PNG 或 WebP，并检查开始帧、结束帧、透明度与轨迹；默认从第 5 帧开始出现。
- **批量目录被跳过**：确认该直接子目录中至少有 2 个 MP4，并且 PNG、SRT、MP3 各恰好 1 个；文件扩展名不区分大小写。
- **批量编号缺少某一项**：为防止覆盖，已有目标 MP4 会导致对应任务被跳过；下载日志可查看具体路径。
- **成片体积比剪映小**：标准档是内容自适应压缩，静态或低运动画面会很小；选择目标 12/16/20 Mbps 可以更直接地控制体积。理论体积约为“时长秒数 × Mbps ÷ 8”。
- **素材太短无法转场**：每段裁剪后的有效时长至少需要达到所设转场时长的两倍，避免相邻转场重叠；可缩短转场、选择无转场或放宽裁剪范围。
- **画质没有变出真实 2K 细节**：输出画布是 1440×2560，但低分辨率或严重压缩的原片无法通过非 AI 放大恢复不存在的细节；输出区会提示低清素材。
- **监控目录没有立即开始**：为避免读取仍在复制的大文件，新目录必须连续两次轮询得到相同的文件数、总大小和最新修改时间。
- **`config.json` 被跳过**：选择“按 config.json”排序时检查 `video_order` 中的文件名是否存在；JSON 必须是 UTF-8 对象，参数值会按安全范围校正。
- **磁盘不足**：单次编码模式不生成逐片有损中间视频，但最终 `.part.mp4`、字幕和报告仍需要空间；输出区和日志都会显示估计值。
- **取消后没有成片**：这是正确行为；取消或失败会删除 `.part.mp4` 和本任务临时目录，防止把残片当成完成品。
- **超长路径或权限失败**：选择较短且当前用户可写的输出目录；应用不会绕过 Windows 权限。

## 平台说明

开发与自动集成测试可在 Linux 执行，但 Linux 的 PyInstaller 产物不是 Windows EXE。本仓库只把 `scripts\build_windows.bat` 或 Windows GitHub Actions runner 生成的结果视为 Windows 构建；发布前仍应在 Windows 10 x64 上启动 GUI，并用实际素材做一次人工验收。
