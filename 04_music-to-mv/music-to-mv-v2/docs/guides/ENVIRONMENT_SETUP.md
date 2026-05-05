# Music-to-MV v2 环境安装说明

本项目是 Python v2 版本，主入口是：

```bash
python -m src.main
```

建议使用 Python 3.10 或 3.11。Windows、macOS、Linux 都可以运行；Windows 下推荐直接用 PowerShell，也可以用 Git Bash。

## 1. 必装环境

### Python

安装 Python 3.10/3.11，并确认命令可用：

```bash
python --version
pip --version
```

如果 Windows 上 `python` 不可用，可以尝试：

```bash
py --version
```

### Python 依赖

项目依赖写在 `requirements.txt` 中。

最小可运行：

```bash
pip install pyyaml jinja2
```

完整安装：

```bash
pip install -r requirements.txt
```

依赖用途：

| 依赖 | 是否必需 | 用途 |
| --- | --- | --- |
| `PyYAML` | 必需 | 读取 `prompts/registry.yaml` |
| `jinja2` | 推荐 | 增强 Prompt 模板渲染 |
| `Pillow` | 可选 | `--no-api` / dry-run 模式生成占位图 |
| `openai-whisper` | 可选 | 歌词时间轴自动对齐 |
| `demucs` | 可选 | 人声分离，提升歌词对齐准确度 |

音频相关依赖说明：

| 能力 | 依赖 | 类型 | 说明 |
| --- | --- | --- | --- |
| 获取音频/视频时长 | `ffprobe` | 系统工具 | `pipeline.py` 和 `exporter.py` 会调用 |
| 音视频合成与同步 | `ffmpeg` | 系统工具 | 把 `concat.mp4 + song.mp3 + song.srt` 合成 `final.mp4` |
| 字幕烧录 | `ffmpeg` | 系统工具 | 使用 subtitles 滤镜把 SRT 烧进视频 |
| 音频解码/格式处理 | `ffmpeg` | 系统工具 | Whisper/Demucs 处理 MP3/WAV 时也需要稳定解码环境 |
| 自动歌词对齐 | `openai-whisper` | Python 包 | 把音频转写成带时间戳的 segments |
| 人声分离 | `demucs` | Python 包/命令行 | 从 `song.mp3` 分离 `vocals.wav` 后再给 Whisper |
| 基础 SRT fallback | 无额外 Python 包 | 内置逻辑 | 根据 `audio_duration_sec` 均匀分配歌词时间戳 |

## 2. 必装系统工具

### ffmpeg

完整生成视频必须安装 `ffmpeg`，并确保 `ffmpeg` 和 `ffprobe` 在 PATH 中：

```bash
ffmpeg -version
ffprobe -version
```

`ffmpeg` / `ffprobe` 是本项目里音频提取、音频同步、视频合成的核心系统依赖，不是 Python 包。

ffmpeg 用于：

- Ken Burns 图片动画生成
- 视频片段拼接
- 音视频合成
- 字幕烧录
- TikTok / 竖屏版本导出
- 从媒体文件中抽取音轨、转换音频格式（如 MP3/WAV）
- 对齐前的人声分离/转写流程中的音频解码

ffprobe 用于：

- 读取 `song.mp3` / `final.mp4` / `concat.mp4` 的真实时长
- 给歌词 SRT、场景时长、视频片段时长提供同步基准
- 质量报告中统计音频和视频时长

如果没有 ffmpeg/ffprobe，图片和音乐可能能生成，但以下阶段会失败或降级：

- Step ③ 歌词对齐：无法可靠读取音频时长，基础 SRT fallback 可能失败
- Step ⑧ Ken Burns：无法把图片转视频片段
- Step ⑨-⑪：无法拼接、合并音频、烧字幕、导出版本
- 最终报告中的音视频时长可能为 0 或缺失

### Whisper / Demucs 背后的系统依赖

`openai-whisper` 和 `demucs` 是 Python 包，但它们实际处理音频时也依赖可用的音频解码环境。最稳妥的组合是：

```bash
pip install openai-whisper demucs
ffmpeg -version
ffprobe -version
```

安装 `openai-whisper` 通常会同时安装 `torch` 等依赖，体积较大。第一次运行 Whisper 会下载模型，例如 `small/base/tiny`，需要网络和磁盘空间。

## 3. API 配置

复制环境变量模板：

```bash
copy .env.example .env
```

macOS/Linux/Git Bash：

```bash
cp .env.example .env
```

至少需要配置：

```ini
MINIMAX_TOKEN=你的 MiniMax Token
MINIMAX_API_HOST=https://api.minimaxi.com
LLM_MODEL=MiniMax-M2.7
IMAGE_API_PROVIDER=minimax
WORKSPACE_ROOT=~/.openclaw/workspace/mv
```

可选图片 Provider：

```ini
IMAGE_API_PROVIDER=minimax      # 推荐，需 MINIMAX_TOKEN
IMAGE_API_PROVIDER=pollinations # 可测试，通常不需要 Token
IMAGE_API_PROVIDER=alibaba      # 需 ALIBABA_TOKEN
IMAGE_API_PROVIDER=dall-e       # 需 OPENAI_TOKEN
```

## 4. 推荐安装组合

### 只测试流程

```bash
pip install pyyaml jinja2 Pillow
```

运行：

```bash
python -m src.main --theme "春风" --style "国风" --music-style "中国风" --mood "梦幻" --auto --no-api
```

### 完整自动出片

```bash
pip install -r requirements.txt
```

并安装：

- ffmpeg
- MiniMax Token

运行：

```bash
python -m src.main --theme "春风" --style "国风" --music-style "中国风" --mood "梦幻" --auto
```

### 高质量歌词对齐

在完整环境基础上，确认安装：

```bash
pip install openai-whisper demucs
ffmpeg -version
ffprobe -version
```

说明：

- 没装 Whisper/Demucs 时，项目会回退到基础均匀时间戳 SRT。
- 装了 Whisper 后，对齐更准确，但会更慢。
- Demucs 会进一步分离人声，提升对齐质量，但耗时和依赖更重。
- 自动对齐链路是：`song.mp3` → Demucs 分离人声（可选）→ Whisper 转写 → 匹配歌词 → 生成 `audio/song.srt`。
- 音视频同步链路是：`clips/*.mp4` → concat → `song.mp3 + song.srt` → `output/final.mp4`，核心依赖是 `ffmpeg`。

如果电脑有 NVIDIA 显卡并安装了 CUDA 版 PyTorch，可以在 `.env` 中启用显卡自动检测和中等 Whisper 模型：

```ini
# 快速测试流程时可设 false：跳过 Whisper/Demucs，直接生成基础均匀 SRT
ALIGN_ASR_ENABLED=true

# 中等 Whisper 模型：精度高于 small/base，首次运行会下载模型
ALIGN_WHISPER_MODEL=medium
ALIGN_WHISPER_FALLBACK_MODELS=small,base,tiny

# auto 表示检测到 CUDA 就用显卡，否则回退 CPU；也可填 cuda / cuda:0 / cpu
ALIGN_WHISPER_DEVICE=auto

# 中文歌曲建议固定 zh，避免自动识别语言跑偏
ALIGN_WHISPER_LANGUAGE=zh

# Demucs 人声分离也使用同样的设备策略；失败会自动回退原始音频
ALIGN_DEMUCS_ENABLED=true
ALIGN_DEMUCS_DEVICE=auto
ALIGN_DEMUCS_CHECK_TIMEOUT_SEC=10
```

确认 PyTorch 是否能看到显卡：

```bash
python -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu')"
```

如果输出 `False`，说明当前 Python 环境里的 PyTorch 不是 CUDA 版，或 CUDA/驱动不可用。此时 `auto` 会自动回退 CPU。

## 5. 关键运行参数

并发、API 超时、重试次数都可以在 `.env` 中配置。配置优先级是：系统环境变量 > `.env` > 代码默认值。

常用配置：

```ini
# 图片生成并发。MiniMax 建议 1；网络稳定或 provider 支持时可调 2-4
IMAGE_PARALLEL=1

# 通用 API 默认超时和重试
API_MAX_RETRIES=3
API_BASE_DELAY_SEC=2
API_MAX_DELAY_SEC=30
API_TIMEOUT_SEC=60

# 大模型/API 控制台日志
API_LOG_ENABLED=false
API_LOG_RETRIES=true
API_LOG_PROMPT=false
API_LOG_RESPONSE=false
API_LOG_MAX_CHARS=500

# 歌词生成
LYRICS_API_MAX_RETRIES=2
LYRICS_API_BASE_DELAY_SEC=2
LYRICS_API_TIMEOUT_SEC=120

# 歌词/音乐结构
# 可选: adaptive | classic_pop | cinematic | ancient_poem | ballad_story | ambient_mood | rock_build
LYRICS_STRUCTURE_MODE=adaptive
# 自定义结构留空则自动选择；填写后优先使用
LYRICS_STRUCTURE=

# 音乐生成通常最慢，可以适当调大
MUSIC_API_MAX_RETRIES=2
MUSIC_API_BASE_DELAY_SEC=5
MUSIC_API_TIMEOUT_SEC=180

# 图片生成和图片下载
IMAGE_API_MAX_RETRIES=3
IMAGE_API_BASE_DELAY_SEC=2
IMAGE_API_TIMEOUT_SEC=60
SCENE_DESC_API_MAX_RETRIES=3
SCENE_DESC_API_BASE_DELAY_SEC=2
SCENE_DESC_API_TIMEOUT_SEC=120
VARIANT_API_MAX_RETRIES=3
VARIANT_API_BASE_DELAY_SEC=2
VARIANT_API_TIMEOUT_SEC=120
DOWNLOAD_MAX_RETRIES=3
DOWNLOAD_BASE_DELAY_SEC=2
DOWNLOAD_TIMEOUT_SEC=60

# Chat completion 输出长度。场景描述建议小批次，减少超时和 JSON 失败
SCENE_DESC_MAX_TOKENS=4096
SCENE_DESC_BATCH_SIZE=2
VARIANT_DESC_MAX_TOKENS=4096
VARIANT_DESC_BATCH_SIZE=4
VISUAL_BIBLE_MAX_TOKENS=2048
CREATIVE_BRIEF_MAX_TOKENS=2048

# 本地处理超时
ALIGN_TIMEOUT_SEC=600
ALIGN_ASR_ENABLED=true
ALIGN_WHISPER_MODEL=medium
ALIGN_WHISPER_FALLBACK_MODELS=small,base,tiny
ALIGN_WHISPER_DEVICE=auto
ALIGN_WHISPER_LANGUAGE=zh
ALIGN_DEMUCS_ENABLED=true
ALIGN_DEMUCS_DEVICE=auto
ALIGN_DEMUCS_CHECK_TIMEOUT_SEC=10
SCRIPT_TIMEOUT_SEC=600
SCENE_ANALYSIS_TIMEOUT_SEC=180
FFMPEG_TIMEOUT_SEC=600
FFPROBE_TIMEOUT_SEC=10
KB_TIMEOUT_BUFFER_SEC=30

# Ken Burns 镜头运动
KB_ZOOM_START=1.0
KB_ZOOM_END=1.12
KB_PAN_X=30
KB_PAN_Y=18
KB_SUPERSAMPLE_SCALE=2

# 图片自动质检
# 是否在 Step⑤-⑦ 批量生图后自动检查图片质量，并写入 metadata/image_quality_report.json
IMAGE_QUALITY_ENABLED=true
# 图片文件最小字节数。小于该值通常表示下载失败、接口返回错误页、空文件或损坏文件
IMAGE_QUALITY_MIN_FILE_SIZE=1000
# 图片最小宽度。小于该值判定为 resolution_too_small
IMAGE_QUALITY_MIN_WIDTH=512
# 图片最小高度。小于该值判定为 resolution_too_small
IMAGE_QUALITY_MIN_HEIGHT=512
# 灰度亮度标准差下限。越小说明越接近纯色/低信息量；小于该值判定为 low_visual_variance
IMAGE_QUALITY_MIN_STDDEV=6
```

调参建议：

- 图片经常 `read operation timed out`：先保持 `IMAGE_PARALLEL=1`，再把 `IMAGE_API_TIMEOUT_SEC` 和 `DOWNLOAD_TIMEOUT_SEC` 调大。
- 音乐生成经常超时：把 `MUSIC_API_TIMEOUT_SEC` 调到 `240` 或 `300`。
- 场景描述/视觉总纲日志里出现 `finish_reason=length`，并且随后 `解析失败`：把 `SCENE_DESC_MAX_TOKENS`、`VARIANT_DESC_MAX_TOKENS` 或 `VISUAL_BIBLE_MAX_TOKENS` 调大。
- ffmpeg 处理长歌超时：把 `FFMPEG_TIMEOUT_SEC` 调到 `900` 或 `1200`。
- Whisper/Demucs 对齐长音频超时：把 `ALIGN_TIMEOUT_SEC` 调大。
- 最终视频图片抖动明显：降低 `KB_ZOOM_END`、`KB_PAN_X`、`KB_PAN_Y`；保持 `KB_SUPERSAMPLE_SCALE=2` 或调到 `3`。
- 歌词结构太固定：保持 `LYRICS_STRUCTURE_MODE=adaptive`，或改成 `ancient_poem` / `cinematic` / `ambient_mood` 等；需要完全指定时填写 `LYRICS_STRUCTURE`。
- 生成图出现黑图、白图、纯色占位或尺寸异常：查看 `metadata/image_quality_report.json`，或用 `python tools/check_image_quality.py --project <项目目录>` 复查。

图片质检参数说明：

- `IMAGE_QUALITY_ENABLED=true`：开启自动质检。关闭后不会生成 `metadata/image_quality_report.json`。
- `IMAGE_QUALITY_MIN_FILE_SIZE=1000`：文件大小下限，单位 byte。低于该值通常是空文件、错误页或下载失败。
- `IMAGE_QUALITY_MIN_WIDTH=512`：宽度下限，低于该值会标记 `resolution_too_small`。
- `IMAGE_QUALITY_MIN_HEIGHT=512`：高度下限，低于该值会标记 `resolution_too_small`。
- `IMAGE_QUALITY_MIN_STDDEV=6`：灰度亮度标准差下限。低于该值说明画面接近纯色或信息量过低，会标记 `low_visual_variance`。

API 日志说明：

- `API_LOG_ENABLED=true`：打印每次大模型/API 请求的 `key/model/attempt/timeout`，以及成功或失败摘要。
- `API_LOG_RETRIES=true`：打印失败后的重试等待信息。默认开启，保持原来的行为。
- `API_LOG_PROMPT=true`：额外打印 prompt 预览。
- `API_LOG_RESPONSE=true`：额外打印 response 预览。
- `API_LOG_MAX_CHARS=500`：控制 prompt/response 预览最大字符数。

建议日常只开：

```ini
API_LOG_ENABLED=true
API_LOG_RETRIES=true
API_LOG_PROMPT=false
API_LOG_RESPONSE=false
```

需要排查 prompt 或模型返回内容时，再临时打开：

```ini
API_LOG_PROMPT=true
API_LOG_RESPONSE=true
API_LOG_MAX_CHARS=1000
```

## 6. 快速检查

```bash
python -c "import yaml, jinja2; print('python deps ok')"
ffmpeg -version
ffprobe -version
python -m src.main --list
```

看到项目列表或空列表，即表示基础 Python 环境和入口正常。
