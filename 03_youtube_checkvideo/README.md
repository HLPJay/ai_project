# 视频雷达

YouTube 视频内容分析工具——输入链接，自动提取字幕/转录内容，生成结构化报告，接入telegram，对话框交互信息。

个人原型探索：

1.通过接口获取youtube相关视频必要接口，获取视频文件内容，通过大模型解析提取文案要点，使用代码生成对应卡片。

2.接入telegram工具，使用对话框的方式和需求进行交互，支持/help,/list,/watch,/sub,/unsub等指令，待完善。

3.这里提取视频内容通过字幕/语言转文字（接入了**本地大模型** faster-whisper [ faster-whisper-medium](https://huggingface.co/Systran/faster-whisper-medium)），生成报告卡片是代码实现的。

4.**关注代码问题**，代码防护需要关注启动多个实例时的异常，关注后台进程；高并发性能可优化；更智能的命令支持（入口/定时器/线程池等逻辑）。

5.产品的可优化：比如更合理的获取信息能力，相关关键报告转为语音的能力，借助数据库存储的能力，临时缓存的能力。

====》核心遗留的问题可能有，第一，网络代理导致请求失败的问题。 2.本地大模型gpu问题导致内存问题。

6.基于项目进展，需要考虑ai架构使用逻辑：

===》 CLAUDE.md  ===》PLAN.md ===》tasks/STATUS.md ===》上下文污染问题，需要把踩过的坑记忆。

7.注意，还得考虑**日志和监控功能**。 需要用性能参数进行说明。



====》这里现阶段本质问题是代理的问题。



核心成果演示：

比如通过后台服务器实现前端页面的控制获取信息，这里用到了本地数据库进行处理：

```
(venv) PS D:\claude_code\20260411_youtube_视频分析> uvicorn server:app --reload --port 8000
INFO:     Will watch for changes in these directories: ['D:\\claude_code\\20260411_youtube_视频分析']
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [41056] using StatReload
INFO:     Started server process [23268]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     127.0.0.1:50287 - "GET / HTTP/1.1" 200 OK
INFO:     127.0.0.1:62247 - "GET /.well-known/appspecific/com.chrome.devtools.json HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:56992 - "GET / HTTP/1.1" 200 OK
INFO:     127.0.0.1:56992 - "GET /.well-known/appspecific/com.chrome.devtools.json HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:56992 - "GET /api/reports HTTP/1.1" 200 OK
INFO:     127.0.0.1:56992 - "GET /favicon.ico HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:59943 - "GET /api/process?url=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3DkoRzYM3R-gg HTTP/1.1" 200 OK
INFO:     127.0.0.1:59943 - "GET /api/reports HTTP/1.1" 200 OK
INFO:     127.0.0.1:56763 - "GET /api/process?url=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3D95MHV2LvISs HTTP/1.1" 200 OK
WARNING: [youtube] No supported JavaScript runtime could be found. Only deno is enabled by default; to use another runtime add  --js-runtimes RUNTIME[:PATH]  to your command/config. YouTube extraction without a JS runtime has been deprecated, and some formats may be missing. See  https://github.com/yt-dlp/yt-dlp/wiki/EJS  for details on installing one
[ 路径1 ] 尝试获取 YouTube 字幕...
  ✅ 字幕获取成功（400 词）
INFO:     127.0.0.1:56763 - "GET /api/reports HTTP/1.1" 200 OK
```

核心效果如图：

![image-20260413090742718](C:\Users\yun68\AppData\Roaming\Typora\typora-user-images\image-20260413090742718.png)

使用telegram进行测试（这里要注意后台代码运行逻辑）

![image-20260413091255170](C:\Users\yun68\AppData\Roaming\Typora\typora-user-images\image-20260413091255170.png)

---

## 项目入口（三种使用方式）

| 入口 | 启动命令 | 说明 |
|------|----------|------|
| **Telegram Bot** | `python telegram_bot_last.py` | 最主要入口，支持订阅频道自动推送 |
| **Web API** | `uvicorn server:app --reload --port 8000` | FastAPI 网页服务，支持 SSE 进度流 |
| **命令行** | `python main.py` | 手动处理单个视频，报告存档到 `reports/` |

---

## 核心模块

| 文件 | 职责 |
|------|------|
| `local_transcript.py` | 字幕提取（入口函数：`get_transcript`）<br>① 优先 YouTube 字幕（秒级）<br>② 无字幕 → yt-dlp 下载音频 + faster-whisper 本地转录 |
| `generate_report.py` | AI 报告生成（入口函数：`generate_report`）<br>调用 DeepSeek API，输出核心观点 / 关键要点 / 详细笔记 / 适合人群 / 是否值得看 |
| `monitor.py` | 频道监控（入口函数：`check_and_push`）<br>通过 YouTube RSS 检测新视频，触发报告生成并推送 Telegram 用户 |
| `db.py` | 数据库（`reports.db`）<br>订阅管理（subscriptions 表）<br>已处理视频去重（processed_videos 表） |
| `server.py` | FastAPI Web 服务<br>`GET /api/process?url=...` — SSE 进度流处理视频<br>`GET /api/reports` — 查询历史报告<br>`DELETE /api/reports/{video_id}` — 删除报告 |
| `telegram_bot_last.py` | Telegram Bot 主入口 |

---

## Telegram Bot 命令

| 命令 | 说明 |
|------|------|
| `/start` `/help` | 欢迎与帮助 |
| `/watch [URL]` | 分析单个视频 |
| `/sub [频道URL]` | 订阅频道（支持 `@channelname` 或 `/channel/UCxxx` 格式） |
| `/unsub` | 取消订阅（交互式选择） |
| `/list` | 查看当前订阅列表 |

订阅后每 **2 小时**自动检测频道新视频，有新内容时主动推送报告。

---

## 字幕 / 转录流程（`local_transcript.py`）

```
URL 输入
   │
   ▼
extract_video_id(url)          解析出 video_id
   │
   ▼
路径一：YouTube 字幕
   ├── get_from_captions()     youtube-transcript-api
   └── 成功 → 直接返回（秒级）
   │
   ▼（字幕不可用时）
路径二：faster-whisper 本地转录
   ├── download_audio()        yt-dlp 下载 m4a/webm 音频
   └── transcribe_local()      faster-whisper medium 模型转录
                                （首次运行自动下载 ~1.5GB 模型）
```

---

## 数据流总览

```
用户输入 YouTube URL
    │
    ├─→ Telegram Bot (telegram_bot_last.py)
    │       │
    │       ├→ get_transcript()      提取字幕
    │       ├→ generate_report()      AI 生成报告
    │       └→ Bot 推送报告给用户
    │
    ├─→ Web API (server.py)
    │       │
    │       ├→ get_transcript()
    │       ├→ generate_report()
    │       └→ SSE 流式推送进度 → 前端展示
    │
    └─→ 命令行 (main.py)
            │
            ├→ get_transcript()
            ├→ generate_report()
            └→ 报告存档至 reports/*.json

频道订阅监控（定时任务，每 2 小时）
    │
    ├→ fetch_rss_videos()      拉取 YouTube RSS
    ├→ get_transcript()
    ├→ generate_report()
    └→ Bot 主动推送报告给订阅用户
```

---

## 环境与依赖

```
Python ≥ 3.10
CUDA + cuDNN（faster-whisper GPU 加速用）
```

**核心依赖：**
- `faster-whisper` — 本地语音转录
- `yt-dlp` — 音频下载
- `youtube-transcript-api` — YouTube 字幕获取
- `python-telegram-bot` — Telegram Bot
- `apscheduler` — 定时任务
- `openai` — DeepSeek API 调用
- `fastapi` + `uvicorn` — Web 服务

**安装：**
```bash
pip install faster-whisper yt-dlp youtube-transcript-api \
            python-telegram-bot apscheduler openai fastapi uvicorn
```

**本地代理**（必须）：本项目所有 HTTP 请求通过本地代理发出，请在 `.env` 或代码中配置：
```python
PROXY_URL = "http://127.0.0.1:7888"   # telegram_bot_last.py 第 46 行
```

---

## 配置文件关键项

| 配置项 | 位置 | 说明 |
|--------|------|------|
| `BOT_TOKEN` | `telegram_bot_last.py:45` | Telegram Bot Token（BotFather 获取） |
| `PROXY_URL` | `telegram_bot_last.py:46` | 本地代理地址 |
| `CHECK_INTERVAL_HOURS` | `telegram_bot_last.py:47` | 频道检测频率，默认 2 小时 |
| `DEEPSEEK_API_KEY` | `generate_report.py:9` | DeepSeek API 密钥 |
| `DB_PATH` | `db.py:9` | SQLite 数据库路径（`reports.db`） |

# 个人汇总
## 指令汇总
### 第一步：在项目目录下创建虚拟环境（只做一次）
cd D:\claude_code\20260411_youtube_视频分析
python -m venv venv

### 第二步：激活虚拟环境
venv\Scripts\activate

### 激活后命令行前面会出现 (venv) 字样，说明成功了

### 第三步：正常 pip install，就会装到当前目录的 venv 文件夹里
这里其他文件中还有pip依赖其他的库,按需进行安装。
pip install faster-whisper yt-dlp youtube-transcript-api

### 先退出虚拟环境
deactivate

### 使用指令测试环境是否正常 注意代理
C:\Users\yun68>curl -x http://127.0.0.1:7888 https://api.telegram.org/bot8733793389:AAG2xAA2U9UX9gd8zs_LAqq4zAt21lPGHkY/getMe
{"ok":true,"result":{"id":8733793389,"is_bot":true,"first_name":"\u5927\u9e4f\u7684\u673a\u5668\u4eba","username":"handapeng_bot","can_join_groups":true,"can_read_all_group_messages":false,"supports_inline_queries":false,"can_connect_to_business":false,"has_main_web_app":false,"has_topics_enabled":false,"allows_users_to_create_topics":false,"can_manage_bots":false}}

### 需要关注这里的服务和后台运行个数，代码需要加防护，以及高并发处理

C:\Users\yun68>tasklist|findstr python