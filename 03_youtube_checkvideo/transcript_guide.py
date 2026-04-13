"""
youtube-transcript-api 完整使用指南
版本：最新版（使用实例化方式）
安装：pip install youtube-transcript-api
"""

# ============================================================
# 第一部分：基础用法
# ============================================================

from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,   # 视频关闭了字幕功能
    NoTranscriptFound,     # 找不到指定语言的字幕
    VideoUnavailable,      # 视频不存在或私密
)


# ------ 1. 提取视频 ID ------
def extract_video_id(url: str) -> str:
    """
    从各种格式的 YouTube URL 中提取视频 ID

    支持的格式：
    - https://www.youtube.com/watch?v=abc123
    - https://youtu.be/abc123
    - https://www.youtube.com/embed/abc123
    - abc123（直接传 ID 也行）
    """
    import re
    patterns = [
        r'(?:v=|youtu\.be/|embed/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"无法从 URL 中提取视频 ID: {url}")


# 示例
url1 = "https://www.youtube.com/watch?v=iG9CE55wbtY"
url2 = "https://youtu.be/iG9CE55wbtY"
url3 = "iG9CE55wbtY"

# extract_video_id(url1) → "iG9CE55wbtY"
# extract_video_id(url2) → "iG9CE55wbtY"
# extract_video_id(url3) → "iG9CE55wbtY"


# ------ 2. 最简单的用法 ------
def simple_get_transcript(video_id: str) -> str:
    """最简单版本：直接拿英文字幕，返回纯文本"""
    api = YouTubeTranscriptApi()
    transcript = api.fetch(video_id, languages=['en'])
    return " ".join([s.text for s in transcript.snippets])


# ------ 3. 查看视频有哪些字幕可用 ------
def list_available_transcripts(video_id: str):
    """
    列出一个视频所有可用的字幕语言

    返回示例：
    [
      {'language': 'English', 'code': 'en', 'is_generated': False},
      {'language': 'Chinese (Simplified)', 'code': 'zh-Hans', 'is_generated': True},
      {'language': '中文（简体）', 'code': 'zh-Hans', 'is_generated': True},
    ]
    """
    api = YouTubeTranscriptApi()
    transcript_list = api.list(video_id)

    results = []
    for t in transcript_list:
        results.append({
            'language': t.language,
            'code': t.language_code,
            'is_generated': t.is_generated,  # True=自动生成，False=人工上传
        })
    return results


# ============================================================
# 第二部分：语言选择策略
# ============================================================

def get_transcript_with_priority(video_id: str) -> dict:
    """
    按优先级尝试不同语言的字幕：
    中文人工 > 英文人工 > 中文自动 > 英文自动

    返回：
    {
        'text': '完整字幕文本',
        'language': 'zh-Hans',
        'is_generated': True,
        'segments': [{'text': '...', 'start': 0.0, 'duration': 3.2}, ...]
    }
    """
    api = YouTubeTranscriptApi()
    transcript_list = api.list(video_id)

    # 策略1：优先找人工上传的字幕（质量更高）
    try:
        transcript = transcript_list.find_manually_created_transcript(
            ['zh-Hans', 'zh-TW', 'zh', 'en']
        )
        t = transcript.fetch()
        return _format_transcript(t, transcript.language_code, is_generated=False)
    except NoTranscriptFound:
        pass

    # 策略2：再找自动生成的字幕
    try:
        transcript = transcript_list.find_generated_transcript(
            ['zh-Hans', 'zh-TW', 'zh', 'en']
        )
        t = transcript.fetch()
        return _format_transcript(t, transcript.language_code, is_generated=True)
    except NoTranscriptFound:
        pass

    # 策略3：找任意语言，然后翻译成英文
    try:
        for t in transcript_list:
            if t.is_translatable:
                translated = t.translate('en').fetch()
                return _format_transcript(translated, 'en-translated', is_generated=True)
    except Exception:
        pass

    return None


def _format_transcript(transcript, language_code: str, is_generated: bool) -> dict:
    """将 transcript 对象格式化为统一结构"""
    segments = [
        {
            'text': s.text,
            'start': round(s.start, 2),
            'duration': round(s.duration, 2),
        }
        for s in transcript.snippets
    ]
    full_text = " ".join([s['text'] for s in segments])
    return {
        'text': full_text,
        'language': language_code,
        'is_generated': is_generated,
        'segments': segments,
        'word_count': len(full_text.split()),
    }


# ============================================================
# 第三部分：字幕清洗（非常重要）
# ============================================================

def clean_transcript(raw_text: str) -> str:
    """
    清洗自动生成的字幕文本

    自动字幕的常见噪音：
    - [Music] [Applause] 等音效标记
    - >> 发言人切换符号
    - 重复词（"I I think" → "I think"）
    - 多余空格
    - HTML 实体（&amp; &lt; 等）
    """
    import re
    import html

    text = raw_text

    # 1. 解码 HTML 实体（&amp; → &）
    text = html.unescape(text)

    # 2. 去掉音效标签 [Music] [Applause] (Music) 等
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\(.*?\)', '', text)

    # 3. 去掉发言人标记（>> 或 Speaker:）
    text = re.sub(r'>>\s*', '', text)
    text = re.sub(r'\w+:\s+', '', text)

    # 4. 去掉换行，统一为空格
    text = text.replace('\n', ' ')

    # 5. 压缩多余空格
    text = re.sub(r'\s+', ' ', text).strip()

    # 6. 去掉重复词（自动字幕常见问题：单词被重复转录）
    words = text.split()
    cleaned_words = []
    for i, word in enumerate(words):
        if i == 0 or word.lower() != words[i - 1].lower():
            cleaned_words.append(word)
    text = ' '.join(cleaned_words)

    return text


# ============================================================
# 第四部分：完整的错误处理
# ============================================================

def get_transcript_safe(url: str) -> dict:
    """
    生产级用法：完整错误处理 + 降级策略

    返回：
    {
        'success': True/False,
        'text': '字幕文本' or None,
        'language': 'en',
        'is_generated': True,
        'word_count': 1234,
        'error': None or '错误原因',
        'fallback_used': False,  # 是否使用了降级方案
    }
    """
    result = {
        'success': False,
        'text': None,
        'language': None,
        'is_generated': None,
        'word_count': 0,
        'error': None,
        'fallback_used': False,
    }

    # Step 1: 提取视频 ID
    try:
        video_id = extract_video_id(url)
    except ValueError as e:
        result['error'] = f'无效的 YouTube URL: {e}'
        return result

    # Step 2: 获取字幕
    try:
        data = get_transcript_with_priority(video_id)

        if data is None:
            result['error'] = '该视频没有任何可用字幕（包括自动生成）'
            return result

        # Step 3: 清洗文本
        cleaned = clean_transcript(data['text'])

        result.update({
            'success': True,
            'text': cleaned,
            'language': data['language'],
            'is_generated': data['is_generated'],
            'word_count': len(cleaned.split()),
            'segments': data['segments'],
        })

    except TranscriptsDisabled:
        result['error'] = '该视频已禁用字幕功能'

    except VideoUnavailable:
        result['error'] = '视频不存在、已删除或设为私密'

    except Exception as e:
        result['error'] = f'未知错误: {str(e)}'

    return result


# ============================================================
# 第五部分：长视频分段处理（配合 AI 分析用）
# ============================================================

def split_transcript_for_ai(segments: list, max_words_per_chunk: int = 3000) -> list:
    """
    将长视频字幕切分成多段，每段不超过 max_words 词
    用于后续分段喂给 Claude 处理

    参数：
    - segments: 从 get_transcript_safe() 返回的 segments 列表
    - max_words_per_chunk: 每段最大词数，3000词 ≈ 4000 tokens，安全范围

    返回：
    [
        {
            'chunk_index': 0,
            'start_time': 0.0,
            'end_time': 600.0,
            'text': '第一段文本...',
            'word_count': 2800,
        },
        ...
    ]
    """
    chunks = []
    current_chunk_segments = []
    current_word_count = 0

    for segment in segments:
        words_in_segment = len(segment['text'].split())

        # 当前段加上这条字幕会超出限制
        if current_word_count + words_in_segment > max_words_per_chunk and current_chunk_segments:
            # 保存当前块
            chunks.append(_build_chunk(current_chunk_segments, len(chunks)))
            # 开新块
            current_chunk_segments = [segment]
            current_word_count = words_in_segment
        else:
            current_chunk_segments.append(segment)
            current_word_count += words_in_segment

    # 最后一块
    if current_chunk_segments:
        chunks.append(_build_chunk(current_chunk_segments, len(chunks)))

    return chunks


def _build_chunk(segments: list, index: int) -> dict:
    text = clean_transcript(" ".join([s['text'] for s in segments]))
    return {
        'chunk_index': index,
        'start_time': segments[0]['start'],
        'end_time': segments[-1]['start'] + segments[-1]['duration'],
        'text': text,
        'word_count': len(text.split()),
    }


# ============================================================
# 第六部分：完整流水线示例
# ============================================================

def full_pipeline_example(url: str):
    """
    完整示例：从 URL 到准备好喂给 AI 的文本

    这是你在项目里实际会用的入口函数
    """
    print(f"处理视频: {url}")
    print("-" * 50)

    # 1. 获取字幕
    result = get_transcript_safe(url)

    if not result['success']:
        print(f"❌ 字幕获取失败: {result['error']}")
        print("→ 需要降级到 Whisper 语音识别")
        return None

    print(f"✅ 字幕获取成功")
    print(f"   语言: {result['language']}")
    print(f"   类型: {'自动生成' if result['is_generated'] else '人工上传'}")
    print(f"   总词数: {result['word_count']}")

    # 2. 判断是否需要分段
    if result['word_count'] <= 4000:
        print(f"\n📄 短视频，直接处理")
        print(f"   文本预览: {result['text'][:200]}...")
        return {'mode': 'direct', 'text': result['text']}
    else:
        print(f"\n📚 长视频，需要分段处理")
        chunks = split_transcript_for_ai(result['segments'])
        print(f"   切分为 {len(chunks)} 段")
        for c in chunks[:3]:  # 只展示前3段
            print(f"   段{c['chunk_index']}: {c['start_time']:.0f}s-{c['end_time']:.0f}s, {c['word_count']} 词")
        return {'mode': 'chunked', 'chunks': chunks}


# ============================================================
# 运行示例（本地测试用）
# ============================================================

if __name__ == "__main__":
    # 替换成你想测试的视频 URL
    test_url = "https://www.youtube.com/watch?v=iG9CE55wbtY"

    # 示例1：最简单用法
    # video_id = extract_video_id(test_url)
    # print(simple_get_transcript(video_id))

    # 示例2：完整流水线
    result = full_pipeline_example(test_url)
    print("\n最终结果:", result)
