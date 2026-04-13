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

# 修复 Windows 中文编码
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ⚠️ CUDA 库路径（如果和 Whisper 在同一台机器上）
os.add_dll_directory(r"D:\claude_code\20260411_youtube_视频分析\venv\Lib\site-packages\nvidia\cublas\bin")
os.add_dll_directory(r"D:\claude_code\20260411_youtube_视频分析\venv\Lib\site-packages\nvidia\cudnn\bin")

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

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
# 报告格式化（Telegram Markdown）
# ============================================================

def format_report(data: dict) -> str:
    """
    把报告字典格式化成 Telegram 消息文本

    Telegram 单条消息限制 4096 字符，超出需要分条发送
    这里控制在 3500 字以内，保留余量
    """
    r = data.get('report', {})
    worthy = r.get('watch_worthy', True)
    worthy_text = '✅ 值得看' if worthy else '⏭️ 可跳过'

    title    = data.get('title', '未知标题')
    channel  = data.get('channel', '')
    source   = '字幕' if data.get('source') == 'youtube_captions' else '语音转录'
    cached   = ' (缓存)' if data.get('cached') else ''

    lines = [
        f"📺 *{escape_md(title)}*{cached}",
        f"频道：{escape_md(channel)} · 来源：{source}",
        '',
        '━━━━━━━━━━━━━━━━',
        '',
        '💡 *核心观点*',
        escape_md(r.get('core_thesis', '')),
        '',
        '📌 *关键要点*',
    ]

    for i, point in enumerate(r.get('key_points', []), 1):
        lines.append(f"{i}\\. {escape_md(point)}")

    lines += [
        '',
        '👥 *适合人群*',
        escape_md(r.get('target_audience', '')),
        '',
        f"*{worthy_text}*",
        escape_md(r.get('reason', '')),
    ]

    text = '\n'.join(lines)

    # 超长时截断
    if len(text) > 3500:
        text = text[:3450] + '\n\\.\\.\\.'

    return text


def escape_md(text: str) -> str:
    """转义 Telegram MarkdownV2 的特殊字符"""
    if not text:
        return ''
    special = r'\_*[]()~`>#+-=|{}.!'
    for ch in special:
        text = text.replace(ch, f'\\{ch}')
    return text


# ============================================================
# Bot 命令处理
# ============================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令"""
    text = (
        "👋 你好！我是*视频雷达 Bot*\n\n"
        "发送 YouTube 链接给我，我帮你生成内容报告。\n\n"
        "支持的命令：\n"
        "/watch \\[URL\\] \\- 分析视频\n"
        "/help \\- 查看帮助"
    )
    await update.message.reply_text(text, parse_mode='MarkdownV2')


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /help 命令"""
    text = (
        "📖 *使用方法*\n\n"
        "*分析单个视频：*\n"
        "`/watch https://youtube.com/watch?v=xxx`\n\n"
        "*也可以直接发链接：*\n"
        "直接发送 YouTube 链接，Bot 自动识别并分析\n\n"
        "⏱ 有字幕的视频约 30 秒，无字幕视频需要几分钟"
    )
    await update.message.reply_text(text, parse_mode='MarkdownV2')


async def cmd_watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /watch [URL] 命令"""
    args = context.args
    if not args:
        await update.message.reply_text(
            "请提供 YouTube 链接，例如：\n`/watch https://youtube.com/watch?v=xxx`",
            parse_mode='MarkdownV2'
        )
        return

    url = args[0]
    await _process_url(update, url)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理普通消息：如果包含 YouTube 链接，自动分析"""
    text = update.message.text or ''
    if 'youtube.com/watch' in text or 'youtu.be/' in text:
        # 从消息里提取 URL
        import re
        match = re.search(r'https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w-]+', text)
        if match:
            await _process_url(update, match.group())
            return

    await update.message.reply_text(
        "发送 YouTube 链接给我，我帮你生成内容报告。\n"
        "或者使用 /help 查看帮助。"
    )


async def _process_url(update: Update, url: str):
    """核心处理逻辑：URL → 报告 → 发送"""

    # 发送"处理中"提示
    processing_msg = await update.message.reply_text(
        "⏳ 正在处理，请稍候...\n"
        "_有字幕约 30 秒，无字幕需要几分钟_",
        parse_mode='MarkdownV2'
    )

    try:
        # 第一步：获取字幕
        await processing_msg.edit_text(
            "⏳ *第 1 步*：提取视频内容\\.\\.\\.",
            #parse_mode='MarkdownV2'
        )
        transcript_result = get_transcript(url)

        if not transcript_result['success']:
            await processing_msg.edit_text(
                f"❌ 内容获取失败：{escape_md(transcript_result['error'])}\n\n"
                "可能原因：视频无字幕且语音识别失败，或视频不可访问。",
                #parse_mode='MarkdownV2'
            )
            return

        # 自动获取标题
        title, channel = '', ''
        try:
            import yt_dlp
            with yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                title   = info.get('title', '')
                channel = info.get('channel', '')
        except Exception:
            pass

        # 第二步：生成报告
        src_label = '字幕' if transcript_result['source'] == 'youtube_captions' else '语音转录'
        await processing_msg.edit_text(
            f"⏳ *第 2 步*：AI 分析中\\.\\.\\.\n"
            f"_内容来源：{src_label}，{transcript_result['word_count']} 词_",
            #parse_mode='MarkdownV2'
        )

        report = generate_report(
            transcript=transcript_result['text'],
            title=title,
            channel=channel,
        )

        if not report.get('success'):
            await processing_msg.edit_text(
                f"❌ 报告生成失败：{escape_md(report.get('error', '未知错误'))}",
                #parse_mode='MarkdownV2'
            )
            return

        # 第三步：发送报告
        data = {
            'title': title,
            'channel': channel,
            'source': transcript_result['source'],
            'cached': False,
            'report': report,
        }
        report_text = format_report(data)
        await processing_msg.edit_text(report_text, parse_mode='MarkdownV2')

        # 附上原视频链接
        await update.message.reply_text(f"🔗 原视频：{url}")

    except Exception as e:
        logger.error(f"处理失败: {e}")
        await processing_msg.edit_text(
            f"❌ 处理出错：{escape_md(str(e).splitlines()[0])}",
            parse_mode='MarkdownV2'
        )


# ============================================================
# 启动 Bot
# ============================================================

def main():
    print("启动 Telegram Bot...")
    print(f"代理：{PROXY_URL}")
    print("按 Ctrl+C 停止\n")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .proxy(PROXY_URL)          # 设置代理
        .get_updates_proxy(PROXY_URL)
        .build()
    )

    # 注册命令处理器
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help",  cmd_help))
    app.add_handler(CommandHandler("watch", cmd_watch))

    # 处理普通消息（直接发链接）
    from telegram.ext import MessageHandler, filters
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # 启动
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
