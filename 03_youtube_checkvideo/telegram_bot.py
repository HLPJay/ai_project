"""
Telegram Bot - 视频报告助手（含频道订阅 + 定时推送）
启动方式：python telegram_bot.py
依赖：pip install python-telegram-bot apscheduler requests
"""

import os, sys, io, logging, re, asyncio

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

os.add_dll_directory(r"D:\claude_code\20260411_youtube_视频分析\venv\Lib\site-packages\nvidia\cublas\bin")
os.add_dll_directory(r"D:\claude_code\20260411_youtube_视频分析\venv\Lib\site-packages\nvidia\cudnn\bin")

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from db import init_db, add_subscription, remove_subscription, get_user_subscriptions
from monitor import get_channel_info, check_and_push
from local_transcript import get_transcript
from generate_report import generate_report

# ============================================================
# 配置
# ============================================================

BOT_TOKEN = "8733793389:AAG2xAA2U9UX9gd8zs_LAqq4zAt21lPGHkY"   # ← 替换成 BotFather 给你的 Token
PROXY_URL = "http://127.0.0.1:7888"  # ← 本地代理端口
CHECK_INTERVAL_HOURS = 2

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    encoding='utf-8',
)
logger = logging.getLogger(__name__)


# ============================================================
# HTML 工具
# ============================================================

def esc(text: str) -> str:
    if not text:
        return ''
    return str(text).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')


def fmt(data: dict) -> str:
    r       = data.get('report', {})
    worthy  = r.get('watch_worthy', True)
    verdict = '✅ 值得看' if worthy else '⏭️ 可跳过'
    cached  = ' <i>(缓存)</i>' if data.get('cached') else ''
    source  = '字幕' if data.get('source') == 'youtube_captions' else '语音转录'

    lines = [
        f"📺 <b>{esc(data.get('title','未知标题'))}</b>{cached}",
        f"频道：{esc(data.get('channel',''))} · 来源：{source}",
        '',
        '━━━━━━━━━━━━━━━━',
        '',
        '💡 <b>核心观点</b>',
        esc(r.get('core_thesis', '')),
        '',
        '📌 <b>关键要点</b>',
    ]
    for i, p in enumerate(r.get('key_points', []), 1):
        lines.append(f"{i}. {esc(p)}")
    lines += [
        '',
        '👥 <b>适合人群</b>',
        esc(r.get('target_audience', '')),
        '',
        f"<b>{verdict}</b> — {esc(r.get('reason',''))}",
    ]
    text = '\n'.join(lines)
    return text[:3800] + '\n...' if len(text) > 3800 else text


# ============================================================
# /start  /help
# ============================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 你好！我是 <b>视频雷达 Bot</b>\n\n"
        "发 YouTube 链接给我，我帮你生成内容报告。\n"
        "订阅频道后，有新视频时我会主动推送给你。\n\n"
        "<b>命令列表</b>\n"
        "/watch [URL] — 分析单个视频\n"
        "/sub [URL]   — 订阅频道\n"
        "/unsub       — 取消订阅\n"
        "/list        — 查看订阅\n"
        "/help        — 帮助",
        parse_mode='HTML',
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 <b>使用说明</b>\n\n"
        "<b>分析视频</b>\n"
        "<code>/watch https://youtube.com/watch?v=xxx</code>\n\n"
        "<b>订阅频道</b>\n"
        "<code>/sub https://youtube.com/@channelname</code>\n\n"
        "<b>查看/取消订阅</b>\n"
        "<code>/list</code>  <code>/unsub</code>\n\n"
        "⏱ 有字幕约 30 秒，无字幕需要几分钟\n"
        "🔔 订阅后每隔 2 小时自动检测新视频",
        parse_mode='HTML',
    )


# ============================================================
# /watch
# ============================================================

async def cmd_watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "请提供 YouTube 链接：\n"
            "<code>/watch https://youtube.com/watch?v=xxx</code>",
            parse_mode='HTML',
        )
        return
    await _process_url(update, context.args[0])


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text  = update.message.text or ''
    match = re.search(
        r'https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w\-]+', text
    )
    if match:
        await _process_url(update, match.group())
    else:
        await update.message.reply_text(
            "发送 YouTube 链接，或 /help 查看帮助。"
        )


async def _process_url(update: Update, url: str):
    """核心流程：URL → 字幕 → 报告 → 发送"""
    msg = await update.message.reply_text("⏳ 正在处理，请稍候...")
    loop = asyncio.get_event_loop()

    try:
        # 步骤1：提取字幕
        await msg.edit_text("⏳ 步骤 1/3：提取视频内容")
        transcript_result = await loop.run_in_executor(
            None, lambda: get_transcript(url)
        )

        if not transcript_result['success']:
            await msg.edit_text(
                f"❌ <b>内容获取失败</b>\n\n{esc(transcript_result['error'])}",
                parse_mode='HTML',
            )
            return

        # 步骤2：获取视频信息
        title, channel = '', ''
        try:
            import yt_dlp
            def _info():
                with yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True}) as ydl:
                    info = ydl.extract_info(url, download=False)
                    return info.get('title', ''), info.get('channel', '')
            title, channel = await loop.run_in_executor(None, _info)
        except Exception:
            pass

        src = '字幕' if transcript_result['source'] == 'youtube_captions' else '语音转录'
        await msg.edit_text(
            f"⏳ 步骤 2/3：AI 分析中（{src}，{transcript_result['word_count']} 词）"
        )

        # 步骤3：生成报告
        report = await loop.run_in_executor(
            None,
            lambda: generate_report(
                transcript=transcript_result['text'],
                title=title,
                channel=channel,
            )
        )

        if not report.get('success'):
            await msg.edit_text(
                f"❌ <b>报告生成失败</b>\n\n{esc(report.get('error',''))}",
                parse_mode='HTML',
            )
            return

        await msg.edit_text("⏳ 步骤 3/3：整理报告...")

        await msg.edit_text(
            fmt({'title': title, 'channel': channel,
                 'source': transcript_result['source'],
                 'cached': False, 'report': report}),
            parse_mode='HTML',
        )
        await update.message.reply_text(f"🔗 原视频：{url}")

    except Exception as e:
        logger.error(f"处理失败: {e}", exc_info=True)
        try:
            await msg.edit_text(
                f"❌ <b>处理出错</b>\n\n{esc(str(e).splitlines()[0])}",
                parse_mode='HTML',
            )
        except Exception:
            pass


# ============================================================
# /sub  /unsub  /list
# ============================================================

async def cmd_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "请提供频道链接：\n"
            "<code>/sub https://youtube.com/@channelname</code>",
            parse_mode='HTML',
        )
        return

    url = context.args[0]
    msg = await update.message.reply_text("⏳ 正在获取频道信息...")
    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(None, lambda: get_channel_info(url))

    if not info:
        await msg.edit_text(
            "❌ 无法识别该频道，请确认链接格式：\n"
            "• https://youtube.com/@channelname\n"
            "• https://youtube.com/channel/UCxxxxxxx",
            parse_mode='HTML',
        )
        return

    is_new = add_subscription(
        user_id=update.effective_user.id,
        channel_id=info['channel_id'],
        channel_name=info['channel_name'],
        channel_url=url,
    )

    if is_new:
        await msg.edit_text(
            f"✅ 订阅成功！\n\n"
            f"频道：<b>{esc(info['channel_name'])}</b>\n\n"
            f"有新视频时我会自动推送报告（每 {CHECK_INTERVAL_HOURS} 小时检测一次）",
            parse_mode='HTML',
        )
    else:
        await msg.edit_text(
            f"你已经订阅了 <b>{esc(info['channel_name'])}</b>",
            parse_mode='HTML',
        )


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subs = get_user_subscriptions(update.effective_user.id)
    if not subs:
        await update.message.reply_text(
            "你还没有订阅任何频道。\n使用 <code>/sub [频道URL]</code> 订阅",
            parse_mode='HTML',
        )
        return

    lines = ['📋 <b>我的订阅</b>\n']
    for i, s in enumerate(subs, 1):
        lines.append(f"{i}. <b>{esc(s['channel_name'])}</b>")
        lines.append(f"   订阅于 {s['created_at'][:10]}")
    lines.append('\n使用 /unsub 取消订阅')
    await update.message.reply_text('\n'.join(lines), parse_mode='HTML')


async def cmd_unsub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subs = get_user_subscriptions(update.effective_user.id)
    if not subs:
        await update.message.reply_text("你还没有订阅任何频道。")
        return

    keyboard = [
        [InlineKeyboardButton(
            f"❌ {s['channel_name']}",
            callback_data=f"unsub:{s['channel_id']}:{s['channel_name']}"
        )]
        for s in subs
    ]
    keyboard.append([InlineKeyboardButton("取消", callback_data="unsub:cancel:")])

    await update.message.reply_text(
        "选择要取消订阅的频道：",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def handle_unsub_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split(':', 2)
    if parts[1] == 'cancel':
        await query.edit_message_text("已取消操作")
        return

    channel_id   = parts[1]
    channel_name = parts[2] if len(parts) > 2 else '该频道'
    ok = remove_subscription(update.effective_user.id, channel_id)
    if ok:
        await query.edit_message_text(
            f"✅ 已取消订阅 <b>{esc(channel_name)}</b>",
            parse_mode='HTML',
        )
    else:
        await query.edit_message_text("❌ 取消失败，请重试")


# ============================================================
# 定时任务
# ============================================================

_scheduler: AsyncIOScheduler | None = None

async def on_startup(app: Application):
    """Bot 启动后初始化调度器"""
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone='Asia/Shanghai')

    async def job():
        logger.info("定时任务触发：开始检测频道更新")
        await check_and_push(app)

    _scheduler.add_job(
        job,
        trigger='interval',
        hours=CHECK_INTERVAL_HOURS,
        id='channel_monitor',
        max_instances=1,
        misfire_grace_time=300,
    )
    _scheduler.start()
    logger.info(f"定时任务已启动，每 {CHECK_INTERVAL_HOURS} 小时检测一次")


async def on_shutdown(app: Application):
    """Bot 停止时关闭调度器"""
    if _scheduler:
        _scheduler.shutdown(wait=False)


# ============================================================
# 启动
# ============================================================

def main():
    init_db()
    print("数据库初始化完成")
    print(f"启动 Telegram Bot...")
    print(f"代理：{PROXY_URL}")
    print(f"检测频率：每 {CHECK_INTERVAL_HOURS} 小时")
    print("按 Ctrl+C 停止\n")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .proxy(PROXY_URL)
        .get_updates_proxy(PROXY_URL)
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("watch",  cmd_watch))
    app.add_handler(CommandHandler("sub",    cmd_sub))
    app.add_handler(CommandHandler("unsub",  cmd_unsub))
    app.add_handler(CommandHandler("list",   cmd_list))
    app.add_handler(CallbackQueryHandler(handle_unsub_cb, pattern=r'^unsub:'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
