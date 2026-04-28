# Music Generation (Step ②)

## 🎯 目标

读取 Step① 生成的歌词文件，构造音乐风格 prompt，调用 MiniMax `music-2.6` API 生成完整歌曲，输出 MP3 文件并更新元数据中的时长信息。

**关键特性：** MiniMax `music_generation` API 是**同步**的——响应直接返回 hex 编码的 MP3 数据，无需轮询。

## 📦 边界

**输入：**
- `{project_dir}/audio/lyrics.txt` — Step① 产出

**本步骤产出：**
- `{project_dir}/audio/song.mp3`
- 更新 `{project_dir}/metadata/info.json`（`audio_duration_sec`）

**本步骤不负责：**
- 歌词生成（Step①）
- 歌词对齐（Step③）
- 视频制作（Step④-⑪）

## 📝 步骤

### Step 1: 读取歌词并预处理

从 `audio/lyrics.txt` 提取歌词正文：
1. 跳过所有 `## ` 开头的元数据行（两个 `#` + 空格）
2. 跳过其他以 `#` 开头的残留元数据行
3. 跳过空行
4. 保留 `[Verse]`, `[Chorus]` 等段落标记（帮助 API 理解结构）

```bash
LYRICS=$(grep -v '^## ' "$LYRICS_FILE" | grep -v '^#' | grep -v '^$' | paste -sd ' ' -)
```

### Step 2: 从 info.json 构造 prompt

prompt 必须**动态构造**，不得写死。

```
prompt = "{song_title}，{style_tags.join('，')}，{theme}"
```

**示例：**
```json
{
  "song_title": "童年小纸飞机",
  "style_tags": ["nostalgic", "warm", "childhood"],
  "theme": "童年回忆，温馨美好"
}
→ "童年小纸飞机，nostalgic，warm，childhood，童年回忆，温馨美好"
```

### Step 3: 调用 MiniMax /music_generation API

**请求：**
```
POST https://api.minimaxi.com/v1/music_generation
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model` | string | ✅ | 固定值：`music-2.6` |
| `prompt` | string | ✅ | 动态构造（见 Step 2） |
| `lyrics` | string | ✅ | 预处理后的歌词正文 |
| `is_instrumental` | bool | ✅ | 固定值：`false` |

**响应：**
| 字段 | 类型 | 说明 |
|------|------|------|
| `data.audio` | string | hex 编码的 MP3 音频字节 |
| `base_resp.status_code` | int | `0` = 成功，非0 = 错误 |

### Step 4: hex 解码并保存 MP3

将响应中的 `data.audio` 字段从 hex 转为字节，写入 `audio/song.mp3`。

### Step 5: 获取时长并更新 info.json

使用 ffprobe 读取 MP3 时长，写入 `info.json`：
```json
{
  "audio_duration_sec": 167
}
```

## 📊 过程日志输出

本步骤在执行过程中向用户输出可读的进度日志，同时更新 `status.json`。

**日志级别：**

| 级别 | 格式 | 时机 |
|------|------|------|
| `🔄` | `[② music] starting...` | 子步骤开始 |
| `🔄` | `[② music] reading lyrics...` | 读取歌词文件 |
| `🔄` | `[② music] calling music_generation API...` | 正在调用 API |
| `🔄` | `[② music] API failed, retry N/3 in Xs...` | API 失败重试中 |
| `🔄` | `[② music] API call succeeded` | API 调用成功 |
| `🔄` | `[② music] decoding audio...` | hex 解码中 |
| `🔄` | `[② music] updating metadata...` | 更新元数据 |
| `✅` | `[② music] completed: <size>, <duration>s` | 成功完成 |
| `❌` | `[② music] FAILED: <reason>` | 执行失败 |
| `⚠️` | `[② music] interrupted: <reason>` | 被用户打断 |

**子步骤检查点：** 脚本在每个子步骤开始前调用 `check_interrupt()`，发现打断信号则输出 `⚠️` 并以退出码 0 终止。

**打断机制：** 详见 [SKILL.md — Unified Status Tracking](../SKILL.md#unified-status-tracking)。

## ⚙️ 其他要求

### 错误处理

| 错误类型 | 处理方式 |
|---------|---------|
| API 返回 `status_code != 0` | 输出错误信息到日志，脚本以非零退出码终止 |
| API 无响应 / 超时 | curl `--max-time 120`，超时则视为失败（音乐生成较慢） |
| API 失败 | 重试 3 次，间隔 2/4/8 秒（指数退避） |
| 响应中无 `data.audio` | 输出错误信息，脚本终止 |
| 歌词文件为空 | 脚本输出错误并终止 |
| ffprobe 缺失 | 时长记为 0，不终止执行 |

### 边界条件

| 条件 | 说明 |
|------|------|
| `lyrics.txt` 不存在 | 脚本输出错误并以非零码退出 |
| `MINIMAX_TOKEN` 未设置 | 脚本输出错误并以非零码退出 |
| prompt 构造失败 | 脚本输出错误并以非零码退出 |
| lyrics.txt 为空 | 脚本输出错误并以非零码退出 |

### 幂等性

本步骤是幂等的：
- 重复执行会覆盖已有的 `audio/song.mp3` 和 `info.json`
- 适用于从失败点恢复或重新生成

### 性能约束

- API 调用预期耗时：30-90 秒（音乐生成较慢）
- 整体步骤预期耗时：< 3 分钟（含网络延迟和最多 3 次重试）

## 🔗 Pipeline 位置

```
{project_dir}/audio/lyrics.txt  ←─── Step ① 产出
        ↓
generate_music.sh <project_dir>  ←─── Step ② 读取 + 生成
        ↓
{project_dir}/audio/song.mp3     ←─── 产出
        ↓
align_lyrics.sh <project_dir>   ←─── Step ③ 读取
```

## 📜 执行脚本

脚本位于：
```
scripts/generate_music.sh
```

共享状态函数库位于：
```
scripts/status_funcs.sh
```

脚本执行时 source `status_funcs.sh`，调用 `update_status()` 和 `check_interrupt()` 更新状态和检查打断。不要复制或内联此脚本 — 直接运行。

## → 下一步

**→ Step ③: Lyrics Alignment**

阅读 `references/alignment-workflow.md` 并执行：
```bash
./align_lyrics.sh <project_dir>
```
