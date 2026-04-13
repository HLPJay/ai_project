# test_transcript.py
# 运行方式：python test_transcript.py

from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)

# ✏️ 换成你想测试的视频 URL 或 ID
VIDEO_URL = "https://www.youtube.com/watch?v=RgGVHW7Qt6c"

def extract_video_id(url: str) -> str:
    import re
    patterns = [
        r'(?:v=|youtu\.be/|embed/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"无法识别的 URL: {url}")


def main():
    print(f"视频: {VIDEO_URL}")
    print("-" * 50)

    # 1. 提取视频 ID
    video_id = extract_video_id(VIDEO_URL)
    print(f"视频 ID: {video_id}")

    api = YouTubeTranscriptApi()

    # 2. 查看有哪些字幕可用
    print("\n可用字幕语言：")
    try:
        transcript_list = api.list(video_id)
        for t in transcript_list:
            kind = "自动生成" if t.is_generated else "人工上传"
            print(f"  [{kind}] {t.language} ({t.language_code})")
    except Exception as e:
        print(f"  查询失败: {e}")
        return

    # 3. 获取字幕（优先中文，其次英文）
    print("\n获取字幕中...")
    try:
        transcript = api.fetch(video_id, languages=['zh-Hans', 'zh', 'zh-TW', 'en'])
    except NoTranscriptFound:
        print("没有中文字幕，尝试英文...")
        transcript = api.fetch(video_id, languages=['en'])

    # 4. 打印结果
    snippets = transcript.snippets
    print(f"共 {len(snippets)} 条字幕片段\n")

    print("前 5 条字幕：")
    for s in snippets[:5]:
        print(f"  [{s.start:.1f}s] {s.text}")

    print("\n完整文本（前 500 字）：")
    full_text = " ".join([s.text for s in snippets])
    print(full_text[:500])
    print(f"\n... 共约 {len(full_text.split())} 词")


if __name__ == "__main__":
    try:
        main()
    except VideoUnavailable:
        print("错误：视频不存在或已设为私密")
    except TranscriptsDisabled:
        print("错误：该视频已禁用字幕")
    except Exception as e:
        print(f"错误：{e}")
        print("\n如果是网络错误，请检查代理设置：")
        print("  Windows CMD: set https_proxy=http://127.0.0.1:你的代理端口")
