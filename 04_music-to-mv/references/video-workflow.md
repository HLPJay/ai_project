# Video Production (Steps ④–⑧)

## 🎯 目标

将静态图片转化为动态 Ken Burns 视频片段，为后续合并音视频做准备。

**产出：** `clips/*_kb.mp4`（N 个 Ken Burns 视频片段，N 由 `analyze_srt.py` 动态决定，通常 10-22 个）

**下一步：** `merge_and_export.sh` 负责拼接、合并音视频、导出 TikTok 版本。

**不使用 Kling AI**，全部依赖 MiniMax Image-01 + ffmpeg Ken Burns 实现。

## 📦 边界

**输入：**
- `{project_dir}/metadata/info.json`（含 song_title）
- `{project_dir}/audio/song.srt`（用于质量校验，若行数 < 5 则终止执行）

**本步骤产出：**
- `{project_dir}/images/base_character.png` — Step ④
- `{project_dir}/images/seg{N}_{label}.png`（×N，动态 10-22）— Steps ⑤-⑦
- `{project_dir}/clips/seg{N}_{label}_kb.mp4`（×N）— Step ⑧

**本步骤不负责：**
- 音视频合并（Step ⑨-⑩ → merge_and_export.sh）
- TikTok 导出（Step ⑪ → merge_and_export.sh）

## 📝 步骤

### Step ④: 生成基础角色参考图

使用 Image-01 生成一个角色参考图，作为后续所有场景图的 prompt 前缀，确保视觉一致性。

Prompt 结构：
```
A cute Chinese boy, 7-8 years old, with short black slightly curly hair,
big bright eyes, warm smile, wearing simple white t-shirt and dark shorts,
{optional: $SONG_TITLE}, illustration style, soft colors, heartwarming atmosphere
```

**注意：** Image-01 目前不支持 reference image 参数，角色一致性通过 prompt 前缀策略实现。

**重试机制：** API 失败时重试 2 次，间隔 2/4 秒（指数退避）。

### Steps ⑤-⑦: 生成 N 个场景图（动态，10-22 张）

场景数量 N 由 [analyze_srt.py](../scripts/analyze_srt.py) 根据 SRT 歌词段落动态决定（典型范围 10-22）。每个场景独立调用 Image-01，prompt 结构：
```
{base_character_prefix}, {scene_specific_description}, illustration style, soft warm colors
```

**场景划分原则（基于歌词结构，由 LLM 自动分配 label/desc）：**

| 段落类型 | label 示例 | 视觉重点 |
|---------|-----------|---------|
| Intro | `intro` | 建立场景，角色在环境中 |
| Verse | `verse1` / `verse2` | 动作：奔跑、探索、不同场景 |
| Pre-Chorus | `prechorus` | 情感铺垫：细节场景 |
| Chorus（重复段） | `chorus` | 高潮：广角、动作；重复段 `is_repeated=true` 触发变体图 |
| Bridge | `bridge` | 安静、反思性时刻 |
| Outro | `outro` | 结局，梦境或象征性画面 |

> 实际场景数 N 与 label 全部来自 `metadata/scenes.json`（由 analyze_srt.py 生成），脚本不写死。

**重试机制：** 每个场景失败时重试 2 次，间隔 2/4 秒，仍失败则跳过该场景继续下一个。

**场景间延迟：** 每场景间隔 2 秒（API 限速）。

### Step ⑧: Ken Burns 效果

对每张静态图应用 Ken Burns 效果（ffmpeg zoompan），生成动态视频片段。

**Ken Burns 参数：**

| 参数 | 值 | 说明 |
|------|---|------|
| scale | 3200:-1 | 宽幅 3.2×，保证缩放平滑 |
| zoom_rate | 0.0003 | 每帧缩放增量（缓慢） |
| max_zoom | 1.3 | 最大缩放 30% |
| x_offset | +50px | 轻微右移 |
| y_offset | -30px | 轻微上移 |
| fade_in | 2s | 淡入 |
| fade_out | 2s | 淡出 |
| 输出分辨率 | 1280×720 | 统一分辨率 |
| fps | 25 | 标准帧率 |

**每张图生成的片段时长由 `scenes.json` 中该场景的 `duration` 字段决定**（来自 SRT 对齐）：
- 单场景：使用 SRT 该段的实际时长
- 变体图场景（`is_repeated=true`）：总时长 / 图数，多图 crossfade 拼接
- 加上 2s 淡入 + 2s 淡出
- 全片总时长 ≈ 歌曲音频总时长（典型 2-3 分钟）

## 📊 过程日志输出

本步骤在执行过程中向用户输出可读的进度日志，同时更新 `status.json`。

**日志级别：**

| 级别 | 格式 | 时机 |
|------|------|------|
| `🔄` | `[④ base] starting...` | 子步骤开始 |
| `🔄` | `[④ base] calling Image-01 API...` | 调用 API |
| `🔄` | `[④ base] API failed, retry 1/2 in 2s...` | API 重试中 |
| `🔄` | `[④ base] downloading...` | 下载图片 |
| `✅` | `[④ base] base_character.png (142KB)` | 完成 |
| `🔄` | `[⑤-⑦ images] scene 3/N: pre-chorus...` | 场景生成中（N = 总场景数） |
| `🔄` | `[⑤-⑦ images] scene 3/N: pre-chorus, retry 1/2 in 2s...` | 场景重试中 |
| `🔄` | `[⑤-⑦ images] scene 3/N: pre-chorus failed after 2 retries` | 场景跳过 |
| `✅` | `[⑤-⑦ images] completed: N/N scenes (0 failed)` | 全部成功 |
| `⚠️` | `[⑤-⑦ images] completed: (N-1)/N scenes (1 failed)` | 部分成功 |
| `🔄` | `[⑧ kb] clip 2/N: seg2_verse1...` | KB 处理中 |
| `✅` | `[⑧ kb] completed: N clips` | 完成 |
| `❌` | `[④ base] FAILED: <reason>` | 执行失败 |
| `❌` | `[⑤-⑦ images] FAILED: no scenes generated` | 执行失败 |
| `❌` | `[⑧ kb] FAILED: no clips generated` | 执行失败 |
| `⚠️` | `[④ base] interrupted: stopped by user` | 被用户打断 |

**打断检查点：** 每个子步骤开始前、API 调用前、下载前、重试间隔（每秒轮询）均检查打断信号。

**打断机制：** 详见 [SKILL.md — Unified Status Tracking](../SKILL.md#unified-status-tracking)。

## ⚙️ 其他要求

### 错误处理

| 错误类型 | 处理方式 |
|---------|---------|
| Image-01 API 失败（base） | 重试 2 次，间隔 2/4s，仍失败则脚本终止 |
| Image-01 API 失败（scene） | 每场景重试 2 次，仍失败则跳过，记录 `FAILED_SCENES` |
| KB 片段全部生成失败 | 脚本终止 |
| MINIMAX_TOKEN 未设置 | 脚本以非零退出码终止 |

### 边界条件

| 条件 | 说明 |
|------|------|
| 某个场景图 API 失败 | 跳过该场景，继续下一个 |
| 场景图已存在 | 跳过该场景（幂等性） |
| KB 片段已存在 | 跳过（幂等性） |

### 幂等性

本步骤是幂等的：
- 重复执行会覆盖已有的图片和片段
- 已存在的文件会被跳过（可重新生成缺失部分）

### 性能约束

| 子步骤 | 预期耗时 |
|--------|---------|
| ④ base | ~5 秒（含 1 次重试） |
| ⑤-⑦ images | N × ~8 秒（含失败重试），并行 4 路约缩短到 N/4 × 8 秒 |
| ⑧ kb | N × ~10 秒 |
| **总计** | 与 N 成线性，典型 ~2-4 分钟 |

## 🔗 Pipeline 位置

```
{project_dir}/metadata/info.json    ←─── Step②/③ 产出
        ↓
produce_mv.sh <project_dir>           ←─── Steps ④-⑧
        ↓
{project_dir}/
├── images/
│   ├── base_character.png            ←─── ④
│   └── seg{N}_{label}.png           ←─── ⑤-⑦
├── clips/
│   └── seg{N}_{label}_kb.mp4        ←─── ⑧
└── temp/                             ←─── (空，⑨ 由 merge_and_export.sh 写入)
        ↓
merge_and_export.sh <project_dir>    ←─── Steps ⑨-⑪
```

## 📜 执行脚本

脚本位于：
```
scripts/produce_mv.sh
```

共享状态函数库位于：
```
scripts/status_funcs.sh
```

脚本执行时 source `status_funcs.sh`，调用 `update_status()` 和 `check_interrupt()` 更新状态和检查打断。不要复制或内联此脚本 — 直接运行。

## → 下一步

**→ Steps ⑨-⑪: Merge & Export**

阅读 `references/merge-workflow.md` 并执行：
```bash
./merge_and_export.sh <project_dir>
```
