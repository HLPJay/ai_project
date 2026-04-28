# Merge & Export (Steps ⑨-⑪)

## 🎯 目标

将 Ken Burns 片段拼接为原始视频，合并音频与字幕，导出 TikTok/YouTube 适用版本。

**关键特性：** 步骤⑨需要访问 `clips/` 目录（由 `produce_mv.sh` 产出），因此执行顺序为：
1. 先执行 `produce_mv.sh`（Steps ④-⑧）
2. 再执行 `merge_and_export.sh`（Steps ⑨-⑪）

## 📦 边界

**输入：**
- `{project_dir}/clips/*_kb.mp4` — produce_mv.sh 产出
- `{project_dir}/audio/song.mp3` — Step② 产出
- `{project_dir}/audio/song.srt` — Step③ 产出（用于质量校验，若行数 < 5 则终止执行）

**本步骤产出：**
- `{project_dir}/temp/video_raw.mp4`
- `{project_dir}/output/final.mp4`（软字幕）
- `{project_dir}/output/tiktok.mp4`（硬字幕横屏）
- `{project_dir}/output/vertical.mp4`（硬字幕竖屏）

**本步骤不负责：**
- 图片生成（Step④-⑦）
- Ken Burns 效果（Step⑧）

## 📝 步骤

### Step ⑨: 拼接视频

将 `clips/` 目录下的所有 `*_kb.mp4` 片段按文件名排序，用 ffmpeg concat 拼接为 `temp/video_raw.mp4`。

```bash
ffmpeg -y -f concat -safe 0 -i concat_list.txt \
    -c:v libx264 -preset ultrafast -crf 20 -pix_fmt yuv420p \
    temp/video_raw.mp4
```

**concat_list.txt 格式：**
```
file 'seg1_intro_kb.mp4'
file 'seg2_verse1_kb.mp4'
...
```

### Step ⑩: 合并音视频 + 字幕

将 `temp/video_raw.mp4` 与 `audio/song.mp3` 合并，有 SRT 时嵌入软字幕，输出 `output/final.mp4`。

| 场景 | 处理方式 |
|------|---------|
| 有 SRT | 软字幕封装（mov_text） |
| 无 SRT | 纯音视频合并 |

```bash
ffmpeg -y -i temp/video_raw.mp4 \
    -i audio/song.mp3 \
    -i audio/song.srt \
    -c:v libx264 -c:a aac -c:s mov_text \
    output/final.mp4
```

### Step ⑪: 导出 TikTok 版本

从 `final.mp4` 导出两个版本：

**tiktok.mp4（横屏 1280×720，硬字幕）：**
```bash
ffmpeg -y -i output/final.mp4 \
    -vf "subtitles=${SRT_ESCAPED}:force_style='...' " \
    -c:v libx264 -preset medium -crf 20 \
    output/tiktok.mp4
```

**vertical.mp4（竖屏 1080×1920，硬字幕）：**
```bash
ffmpeg -y -i output/tiktok.mp4 \
    -vf "scale=1080:-1,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black" \
    output/vertical.mp4
```

**字幕路径转义：** SRT 路径通过 Python JSON 转义（`json.dumps` + 去引号），防止空格和特殊字符导致 ffmpeg 解析失败。

## 📊 过程日志输出

本步骤在执行过程中向用户输出可读的进度日志，同时更新 `status.json`。

**日志级别：**

| 级别 | 格式 | 时机 |
|------|------|------|
| `🔄` | `[⑨ concat] starting...` | 子步骤开始 |
| `🔄` | `[⑨ concat] concatenating...` | ffmpeg 执行中 |
| `✅` | `[⑨ concat] completed: video_raw.mp4 (24MB, 189s)` | 成功完成 |
| `🔄` | `[⑩ merge] starting...` | 子步骤开始 |
| `🔄` | `[⑩ merge] with SRT subtitles...` | 有字幕合并 |
| `🔄` | `[⑩ merge] without subtitles...` | 无字幕合并 |
| `✅` | `[⑩ merge] completed: final.mp4 (24MB, 167s)` | 成功完成 |
| `🔄` | `[⑪ export] starting...` | 子步骤开始 |
| `🔄` | `[⑪ export] tiktok.mp4...` | 导出横屏版 |
| `🔄` | `[⑪ export] vertical.mp4...` | 导出竖屏版 |
| `✅` | `[⑪ export] completed: tiktok=26MB, vertical=18MB` | 成功完成 |
| `❌` | `[⑨ concat] FAILED: no KB clips found` | 执行失败 |
| `❌` | `[⑩ merge] FAILED` | 执行失败 |
| `⚠️` | `[⑨ concat] interrupted: stopped by user` | 被用户打断 |

**打断检查点：** 脚本在每个子步骤开始前和关键节点前调用 `check_interrupt()`。

**打断机制：** 详见 [SKILL.md — Unified Status Tracking](../SKILL.md#unified-status-tracking)。

**ffmpeg 日志：** 所有 ffmpeg 的 stdout 和 stderr 写入 `{project_dir}/metadata/ffmpeg.log`。

## ⚙️ 其他要求

### 错误处理

| 错误类型 | 处理方式 |
|---------|---------|
| `clips/` 目录为空 | 脚本终止，输出 "no KB clips found" |
| ffmpeg concat 失败 | 错误写入 ffmpeg.log，脚本终止 |
| ffmpeg merge 失败 | 错误写入 ffmpeg.log，脚本终止 |
| ffmpeg export 失败 | 错误写入 ffmpeg.log，脚本终止 |
| `song.mp3` 不存在 | 脚本以非零退出码终止 |
| SRT 路径含空格 | 通过 JSON 引号转义处理 |

### 边界条件

| 条件 | 说明 |
|------|------|
| `clips/*_kb.mp4` 不存在 | 脚本终止 |
| `song.mp3` 不存在 | 脚本终止 |
| SRT 不存在 | 跳过软字幕封装 / 硬烧录（tiktok 由 final.mp4 复制） |
| SRT 路径含空格 | JSON 转义处理 |

### 幂等性

本步骤是幂等的：
- 重复执行会覆盖已有的 `output/final.mp4`、`output/tiktok.mp4`、`output/vertical.mp4`
- `temp/video_raw.mp4` 每次重新生成

### 性能约束

| 子步骤 | 预期耗时 |
|--------|---------|
| ⑨ concat | ~10 秒 |
| ⑩ merge | ~10 秒 |
| ⑪ export | ~20 秒 |
| **总计** | **~40 秒** |

## 🔗 Pipeline 位置

```
produce_mv.sh <project_dir>      ←─── Steps ④-⑧ 产出 clips/*_kb.mp4
        ↓
merge_and_export.sh <project_dir>  ←─── Steps ⑨-⑪
        ↓
{project_dir}/
├── temp/video_raw.mp4           ←─── ⑨ 产出
└── output/
    ├── final.mp4               ←─── ⑩ 产出
    ├── tiktok.mp4             ←─── ⑪ 产出
    └── vertical.mp4            ←─── ⑪ 产出
```

## 📜 执行脚本

脚本位于：
```
scripts/merge_and_export.sh
```

共享状态函数库位于：
```
scripts/status_funcs.sh
```

脚本执行时 source `status_funcs.sh`，调用 `update_status()` 和 `check_interrupt()` 更新状态和检查打断。不要复制或内联此脚本 — 直接运行。

## → Pipeline 结束

合并+导出完成后，最终 MV 文件位于 `output/` 目录。流程结束。

如需单独重新导出 TikTok 版本，可使用：
```bash
./assemble_mv.sh -p <project_dir> -o output/assembled.mp4  # 拼接（带黑场）
./burn_subtitle.sh -p <project_dir> -i output/final.mp4 -s audio/song.srt -o output/tiktok.mp4  # 重新烧录
```
