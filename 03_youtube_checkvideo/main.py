"""
主流程：URL → 字幕 → 报告 → 存档
用法：python main.py
"""

import os
import json
import datetime

# ⚠️ 必须在最前面，让系统找到 CUDA 库
os.add_dll_directory(r"D:\claude_code\20260411_youtube_视频分析\venv\Lib\site-packages\nvidia\cublas\bin")
os.add_dll_directory(r"D:\claude_code\20260411_youtube_视频分析\venv\Lib\site-packages\nvidia\cudnn\bin")

from local_transcript import get_transcript
from generate_report import generate_report, print_report


# ============================================================
# 报告存档
# ============================================================

REPORTS_DIR = r"D:\claude_code\20260411_youtube_视频分析\reports"


def save_report(url: str, transcript_result: dict, report: dict):
    """把报告保存成 JSON 文件"""
    os.makedirs(REPORTS_DIR, exist_ok=True)

    # 用时间戳命名，避免重名
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}.json"
    filepath = os.path.join(REPORTS_DIR, filename)

    data = {
        'url': url,
        'created_at': timestamp,
        'transcript_source': transcript_result.get('source'),
        'word_count': transcript_result.get('word_count'),
        'transcript': transcript_result.get('text'),
        'report': report,
    }

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n📁 报告已保存：{filepath}")
    return filepath


# ============================================================
# 主流程
# ============================================================

def process_video(url: str, title: str = "", channel: str = "") -> dict:
    """
    完整流程：URL → 字幕 → 报告 → 存档

    参数：
      url     - YouTube 视频链接
      title   - 视频标题（可选，不填也能跑）
      channel - 频道名称（可选）
    """

    print(f"\n{'='*55}")
    print(f"开始处理：{url}")
    print(f"{'='*55}")

    # 第一步：获取字幕
    transcript_result = get_transcript(url)

    if not transcript_result['success']:
        print(f"\n❌ 字幕获取失败：{transcript_result['error']}")
        return {'success': False, 'error': transcript_result['error']}

    print(f"\n✅ 内容获取完成")
    print(f"   来源：{transcript_result['source']}")
    print(f"   词数：{transcript_result['word_count']}")

    # 第二步：生成报告
    print(f"\n⏳ 正在生成报告...")
    report = generate_report(
        transcript=transcript_result['text'],
        title=title,
        channel=channel,
    )

    if not report.get('success'):
        print(f"\n❌ 报告生成失败：{report.get('error')}")
        return {'success': False, 'error': report.get('error')}

    # 第三步：打印报告
    print_report(report)

    # 第四步：保存存档
    save_report(url, transcript_result, report)

    return {'success': True, 'report': report}

def get_video_info(url: str) -> dict:
    """自动获取视频标题、频道名等信息"""
    import yt_dlp

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,   # 只获取信息，不下载
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return {
            'title': info.get('title', ''),
            'channel': info.get('channel', ''),
            'duration': info.get('duration', 0),   # 秒
            'view_count': info.get('view_count', 0),
        }
    
def process_video(url: str) -> dict:

    # 自动获取视频信息
    print("获取视频信息...")
    info = get_video_info(url)
    print(f"标题：{info['title']}")
    print(f"频道：{info['channel']}")
    # 第一步：获取字幕
    # 后面不变，title 和 channel 自动传入
    transcript_result = get_transcript(url)
    report = generate_report(
        transcript=transcript_result['text'],
        title=info['title'],       # 自动填入
        channel=info['channel'],   # 自动填入
    )

    if not report.get('success'):
        print(f"\n❌ 报告生成失败：{report.get('error')}")
        return {'success': False, 'error': report.get('error')}

    # 第三步：打印报告
    print_report(report)

    # 第四步：保存存档
    save_report(url, transcript_result, report)

    return {'success': True, 'report': report}
# ============================================================
# 测试入口
# ============================================================

if __name__ == "__main__":

    # 测试1：有字幕的视频
    # process_video(
    #     url="https://www.youtube.com/watch?v=iG9CE55wbtY",
    #     title="Do schools kill creativity?",
    #     channel="TED",
    # )

    # 测试2：无字幕视频（触发 Whisper）
    # process_video(
    #     url="https://www.youtube.com/watch?v=RgGVHW7Qt6c",
    #     title="Hermes Agent 介绍",
    # )

    # process_video("https://www.youtube.com/watch?v=iG9CE55wbtY")
    process_video("https://www.youtube.com/watch?v=RgGVHW7Qt6c")
