"""
本地语音识别方案
依赖：pip install faster-whisper yt-dlp youtube-transcript-api

流程：
  1. 先尝试 YouTube 字幕（免费、秒级）
  2. 没有字幕 → yt-dlp 下载音频 → faster-whisper 本地转录
"""

import re
import os
import tempfile
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)

# 告诉系统去哪里找 CUDA 库
# nvidia_libs = os.path.join(os.path.dirname(__file__), r"venv\Lib\site-packages\nvidia\cublas\bin")
# os.add_dll_directory(nvidia_libs)

# cudnn_libs = os.path.join(os.path.dirname(__file__), r"venv\Lib\site-packages\nvidia\cudnn\bin")
# os.add_dll_directory(cudnn_libs)

# 如果还有问题  就是把他放在import re之前 
# 方法1：添加到 PATH 环境变量（更可靠）
os.environ['PATH'] = (
    r"D:\claude_code\20260411_youtube_视频分析\venv\Lib\site-packages\nvidia\cublas\bin" + os.pathsep +
    r"D:\claude_code\20260411_youtube_视频分析\venv\Lib\site-packages\nvidia\cudnn\bin" + os.pathsep +
    os.environ.get('PATH', '')
)

# 方法2：add_dll_directory（可选，和方法1二选一）
os.add_dll_directory(r"D:\claude_code\20260411_youtube_视频分析\venv\Lib\site-packages\nvidia\cublas\bin")
os.add_dll_directory(r"D:\claude_code\20260411_youtube_视频分析\venv\Lib\site-packages\nvidia\cudnn\bin")

#  
# ============================================================
# 工具函数
# ============================================================

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


def clean_text(text: str) -> str:
    import html
    text = html.unescape(text)
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\(.*?\)', '', text)
    text = re.sub(r'>>\s*', '', text)
    text = text.replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ============================================================
# 路径一：YouTube 字幕
# ============================================================

def get_from_captions(video_id: str) -> dict | None:
    api = YouTubeTranscriptApi()
    try:
        transcript = api.fetch(
            video_id,
            languages=['zh-Hans', 'zh', 'zh-TW', 'en']
        )
        text = clean_text(" ".join([s.text for s in transcript.snippets]))
        return {
            'text': text,
            'source': 'youtube_captions',
            'word_count': len(text.split()),
        }
    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable):
        return None
    except Exception as e:
        print(f"  字幕获取异常: {str(e).splitlines()[0]}")
        return None


# ============================================================
# 路径二：本地 faster-whisper
# ============================================================

def download_audio(video_id: str, output_dir: str) -> str:
    """用 yt-dlp 下载音频，返回文件路径"""
    import yt_dlp

    url = f"https://www.youtube.com/watch?v={video_id}"
    output_template = os.path.join(output_dir, '%(id)s.%(ext)s')

    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)

    # yt-dlp 实际扩展名可能和模板不同，找一下真实文件
    base = os.path.splitext(filename)[0]
    for ext in ['m4a', 'webm', 'mp4', 'ogg', 'opus']:
        candidate = f"{base}.{ext}"
        if os.path.exists(candidate):
            return candidate

    return filename


def transcribe_local(audio_path: str, model_size: str = 'medium') -> str:
    """
    用 faster-whisper 本地转录音频

    model_size 选项（按质量和速度权衡）：
      tiny   - 最快，质量一般，适合测试
      base   - 快，质量尚可
      small  - 中等，适合日常使用
      medium - 较好，中文效果好，推荐 ✅
      large-v3 - 最好，需要更多内存

    首次运行会自动下载对应模型文件：
      tiny   ≈ 75MB
      base   ≈ 145MB
      small  ≈ 465MB
      medium ≈ 1.5GB
      large-v3 ≈ 3GB
    """
    from faster_whisper import WhisperModel

    print(f"  加载模型 [{model_size}]（首次运行会下载模型，请耐心等待）...")
    # model = WhisperModel(
    #     model_size,
    #     device='cpu',          # 没有 NVIDIA 显卡用 cpu
    #     compute_type='int8',   # CPU 模式下用 int8，减少内存占用
    # )
    model = WhisperModel(
        model_size,
        device='cuda',          # 没有 NVIDIA 显卡用 cpu
        compute_type='int8_float16',   # CPU 模式下用 int8，减少内存占用
    )

    print(f"  开始转录...")
    segments, info = model.transcribe(
        audio_path,
        language='zh',         # 指定中文，提高准确率
                               # 改成 None 让模型自动检测语言
        vad_filter=True,       # 过滤静音片段，加快速度
        beam_size=5,           # 解码束宽，越大越准但越慢
    )

    # segments 是生成器，需要迭代收集
    text_parts = []
    for seg in segments:
        text_parts.append(seg.text.strip())

    return clean_text(" ".join(text_parts))


# def get_from_whisper_local(video_id: str, model_size: str = 'medium') -> dict | None:
#     """下载音频 + 本地转录，临时文件用完自动清理"""
#     with tempfile.TemporaryDirectory() as tmp_dir:

#         # 1. 下载音频
#         print("  下载音频中...")
#         try:
#             audio_path = download_audio(video_id, tmp_dir)
#             size_mb = os.path.getsize(audio_path) / 1024 / 1024
#             print(f"  音频下载完成 ({size_mb:.1f} MB)")
#         except Exception as e:
#             print(f"  下载失败: {str(e).splitlines()[0]}")
#             return None

#         # 2. 本地转录
#         try:
#             text = transcribe_local(audio_path, model_size)
#             return {
#                 'text': text,
#                 'source': f'faster_whisper_{model_size}',
#                 'word_count': len(text.split()),
#             }
#         except Exception as e:
#             print(f"  转录失败: {str(e).splitlines()[0]}")
#             return None


def get_from_whisper_local(video_id: str, model_size: str = 'medium') -> dict | None:
    """下载音频 + 本地转录，音频文件保留到固定目录"""

    audio_dir = r"D:\claude_code\20260411_youtube_视频分析\audio"
    os.makedirs(audio_dir, exist_ok=True)

    # 1. 下载音频（如果已存在则跳过）
    existing = [f for f in os.listdir(audio_dir) if f.startswith(video_id)]
    if existing:
        audio_path = os.path.join(audio_dir, existing[0])
        print(f"  音频已存在，跳过下载：{existing[0]}")
    else:
        print("  下载音频中...")
        try:
            audio_path = download_audio(video_id, audio_dir)
            size_mb = os.path.getsize(audio_path) / 1024 / 1024
            print(f"  音频下载完成 ({size_mb:.1f} MB)")
        except Exception as e:
            print(f"  下载失败: {str(e).splitlines()[0]}")
            return None

    # 2. 本地转录
    try:
        text = transcribe_local(audio_path, model_size)
        return {
            'text': text,
            'source': f'faster_whisper_{model_size}',
            'word_count': len(text.split()),
        }
    except Exception as e:
        print(f"  转录失败: {str(e).splitlines()[0]}")
        return None

# ============================================================
# 主入口：自动降级
# ============================================================

def get_transcript(url: str, whisper_model: str = 'medium') -> dict:
    """
    获取视频文字内容（自动降级）

    参数：
      url           - YouTube 视频链接
      whisper_model - 没有字幕时使用的本地模型大小
                      推荐 'medium'，想快点用 'small'，想更准用 'large-v3'

    返回：
    {
        'success'   : True / False,
        'text'      : '完整文本' or None,
        'source'    : 'youtube_captions' | 'faster_whisper_medium' | None,
        'word_count': 1234,
        'error'     : None or '失败原因',
    }
    """
    result = {
        'success': False,
        'text': None,
        'source': None,
        'word_count': 0,
        'error': None,
    }

    try:
        video_id = extract_video_id(url)
    except ValueError as e:
        result['error'] = str(e)
        return result

    # 路径一：YouTube 字幕（优先）
    print("[ 路径1 ] 尝试获取 YouTube 字幕...")
    data = get_from_captions(video_id)
    if data:
        print(f"  ✅ 字幕获取成功（{data['word_count']} 词）")
        result.update({'success': True, **data})
        return result

    # 路径二：本地 Whisper
    print("  ⚠️  无字幕，切换到本地 Whisper 转录...")
    print(f"[ 路径2 ] faster-whisper [{whisper_model}] 转录中...")
    data = get_from_whisper_local(video_id, whisper_model)
    if data:
        print(f"  ✅ 转录完成（{data['word_count']} 词）")
        result.update({'success': True, **data})
        return result

    result['error'] = '字幕和本地转录均失败'
    return result


# ============================================================
# 测试入口
# ============================================================
# import torch
# print(torch.cuda.is_available())       # 应该输出 True
# print(torch.cuda.get_device_name(0))   # 应该输出 NVIDIA GeForce RTX 4070 ...
if __name__ == "__main__":

    print("=" * 55)
    print("测试1：有字幕的视频（走路径一，秒级返回）")
    print("=" * 55)
    r = get_transcript("https://www.youtube.com/watch?v=iG9CE55wbtY")
    if r['success']:
        print(f"\n来源 : {r['source']}")
        print(f"词数 : {r['word_count']}")
        print(f"预览 : {r['text'][:200]}...\n")
    else:
        print(f"失败 : {r['error']}\n")

    print("=" * 55)
    print("测试2：无字幕视频（走路径二，触发本地转录）")
    print("说明：首次运行会下载 ~1.5GB 模型文件")
    print("=" * 55)
    r = get_transcript(
        "https://www.youtube.com/watch?v=RgGVHW7Qt6c",
        whisper_model='medium',    # 改成 'small' 更快，'large-v3' 更准
    )
    if r['success']:
        print(f"\n来源 : {r['source']}")
        print(f"词数 : {r['word_count']}")
        print(f"预览 : {r['text'][:200]}...\n")
    else:
        print(f"失败 : {r['error']}\n")
