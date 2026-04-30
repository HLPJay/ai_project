# 🎬 Music-to-MV v2 — LLM-First 架构重构版

> **AI 驱动的音乐视频（MV）全自动生成系统**  
> 输入**主题**和**风格**，自动完成：歌词创作 → 音乐生成 → 时间轴对齐 → 场景规划 → 逐帧生图 → Ken Burns 动画 → 音视频合成 → 导出 MP4

<p align="center">
  <b>只需 2 行命令，2 分钟产出你的专属 MV 🎵</b>
</p>

---

## ✨ 快速体验

```bash
# 1. 安装依赖
pip install pyyaml jinja2

# 2. 配置 API Token（申请地址: https://minimaxi.com）
cp .env.example .env
# 编辑 .env 填入 MINIMAX_TOKEN=sk-xxx...

# 3. 一键生成 MV 🚀
python -m src.main --theme "童年" --style "动漫风" --music-style "民谣" --mood "怀旧"
```

> 💡 **首次运行音乐生成约需 60 秒**（MiniMax music-2.6 模型推理时间），后续步骤通常在几秒内完成。

---

## 📋 目录

- [系统架构](#-系统架构)
- [11 步 Pipeline](#-11-步-pipeline)
- [快速上手](#-快速上手)
- [CLI 使用详解](#-cli-使用详解)
- [项目结构](#-项目结构)
- [风格映射体系](#-风格映射体系)
- [多 API Provider](#-多-api-provider)
- [Prompt 版本管理](#-prompt-版本管理)
- [可观测性](#-可观测性)
- [测试体系](#-测试体系)
- [常见问题](#-常见问题)
- [与原版对比](#-与原版对比)
- [开发路线图](#-开发路线图)
- [修复记录](#-修复记录)

---

## 🏗 系统架构

```
┌─ CLI ───────────────────────────────────────────────────────┐
│  main.py  (--theme / --style / --auto / --phase / --list)   │
└────────────────────────┬────────────────────────────────────┘
                         │
            MVPipeline 编排器 (pipeline.py)
            11 步状态机 + 暂停点 + 断点续传
                         │
     ┌───────────────────┼─────────────────────┐
     │                   │                     │
  LLM API 层        脚本桥接层             底座支撑层
  ┌─────────────┐  ┌─────────────┐  ┌───────────────────┐
  │ client.py   │  │ scripts_    │  │ project_manager   │
  │ (MiniMax /  │  │ bridge.py   │  │ config_manager    │
  │  Pollina-   │  │ (调用原版   │  │ style_map (核心   │
  │  tions /    │  │  Shell 脚本)│  │ 数据映射层)       │
  │  Alibaba /  │  │             │  └───────────────────┘
  │  DALL-E)    │  │ ── 未来 ──  │
  │             │  │  纯 Python  │
  │ logger.py   │  │  重写替代   │
  │ registry.py │  └─────────────┘
  └─────────────┘
```

### 设计原则

- **LLM-First** — Prompt 模板版本化、注册表管理，非硬编码
- **可观测性** — 所有 API 调用自动记录 JSONL + 聚合统计
- **可替换性** — 多 Provider 支持，一键切换图片/LLM 服务商
- **断点续传** — 11 步状态机，失败后可从中断步骤恢复

---

## 🎯 11 步 Pipeline

| 步骤 | 名称 | 输入 → 输出 | 核心模块 | 耗时参考 |
|------|------|------------|----------|---------|
| ① | **歌词创作** | theme/style/mood → lyrics.txt | `LLMClient.call_minimax_lyrics()` | ~2s |
| ② | **音乐创作** | lyrics + prompt → song.mp3 | `LLMClient.call_minimax_music()` | ~60s |
| ③ | **歌词对齐** | song.mp3 + lyrics.txt → song.srt | `align.py` (Whisper + 两遍匹配) | ~30s |
| ③.5 | **场景分析** | srt + lyrics → scenes.json | `scene_analyzer.py` (LLM 场景分割) | ~10s |
| ④ | **角色设计** | style/theme/mood → base_char.json | `style_map.build_char_prompt()` | ~3s |
| ⑤-⑦ | **逐帧生图** | scenes + char_prompt → scene_*.png | `scene_generator.py` (多 Provider) | ~15s/张 |
| ⑧ | **Ken Burns** | images → clips/*.mp4 | `ken_burns.py` (ffmpeg zoompan) | ~10s |
| ⑨ | **片段拼接** | clips/*.mp4 → concat.mp4 | `exporter.py` (ffmpeg concat) | ~5s |
| ⑩ | **音视频合成** | concat.mp4 + song.mp3 → final.mp4 | `exporter.py` (ffmpeg) | ~10s |
| ⑪ | **导出** | final.mp4 → export/*.mp4 | `exporter.py` (多种尺寸) | ~5s |

> ⏱ **总耗时：约 2-3 分钟**（主要瓶颈在步骤②音乐生成）

---

## 🚀 快速上手

### 安装

```bash
git clone <repo-url>
cd music-to-mv-v2

# 核心依赖
pip install pyyaml jinja2

# 可选依赖（歌词对齐用）
pip install openai-whisper            # 语音转写
pip install demucs                    # 人声分离（提升对齐精度）

# 可选依赖（图片生成用）
pip install Pillow                    # dry_run 占位图生成
```

### 配置

复制环境变量模板并编辑：

```bash
cp .env.example .env
```

关键配置项：

```ini
# 🔴 必填
MINIMAX_TOKEN=sk-xxx...              # MiniMax API Token（申请: https://minimaxi.com）

# 🟡 可选（默认使用 MiniMax）
IMAGE_API_PROVIDER=minimax           # minimax | pollinations | alibaba | dalle
LLM_MODEL=MiniMax-M2.7

# 🟢 代理设置（如需）
HTTP_PROXY=http://127.0.0.1:10809
HTTPS_PROXY=http://127.0.0.1:10809
```

### 运行

```bash
# 交互模式（默认，含暂停点供人工确认）
python -m src.main

# 一键全自动模式（无人工干预）
python -m src.main --auto

# 指定主题和风格
python -m src.main --theme "星空" --style "国风" --music-style "中国风" --mood "梦幻"

# 只跑部分阶段（断点续传）
python -m src.main --project "~/mv/我的项目" --phase 5

# 列出所有项目
python -m src.main --list
```

---

## 🎮 CLI 使用详解

### 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--theme` | `春天` | MV 主题（如：童年、星空、大海、城市） |
| `--style` | `动漫风` | 画面风格（12 种可选） |
| `--music-style` | `流行` | 音乐风格（14 种可选） |
| `--mood` | `温柔` | 情绪氛围（17 种可选） |
| `--language` | `中文` | 歌词语言 |
| `--project` | `""` | 已有项目目录（用于断点续传） |
| `--phase` | `1` | 开始阶段（1-11） |
| `--auto` | `False` | 全自动模式，跳过所有暂停点 |
| `--list` | `False` | 列出 workspace 中所有项目 |
| `--no-api` | `False` | 跳过真实 API 调用（测试用） |

### 分阶段运行

```bash
# 只生成歌词和音乐
python -m src.main --phase 1

# 从图片生成开始（假设前 4 步已完成）
python -m src.main --project "~/mv/我的项目" --phase 5
```

---

## 📁 项目结构

```
music-to-mv-v2/
├── src/                          # 核心源码
│   ├── main.py                   CLI 入口 + 参数解析
│   ├── pipeline.py               MVPipeline 11 步状态机编排器
│   ├── project_manager.py        项目状态管理（原子化步骤追踪）
│   ├── config_manager.py         多 Provider 配置管理
│   ├── style_map.py              数据映射层（★ 核心 12 风格/17 情绪/49 主题）
│   ├── interaction.py            交互暂停点管理（3 个用户确认点）
│   ├── scripts_bridge.py         原版 Shell 脚本桥接层
│   ├── align.py                  纯 Python 歌词对齐（Demucs+Whisper+两遍匹配）
│   ├── scene_analyzer.py         SRT 场景分析器（LLM + 本地双策略）
│   ├── scene_generator.py        场景图生成器（多 Provider + 并行 + 变体）
│   ├── ken_burns.py              Ken Burns 动画生成（ffmpeg zoompan）
│   ├── exporter.py               MV 合成导出器（concat / merge / 多尺寸）
│   ├── report_generator.py       LLM 调用报告生成器
│   └── llm/
│       ├── client.py             多 API 统一客户端（重试 + 日志）
│       ├── logger.py             可观测性日志系统（JSONL + 聚合统计）
│       └── registry.py           Prompt 注册表（版本管理 + 渲染引擎）
├── prompts/                      # Prompt 模板
│   ├── registry.yaml             版本管理配置
│   ├── lyrics/                   lyrics.v1.0.txt, v2.0.txt
│   ├── music/                    music.v1.0.txt
│   ├── image/                    image.v1.0.txt
│   └── scene_analysis/           场景分析 prompt
├── tests/                        # 自动化测试
│   ├── test_imports.py           6 项模块导入测试
│   ├── test_style_map.py         9 项数据映射测试
│   ├── test_integration_e2e.py   10 项端到端集成测试
│   ├── test_real_api.py          真实 API 调用测试
│   ├── test_full_pipeline.py     完整 Pipeline 测试（混合模式）
│   ├── test_full_pipeline_v2.py  完整 Pipeline 测试（纯 Python 版）
│   ├── test_scene_generator.py   场景图生成器测试
│   ├── test_scene_analyzer.py    场景分析器测试
│   ├── test_exporter.py          导出器测试
│   ├── test_ken_burns.py         Ken Burns 测试
│   └── test_report_generator.py  报告生成器测试
├── .env.example                  环境变量模板
├── run.sh                        快速启动脚本
└── README.md                     本文件
```

---

## 🎨 风格映射体系

`style_map.py` 是系统的**核心数据映射层**，集中管理所有风格相关的配置：

### 12 种画面风格

| 风格 | 英文描述 | 负面词 |
|------|---------|--------|
| 🏮 国风 | Chinese ink painting, calligraphy strokes | photography, 3d render |
| 🎬 动漫风 | Japanese anime style, cel shading | realistic, photography |
| 📷 写实摄影风 | Photorealistic, DSLR, natural lighting | cartoon, anime |
| 🎨 水彩插画风 | Watercolor painting, soft wet brushes | sharp lines, digital |
| 🕹 像素游戏风 | 8-bit pixel art, retro game | smooth, realistic |
| 🎞 电影感写实风 | Cinematic film grain, anamorphic | flat, digital |
| 🔷 极简几何风 | Minimalist geometric shapes, flat design | texture, detail |
| 🌊 浮世绘和风 | Ukiyo-e woodblock, Hokusai style | modern, 3d |
| 📀 复古胶片风 | Vintage film, Kodachrome, grain | digital, clean |
| 🎭 漫画美式涂鸦风 | American comic book, bold inks | anime, realistic |
| ⚙️ 蒸汽朋克风 | Steampunk, brass, Victorian machinery | modern, sci-fi |
| 🤖 赛博朋克风 | Cyberpunk, neon, high tech | natural, rustic |

### 17 种情绪描述

欢快 / 温柔 / 史诗 / 忧伤 / 热血 / 梦幻 / 浪漫 / 怀旧 / 希望 / 暗黑 / 宁静 / 慵懒 / 清新 / 叛逆 / 孤独 / 悬疑 / 魔幻

### 49 个主题视觉

春天 / 夏天 / 星空 / 大海 / 森林 / 童年 / 城市 / 古风 / 星际 / 魔法 / 江南 / 武侠 / 草原 / 雪国 / 沙漠 / 晨曦 / 黄昏 / 月光 / 烟火 / 樱花 / 枫叶 / 荷塘 / 竹林 / 银河 / 极光 / 彩虹 / 云海 / 瀑布 / 溪流 / 花园 / 田园 / 校园 / 游乐园 / 老街 / 古镇 / 庙会 / 茶道 / 书法 / 围棋 / 古琴 / 红灯笼 / 油纸伞 / 风筝 / 纸鹤 / 蒲公英 / 萤火虫 / 星空 / 锦鲤 / 梅花

### 14 种音乐风格

流行 / 说唱 / 民谣 / 电子 / 摇滚 / 古典 / 爵士 / R&B / 中国风 / 新世纪 / EDM / 乡村 / 朋克 / HipHop

---

## 🔌 多 API Provider

| Provider | 图片生成 | LLM/歌词 | 音乐生成 | 特点 |
|----------|---------|----------|---------|------|
| **MiniMax** | ✅ Image-01 | ✅ M2.7 | ✅ music-2.6 | 中文友好，质量高（推荐） |
| **Pollinations** | ✅ 免费 | ❌ | ❌ | 无需 Token，适合测试 |
| **Alibaba（通义万相）** | ✅ | ❌ | ❌ | 中文理解能力强 |
| **DALL-E（OpenAI）** | ✅ | ❌ | ❌ | 质量最高，需翻墙 |

切换方式（环境变量）：

```ini
IMAGE_API_PROVIDER=minimax        # 当前使用的图片 Provider
IMAGE_PROVIDER_LIST=minimax,pollinations,alibaba  # 多 Provider 轮换
```

---

## 📝 Prompt 版本管理

所有 Prompt 通过 `registry.yaml` 集中管理，支持多版本、默认版本、渐进式升级：

```
prompts/
├── registry.yaml        ← 定义所有 prompt 版本
│   prompts:
│     lyrics.generation:
│       default_version: v2.0
│       versions:
│         v1.0: { file: lyrics/v1.0.txt, desc: "基础"    }
│         v2.0: { file: lyrics/v2.0.txt, desc: "增强结构" }
│
├── lyrics/v1.0.txt     ← 简单模板
├── lyrics/v2.0.txt     ← 含结构化要求、押韵规则
└── music/v1.0.txt
```

内置渲染引擎（无需 Jinja2 也可运行）：

```python
# 模板变量渲染
template.render({"theme": "春天", "style": "国风"})
# 支持 {{ variable }} + {% if var %}...{% endif %}
```

---

## 📊 可观测性

所有 LLM/API 调用自动记录到项目目录下的 `metadata/llm_calls/`：

```
metadata/llm_calls/
├── calls.jsonl              ← 每次调用的摘要（JSONL 格式）
├── responses/*.json         ← 完整原始响应
├── stats.json               ← 聚合统计
├── errors.jsonl             ← 失败记录
└── versions.json            ← 版本使用追踪
```

查看统计摘要：

```python
from src.llm.logger import LLMLogger

logger = LLMLogger("your_project_dir")
logger.print_summary()
```

输出示例：

```
=======================================================
  LLM 调用统计摘要
=======================================================
  总调用次数: 13
  总 Token:    123,456
  总成本:      $0.0034
  ── 按类型统计 ──
  lyrics_generation:  3 次调用  2,580 tokens
  music_generation:   2 次调用  10,287 tokens
  image_generation:   8 次调用  4,000 tokens
```

---

## 🧪 测试体系

项目包含 **11 个测试文件**，覆盖模块导入 → 数据映射 → 端到端流程 → 真实 API 四个层次：

```bash
# 1️⃣ 模块导入测试（快速验证环境）
python tests/test_imports.py

# 2️⃣ 数据映射测试（验证 style_map 完整性）
python tests/test_style_map.py

# 3️⃣ 端到端集成测试（不调 API，验证模块间协作）
python tests/test_integration_e2e.py

# 4️⃣ 真实 API 调用测试（需要 MINIMAX_TOKEN）
python tests/test_real_api.py                  # 全流程
python tests/test_real_api.py lyrics           # 仅歌词
python tests/test_real_api.py music            # 仅音乐
python tests/test_real_api.py image            # 仅图片

# 5️⃣ 完整 Pipeline 测试（跳过 API 调用）
python tests/test_full_pipeline_v2.py --no-api

# 6️⃣ 各模块独立测试
python -m unittest tests/test_scene_generator.py
python -m unittest tests/test_scene_analyzer.py
python -m unittest tests/test_exporter.py
python -m unittest tests/test_ken_burns.py
python -m unittest tests/test_report_generator.py
```

### 测试覆盖

| 测试文件 | 数量 | 覆盖内容 |
|----------|------|---------|
| `test_imports.py` | 6 项 | 模块导入 + 类实例化 |
| `test_style_map.py` | 9 项 | 12 风格, 17 情绪, 49 主题, 8 角色模板, 14 音乐风格 |
| `test_integration_e2e.py` | 10 项 | 生命周期, 数据流, 编排, Provider, Logger |
| `test_scene_generator.py` | ✅ | 场景图生成全流程 |
| `test_scene_analyzer.py` | ✅ | SRT 解析 + 场景分析 |
| `test_exporter.py` | ✅ | 导出 + 质量报告 |
| `test_ken_burns.py` | ✅ | Ken Burns 动画 |
| `test_report_generator.py` | ✅ | 报告生成 |

---

## ❓ 常见问题

### Q: 必须要有 MiniMax API Token 吗？

**是的**。歌词、音乐、图片生成都依赖 MiniMax API（推荐）。如果只想测试流程，可以用 `--no-api` 模式：

```bash
python tests/test_full_pipeline_v2.py --no-api
```

### Q: 支持哪些平台？

Windows、macOS、Linux 均可运行。歌词对齐需要安装 ffmpeg（所有平台的 ffprobe 已包含在 ffmpeg 包中）。

### Q: 如何换一个图片生成服务商？

修改 `.env` 中的 `IMAGE_API_PROVIDER`：

```ini
IMAGE_API_PROVIDER=pollinations   # 免费无需 Token
# 或
IMAGE_API_PROVIDER=alibaba        # 需要 ALIBABA_TOKEN
# 或
IMAGE_API_PROVIDER=dalle          # 需要 OPENAI_TOKEN
```

### Q: 提示 `PromptRegistry 渲染失败` 怎么办？

这通常是 PromptRegistry 注册表与实际模板文件不一致导致的。可忽略——系统会自动使用内置的 fallback prompt 拼接逻辑，不影响正常使用。

### Q: 如何断点续传？

```bash
# 指定已有项目目录和起始阶段
python -m src.main --project "~/mv/我的项目" --phase 5
```

项目状态保存在 `metadata/info.json` 的 `pipeline` 字段中。

---

## 📊 与原版对比

| 维度 | 原版（Shell 脚本） | v2（Python 重构版） |
|------|-------------------|-------------------|
| **架构** | Shell 脚本 + Python 片段混排 | 纯 Python 分层架构 |
| **状态管理** | 文件全局变量 | `ProjectManager` 原子化步骤追踪 |
| **配置** | 散落在 `.env` 和脚本参数 | `ConfigManager` 统一管理 |
| **可观测性** | ❌ 无 | ✅ `LLMLogger` JSONL + 聚合统计 |
| **Prompt 管理** | 硬编码在 Python 代码 | ✅ `registry.yaml` 版本管理 |
| **测试** | ❌ 无 | ✅ 11 个测试文件 |
| **CLI** | 固定参数顺序 | ✅ 参数化 + 分阶段运行 |
| **API 管理** | 单 Provider 硬编码 | ✅ 多 Provider 轮换 |
| **歌词对齐** | 依赖 Shell 命令 | ✅ 纯 Python（Whisper+两遍匹配） |
| **Windows 兼容** | ❌ 差 | ✅ 修复路径和编码问题 |
| **代码行数** | ~1,100 行 | ~2,600 行 |

---

## 🗺 开发路线图

- [x] 底座层：`ProjectManager` + `ConfigManager`
- [x] 数据层：`style_map` (12 风格 / 17 情绪 / 49 主题)
- [x] LLM 层：多 API 客户端 + 日志 + Prompt 版本管理
- [x] 编排层：`MVPipeline` 11 步状态机
- [x] 交互层：3 个暂停点 + 恢复
- [x] 桥接层：`scripts_bridge` 路径适配
- [x] 纯 Python 歌词对齐：`align.py` (Demucs+Whisper)
- [x] 纯 Python 场景分析：`scene_analyzer.py`
- [x] 纯 Python Ken Burns：`ken_burns.py`
- [x] 纯 Python 合成导出：`exporter.py`
- [x] 测试：11 个测试文件
- [x] Windows 兼容性修复

- [ ] **错误恢复**：更健壮的断点续传 + 自动重试
- [ ] **Web UI**：Gradio 可视化界面
- [ ] **Docker**：一键部署
- [ ] **模板市场**：多语言/多风格 prompt 模板
- [ ] **批量生产**：一次配置多个项目批量生成

---

## 🔧 修复记录

### 关键修复

1. **`_write_scenes` 写入目标目录不存在** — `scene_analyzer.py` 写入前 `mkdir(parents=True, exist_ok=True)`
2. **LLM JSON 解析失败（markdown 代码块 + 思考标签）** — `scene_analyzer.py` 剥离代码块标记和思考标签，失败降级到 local fallback
3. **Ken Burns `crop` 滤镜对竖屏图无效** — `ken_burns.py` 改用 `scale+pad` 等比缩放 + 黑边填充
4. **zoompan 表达式中的逗号被 ffmpeg 解析为滤镜分隔符** — 改为纯线性缩放 `z=1+step*on`
5. **测试文件名匹配模式不匹配** — 搜索模式从 `scene_*.png` 改为 `*_scene.png`
6. **ffmpeg stderr 被 DEVNULL 吞掉** — 改为 `PIPE`，首次失败时输出末尾 200 字符
7. **Windows 上 subtitles 滤镜路径问题** — `cwd` + 相对路径方案

### 重要修复

8. **`SceneImageGenerator` 不受 `--no-api` 控制** — 新增 `dry_run=True` 参数，PIL 生成占位图
9. **dry_run 占位图缺乏可视化信息** — 按段落类型着色 + 标注场景编号/名称/歌词预览
10. **步骤统计不准确** — 统一步骤命名格式，补全导出阶段状态更新
11. **`LLMLogger` 被静默跳过** — `LLMClient` 支持 `project_dir` 自动创建 logger 及全局单例
