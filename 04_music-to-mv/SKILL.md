---
name: music-to-mv
description: "Turn a theme into a complete 2-3 min music video: AI lyrics + music (MiniMax) → Vocal separation + Whisper + Two-pass alignment → Image-01 visuals with Ken Burns → TikTok/YouTube export. Triggers: make an MV, 生成MV, 做个MV, 制作MV, 帮我做MV, 做音乐视频, 制作音乐视频, create music video, produce music video, 音乐视频, 音乐短片."
---

## 🎬 用户请求生成 MV 时的交互规范

当用户说「生成mv」或类似触发词时，**必须**按以下方式交互：

### 第一步：展示完整选项菜单

直接向用户展示以下所有可选参数（每个选项都要有一句话说明）：

---
**请选择 MV 的主题和风格：**

**① theme（必填）** — 说一个主题，比如：童年、星空、战争、爱情、梦想、冒险 等任意词

**② style（画面风格）** — 可选，默认动漫风：
| 风格 | 说明 |
|------|------|
| 动漫风 | 日系动漫画风，大眼睛，赛璐璐上色（默认） |
| 国风 | 传统水墨风格，宣纸质感，中国传统配色 |
| 写实摄影风 | 真实摄影风格，自然光，浅景深 |
| 水彩插画风 | 手绘水彩质感，柔和笔触，马卡龙色调 |
| 像素游戏风 | 像素艺术风格，8-bit 复古游戏感 |
| 电影感写实风 | 电影调色，电影颗粒感，叙事感强 |
| 极简几何风 | 几何图形，简洁线条，撞色设计 |
| 浮世绘和风 | 日本传统浮世绘，平面色块，粗黑轮廓线 |
| 复古胶片风 | 复古胶片摄影，暖色调，漏光颗粒感 |
| 漫画美式涂鸦风 | 美式漫画风格，粗黑线框，半色调网点 |
| 蒸汽朋克风 | 维多利亚机械风，黄铜齿轮，蒸汽朋克美学 |
| 赛博朋克风 | 霓虹未来风，霓虹灯光，赛博朋克美学 |

**③ music_style（音乐风格）** — 可选，默认流行：
| 风格 | 说明 |
|------|------|
| 流行 | 主流流行歌曲节奏（默认） |
| 说唱 | Rap 说唱节奏 |
| 民谣 | 原声吉他为主，民谣叙事 |
| 电子 | 电子合成音色，科技感 |
| 摇滚 | 吉他摇滚风格，有力量感 |
| 古典 | 古典管弦乐，宏大感 |
| 爵士 | 即兴爵士氛围 |
| HipHop | 嘻哈节奏，强律动 |
| R&B | 节奏布鲁斯，灵魂乐感 |
| 中国风 | 古风配器，中国传统乐器 |
| 新世纪NewAge | 空灵氛围音乐 |
| EDM舞曲 | 电子舞曲，强节拍 |
| 乡村Country | 乡村吉他，民谣叙事 |
| 朋克Punk | 朋克摇滚，躁郁青春 |

**④ mood（情绪基调）** — 可选，默认温柔：
| 情绪 | 说明 |
|------|------|
| 欢快 | 快乐活泼，跳跃感 |
| 温柔 | 温馨柔和，柔软感（默认） |
| 史诗 | 宏大叙事，史诗感 |
| 忧伤 | 忧郁抒情，心碎感 |
| 热血 | 热血沸腾，战斗向 |
| 梦幻 | 梦幻飘渺，童话感 |
| 浪漫 | 浪漫甜蜜，爱情向 |
| 怀旧 | 怀旧复古，回忆感 |
| 希望 | 积极向上，励志感 |
| 暗黑 | 暗黑阴森，压抑感 |
| 宁静 | 宁静治愈，放松感 |
| 慵懒 | 放松悠闲，懒散感 |

---

### 第二步：简单引导

在展示菜单后，加上：

> **只需要告诉我 theme 是什么，其他都可以用默认或随便选。**
> 
> 例如：「主题：童年，风格默认动漫风，音乐说唱，情绪怀旧」

> **关于对齐方式：**Step② 完成后会专门询问你选择哪种对齐方式（A/B/C），届时请回复选项字母即可。

### 注意事项
- **不要**在用户未选择时就猜测 theme 并直接开始执行
- **不要**只列 theme 一个选项就停下来
- **不要**说「需要什么参数」这种生硬的技术语言
- **只有**用户明确说「直接开始」或「用默认」时，才使用默认值（动漫风 + 流行 + 温柔）
- pipeline 后续逻辑不变，仍按 Step ①→②→③... 执行

---

### 第三步：Step③ 对齐方式（强制询问）

歌词 + 音乐生成完成后，**必须暂停**，向用户展示对齐方式选项：

| 选项 | 说明 | 适用场景 |
|------|------|----------|
| **A. Demucs 自动（推荐）** | 人声分离 + Whisper 对齐，精度最高，自动处理 | 大多数情况 |
| **B. 手动 SRT** | 自己提供 .srt 文件（需提前准备好歌词时间轴） | 有专业字幕基础 |

**强制规则：**
- 暂停后**必须展示**两个选项，等待用户明确选择
- 只有用户说「随便」「都行」「继续」「A」等明确指示时，才能用默认（推荐 A）
- **禁止**在用户未表态前自动选择对齐模式
- 若用户选择了 B（手动 SRT），需要继续询问 `.srt` 文件路径

**暂停点示例（必须这样说）：**
> 🎵 歌曲《xxx》已生成完毕（时长 xxx 秒）
> 📝 歌词已同步。
>
> **请选择歌词对齐方式：**
> - A. Demucs 自动（推荐）— 人声分离 + AI 对齐，精度最高
> - B. 手动 SRT — 我有现成的字幕文件
>
> 请回复：A / B（或直接告诉我路径）

---

# Music-to-MV Pipeline

## 📑 文档导航

> 829 行长文档按用途分组。Ctrl+F 任一节标题即可定位。
> 顶部「🎬 交互规范」是 LLM 触发响应模板，下面是技术参考。

**🚀 入门 / 触发**
- **Prerequisites** — 依赖清单（Token / ffmpeg / Whisper / Demucs）
- **第一次配置** — `.env` 模板 + 环境变量注入原理
- **Usage (Agent)** — Agent 接到「生成MV」时的交互流程（含强制暂停点）
- **Resume Failed Pipeline** — 失败项目查找 + 分步重跑命令

**🎯 总览**
- **What It Does** — 一句话产出说明
- **Pipeline Overview** — 11 步 ASCII 流程图
- **Skill Rules** — Input / Output / 目录结构 / 参数全集

**🛠️ 脚本与子文档**
- **Scripts Reference** — 11 个脚本的 I/O 契约
- **References** — 子流程深度文档（lyrics / music / alignment / video / merge）
- **Pipeline Internals** — Step ③.5 场景分析（自动，不暂停）
- **Default Parameters** — 视频/字幕/对齐默认值

**🔍 算法与状态**
- **Alignment Algorithm** — 两遍贪心 + 后处理修正流程图
- **Unified Status Tracking** — `status.json` + `interrupt.json` Schema
- **Pipeline Log Format** — `steps.log` 样例

**🛟 健壮性 / 维护**
- **Error Handling** — 重试策略与降级方案
- **Idempotency** — 各步覆盖语义
- **已知问题与局限** — 字级对齐 / 重复歌词段 / OOM 等
- **后期可优化方向** — Roadmap

---

## Prerequisites

| 依赖 | 安装方式 | 说明 |
|------|---------|------|
| `MINIMAX_TOKEN` | `.env` 文件或 `export MINIMAX_TOKEN=<token>` → [获取地址](https://www.minimaxi.com/user-center/basic-information/interface-key) | **核心 Token**：Image-01 + Music-2.6 + MiniMax-M2.7（场景描述） |
| `DEEPSEEK_TOKEN` | `.env` 文件（**遗留，可留空**） | 历史遗留：当前代码已切到 MiniMax-M2.7，preflight.sh 不再校验，保留变量仅为向后兼容 |
| `OPENAI_TOKEN` | `.env` 文件（可选） | 备选图片 API（DALL-E 3）|
| `ffmpeg` + `ffprobe` | `sudo apt install ffmpeg` / `brew install ffmpeg` | 视频处理 |
| `whisper` | `pip install openai-whisper` | 本地语音识别（3分钟音频约30秒，small模型） |
| `python3` | 系统自带 | json / re / urllib 模块 |
| `demucs` (推荐) | `pip install demucs --break-system-packages` | 人声分离（大幅提升对齐质量，可选） |
| `torchaudio` (配套) | `pip install torchaudio --break-system-packages --index-url https://download.pytorch.org/whl/cpu` | Demucs 依赖（CPU版） |

> **内存提示：** Whisper small 需要 ~1.5GB 内存。若 OOM，脚本会自动 fallback 到 base 模型（更快但精度略低）。Demucs 需要 ~2GB 内存。

启动前运行 `./scripts/preflight.sh` 验证全部依赖。

---

## 第一次配置

首次使用 Skill 前，需要配置 API Token（否则图片和音乐生成会失败）。

**步骤：**

```bash
# 1. 进入 Skill 目录
cd ~/.openclaw/skills/music-to-mv/music-to-mv

# 2. 复制配置模板
cp .env.example .env

# 3. 编辑 .env，填入你的 Token
nano .env   # 或任意编辑器
```

`.env` 模板内容：
```bash
# MiniMax Token（图片 + 音乐 + 场景描述 LLM，核心 Token）
export MINIMAX_TOKEN='your_token_here'

# DeepSeek Token（遗留校验，可留空字符串。当前 LLM 已切到 MiniMax-M2.7）
export DEEPSEEK_TOKEN=''

# OpenAI Token（可选，DALL-E 3 备选图片 API）
export OPENAI_TOKEN=''

# 阿里云 Token（可选，阿里云通义万通备选图片 API）
export ALIBABA_TOKEN=''

# 图片 API 选择：minimax | alibaba | pollinations | dall-e
export IMAGE_API_PROVIDER='minimax'
```

**获取 Token：**
- MiniMax: https://www.minimaxi.com/user-center/basic-information/interface-key
- OpenAI: https://platform.openai.com/api-keys
- 阿里云: https://dashscope.console.aliyun.com/api-key

**切换图片 API：**

| Provider | Token | 说明 |
|----------|-------|------|
| `minimax`（默认）| 需要 `MINIMAX_TOKEN` | 质量好，有用量限制 |
| `alibaba` | 需要 `ALIBABA_TOKEN` | 阿里云通义万通（wanx2.1），质量稳定 |
| `pollinations` | 无需 token | 免费 flux 模型，立即可用 |
| `dall-e` | 需要 `OPENAI_TOKEN` | 质量最高，按量付费 |

```bash
# 切换到免费 Pollinations（额度用完时）
echo "IMAGE_API_PROVIDER=pollinations" >> .env

# 切回 MiniMax
echo "IMAGE_API_PROVIDER=minimax" >> .env
```

### 环境变量注入原理

代码不直接读取 `.env` 文件，而是通过 Shell 环境变量获取 Token 和 API 配置。

**注入流程：**
```
.env 文件
    ↓
source config.sh  ← 每个脚本运行时自动执行
    ↓
Shell 环境变量（os.environ）
    ↓
Python / Bash 代码（os.environ.get / $VAR）
```

**具体机制：**

脚本开头会自动执行 `source scripts/config.sh`，config.sh 读取 `.env` 文件并将内容导出为 Shell 环境变量。此后 Python 脚本通过 `os.environ.get("MINIMAX_TOKEN")` 即可获取实际值。

**三种配置方式（任选其一）：**

| 方式 | 操作 | 说明 |
|------|------|------|
| `.env` 文件 | 编辑 `scripts/.env` | **推荐**，Token 集中管理 |
| 手动 export | 终端执行 `export MINIMAX_TOKEN=xxx` | 仅当前会话生效 |
| Python dotenv | 代码中用 `load_dotenv()` | 无需 shell，依赖第三方库 |

**config.sh 不需要手动执行**——它会被 `produce_mv.sh`、`generate_scene_imgs.py` 等脚本自动 source。

---

## What It Does

One command → full 2-3 minute music video with:
- AI-generated song (MiniMax Music-2.6)
- Lyric-synchronized subtitles (Demucs vocal separation → Whisper → Two-pass alignment → SRT)
- Consistent AI character visuals (MiniMax Image-01, 10-22 dynamic scenes)
- Ken Burns dynamic effects (ffmpeg)
- TikTok/YouTube-ready exports (16:9 + 9:16)

## Pipeline Overview

```
Step ① Generate Lyrics     → audio/lyrics.txt
Step ② Generate Music      → audio/song.mp3
Step ③ Align Lyrics        → audio/song.srt
        ├─ ③-a 人声分离（Demucs，可选）
        ├─ ③-b Whisper 转写（人声轨）
        ├─ ③-c 两遍对齐算法（阈值0.25/0.20）
        └─ ③-d 后处理修正（首行补全 + 跳行插值）
Step ③.5 Analyze Scenes    → metadata/{scenes,variants,base_char}.json
        └─ MiniMax-M2.7 自动生成场景描述 + 变体标记（auto，不暂停）
Step ④ Base Character      → images/base_character.png
Step ⑤-⑦ Scene Images     → images/seg{N}_{label}.png (×N，动态 10-22 张)
Step ⑧ Ken Burns           → clips/seg{N}_{label}_kb.mp4 (×N)
Step ⑨ Concatenate          → temp/video_raw.mp4
Step ⑩ Merge + Subtitles   → output/final.mp4
Step ⑪ Export               → output/tiktok.mp4 + vertical.mp4
```

**各步骤对应参考文档（遇到细节问题或想调试某一步时，查阅对应的 reference）：**

| Step | 参考文档 | 内容 |
|------|---------|------|
| ① 歌词 | `references/lyrics-workflow.md` | API 参数、响应解析、错误码表 |
| ② 音乐 | `references/music-workflow.md` | API prompt 构造、同步响应处理 |
| ③ 对齐 | `references/alignment-workflow.md` | Demucs + Whisper + 两遍对齐算法 + Troubleshooting |
| ③.5 场景分析 | — | 已在 SKILL.md Pipeline Internals 中完整覆盖 |
| ④-⑧ 画面制作 | `references/video-workflow.md` | 角色图 + 场景图 + Ken Burns 参数 |
| ⑨-⑪ 合成导出 | `references/merge-workflow.md` | 拼接、合并、字幕、TikTok 导出 |

## Skill Rules

### Input

| Field | 类型 | 默认值 | Description |
|-------|------|--------|-------------|
| `theme` | **必填** | — | 主题描述（如："春天"、"童年回忆"） |
| `style` | 可选 | 动漫风 | 画面风格（见下方详细说明） |
| `music_style` | 可选 | 流行 | 音乐风格（见下方详细说明） |
| `mood` | 可选 | 温柔 | 情绪基调（见下方详细说明） |
| `language` | 可选 | 中文 | 歌词语言：中文 / 英文 / 双语 |
| `reference` | 可选 | — | 角色描述（如"7岁中国女孩"）或风格参考（支持中英文） |
| `notifications` | 可选 | false | Telegram 完成通知开关 |

> **只有 `theme` 是真正必填项**。其余参数可从用户消息上下文推断，推断不出时才询问。
> **角色自定义**：`reference` 字段支持描述角色外观，如"7岁中国女孩"将覆盖默认角色描述。

### 画面风格选项（style）

| 风格 | 说明 |
|------|------|
| 动漫风 | 日系动漫画风，赛璐璐上色，大眼睛（默认） |
| 国风 | 传统水墨风格，宣纸质感，中国传统配色 |
| 写实摄影风 | 真实摄影风格，自然光，浅景深 |
| 水彩插画风 | 手绘水彩质感，柔和笔触，马卡龙色调 |
| 像素游戏风 | 像素艺术风格，8-bit 复古游戏感 |
| 电影感写实风 | 电影调色，电影颗粒感，叙事感强 |
| 极简几何风 | 几何图形，简洁线条，撞色设计 |
| 浮世绘和风 | 日本传统浮世绘，平面色块，粗黑轮廓线 |
| 复古胶片风 | 复古胶片摄影，暖色调，漏光颗粒感 |
| 漫画美式涂鸦风 | 美式漫画风格，粗黑线框，半色调网点 |
| 蒸汽朋克风 | 维多利亚机械风，黄铜齿轮，蒸汽朋克美学 |
| 赛博朋克风 | 霓虹未来风，霓虹灯光，赛博朋克美学 |

### 音乐风格选项（music_style）

| 风格 | 说明 |
|------|------|
| 流行 | Pop，主流流行风格（默认） |
| 电子 | Electronic，电子合成音色 |
| 民谣 | Folk，原声吉他为主 |
| 说唱 | Rap/Hip-Hop，说唱节奏 |
| 古典 | Classical，古典管弦乐 |
| 摇滚 | Rock，吉他摇滚风格 |
| 爵士 | Jazz，即兴爵士氛围 |
| HipHop | 嘻哈节奏，强律动 |
| R&B | 节奏布鲁斯，灵魂乐感 |
| 拉丁BossaNova | 热带风情，巴西节奏 |
| 乡村Country | 乡村吉他，民谣叙事 |
| 朋克Punk | 朋克摇滚，躁郁青春 |
| EDM舞曲 | 电子舞曲，强节拍 |
| 中国风 | 古风配器，中国传统乐器 |
| 新世纪NewAge | 空灵氛围音乐 |
| 民歌 | 民族歌曲，地域特色 |
| 蓝调Blues | 蓝调音乐，情感充沛 |

### 情绪基调选项（mood）

| 情绪 | 说明 |
|------|------|
| 欢快 | 快乐活泼，跳跃感 |
| 温柔 | 温馨柔和，柔软感 |
| 史诗 | 宏大叙事，史诗感 |
| 忧伤 | 忧郁抒情，心碎感 |
| 慵懒 | 放松悠闲，懒散感 |
| 梦幻 | 梦幻飘渺，童话感 |
| 浪漫 | 浪漫甜蜜，爱情向 |
| 热血 | 热血沸腾，战斗向 |
| 宁静 | 宁静治愈，放松感 |
| 怀旧 | 怀旧复古，回忆感 |
| 叛逆 | 叛逆不羁，反骨感 |
| 希望 | 积极向上，励志感 |
| 孤独 | 孤独沉思，寂寞感 |
| 悬疑 | 神秘紧张，悬疑感 |
| 暗黑 | 暗黑阴森，压抑感 |
| 魔幻 | 魔幻魔法，奇幻感 |
| 清新 | 清新自然，清爽感 |

### Output
| File | Description |
|------|-------------|
| `output/final.mp4` | Main MV (1280×720, soft subtitles) |
| `output/tiktok.mp4` | 16:9 with hard-burn Chinese subtitles |
| `output/vertical.mp4` | 9:16 vertical (TikTok mobile) |

### Directory Structure
Each execution creates a unique project directory:

```
~/.openclaw/workspace/mv/
└── {theme}_{YYYYMMDD_HHmmss}/
    ├── metadata/
    │   ├── info.json          # Project config, tags, completion status
    │   ├── steps.log          # Step execution log
    │   ├── scenes.json        # (optional) Pre-generated scene descriptions
    │   └── status.json        # Real-time pipeline status
    ├── audio/                  # Steps ①-③
    │   ├── lyrics.txt
    │   ├── song.mp3
    │   └── song.srt
    ├── images/                # Steps ④-⑦
    │   ├── base_character.png
    │   └── seg{N}_{label}.png
    ├── clips/                  # Step ⑧
    │   └── seg{N}_{label}_kb.mp4
    ├── temp/                   # Intermediate (auto-cleared)
    │   ├── song.json           # Whisper output
    │   ├── demucs_out/         # (if used) Demucs separation output
    │   └── video_raw.mp4
    └── output/                 # Final deliverables
        ├── final.mp4
        ├── tiktok.mp4
        └── vertical.mp4
```

### Step Execution Rules
1. Steps run sequentially — no skipping
2. Each step checks that required inputs exist before running
3. Any failure → pipeline halts, all generated files preserved
4. Completed steps are idempotent — re-running overwrites existing files
5. temp/ is cleared automatically after Step ⑩ finishes

### 图片 API 配置

所有脚本通过 `source scripts/config.sh` 统一读取配置，支持切换不同的图片 provider。详见上方 **第一次配置** 一节。

**config.sh 读取优先级：**
1. 当前 shell 已设置的环境变量（最高）
2. `.env` 文件（若存在）
3. 默认值（hardcoded fallback）

**当前支持的 Provider：**

| Provider | Token | Endpoint | 说明 |
|----------|-------|----------|------|
| `minimax`（默认）| `MINIMAX_TOKEN` | `/v1/image_generation` | MiniMax Image-01，质量好，有用量限制 |
| `alibaba` | `ALIBABA_TOKEN` | `dashscope.../text2image/image-synthesis` | 阿里云通义万通（wanx2.1），质量稳定 |
| `pollinations` | 无需 | `image.pollinations.ai` | 免费 flux/sdxl，立即可用 |
| `dall-e` | `OPENAI_TOKEN` | `/v1/images/generations` | DALL-E 3，质量最高，按量付费 |

### API Endpoints Used
| API | Endpoint | Provider |
|-----|----------|----------|
| lyrics_generation | `POST /v1/lyrics_generation` | MiniMax |
| music_generation | `POST /v1/music_generation` | MiniMax |
| image_generation | `IMAGE_API_URL`（可配置）| 可切换 |
| scene_desc_generation | MiniMax `/v1/chat/completions` | MiniMax-M2.7（默认，可由 `LLM_MODEL` 覆盖） |
| Whisper (local) | CLI | — |
| Demucs (local, optional) | CLI | — |

### Network Notes
- `api.minimaxi.com` requires `--noproxy '*'` to avoid SSL_ERROR_SYSCALL
- Whisper runs locally (`small` model default, fallback to `base` on OOM)
- Demucs runs locally (`htdemucs` model, CPU)
- All `--noproxy` flags are mandatory for MiniMax API calls

## Scripts Reference

| Script | Covers | Input | Output | Reference |
|--------|--------|-------|--------|-----------|
| `create_mv.sh` | **统一入口**（分阶段执行） | `--theme --style --music-style --mood` 等 | 见各子步骤 | — |
| `config.sh` | API 配置统一读取 | `.env` 文件或 shell 环境变量 | 设置 `IMAGE_API_URL`, `IMAGE_MODEL` 等 | — |
| `init_project.sh` | Directory setup + preflight | theme name | project path | — |
| `status_funcs.sh` | Shared utilities | — | status.json / interrupt.json | — |
| `generate_lyrics.sh` | Step ① | project_dir（theme 从 info.json 读取） | audio/lyrics.txt | `references/lyrics-workflow.md` |
| `generate_music.sh` | Step ② | project_dir | audio/song.mp3 | `references/music-workflow.md` |
| `align_lyrics.sh` | Step ③ | project_dir | audio/song.srt | `references/alignment-workflow.md` |
| `produce_mv.sh` | Steps ④-⑧ | project_dir | images/*.png, clips/*_kb.mp4 | `references/video-workflow.md` |
| `merge_and_export.sh` | Steps ⑨-⑪ | project_dir | output/*.mp4 | `references/merge-workflow.md` |
| `assemble_mv.sh` | Video concat | project_dir + KB clips | output/assembled.mp4 | — |
| `burn_subtitle.sh` | Hard subtitles | project_dir + video + SRT | output/burned.mp4 | — |
| `generate_scene_imgs.py` | 并行场景图+变体图生成 | scenes.json + base_char.json | images/*.png + variants.json | `references/video-workflow.md` |
| `generate_kb_video.py` | Ken Burns视频生成（支持变体crossfade拼接） | images/*.png + variants.json | clips/*_kb.mp4 | `references/video-workflow.md` |

## References

> reference 是**按需查阅的深度参考**，不是每次执行的必读项。
> 正常跑流程只看 SKILL.md 就够了；当某一步出错、或需要调参、或想理解细节时，才去读对应的 reference。

| Reference | Covers |
|-----------|--------|
| `references/lyrics-workflow.md` | Step ① — API params, response fields, prompt design |
| `references/music-workflow.md` | Step ② — API params, prompt construction, sync behavior |
| `references/alignment-workflow.md` | Step ③ — Demucs + Whisper + Two-pass alignment + post-processing |
| `references/video-workflow.md` | Steps ④-⑧ — Base character, scene images, Ken Burns |
| `references/merge-workflow.md` | Steps ⑨-⑪ — Concat + merge audio/subtitles + TikTok hard-burn + 9:16 export |
| `references/export-workflow.md` | ⚠️ **已废弃**（保留作为 ffmpeg 字幕参数与历史命令参考，不再代表当前流程） |

## Usage (Agent)

### ⚠️ 强制暂停点（Agent 必须遵守）

| 暂停时机 | 必须询问 | 允许的回复 |
|---------|---------|-----------|
| Step ①② 完成后 | "是否继续后续步骤？" | 继续 / 暂停查看歌词 |
| Step ③ 开始前 | "对齐方式 A/B/C？" | A 自动 / B 跳过 / C 手动 SRT |

> 其余步骤（④-⑧ 生图+KB、⑨-⑪ 合并+导出）**自动串行执行**，无需暂停。
> 暂停由 `info.json` 中的 `step2_pending_approval: true` 实现**代码级强制**，未确认时 `--phase align` 会被阻塞。

### 交互流程

用户说「生成MV」后，按以下顺序进行：

---

**第1步：展示完整选项菜单（必须）**

按照文档顶部「🎬 用户请求生成 MV 时的交互规范」一节中的菜单原样展示给用户（theme + style + music_style + mood）。

> 完整可选项清单（包含小众风格/情绪）参见下方「Skill Rules → 画面风格选项 / 音乐风格选项 / 情绪基调选项」。
> 顶部菜单为高频"精选版"（更友好），Skill Rules 为完整"全集"（用户问"还有别的吗"时再展开）。

---

**第2步：确认后执行歌词 + 音乐生成**

用户确认参数后，一键执行：

```bash
./scripts/create_mv.sh --theme "$THEME" --style "$STYLE" --music-style "$MUSIC_STYLE" --mood "$MOOD" --language "$LANGUAGE"
```

`create_mv.sh` 内部会：
1. 调用 `init_project.sh` 创建项目目录
2. 调用 `generate_lyrics.sh`（从 `info.json` 自动读 theme，无需传第二遍）
3. 调用 `generate_music.sh`
4. 写入 `info.json` 暂停标记 `pause_step2: true`

**完成后必须暂停，主动告知用户：**
> ✅ 歌词已生成：「XXX」
> ✅ 音乐已生成：X.XMB，XXX秒
>
> **是否继续后续步骤？**
> - 回复「继续」：进入 Step③ 对齐
> - 回复「暂停」：先查看歌词/听音乐，稍后再说

> ⚠️ `create_mv.sh` 在 `info.json` 里写入了 `step2_pending_approval: true`。
> 在用户确认前，`--phase align` 阶段会被阻塞。这是 **代码级的强制暂停**。

---

**第3步：询问对齐方式（必须由用户选择！禁止自动执行）**

> Agent:
> ```
> 现在进入 Step③ 对齐（约5-10分钟，是最慢的一步）
> 请选择方式：
>
>   A. 自动跑（推荐）
>         Demucs人声分离 + Whisper转写
>         需要等 5-10 分钟
>
>   B. 跳过，已有 SRT 文件
>         已有 audio/song.srt 或 temp/song.json 时选这个，秒完成
>
>   C. 手动提供 SRT 文件
>         用其他工具生成好了，直接使用
>
> 回复：A / B / C
> ```

**严禁**在用户未回复 A/B/C 之前自动运行 `--phase align`。

用户选择后，设置 `info.json` 标记：
```bash
python3 -c "
import json
path = '${PROJECT_DIR}/metadata/info.json'
with open(path) as f:
    d = json.load(f)
d['step2_approved'] = True
d['align_mode'] = 'AUTO'    # ← 根据用户选择：auto / manual
d['manual_srt_file'] = ''   # ← manual 模式时填入 SRT 路径
with open(path, 'w') as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
"
```

---

**第4步：用户选择后，执行对齐 + 后续步骤**

```bash
# 对齐（用户选的模式，从 info.json 读取）
./scripts/create_mv.sh "$PROJECT_DIR" --phase align

# 生图+Ken Burns+合成导出（自动链式执行）
./scripts/create_mv.sh "$PROJECT_DIR" --phase produce
./scripts/create_mv.sh "$PROJECT_DIR" --phase export

# 或用 --auto 全自动（测试用）：
# ./scripts/create_mv.sh --theme "$THEME" --style "$STYLE" --auto --align-mode auto
```

`--phase produce` 和 `--phase export` 会自动串行执行（无暂停点）。

---

**第5步：执行中分步报告**

每步完成时报结果：
> ① 歌词+音乐 ✅ 完成
> ② 对齐 ✅ 完成（X分钟）/ ⏭️ 跳过
> ③ 场景分析 ✅ 完成
> ④ 角色图 ✅ 完成
> ⑤ 场景图 🔄 进行中（X/XX张）...
> ⑥ KB视频 ⏳ 待开始
> ⑦ 合成导出 ⏳ 待开始

中途失败时告知原因 + 给出「重试」/「跳过」/「终止」选项。

### 完成通知

Pipeline 结束后告知用户：

```
🎬 MV 制作完成！
📹 主视频:  {PROJECT_DIR}/output/final.mp4
📱 TikTok:  {PROJECT_DIR}/output/tiktok.mp4
📱 竖版:    {PROJECT_DIR}/output/vertical.mp4
⏱️ 总耗时: ~X 分钟
🤖 LLM 日志: {PROJECT_DIR}/metadata/llm_calls/  （共 N 条调用）
📊 日志报告: {PROJECT_DIR}/output/llm_report.html
```

> **LLM 日志说明：** 每次 LLM 调用（场景描述 / 变体描述 / 图片 prompt / 歌词生成 / 音乐生成）都会记录完整 prompt + response 到 `metadata/llm_calls/*.jsonl`，并在 `output/llm_report.html` 汇总展示。

---

## Pipeline Internals

### Step ③.5 — 场景分析（自动，不暂停）

`produce_mv.sh` 在调用 `analyze_srt.py` 前会自动执行此步：

```bash
python3 ./scripts/analyze_srt.py "$PROJECT_DIR"
```

| 产出 | 内容 |
|------|------|
| `metadata/scenes.json` | 10-22 个场景：`start/end/duration` + `label`（中文）+ `desc`（英文），含 `is_repeated` 标记 |
| `metadata/variants.json` | 变体图配置：哪些场景需要多张图 |
| `metadata/base_char.json` | 角色描述（按 style/mood/theme 自动生成） |

**模型：** MiniMax-M2.7（默认，可由 `LLM_MODEL` 覆盖）。`desc` 直接产出歌词相关的英文图像 prompt。
**幂等：** 若 `scenes.json` 已存在且 `label/desc` 非空，脚本跳过生成。
**变体：** 重复段（副歌）自动 `is_repeated=true`，供 Ken Burns crossfade 拼接使用。

---

## Resume Failed Pipeline

### Step 1: 查找项目

```bash
./scripts/list_projects.sh           # 列出全部项目
./scripts/list_projects.sh --failed  # 只列失败/中断项目
```

### Step 2: 读取失败步骤

```bash
cat "$PROJECT_DIR/metadata/status.json"
```

### Step 3: 从失败步骤重跑

| 失败步骤 | 重跑命令 |
|---------|---------|
| ① lyrics | `./scripts/generate_lyrics.sh "$PROJECT_DIR" "$THEME"` |
| ② music | `./scripts/generate_music.sh "$PROJECT_DIR"` |
| ③ align | `./scripts/align_lyrics.sh "$PROJECT_DIR"`（Demucs 自动对齐）<br>`./scripts/align_lyrics.sh "$PROJECT_DIR" --align-mode manual --srt-file <path>`（手动 SRT） |
| ④ base | `./scripts/produce_mv.sh "$PROJECT_DIR" --step 4` |
| ⑤-⑦ scenes | `./scripts/produce_mv.sh "$PROJECT_DIR" --step 5` |
| ⑧ KB | `./scripts/produce_mv.sh "$PROJECT_DIR" --step 8` |
| ⑨⑩⑪ | `./scripts/merge_and_export.sh "$PROJECT_DIR"` |

每个脚本均幂等，重跑安全，已生成的文件保留。

---

## Default Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| Video resolution | 1280×720 | Unified for all clips |
| Frame rate | 25fps | Standard |
| KB clip duration | 每场景 duration 秒（来自 scenes.json），变体图场景=总时长/图数 | 2s fade in/out |
| KB zoom | 0.0003/step, max 1.3× | Slow zoom in |
| Scene count | 10-22（动态） | 由 `analyze_srt.py` 根据歌词段落自动决定 |
| Subtitle font | Microsoft YaHei | 32pt, white with black outline |
| Alignment threshold (pass 1) | 0.25 | Two-pass greedy, first pass |
| Alignment threshold (pass 2) | 0.20 | Two-pass greedy, gap-filling pass |
| Whisper model | small → base (OOM fallback) | CPU memory adaptive |
| Demucs model | htdemucs | CPU, vocal separation |

## Alignment Algorithm (Step ③)

```
Original audio (song.mp3)
         ↓
┌───────────────────────────────────────┐
│ ③-a Demucs 人声分离（条件执行）        │
│    song.mp3 → vocals.wav             │
│    若 Demucs 不可用，跳过            │
└───────────────────────────────────────┘
         ↓
┌───────────────────────────────────────┐
│ ③-b Whisper 转写                      │
│    vocals.wav → segments[]           │
│    (timestamped text)                 │
└───────────────────────────────────────┘
         ↓
┌───────────────────────────────────────┐
│ ③-c 两遍对齐算法                       │
│                                       │
│ Pass 1: 顺序贪心                      │
│   - 阈值 0.25，窗口 8                 │
│   - 每个 ASR 片段找最佳匹配歌词行     │
│   - 歌词 index 只增不减              │
│                                       │
│ Pass 2: 补漏                          │
│   - 阈值 0.20（更宽松）               │
│   - 补充分配未匹配的歌词行             │
└───────────────────────────────────────┘
         ↓
┌───────────────────────────────────────┐
│ ③-d 后处理修正                        │
│                                       │
│ 修正1: 第1行歌词无时间戳              │
│   → 分配第一个有效 ASR 片段时间       │
│                                       │
│ 修正2: 跳行（连续未匹配）             │
│   → 前后已匹配行均分插值              │
└───────────────────────────────────────┘
         ↓
song.srt (每行原始歌词 + 对应时间戳)
```

> **新旧方案对比 / 算法实现细节 / Troubleshooting** 见 `references/alignment-workflow.md`。

---

## Unified Status Tracking

All scripts share a 统一的 pipeline status 机制，供 OpenClaw Control UI 实时读取并展示。

### Status Files

| 文件 | 路径 | 用途 |
|------|------|------|
| `status.json` | `{project_dir}/metadata/status.json` | 各步骤当前状态，Control UI 轮询 |
| `interrupt.json` | `{project_dir}/metadata/interrupt.json` | 用户打断信号，脚本在子步骤前检查 |

### status.json Schema

```json
{
  "project": "春天_20260424",
  "pipeline": {
    "① lyrics":    { "status": "completed", "detail": "title='春天的第一滴雨'",   "updated_at": "..." },
    "② music":     { "status": "completed", "detail": "4.1M, 133s",               "updated_at": "..." },
    "③ align":     { "status": "completed", "detail": "36/38 lines aligned",      "updated_at": "..." },
    "④ base":      { "status": "running",   "detail": "calling Image-01 API...",  "updated_at": "..." },
    "⑤-⑦ images": { "status": "pending",   "detail": "",                         "updated_at": "..." },
    "⑧ kb":        { "status": "pending",   "detail": "",                         "updated_at": "..." },
    "⑨ concat":    { "status": "pending",   "detail": "",                         "updated_at": "..." },
    "⑩ merge":     { "status": "pending",   "detail": "",                         "updated_at": "..." },
    "⑪ export":   { "status": "pending",   "detail": "",                         "updated_at": "..." }
  },
  "last_updated": "2026-04-24T16:00:00+08:00"
}
```

**Step Status 枚举：**
| 值 | 含义 |
|----|------|
| `pending` | 未开始 |
| `running` | 执行中 |
| `completed` | 成功完成 |
| `failed` | 失败 |
| `interrupted` | 被用户打断 |

### interrupt.json Schema

用户在 Control UI 点击"停止"时，UI 写入此文件：

```json
{
  "stop": true,
  "requested_at": "2026-04-24T16:05:30+08:00"
}
```

**打断信号清除：** 步骤脚本检测到 `stop: true` 后，自身写入 `"stop": false` 再退出（防止重复打断）。

### Checkpoint Reporting Rule

每个步骤脚本在以下时机必须更新 `status.json`：

| 时机 | `status` 写入 | `detail` 示例 |
|------|--------------|---------------|
| 子步骤开始 | `running` | `"calling API"` |
| 子步骤内每个检查点 | `running` | `"Whisper 30%"` |
| 子步骤完成 | `completed` | `"4.4 MB, 167s"` |
| 子步骤失败 | `failed` | `"API error: rate limit"` |
| 被打断退出 | `interrupted` | `"stopped by user"` |

### 打断检查点

脚本在每个子步骤开始前必须检查 `interrupt.json`：

```bash
check_interrupt() {
  local interrupt_file="$PROJECT_DIR/metadata/interrupt.json"
  if [ -f "$interrupt_file" ]; then
    local stop=$(python3 -c "import json; print(json.load(open('$interrupt_file')).get('stop', False))" 2>/dev/null)
    if [ "$stop" = "True" ]; then
      python3 -c "import json; d=json.load(open('$interrupt_file')); d['stop']=False; json.dump(d, open('$interrupt_file', 'w'))"
      echo "⚠️ [③ align] interrupted by user"
      update_status "③ align" "interrupted" "stopped by user"
      exit 0
    fi
  fi
}
```

打断发生时：
1. 已生成的文件**保留**，不删除
2. 脚本以退出码 `0` 正常退出（不是错误退出）
3. `status.json` 中该步骤标记为 `interrupted`

## Pipeline Log Format

Steps are logged to `metadata/steps.log`:

```
[2026-04-24 10:15:00] [① lyrics] started
[2026-04-24 10:15:03] [① lyrics] completed: title='春天的第一滴雨', tags='儿童插画, 流行, 欢快, 中文'
[2026-04-24 10:15:03] [② music] started
[2026-04-24 10:16:20] [② music] completed: 4.4 MB, 167s
[2026-04-24 10:16:20] [③ align] starting...
[2026-04-24 10:16:21] [③ align] Demucs vocal separation starting...
[2026-04-24 10:16:35] [③ align] Demucs done: vocals extracted
[2026-04-24 10:16:35] [③ align] Whisper transcription starting...
[2026-04-24 10:17:05] [③ align] Whisper transcription completed
[2026-04-24 10:17:05] [③ align] alignment starting...
[2026-04-24 10:17:05] [③ align] post-fix: line 1 assigned to first ASR segment (6.90s)
[2026-04-24 10:17:06] [③ align] alignment completed
[2026-04-24 10:20:00] [MV] ==========================================
[2026-04-24 10:20:00] [MV] 🎬 MV 流水线完成！
[2026-04-24 10:20:00] [MV] 项目目录: /home/.../春天_20260424_165525/
[2026-04-24 10:20:00] [MV] 最终文件: output/final.mp4
```

## Error Handling

| Error | Behavior |
|-------|----------|
| API returns error | Retry 3× with exponential backoff (2/4/8s) |
| All retries fail | Halt pipeline, preserve files, report error |
| Input file missing | Halt immediately with clear error message |
| Disk write failure | Halt immediately with permission/space error |
| Whisper OOM | Auto-fallback from small to base model |
| Demucs unavailable | Skip vocal separation, use original audio |
| Demucs OOM | Skip vocal separation, use original audio |

## Idempotency

Every step is idempotent — running the same step twice overwrites the previous output:

```
Step ① lyrics     → always overwrites audio/lyrics.txt
Step ② music      → always overwrites audio/song.mp3
Step ③ align      → always overwrites audio/song.srt
Step ④ base       → always overwrites images/base_character.png
Step ⑤-⑦ images  → always overwrites each seg{N}_{label}.png
Step ⑧ kb         → always overwrites each seg{N}_{label}_kb.mp4
Step ⑨ concat     → always overwrites temp/video_raw.mp4
Step ⑩ merge      → always overwrites output/final.mp4
Step ⑪ export     → always overwrites output/tiktok.mp4 / vertical.mp4
```

---

## 已知问题与局限

| 问题 | 说明 | 解决状态 |
|------|------|---------|
| 重复歌词段 | 同一句歌词在歌曲中多次出现时，时间戳只分配给第一次 | 部分解决：优先顺序分配，后续重复段无时间戳 |
| ASR 识别错字 | 歌词与演唱不完全一致时，相似度匹配可能跳行 | 已改善：Demucs 人声分离提升识别率 |
| 字级对齐 | 当前只做行级对齐，不支持卡拉OK逐字高亮 | **待实现**：安装 `pip install whisperx` 做 word-level alignment，配合 Whisper 输出可精确到词级别时间戳（方案B）；或安装 MFA（Montency Forces Alignment）做音节级对齐（方案A）；大鹏电脑暂不支持，等待后续条件具备 |
| 内存限制 | <4GB 内存机器上 Whisper 可能 OOM | 已改善：small→base 自动降级 |

---

## 后期可优化方向

| 优化项 | 说明 | 优先级 |
|--------|------|--------|
| **字级时间戳** | 用 WhisperX（推荐：`pip install whisperx`）或 MFA 实现逐字/逐音节对齐，支持卡拉OK歌词特效。当前大鹏电脑暂不支持，暂缓。 | 中（暂缓） |
| ~~并行场景生成~~ | ✅ 已实现（4并发） | — |
| ~~动态场景数量~~ | ✅ 已实现（10-22场景） | — |
| **变体图生成** | 重复段(>4s)自动生成多张变体图，Ken Burns内拼接 | 中 |
| **场景重排** | 根据歌词段落自动映射到场景 | 低 |
| **字幕特效** | burn_subtitle.sh 支持更多字幕样式 | 低 |
| **项目导出/备份** | 完成后的项目打包备份，节省磁盘空间 | 低 |
| **日志自动清理** | `steps.log` 超过一定大小或项目超过 N 天时自动清理 | 低 |
| **进度 UI 优化** | Control UI 实时显示当前 prompt 和 API 响应 | 低 |
