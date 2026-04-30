# Music-to-MV v2 — LLM-First 架构重构版

> **AI 驱动的音乐视频（MV）生成系统**  
> 输入主题和风格，自动完成：歌词创作 → 音乐生成 → 时间轴对齐 → 场景规划 → 逐帧生图 → Ken Burns 动画 → 音视频合成 → 导出 MP4

## 快速体验（2 分钟出歌）

```bash
pip install pyyaml jinja2
cp .env.example .env
# 编辑 .env 填入 MINIMAX_TOKEN

python3 -m src.main --theme "童年" --style "动漫风" --music-style "民谣" --mood "怀旧"
```

**实际运行效果**（真实 API 调用测试结果）：

| 步骤 | API | 耗时 | 产出 |
|------|-----|------|------|
| 歌词生成 | MiniMax-M2.7 | **2.1s** | "夏天的风与旧时光" 歌词 |
| 音乐生成 | music-2.6 | **59.6s** | 104s / 3.2MB MP3 |
| 图生 | Image-01 | **3×~15s** | 每张 220-250KB PNG |
| 视频合成 | ffmpeg | **~20s** | 7.8MB MP4 |

## 架构总览

```
┌─ CLI ─────────────────────────────────────────────────────┐
│  main.py  (--theme / --style / --auto / --phase / --list) │
└────────────────────────┬──────────────────────────────────┘
                         │
            MVPipeline 编排器 (pipeline.py)
            11 步状态机 + 暂停点 + 恢复
                         │
     ┌───────────────────┼─────────────────────┐
     │                   │                     │
  LLM API 层       脚本桥接层             底座支撑层
  ┌──────────┐    ┌────────────┐    ┌────────────────┐
  │ client   │    │ scripts_   │    │ project_       │
  │ (MiniMax │    │ bridge     │    │ manager (项目) │
  │  Polli-  │    │ (调用原版  │    │ config_        │
  │  nations │    │  Shell)    │    │ manager (配置) │
  │  DALL-E  │    │            │    │ style_map      │
  │  Alibaba)│    │ ── 未来 ── │    │ (数据映射层)   │
  │          │    │ 纯 Python  │    └────────────────┘
  │ logger   │    │ 重写替代   │
  │ (可观测) │    └────────────┘
  │          │
  │ registry │
  │(Prompt版)│
  └──────────┘
```

## 11 步 Pipeline

| 步骤 | 名称 | 输入 → 输出 | 核心模块 |
|------|------|------------|----------|
| ① | 歌词创作 | theme/style/mood → lyrics.txt | `LLMClient.call_minimax_lyrics()` |
| ② | 音乐创作 | lyrics + prompt → song.mp3 | `LLMClient.call_minimax_music()` |
| ③ | 歌词对齐 | song.mp3 + lyrics.txt → song.srt | 原版 `align_lyrics.sh` (Demucs+Whisper) |
| ③.5 | 场景分析 | srt + lyrics → scenes.json | 原版 `analyze_srt.py` (LLM 场景分割) |
| ④ | 角色设计 | style/theme/mood → base_char.json | `style_map.build_char_prompt()` |
| ⑤-⑦ | 逐帧生图 | scenes + char_prompt → scene_*.png | `LLMClient.call_image_api()` |
| ⑧ | Ken Burns | images → kb/*.mp4 | ffmpeg zoompan |
| ⑨ | 片段拼接 | kb/*.mp4 → concat.mp4 | ffmpeg concat |
| ⑩ | 音视频合成 | concat.mp4 + song.mp3 → final.mp4 | ffmpeg |
| ⑪ | 导出 | final.mp4 → export/*.mp4 | 文件拷贝 |

## 项目结构

```
music-to-mv-v2/
├── src/
│   ├── main.py               CLI 入口
│   ├── pipeline.py           MVPipeline 状态机编排器
│   ├── interaction.py        交互暂停点管理
│   ├── project_manager.py    项目状态管理
│   ├── config_manager.py     多 Provider 配置
│   ├── style_map.py          数据映射层（★ 核心）
│   ├── scripts_bridge.py     原版 Shell 桥接层
│   └── llm/
│       ├── client.py         多 API 客户端
│       ├── logger.py         可观测性日志
│       └── registry.py       Prompt 注册表（12 个模板）
├── prompts/
│   ├── registry.yaml         版本管理配置
│   ├── lyrics/v1.0.txt, v2.0.txt  歌词 prompt
│   ├── music/v1.0.txt              音乐 prompt
│   ├── image/v1.0.txt              图片 prompt
│   └── scene_analysis/             场景分析 prompt
├── tests/
│   ├── test_imports.py              6 项模块导入测试
│   ├── test_style_map.py            9 项数据映射测试
│   ├── test_integration_e2e.py     10 项端到端集成测试
│   ├── test_real_api.py             真实 API 调用测试
│   └── test_full_pipeline.py        完整 Pipeline 测试
├── .env.example              环境变量模板
├── run.sh                     快速启动脚本
└── README.md
```

## 25 项自动化测试（全部通过 ✓）

```bash
python3 tests/test_imports.py           # 6 PASS
python3 tests/test_style_map.py         # 9 PASS
python3 tests/test_integration_e2e.py   # 10 PASS
```

测试覆盖：
- **模块导入**: ConfigManager, ProjectManager, LLMLogger, PromptRegistry, UserInteraction, MVPipeline
- **数据映射**: 12 种艺术风格, 17 种情绪, 49 个主题, 8 个角色模板, 14 种音乐风格
- **集成场景**: 项目生命周期, 歌词+音乐数据流, 场景编排, 多 Provider 配置, Logger 持久化, scripts_bridge 路径, Prompt 版本管理, CLI 参数, 交互暂停点

## 配置 (ConfigManager)

支持多 Provider 配置，优先度：环境变量 > .env > 默认值：

```bash
# .env 文件
MINIMAX_TOKEN=sk-xxx...
MINIMAX_GROUP_ID=xxx...

# 可选依赖
IMAGE_API_PROVIDER=minimax      # minimax | pollinations | alibaba | dalle
IMAGE_PROVIDER_LIST=minimax,pollinations,alibaba  # 多 Provider 轮换
LLM_MODEL=MiniMax-M2.7

# 代理设置
HTTP_PROXY=http://127.0.0.1:10809
HTTPS_PROXY=http://127.0.0.1:10809
no_proxy=*,NO_PROXY=*
```

## Prompt 版本管理 (PromptRegistry)

支持多版本、默认版本、渐进式升级：

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
template.render({"theme": "春天", "style": "国风"})
# 支持 {{ variable }} + {% if var %}...{% endif %}
```

## 可观测性 (LLMLogger)

所有 LLM 调用自动记录：

```
metadata/llm_calls/
├── calls.jsonl        ← 每次调用的摘要
├── responses/*.json   ← 完整原始响应
├── stats.json         ← 聚合统计
├── errors.jsonl       ← 失败记录
└── versions.json     ← 版本使用追踪
```

```python
logger = LLMLogger("project_dir")
logger.print_summary()
# =======================================================
#   LLM 调用统计摘要
# =======================================================
#   总调用次数: 13
#   总 Token:    123,456
#   总成本:      $0.0034
#   ── 按类型统计 ──
#   lyrics_generation:  3 次调用  2,580 tokens
#   music_generation:   2 次调用  10,287,186 tokens
#   image_generation:   8 次调用  4,000 tokens
```

## CLI 使用

```bash
# 交互模式（默认）
python3 -m src.main

# 指定参数创建
python3 -m src.main --theme "夏天" --style "动漫风" --music-style "流行"

# 指定项目目录
python3 -m src.main --project "~/mv/我的项目"

# 从指定阶段开始（断点续传）
python3 -m src.main --phase 5

# 全自动模式（跳过交互暂停）
python3 -m src.main --auto

# 列出所有项目
python3 -m src.main --list
```

## 风格映射体系 (style_map.py)

**12 种画面风格：**
国风 / 动漫风 / 写实摄影风 / 水彩插画风 / 像素游戏风 / 电影感写实风 / 极简几何风 / 浮世绘和风 / 复古胶片风 / 漫画美式涂鸦风 / 蒸汽朋克风 / 赛博朋克风

**17 种情绪描述：**
欢快 / 温柔 / 史诗 / 忧伤 / 热血 / 梦幻 / 浪漫 / 怀旧 / 希望 / 暗黑 / 宁静 / 慵懒 / 清新 / 叛逆 / 孤独 / 悬疑 / 魔幻

**49 个主题视觉：**
春天 / 夏天 / 星空 / 大海 / 森林 / 童年 / 城市 / 古风 / 星际 / 魔法 / 江南 / 武侠 ... 等

**14 种音乐风格：**
流行 / 说唱 / 民谣 / 电子 / 摇滚 / 古典 / 爵士 / R&B / 中国风 / 新世纪 / EDM / 乡村 / 朋克 / HipHop

## 多 API Provider

| Provider | 图片 | 模型 | 特点 |
|----------|------|------|------|
| MiniMax | Image-01 | M2.7 + music-2.6 | 中文友好，质量高 |
| Pollinations | ✅ | — | 免费，无需 Token |
| Alibaba Tongyi | ✅ | — | 中文理解强 |
| DALL-E (OpenAI) | ✅ | — | 质量最高，需翻墙 |

## 从原版到 v2 的重构

| 维度 | 原版 (1,143 行) | v2 (2,635 行) |
|------|----------------|-------------|
| 架构 | Shell 脚本 + Python 片段混排 | 纯 Python 分层架构 |
| 状态管理 | 文件全局变量 | ProjectManager 原子化 |
| 配置 | 散落在 .env 和脚本参数 | ConfigManager 统一管理 |
| 可观测性 | 无 | LLMLogger JSONL + 统计 |
| Prompt | 硬编码在 Python 代码中 | registry.yaml 版本管理 |
| 测试 | 无 | 25 项自动化测试 |
| CLI | 固定参数顺序 | 参数化 + 分阶段 |
| API 管理 | 单 Provider 硬编码 | 多 Provider 轮换 |

## 开发规划

- [x] 底座层：ProjectManager + ConfigManager
- [x] 数据层：style_map (12 风格/17 情绪/49 主题)
- [x] LLM 层：多 API 客户端 + 日志 + Prompt 版本管理
- [x] 编排层：MVPipeline 11 步状态机
- [x] 交互层：3 个暂停点 + 恢复
- [x] 桥接层：scripts_bridge 路径适配
- [x] 测试：25 项自动化 + 真实 API 测试
- [x] 修复：14 项 Windows 兼容性 + LLM 解析 + 流程缺陷修复
- [ ] 纯 Python 重写：替换 3 个核心 Shell 脚本
- [ ] 错误恢复：断点续传 + 重试
- [ ] Web UI：Gradio 界面
- [ ] Docker：一键部署

---

## 修复记录

本项目在开发过程中修复了以下 14 个问题，按严重程度排序：

### 关键性修复

**1. `_write_scenes` 写入目标目录不存在**
- `src/scene_analyzer.py`
- 原因：`init_new` 初始化时 metadata 目录结构可能不完整
- 修复：写入前 `mkdir(parents=True, exist_ok=True)`

**2. LLM JSON 解析失败 —— markdown 代码块 + 思考标签**
- `src/scene_analyzer.py`
- 原因：MiniMax 返回的 JSON 被 `` ```json...``` `` 代码块包裹，含 `Thinking...` 标签
- 修复：剥离代码块标记和思考标签，提取 `{`-`}` 之间内容，失败降级到 local fallback

**3. Ken Burns `crop` 滤镜对竖屏图无效**
- `src/ken_burns.py`
- 原因：`crop=ih*9/16:ih` 对缩放后的竖屏图计算出超宽值
- 修复：改用 `scale+pad` 等比缩放 + 黑边填充，兼容任意方向图片

**4. zoompan 表达式中的逗号被 ffmpeg 解析为滤镜分隔符**
- `src/ken_burns.py`
- 原因：`min(zoom+step, max)` 内含逗号
- 修复：改为纯线性缩放 `z=1+step*on`

**5. 测试脚本文件名匹配模式不匹配**
- `tests/test_full_pipeline_v2.py`
- 原因：搜索 `scene_*.png` 但文件名为 `seg{sid}_scene.png`
- 修复：改为 `*_scene.png`

**6. ffmpeg stderr 被 DEVNULL 吞掉**
- `src/ken_burns.py`
- 原因：`stderr=subprocess.DEVNULL`
- 修复：改为 `PIPE`，首次失败时输出末尾 200 字符

**7. Windows 上 subtitles 滤镜路径问题**
- `src/exporter.py`
- 原因：ffmpeg subtitles 滤镜不识别带盘符的 Windows 路径
- 修复：`cwd` + 相对路径方案（文件复制到 temp 目录后只传文件名）

### 重要修复

**8. `SKIP_API_flag` 未定义变量**
- `tests/test_full_pipeline_v2.py`
- 修复：改为全局 `_API_FAILED`

**9. SceneImageGenerator 不受 `--no-api` 控制**
- `src/scene_generator.py` + 测试脚本
- 修复：新增 `dry_run=True` 参数，跳过 API 调用，用 PIL 生成占位图

**10. dry_run 占位图缺乏可视化信息**
- `src/scene_generator.py`
- 修复：按段落类型着色 + 标注场景编号/名称/歌词预览/时长/标签

**11. 步骤统计不准确（`6/15` → `9/9`）**
- `tests/test_full_pipeline_v2.py` + `project_manager.py`
- 修复：统一步骤命名格式（`① lyrics`），补全导出阶段状态更新

**12. ffmpeg 日志中文路径被 `repr()` 转义**
- `src/exporter.py`
- 修复：直接 raw 路径，日志用 UTF-8 写入

### 微修复

**13. 残留文件 `_debug_check.py`**
- 删除

**14. `sharpen_params` 参数未在 VF 字符串中使用**
- `src/ken_burns.py`
- 修复：硬编码 `unsharp=5:5:0.8:3:3:0.4` 改为 `f"unsharp={sharpen_params}"`
