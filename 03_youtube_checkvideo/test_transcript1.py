# test_transcript.py
# 运行方式：python test_transcript.py

from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)
import re

# ✏️ 换成你想测试的视频 URL
# 下面这个是 TED 演讲，字幕完整，用来验证库是否正常工作
VIDEO_URL = "https://www.youtube.com/watch?v=iG9CE55wbtY"

# 验证通过后，换成你自己的视频：
# VIDEO_URL = "https://www.youtube.com/watch?v=RgGVHW7Qt6c"


def extract_video_id(url: str) -> str:
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

    video_id = extract_video_id(VIDEO_URL)
    print(f"视频 ID: {video_id}\n")

    api = YouTubeTranscriptApi()

    # Step 1: 查看有哪些字幕
    print("[ 步骤1 ] 查询可用字幕...")
    try:
        transcript_list = api.list(video_id)
        print("可用字幕：")
        for t in transcript_list:
            kind = "自动生成" if t.is_generated else "人工上传"
            print(f"  [{kind}] {t.language} ({t.language_code})")
    except TranscriptsDisabled:
        print("  ❌ 该视频已禁用字幕 → 需要用 Whisper 语音识别")
        return
    except VideoUnavailable:
        print("  ❌ 视频不存在或已设为私密")
        return
    except Exception as e:
        # 只打印第一行，避免超长错误信息刷屏
        first_line = str(e).splitlines()[0]
        print(f"  ❌ 查询失败: {first_line}")
        return

    # Step 2: 获取字幕内容
    print("\n[ 步骤2 ] 获取字幕内容...")
    try:
        # 优先中文，没有就取英文
        transcript = api.fetch(video_id, languages=['zh-Hans', 'zh', 'zh-TW', 'en'])
        snippets = transcript.snippets
        print(f"  ✅ 成功！共 {len(snippets)} 条字幕片段")

    except NoTranscriptFound:
        print("  ❌ 没有找到中文或英文字幕")
        return
    except Exception as e:
        first_line = str(e).splitlines()[0]
        print(f"  ❌ 获取失败: {first_line}")
        return

    # Step 3: 展示结果
    print("\n[ 步骤3 ] 字幕预览（前5条）")
    for s in snippets[:5]:
        print(f"  [{s.start:6.1f}s] {s.text}")

    full_text = " ".join([s.text for s in snippets])
    print(f"\n[ 结果 ]")
    print(f"  总片段数: {len(snippets)}")
    print(f"  总词数:   约 {len(full_text.split())} 词")
    print(f"  文本预览: {full_text[:200]}...")


if __name__ == "__main__":
    main()
