"""
Telegram Bot - 视频报告助手
启动方式：python telegram_bot.py

依赖：pip install python-telegram-bot
需要代理访问 Telegram（国内环境）

Bot 支持的命令：
  /start          - 欢迎消息
  /watch [URL]    - 分析视频并返回报告
  /help           - 帮助信息
"""

import os
import sys
import io
import logging
import re

# 修复 Windows 中文编码
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ⚠️ CUDA 库路径
os.add_dll_directory(r"D:\claude_code\20260411_youtube_视频分析\venv\Lib\site-packages\nvidia\cublas\bin")
os.add_dll_directory(r"D:\claude_code\20260411_youtube_视频分析\venv\Lib\site-packages\nvidia\cudnn\bin")

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from local_transcript import get_transcript
from generate_report import generate_report

# ============================================================
# 配置
# ============================================================

BOT_TOKEN = "8733793389:AAG2xAA2U9UX9gd8zs_LAqq4zAt21lPGHkY"   # ← 替换成 BotFather 给你的 Token
PROXY_URL = "http://127.0.0.1:7888"  # ← 本地代理端口

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    encoding='utf-8',
)
logger = logging.getLogger(__name__)


# ============================================================
# HTML 格式工具
# ============================================================

def esc(text: str) -> str:
    """转义 HTML 特殊字符，防止消息解析出错"""
    if not text:
        return ''
    return (
        str(text)
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
    )


def format_report(data: dict) -> str:
    """把报告字典格式化成 Telegram HTML 消息"""
    r        = data.get('report', {})
    worthy   = r.get('watch_worthy', True)
    title    = data.get('title', '未知标题')
    channel  = data.get('channel', '')
    source   = '字幕' if data.get('source') == 'youtube_captions' else '语音转录'
    cached   = ' <i>(缓存)</i>' if data.get('cached') else ''
    verdict  = '✅ 值得看' if worthy else '⏭️ 可跳过'

    lines = [
        f"📺 <b>{esc(title)}</b>{cached}",
        f"频道：{esc(channel)} · 来源：{source}",
        '',
        '━━━━━━━━━━━━━━━━',
        '',
        '💡 <b>核心观点</b>',
        esc(r.get('core_thesis', '')),
        '',
        '📌 <b>关键要点</b>',
    ]

    for i, point in enumerate(r.get('key_points', []), 1):
        lines.append(f"{i}. {esc(point)}")

    lines += [
        '',
        '👥 <b>适合人群</b>',
        esc(r.get('target_audience', '')),
        '',
        f"<b>{verdict}</b>",
        esc(r.get('reason', '')),
    ]

    text = '\n'.join(lines)

    # 超长时截断（Telegram 单条限制 4096 字符）
    if len(text) > 3800:
        text = text[:3750] + '\n...'

    return text


# ============================================================
# Bot 命令处理
# ============================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start 命令"""
    text = (
        "👋 你好！我是 <b>视频雷达 Bot</b>\n\n"
        "发送 YouTube 链接给我，我帮你生成内容报告。\n\n"
        "支持的命令：\n"
        "/watch [URL] - 分析视频\n"
        "/help - 查看帮助"
    )
    await update.message.reply_text(text, parse_mode='HTML')


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/help 命令"""
    text = (
        "📖 <b>使用方法</b>\n\n"
        "<b>分析单个视频：</b>\n"
        "<code>/watch https://youtube.com/watch?v=xxx</code>\n\n"
        "<b>也可以直接发链接：</b>\n"
        "直接发送 YouTube 链接，Bot 自动识别并分析\n\n"
        "⏱ 有字幕的视频约 30 秒\n"
        "⏱ 无字幕视频需要几分钟（语音转录）"
    )
    await update.message.reply_text(text, parse_mode='HTML')


async def cmd_watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/watch [URL] 命令"""
    if not context.args:
        await update.message.reply_text(
            "请提供 YouTube 链接，例如：\n"
            "<code>/watch https://youtube.com/watch?v=xxx</code>",
            parse_mode='HTML'
        )
        return
    await _process_url(update, context.args[0])


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理普通消息：包含 YouTube 链接时自动分析"""
    text = update.message.text or ''
    match = re.search(
        r'https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w\-]+',
        text
    )
    if match:
        await _process_url(update, match.group())
    else:
        await update.message.reply_text(
            "发送 YouTube 链接给我，我帮你生成内容报告。\n"
            "或者使用 /help 查看帮助。"
        )


# ============================================================
# 核心处理流程
# ============================================================

async def _process_url(update: Update, url: str):
    """URL → 字幕 → 报告 → 发送"""

    # 发送初始进度消息
    msg = await update.message.reply_text("⏳ 正在处理，请稍候...")

    try:
        # 步骤一：提取字幕
        await msg.edit_text("⏳ 第 1 步 / 3：提取视频内容...")
        transcript_result = get_transcript(url)

        if not transcript_result['success']:
            await msg.edit_text(
                f"❌ 内容获取失败\n\n原因：{esc(transcript_result['error'])}\n\n"
                "可能是视频无字幕且语音识别失败，或视频不可访问。",
                parse_mode='HTML'
            )
            return

        # 步骤二：获取视频标题
        title, channel = '', ''
        try:
            import yt_dlp
            with yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True}) as ydl:
                info    = ydl.extract_info(url, download=False)
                title   = info.get('title', '')
                channel = info.get('channel', '')
        except Exception:
            pass

        src_label = '字幕' if transcript_result['source'] == 'youtube_captions' else '语音转录'
        await msg.edit_text(
            f"⏳ 第 2 步 / 3：AI 分析中...\n"
            f"内容来源：{src_label}，{transcript_result['word_count']} 词"
        )

        # 步骤三：生成报告
        report = generate_report(
            transcript=transcript_result['text'],
            title=title,
            channel=channel,
        )

        if not report.get('success'):
            await msg.edit_text(
                f"❌ 报告生成失败\n\n原因：{esc(report.get('error', '未知错误'))}",
                parse_mode='HTML'
            )
            return

        # 发送报告
        await msg.edit_text("⏳ 第 3 步 / 3：整理报告...")

        data = {
            'title':   title,
            'channel': channel,
            'source':  transcript_result['source'],
            'cached':  False,
            'report':  report,
        }

        report_text = format_report(data)
        await msg.edit_text(report_text, parse_mode='HTML')

        # 附上原视频链接
        await update.message.reply_text(f"🔗 原视频：{url}")

    except Exception as e:
        logger.error(f"处理失败: {e}", exc_info=True)
        await msg.edit_text(f"❌ 处理出错：{esc(str(e).splitlines()[0])}", parse_mode='HTML')


# ============================================================
# 启动
# ============================================================

def main():
    print("启动 Telegram Bot...")
    print(f"代理：{PROXY_URL}")
    print("按 Ctrl+C 停止\n")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .proxy(PROXY_URL)
        .get_updates_proxy(PROXY_URL)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help",  cmd_help))
    app.add_handler(CommandHandler("watch", cmd_watch))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
