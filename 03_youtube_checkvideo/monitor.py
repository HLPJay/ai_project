"""
monitor.py - 频道监控 + 报告推送
每隔 2 小时检测订阅频道的新视频，生成报告并推送给订阅用户
"""

import os
import logging
import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

import requests

from db import (
    get_all_channels,
    get_channel_subscribers,
    is_video_processed,
    mark_video_processed,
)
from local_transcript import get_transcript
from generate_report import generate_report

logger = logging.getLogger(__name__)

# YouTube RSS 地址模板
YT_RSS = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

# 只处理最近 N 小时内发布的视频（避免历史视频刷屏）
MAX_VIDEO_AGE_HOURS = 26


# ============================================================
# 工具函数
# ============================================================

def get_channel_info(url: str) -> dict | None:
    """
    通过 yt-dlp 从频道 URL 获取 channel_id 和 channel_name
    支持格式：
      https://youtube.com/@channelname
      https://youtube.com/channel/UCxxxxxxx
      https://youtube.com/c/channelname
    """
    try:
        import yt_dlp
        opts = {
            'quiet': True,
            'skip_download': True,
            'extract_flat': True,
            'playlistend': 1,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            # 频道页面返回的 info 结构
            channel_id   = info.get('channel_id') or info.get('id', '')
            channel_name = info.get('channel') or info.get('uploader') or info.get('title', '')
            if channel_id:
                return {
                    'channel_id':   channel_id,
                    'channel_name': channel_name,
                    'channel_url':  url,
                }
    except Exception as e:
        logger.error(f"获取频道信息失败 [{url}]: {e}")
    return None


def fetch_rss_videos(channel_id: str) -> list:
    """
    从 YouTube RSS 获取频道最新视频列表

    返回：
    [
        {'video_id': 'xxx', 'title': 'xxx', 'published': datetime, 'url': 'xxx'},
        ...
    ]
    """
    rss_url = YT_RSS.format(channel_id=channel_id)
    try:
        resp = requests.get(rss_url, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"RSS 请求失败 [{channel_id}]: {e}")
        return []

    ns = {
        'atom': 'http://www.w3.org/2005/Atom',
        'yt':   'http://www.youtube.com/xml/schemas/2015',
        'media':'http://search.yahoo.com/mrss/',
    }

    videos = []
    try:
        root = ET.fromstring(resp.content)
        for entry in root.findall('atom:entry', ns):
            video_id  = entry.findtext('yt:videoId', namespaces=ns, default='')
            title     = entry.findtext('atom:title', namespaces=ns, default='')
            published = entry.findtext('atom:published', namespaces=ns, default='')
            url       = f"https://www.youtube.com/watch?v={video_id}"

            # 解析发布时间
            pub_dt = None
            if published:
                try:
                    pub_dt = datetime.fromisoformat(published.replace('Z', '+00:00'))
                except ValueError:
                    pass

            if video_id:
                videos.append({
                    'video_id':  video_id,
                    'title':     title,
                    'published': pub_dt,
                    'url':       url,
                })
    except ET.ParseError as e:
        logger.error(f"RSS 解析失败 [{channel_id}]: {e}")

    return videos


def is_recent(pub_dt, max_hours: int = MAX_VIDEO_AGE_HOURS) -> bool:
    """判断视频是否在指定小时内发布"""
    if pub_dt is None:
        return True  # 无法判断时间则视为新视频
    now = datetime.now(timezone.utc)
    return (now - pub_dt) <= timedelta(hours=max_hours)


def esc(text: str) -> str:
    """HTML 特殊字符转义"""
    if not text:
        return ''
    return (str(text)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;'))


def format_push_message(title: str, channel_name: str,
                         report: dict, video_url: str) -> str:
    """格式化推送消息（HTML）"""
    r       = report
    worthy  = r.get('watch_worthy', True)
    verdict = '✅ 值得看' if worthy else '⏭️ 可跳过'

    lines = [
        f"🔔 <b>新视频来了！</b>",
        '',
        f"📺 <b>{esc(title)}</b>",
        f"频道：{esc(channel_name)}",
        '',
        '━━━━━━━━━━━━━━━━',
        '',
        f"💡 <b>核心观点</b>",
        esc(r.get('core_thesis', '')),
        '',
        f"📌 <b>关键要点</b>",
    ]

    for i, point in enumerate(r.get('key_points', []), 1):
        lines.append(f"{i}. {esc(point)}")

    lines += [
        '',
        f"<b>{verdict}</b>",
        esc(r.get('reason', '')),
        '',
        f"🔗 <a href='{video_url}'>查看原视频</a>",
    ]

    text = '\n'.join(lines)
    if len(text) > 3800:
        text = text[:3750] + '\n...'
    return text


# ============================================================
# 主监控任务
# ============================================================

async def check_and_push(app):
    """
    定时任务主函数：
      1. 获取所有订阅频道
      2. 拉取 RSS，找到未处理的新视频
      3. 生成报告
      4. 推送给所有订阅该频道的用户
    """
    channels = get_all_channels()
    if not channels:
        logger.info("没有订阅频道，跳过本次检测")
        return

    logger.info(f"开始检测 {len(channels)} 个频道...")

    for ch in channels:
        channel_id   = ch['channel_id']
        channel_name = ch['channel_name']

        videos = fetch_rss_videos(channel_id)
        logger.info(f"  {channel_name}：RSS 返回 {len(videos)} 条视频")

        for video in videos:
            video_id  = video['video_id']
            title     = video['title']
            video_url = video['url']

            # 跳过太旧的视频
            if not is_recent(video['published']):
                continue

            # 跳过已处理
            if is_video_processed(video_id):
                continue

            logger.info(f"  处理新视频：{title} [{video_id}]")

            # 生成报告（同步函数放线程池执行）
            loop = asyncio.get_event_loop()

            try:
                transcript_result = await loop.run_in_executor(
                    None, lambda: get_transcript(video_url)
                )

                if not transcript_result['success']:
                    logger.warning(f"  字幕获取失败：{transcript_result['error']}")
                    # 标记为已处理（避免反复重试失败的视频）
                    mark_video_processed(video_id, channel_id, title)
                    continue

                report = await loop.run_in_executor(
                    None,
                    lambda: generate_report(
                        transcript=transcript_result['text'],
                        title=title,
                        channel=channel_name,
                    )
                )

                if not report.get('success'):
                    logger.warning(f"  报告生成失败：{report.get('error')}")
                    mark_video_processed(video_id, channel_id, title)
                    continue

                # 推送给所有订阅用户
                subscribers = get_channel_subscribers(channel_id)
                msg_text = format_push_message(title, channel_name, report, video_url)

                for user_id in subscribers:
                    try:
                        await app.bot.send_message(
                            chat_id=user_id,
                            text=msg_text,
                            parse_mode='HTML',
                        )
                        logger.info(f"  已推送给用户 {user_id}")
                    except Exception as e:
                        logger.error(f"  推送失败 [{user_id}]: {e}")

                # 标记为已处理
                mark_video_processed(video_id, channel_id, title)

            except Exception as e:
                logger.error(f"  处理视频失败 [{video_id}]: {e}")

    logger.info("本次检测完成")
