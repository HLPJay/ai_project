# 🎹 Music-to-MV 自动化生成协议 (v2.0 状态驱动版)

## 1. 核心愿景

利用 AI 能力（MiniMax, SD/MJ, FFmpeg）实现从意图到 MV 的全自动生成。架构核心为"状态驱动"，确保流程可审计、可恢复、可扩展。

---

## 2. 技能契约定义 (Atomic Skill Contracts)

### Skill [01]: Lyrics-Gen (歌词生成)
- **输入**: `prompt_idea` (用户意图)
- **输出**: `lyrics.txt`
- **契约**: 必须包含符合 Lrc 格式的时间轴预估或段落标记
- **守卫 (Guard)**: 检查 `.env` 中的 `MINIMAX_API_KEY`

### Skill [02]: Music-Gen (音乐生成)
- **输入**: `lyrics.txt`
- **输出**: `audio.mp3`
- **契约**: 产物必须为指定采样率的 MP3，且时长波动在意图范围内

### Skill [03]: SRT-Analyze (语义与时间轴分析)
- **输入**: `lyrics.srt` (或字幕文件)
- **输出**: `scene_plan.json`
- **数据结构**:
  ```json
  [
    {"start": 0.0, "end": 5.5, "keywords": "森林, 晨光", "style_hint": "油画", "weight": 0.8},
    ...
  ]
  ```

### Skill [04]: Image-Gen (视觉生成)
- **输入**: `scene_plan.json`
- **输出**: `assets/images/` 目录
- **契约**: 每张图片命名必须对应 scene_plan.json 中的索引
- **守卫**: 检查网络代理是否联通，检查 API 余额

### Skill [05]: Video-Assemble (视频合成)
- **输入**: `audio.mp3`, `assets/images/`, `lyrics.srt`
- **输出**: `final_mv.mp4`
- **契约**: 使用 FFmpeg 进行硬编码对齐，确保音频不漂移

---

## 3. 状态转换逻辑 (State Machine)

主程序执行逻辑遵循：`INIT -> CHECK_STATE -> RUN_SKILL -> UPDATE_STATE -> NEXT`

```
┌─────────────┐
│    INIT    │  执行 init_project.sh，生成 UUID 文件夹及 metadata 档案
└──────┬──────┘
       ▼
┌─────────────┐
│   CHECK     │  读取 metadata，若 status.music 为 done，则跳过生成
└──────┬──────┘
       ▼
┌─────────────┐
│ EXECUTE     │  顺序调用原子技能，捕获返回值
└──────┬──────┘
       ▼
┌─────────────┐
│    LOG      │  实时向 llm_logger.py 推送结构化日志
└──────┬──────┘
       ▼
┌─────────────┐
│    NEXT     │  进入下一个 Skill
└─────────────┘
```

---

## 4. 元数据格式 (metadata.json)

```json
{
  "project_id": "MV_20240428_XXXX",
  "created_at": "2024-04-28T19:38:00Z",
  "config": {
    "theme": "关于果树转型的感悟",
    "style": "写实风格",
    "target_resolution": "1080p"
  },
  "workflow_status": {
    "lyrics_gen": {"status": "pending", "output": null, "error": null},
    "music_gen": {"status": "pending", "output": null, "error": null},
    "srt_analyze": {"status": "pending", "output": null, "error": null},
    "image_gen": {"status": "pending", "output": null, "error": null},
    "video_assemble": {"status": "pending", "output": null, "error": null}
  },
  "assets": {
    "audio": "",
    "srt": "",
    "image_dir": "",
    "final_video": ""
  }
}
```

---

## 5. 核心设计原则 (The Red Lines)

| 原则 | 描述 |
|------|------|
| **状态优先 (State-First)** | 脚本运行前先读 metadata.json，运行后必写 metadata.json |
| **契约通信 (Data Contract)** | 脚本间不直接传递变量，而是通过 JSON 交换产物路径与参数 |
| **环境隔离 (Environment Sandbox)** | 所有网络代理、API Key、路径变量统一由底座加载，禁止在 Skill 内部硬编码 |

---

## 6. Guard（准入守卫）定义

每个 Skill 启动前，必须先检查前置条件：

```
Check_Guard()     # 1. 检查 API Key、网络、前置文件
Execute_Skill()   # 2. 执行核心逻辑 (Python/FFmpeg)
Update_Metadata() # 3. 将产物路径和状态写入 metadata.json
```
