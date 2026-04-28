#!/usr/bin/env python3
import urllib.request

NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

from style_map import (get_art_style, get_mood_desc,
                       build_char_prompt, get_fallback_desc, get_label,
                       get_music_style_desc, THEME_VISUALS)

# 日志记录器（延迟导入避免循环依赖）
_llm_logger = None
def _get_logger():
    global _llm_logger
    if _llm_logger is None:
        try:
            from llm_logger import log_llm as _f
            _llm_logger = _f
        except ImportError:
            _llm_logger = lambda *a, **k: None  # 无日志时静默
    return _llm_logger


"""
analyze_srt.py — 分析 SRT 歌曲结构，生成动态场景元数据

用法: python3 analyze_srt.py <project_dir>

输入:
  {project_dir}/audio/song.srt          — 歌词时间戳
  {project_dir}/audio/lyrics.txt         — 原始歌词（用于生成场景描述）
  {project_dir}/metadata/info.json       — 歌曲配置（style, mood, theme）
  {project_dir}/metadata/base_char.json  — 角色描述

输出:
  {project_dir}/metadata/scenes.json     — 动态场景（含时间戳、中文标签、英文描述）
  {project_dir}/metadata/base_char.json   — 角色描述（如不存在则生成）

核心逻辑:
  1. 解析 SRT → 每行歌词的时间戳
  2. 分析歌曲结构（重复歌词=副歌，间隙检测=段落边界）
  3. 动态决定场景数（10-22个，基于歌曲长度，目标每场景7-12秒）
  4. 根据歌词内容 + 段落特征生成 label（中文）和 desc（英文）
  5. 每个场景的 KB 时长 = 段落实际时长
  6. 重复段(副歌) + 时长>4s → 标记 is_repeated=true（供生成变体图）

变体图策略（见 generate_scene_imgs.py）:
  - 条件: is_repeated=True 且 duration>4s
  - 张数: ceil(duration/5)，最多3张，每张至少5秒
  - 变体 prompt: DeepSeek desc + 镜头/动作变化后缀

修复记录:
  - v2: 加入 label/desc 本地生成（无需 API）
  - v2: 加入 no_proxy 环境变量（支持 Python urllib）
  - v3: 场景数增加到10-22（目标每场景7-12秒）
  - v3: 新增 is_repeated 标记，支持变体图生成
  - v4: 方案二优化 → 移除本地THEME_KEYWORDS，全量复用style_map统一THEME_VISUALS主题库
  - v5: 方案三升级 → 智能组合标签（主题+情绪+多关键词融合，贴合MV氛围）
  
修复&优化项：
1. 修复 is_valid_desc 函数顺序导致的 NameError
2. 强化  标签过滤，防碎片/大小写兼容
3. 新增JSON精准截取，彻底解决批量JSON解析失败
4. 全局统一锁定规则，Prompt去重、统一维护
5. 变体强补场景/天气/背景锁定约束，防止画面跑偏
6. 统一API超时为25s，提升批量稳定性
7. 增加空列表防护、时长防负、鲁棒性增强
"""

import json
import os
import re
import sys
import math
import time
def _call_llm(req, max_retries=3):
    """Call LLM API with exponential backoff retry."""
    import time, urllib.error
    delays = [5, 10, 20]
    for attempt in range(max_retries):
        try:
            return urllib.request.urlopen(req, timeout=30)
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == max_retries - 1:
                raise
            print(f"   HTTP {e.code}, retry {attempt+1}/{max_retries} in {delays[attempt]}s...")
            time.sleep(delays[attempt])
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            print(f"   Request failed ({e}), retry {attempt+1}/{max_retries} in {delays[attempt]}s...")
            time.sleep(delays[attempt])


# 全局统一画质后缀 所有描述通用
QUALITY_SUFFIX = (
    ", 8k, ultra detailed, soft cinematic lighting, delicate color grading, "
    "clean MV frame style, high resolution, fine texture, film soft focus, "
    "minimal composition, no extra characters, no text, no logo, no clutter"
)

# ===================== 全局统一锁定规则 一键维护 =====================
GLOBAL_CHAR_LOCK = (
    "Character absolute lock: fixed face, hairstyle, costume, body proportion, "
    "facial features and dressing style, never change."
)

GLOBAL_SCENE_LOCK = (
    "Scene lock: consistent background, environment, weather, time, space, "
    "lighting direction, color palette, saturation and overall tone."
)

GLOBAL_FORBIDDEN = (
    "Strictly forbid: extra people, deformed limbs, blurry face, messy elements, "
    "text, watermark, logo, graffiti, weird distortion, overexposure."
)

MV_BASE_STYLE = (
    "Pure music video aesthetic, gentle film texture, moderate blank space, "
    "stable framing, unified soft cinematic tone, coherent visual rhythm."
)

GLOBAL_UNIFIED_RULES = f"{GLOBAL_CHAR_LOCK} {GLOBAL_SCENE_LOCK} {GLOBAL_FORBIDDEN} {MV_BASE_STYLE}"
# ====================================================================

# 强制取消代理设置（WSL 环境）
os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)
os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)
os.environ.pop('ALL_PROXY', None)
os.environ.pop('all_proxy', None)

# LLM 配置（从环境变量读取，config.sh 会自动设置）
LLM_TOKEN = os.environ.get("MINIMAX_TOKEN", "")
LLM_API_URL = os.environ.get(
    "LLM_API_URL",
    "https://api.minimaxi.com/v1/chat/completions"
)
LLM_MODEL = os.environ.get("LLM_MODEL", "MiniMax-M2.7")

def _strip_think(raw):
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=re.DOTALL)
    return cleaned.strip()
#!/usr/bin/env python3
import urllib.request

NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

from style_map import (get_art_style, get_mood_desc,
                       build_char_prompt, get_fallback_desc, get_label,
                       get_music_style_desc, THEME_VISUALS)

# 日志记录器（延迟导入避免循环依赖）
_llm_logger = None
def _get_logger():
    global _llm_logger
    if _llm_logger is None:
        try:
            from llm_logger import log_llm as _f
            _llm_logger = _f
        except ImportError:
            _llm_logger = lambda *a, **k: None  # 无日志时静默
    return _llm_logger


"""
analyze_srt.py — 分析 SRT 歌曲结构，生成动态场景元数据

用法: python3 analyze_srt.py <project_dir>

输入:
  {project_dir}/audio/song.srt          — 歌词时间戳
  {project_dir}/audio/lyrics.txt         — 原始歌词（用于生成场景描述）
  {project_dir}/metadata/info.json       — 歌曲配置（style, mood, theme）
  {project_dir}/metadata/base_char.json  — 角色描述

输出:
  {project_dir}/metadata/scenes.json     — 动态场景（含时间戳、中文标签、英文描述）
  {project_dir}/metadata/base_char.json   — 角色描述（如不存在则生成）

核心逻辑:
  1. 解析 SRT → 每行歌词的时间戳
  2. 分析歌曲结构（重复歌词=副歌，间隙检测=段落边界）
  3. 动态决定场景数（10-22个，基于歌曲长度，目标每场景7-12秒）
  4. 根据歌词内容 + 段落特征生成 label（中文）和 desc（英文）
  5. 每个场景的 KB 时长 = 段落实际时长
  6. 重复段(副歌) + 时长>4s → 标记 is_repeated=true（供生成变体图）

变体图策略（见 generate_scene_imgs.py）:
  - 条件: is_repeated=True 且 duration>4s
  - 张数: ceil(duration/5)，最多3张，每张至少5秒
  - 变体 prompt: DeepSeek desc + 镜头/动作变化后缀

修复记录:
  - v2: 加入 label/desc 本地生成（无需 API）
  - v2: 加入 no_proxy 环境变量（支持 Python urllib）
  - v3: 场景数增加到10-22（目标每场景7-12秒）
  - v3: 新增 is_repeated 标记，支持变体图生成
  - v4: 方案二优化 → 移除本地THEME_KEYWORDS，全量复用style_map统一THEME_VISUALS主题库
  - v5: 方案三升级 → 智能组合标签（主题+情绪+多关键词融合，贴合MV氛围）
  
修复&优化项：
1. 修复 is_valid_desc 函数顺序导致的 NameError
2. 强化  标签过滤，防碎片/大小写兼容
3. 新增JSON精准截取，彻底解决批量JSON解析失败
4. 全局统一锁定规则，Prompt去重、统一维护
5. 变体强补场景/天气/背景锁定约束，防止画面跑偏
6. 统一API超时为25s，提升批量稳定性
7. 增加空列表防护、时长防负、鲁棒性增强
"""

import json
import os
import re
import sys
import math
import time

# 全局统一画质后缀 所有描述通用
QUALITY_SUFFIX = (
    ", 8k, ultra detailed, soft cinematic lighting, delicate color grading, "
    "clean MV frame style, high resolution, fine texture, film soft focus, "
    "minimal composition, no extra characters, no text, no logo, no clutter"
)

# ===================== 全局统一锁定规则 一键维护 =====================
GLOBAL_CHAR_LOCK = (
    "Character absolute lock: fixed face, hairstyle, costume, body proportion, "
    "facial features and dressing style, never change."
)

GLOBAL_SCENE_LOCK = (
    "Scene lock: consistent background, environment, weather, time, space, "
    "lighting direction, color palette, saturation and overall tone."
)

GLOBAL_FORBIDDEN = (
    "Strictly forbid: extra people, deformed limbs, blurry face, messy elements, "
    "text, watermark, logo, graffiti, weird distortion, overexposure."
)

MV_BASE_STYLE = (
    "Pure music video aesthetic, gentle film texture, moderate blank space, "
    "stable framing, unified soft cinematic tone, coherent visual rhythm."
)

GLOBAL_UNIFIED_RULES = f"{GLOBAL_CHAR_LOCK} {GLOBAL_SCENE_LOCK} {GLOBAL_FORBIDDEN} {MV_BASE_STYLE}"
# ====================================================================

# 强制取消代理设置（WSL 环境）
os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)
os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)
os.environ.pop('ALL_PROXY', None)
os.environ.pop('all_proxy', None)

# LLM 配置（从环境变量读取，config.sh 会自动设置）
LLM_TOKEN = os.environ.get("MINIMAX_TOKEN", "")
LLM_API_URL = os.environ.get(
    "LLM_API_URL",
    "https://api.minimaxi.com/v1/chat/completions"
)
LLM_MODEL = os.environ.get("LLM_MODEL", "MiniMax-M2.7")

def _strip_think(raw):
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=re.DOTALL)
    return cleaned.strip()
#!/usr/bin/env python3
import urllib.request

NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

from style_map import (get_art_style, get_mood_desc,
                       build_char_prompt, get_fallback_desc, get_label,
                       get_music_style_desc, THEME_VISUALS)

# 日志记录器（延迟导入避免循环依赖）
_llm_logger = None
def _get_logger():
    global _llm_logger
    if _llm_logger is None:
        try:
            from llm_logger import log_llm as _f
            _llm_logger = _f
        except ImportError:
            _llm_logger = lambda *a, **k: None  # 无日志时静默
    return _llm_logger


"""
analyze_srt.py — 分析 SRT 歌曲结构，生成动态场景元数据

用法: python3 analyze_srt.py <project_dir>

输入:
  {project_dir}/audio/song.srt          — 歌词时间戳
  {project_dir}/audio/lyrics.txt         — 原始歌词（用于生成场景描述）
  {project_dir}/metadata/info.json       — 歌曲配置（style, mood, theme）
  {project_dir}/metadata/base_char.json  — 角色描述

输出:
  {project_dir}/metadata/scenes.json     — 动态场景（含时间戳、中文标签、英文描述）
  {project_dir}/metadata/base_char.json   — 角色描述（如不存在则生成）

核心逻辑:
  1. 解析 SRT → 每行歌词的时间戳
  2. 分析歌曲结构（重复歌词=副歌，间隙检测=段落边界）
  3. 动态决定场景数（10-22个，基于歌曲长度，目标每场景7-12秒）
  4. 根据歌词内容 + 段落特征生成 label（中文）和 desc（英文）
  5. 每个场景的 KB 时长 = 段落实际时长
  6. 重复段(副歌) + 时长>4s → 标记 is_repeated=true（供生成变体图）

变体图策略（见 generate_scene_imgs.py）:
  - 条件: is_repeated=True 且 duration>4s
  - 张数: ceil(duration/5)，最多3张，每张至少5秒
  - 变体 prompt: DeepSeek desc + 镜头/动作变化后缀

修复记录:
  - v2: 加入 label/desc 本地生成（无需 API）
  - v2: 加入 no_proxy 环境变量（支持 Python urllib）
  - v3: 场景数增加到10-22（目标每场景7-12秒）
  - v3: 新增 is_repeated 标记，支持变体图生成
  - v4: 方案二优化 → 移除本地THEME_KEYWORDS，全量复用style_map统一THEME_VISUALS主题库
  - v5: 方案三升级 → 智能组合标签（主题+情绪+多关键词融合，贴合MV氛围）
  
修复&优化项：
1. 修复 is_valid_desc 函数顺序导致的 NameError
2. 强化  标签过滤，防碎片/大小写兼容
3. 新增JSON精准截取，彻底解决批量JSON解析失败
4. 全局统一锁定规则，Prompt去重、统一维护
5. 变体强补场景/天气/背景锁定约束，防止画面跑偏
6. 统一API超时为25s，提升批量稳定性
7. 增加空列表防护、时长防负、鲁棒性增强
"""

import json
import os
import re
import sys
import math
import time

# 全局统一画质后缀 所有描述通用
QUALITY_SUFFIX = (
    ", 8k, ultra detailed, soft cinematic lighting, delicate color grading, "
    "clean MV frame style, high resolution, fine texture, film soft focus, "
    "minimal composition, no extra characters, no text, no logo, no clutter"
)

# ===================== 全局统一锁定规则 一键维护 =====================
GLOBAL_CHAR_LOCK = (
    "Character absolute lock: fixed face, hairstyle, costume, body proportion, "
    "facial features and dressing style, never change."
)

GLOBAL_SCENE_LOCK = (
    "Scene lock: consistent background, environment, weather, time, space, "
    "lighting direction, color palette, saturation and overall tone."
)

GLOBAL_FORBIDDEN = (
    "Strictly forbid: extra people, deformed limbs, blurry face, messy elements, "
    "text, watermark, logo, graffiti, weird distortion, overexposure."
)

MV_BASE_STYLE = (
    "Pure music video aesthetic, gentle film texture, moderate blank space, "
    "stable framing, unified soft cinematic tone, coherent visual rhythm."
)

GLOBAL_UNIFIED_RULES = f"{GLOBAL_CHAR_LOCK} {GLOBAL_SCENE_LOCK} {GLOBAL_FORBIDDEN} {MV_BASE_STYLE}"
# ====================================================================

# 强制取消代理设置（WSL 环境）
os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)
os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)
os.environ.pop('ALL_PROXY', None)
os.environ.pop('all_proxy', None)

# LLM 配置（从环境变量读取，config.sh 会自动设置）
LLM_TOKEN = os.environ.get("MINIMAX_TOKEN", "")
LLM_API_URL = os.environ.get(
    "LLM_API_URL",
    "https://api.minimaxi.com/v1/chat/completions"
)
LLM_MODEL = os.environ.get("LLM_MODEL", "MiniMax-M2.7")

def _strip_think(raw):
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=re.DOTALL)
    return cleaned.strip()

def extract_json_array(raw_text):
    """精准截取最外层JSON数组，忽略前后多余话术"""
    match = re.search(r"\[\s*\{[\s\S]*\}\s*\]", raw_text, re.DOTALL)
    if match:
        return match.group()
    return raw_text

# ── Variant 类型定义 ─────────────────────────────────
VARIANT_TYPES = [
    ("emotion", "Different emotional focus: the subject shows a distinct facial expression or reaction. Keep subject, clothing, background, lighting and color palette completely unchanged."),
    ("action",  "Different action or pose: the subject is doing a different gentle activity. Keep scene, light, color tone and character appearance identical."),
    ("camera",  "Different camera angle and composition: close-up, wide shot or low angle. Do not modify background, light, character outfit or color style."),
    ("motion",  "Different subtle movement state: slow movement, static pause or gentle floating. Lock all environment and color parameters."),
]

def generate_desc_ai(lyric_text, style, mood, char_prompt, art_style=None, music_style='', project_dir=None):
    """用 LLM 生成歌词相关的英文图像描述（fallback）"""
    if not LLM_TOKEN:
        raise ValueError("LLM_TOKEN (MINIMAX_TOKEN) 环境变量未设置，请执行: source scripts/config.sh")
    art_section = f"\nFixed art style: {art_style}" if art_style else ""
    music_section = f"\nMusic visual atmosphere: {get_music_style_desc(music_style)}" if music_style else ""
    prompt = (
        f"Professional MV cinematic designer, output only 20-25 word English description.\n"
        f"{GLOBAL_UNIFIED_RULES}\n"
        f"Lyric atmosphere: {lyric_text}\n"
        f"Fixed character setting: {char_prompt}\n"
        f"Global visual style: {style}\n"
        f"Core mood: {mood}"
        f"{art_section}{music_section}"
    )
    payload = json.dumps({
        'model': LLM_MODEL,
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 512,
    }).encode('utf-8')
    req = urllib.request.Request(
        LLM_API_URL,
        data=payload,
        headers={'Authorization': f'Bearer {LLM_TOKEN}', 'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with _call_llm(req) as r:
            d = json.loads(r.read())
        raw_desc = _strip_think(d['choices'][0]['message']['content'])
        result = raw_desc + QUALITY_SUFFIX
        log = _get_logger()
        if log and project_dir:
            log(project_dir, "scene_desc_single", LLM_MODEL, prompt, {"desc": result})
        return result
    except Exception as e:
        log = _get_logger()
        if log and project_dir:
            log(project_dir, "scene_desc_single", LLM_MODEL, prompt, None, error=str(e))
        raise

def generate_variant_desc(base_desc, lyric_text, style, mood, char_prompt, variant_idx=0, music_style='', project_dir=None):
    """生成副歌变体描述【强锁定画风/光影/色调/场景】"""
    if not LLM_TOKEN:
        raise ValueError("LLM_TOKEN (MINIMAX_TOKEN) environment variable not set")
    vtype, vrule = VARIANT_TYPES[variant_idx % len(VARIANT_TYPES)]
    art_style = get_art_style(style)
    music_visual = get_music_style_desc(music_style)
    music_section = f"\nMusic style visual atmosphere: {music_visual}" if music_visual else ""
    prompt = (
        f"Write a 20-25 word subtle variant image prompt, keep all core elements locked strictly.\n"
        f"{GLOBAL_CHAR_LOCK}\n"
        f"{GLOBAL_SCENE_LOCK}\n"
        f"Immutable forbidden: no weather change, no background replacement, no tone mutation.\n"
        f"Only adjust single tiny detail: {vrule}\n"
        f"Original scene base: {base_desc}\n"
        f"Lyric context: {lyric_text}\n"
        f"Character lock: {char_prompt}\n"
        f"Unified style: {art_style}, mood: {mood}{music_section}"
    )
    payload = json.dumps({
        'model': LLM_MODEL,
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 512,
    }).encode('utf-8')
    req = urllib.request.Request(
        LLM_API_URL, data=payload,
        headers={'Authorization': f'Bearer {LLM_TOKEN}', 'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with _call_llm(req) as r:
            d = json.loads(r.read())
        raw_desc = _strip_think(d['choices'][0]['message']['content'])
        result = raw_desc + QUALITY_SUFFIX
        log = _get_logger()
        if log and project_dir:
            log(project_dir, "variant_desc_single", LLM_MODEL, prompt, {"desc": result, "variant_type": vtype},
                extra={"base_desc_preview": base_desc[:80], "variant_idx": variant_idx})
        return result
    except Exception as e:
        log = _get_logger()
        if log and project_dir:
            log(project_dir, "variant_desc_single", LLM_MODEL, prompt, None, error=str(e),
                extra={"base_desc_preview": base_desc[:80], "variant_idx": variant_idx})
        raise

# ── SRT 解析 ─────────────────────────────────────────────────
def parse_srt(srt_path):
    """解析 SRT 文件，返回 [(idx, start, end, text)]"""
    if not os.path.exists(srt_path):
        raise FileNotFoundError(f"SRT file not found: {srt_path}")
    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()

    if '\n\n' in content:
        blocks = content.strip().split('\n\n')
    else:
        lines = content.split('\n')
        blocks, current = [], []
        for line in lines:
            s = line.strip()
            if s.isdigit():
                if current:
                    blocks.append('\n'.join(current))
                current = [s]
            else:
                current.append(line)
        if current:
            blocks.append('\n'.join(current))

    segments = []
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 3:
            continue
        ts_match = re.match(
            r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})',
            lines[1].strip()
        )
        if not ts_match:
            continue
        h, mm, ss = ts_match.group(1).replace(',', '.').split(':')
        start = int(h) * 3600 + int(mm) * 60 + float(ss)
        h, mm, ss = ts_match.group(2).replace(',', '.').split(':')
        end = int(h) * 3600 + int(mm) * 60 + float(ss)
        text = '\n'.join(lines[2:]).strip()
        segments.append((int(lines[0].strip()), start, end, text))

    return segments

def clean(t):
    """提取可比的干净文本"""
    return re.sub(r'[^\w\u4e00-\u9fff]', '', t)

# ── 歌曲结构分析 ─────────────────────────────────────────────
def analyze_structure(segments):
    n = len(segments)
    if n == 0:
        return []

    first_start = segments[0][1]
    last_end = segments[-1][2]
    total = max(0.1, last_end - first_start)

    # 场景数按时长分布：目标每场景 7-12 秒
    if total < 60:
        target = 10
    elif total < 100:
        target = 14
    elif total < 140:
        target = 18
    else:
        target = 22

    # 找重复歌词
    fp_idx = {}
    for i, (_, _, _, text) in enumerate(segments):
        fp = clean(text)[:20]
        if fp not in fp_idx:
            fp_idx[fp] = []
        fp_idx[fp].append(i)

    repeated_segs = set()
    for fp, idxs in fp_idx.items():
        if len(idxs) >= 2:
            repeated_segs.update(idxs)

    # 等宽切分
    boundaries = []
    for k in range(target + 1):
        pos = int(n * k / target)
        boundaries.append(pos)
    boundaries[0] = 0
    boundaries[-1] = n

    anchors = {0, n}
    for fp, idxs in fp_idx.items():
        if len(idxs) >= 2:
            anchors.add(idxs[0])

    all_points = sorted(set(boundaries + list(anchors)))

    merged = [all_points[0]]
    for pt in all_points[1:]:
        prev_dur = segments[merged[-1]][1] if merged[-1] < n else 0
        curr_dur = segments[pt][1] if pt < n else total
        if curr_dur - prev_dur < 3 and len(merged) > 1:
            merged[-1] = pt
        else:
            merged.append(pt)

    while len(merged) - 1 > target:
        gaps = []
        for i in range(1, len(merged)):
            s = segments[merged[i-1]][1] if merged[i-1] < n else 0
            e = segments[merged[i]][1] if merged[i] < n else total
            gaps.append((e - s, i))
        gaps.sort()
        gap_len, idx = next((g for g in gaps if g[1] > 1), (gaps[-1][0], len(merged) - 1))
        merged.pop(idx)

    prev_len = -1
    while len(merged) - 1 < target:
        # Guard: if list unchanged from duplicate mid, break to avoid infinite loop
        if len(merged) == prev_len:
            break
        prev_len = len(merged)
        max_gap, max_i = 0, 1
        for i in range(1, len(merged)):
            s = segments[merged[i-1]][1] if merged[i-1] < n else 0
            e = segments[merged[i]][1] if merged[i] < n else total
            if e - s > max_gap:
                max_gap, max_i = e - s, i
        mid_raw = (segments[merged[max_i-1]][1] + segments[merged[max_i]][1]) / 2
        mid = int(round(mid_raw))
        merged.insert(max_i, mid)
        merged = sorted(set(merged))

    paragraphs = []
    for bi in range(len(merged) - 1):
        si, ei = merged[bi], merged[bi + 1]
        segs = segments[si:ei]
        if not segs:
            continue
        start = segs[0][1]
        end = segs[-1][2]
        dur = max(0.1, end - start)
        text = ' '.join(s[3] for s in segs)
        is_rep = any(i in repeated_segs for i in range(si, ei))
        paragraphs.append({
            'start_seg': si, 'end_seg': ei,
            'start': start, 'end': end, 'duration': dur,
            'text': text, 'is_repeated': is_rep,
            'segment_count': ei - si
        })

    return paragraphs

def name_scenes(paragraphs):
    result = []
    used = {}

    for i, p in enumerate(paragraphs):
        if p['is_repeated'] and 'chorus' not in used:
            name = 'chorus'
        elif i == 0:
            name = 'intro'
        elif i == len(paragraphs) - 1:
            name = 'outro'
        elif p['duration'] > 28 and 'chorus' not in used:
            name = 'chorus'
        elif 'verse1' not in used:
            name = 'verse1'
        elif 'prechorus' not in used and p['duration'] < 22:
            name = 'prechorus'
        elif 'chorus' not in used:
            name = 'chorus'
        elif 'verse2' not in used:
            name = 'verse2'
        elif 'bridge' not in used:
            name = 'bridge'
        else:
            name = f'extra{len(used) + 1}'

        used[name] = True
        result.append({
            'id': i + 1,
            'name': name,
            'display_name': name,
            'start': round(p['start'], 2),
            'end': round(p['end'], 2),
            'duration': round(p['duration'], 2),
            'text_preview': p['text'][:80],
            'is_repeated': p['is_repeated'],
            'segment_count': p['segment_count']
        })

    return result

# ── 本地生成 label + desc（方案三：智能组合标签，主题+情绪+多关键词融合）─────────────────────────
def generate_label(name, theme, mood, text_preview):
    """
    方案三优化（智能标签）：
    1. 复用 style_map.THEME_VISUALS 全局主题库，无需重复维护
    2. 多关键词融合（最多2个），生成贴合歌词的组合主题（如：春雨、星空夜）
    3. 主题+情绪组合（如：春意-欢快、夜色-孤独），贴合MV氛围
    4. 优先级排序：主题关键词 > 歌词关键词，避免无关标签
    5. 标签简洁不臃肿，最多2个关键词+1个情绪，易读性强
    """
    # 合并「全局主题theme + 当前场景歌词text_preview」，扩大匹配范围
    full_context = f"{theme}{text_preview}"
    # 存储匹配到的主题关键词（按“主题中出现→歌词中出现”排序，保证核心主题优先）
    matched_keywords = []

    # 第一步：先匹配「全局主题theme」中的关键词（优先级最高）
    for keyword in THEME_VISUALS.keys():
        if keyword in theme and len(matched_keywords) < 2:
            matched_keywords.append(keyword)

    # 第二步：再匹配「歌词text_preview」中的关键词（补充，最多2个）
    if len(matched_keywords) < 2:
        for keyword in THEME_VISUALS.keys():
            if keyword in text_preview and keyword not in matched_keywords:
                matched_keywords.append(keyword)
                if len(matched_keywords) >= 2:
                    break

    # 情况1：匹配到1-2个主题关键词 → 生成「主题组合-情绪」标签
    if matched_keywords:
        # 组合关键词（如：春+雨 → 春雨；星+夜 → 星空夜）
        theme_label = "".join(matched_keywords)
        # 拼接情绪，形成最终标签（如：春雨-温柔、星空夜-孤独）
        return f"{theme_label}-{mood}"

    # 情况2：未匹配到任何主题关键词 → 使用默认段落通用标签（兼容方案二）
    name_label_map = {
        'intro': '序幕',
        'verse1': '故事',
        'prechorus': '蓄势',
        'chorus': '高潮',
        'verse2': '延续',
        'bridge': '转折',
        'outro': '尾声',
        'extra1': '插曲',
        'extra2': '间章',
    }
    return name_label_map.get(name, '片段')

def generate_desc(name, text_preview, theme, mood, char_prompt, art_style):
    mood_desc = get_mood_desc(mood)
    full_desc = get_fallback_desc(name, char_prompt, theme, text_preview, mood_desc, art_style)
    full_desc += ", clean cinematic frame, fixed character appearance, unified color tone"
    return full_desc + QUALITY_SUFFIX

def generate_batch_scene_descs(scenes, style, mood, char_prompt, theme, music_style=None, project_dir=None):
    if not LLM_TOKEN:
        raise ValueError("LLM_TOKEN (MINIMAX_TOKEN) environment variable not set")

    art_style = get_art_style(style)
    music_visual = get_music_style_desc(music_style)
    music_note = f"\nMusic style: {music_style}" if music_style else ""
    music_instruction = f"\nVisual atmosphere by music style: {music_visual}" if music_visual else ""

    lyric_lines = []
    for s in scenes:
        time_range = f"{int(s['start'])}s-{int(s['end'])}s"
        lyric_lines.append(f"[{time_range}] {s['text_preview']}")

    lyric_section = "\n".join(lyric_lines)

    prompt = (
        f"You are a senior MV storyboard & cinematic visual artist.\n"
        f"Generate unified coherent English image prompts for lyric-driven music video scenes.\n"
        f"\n"
        f"【Global Unified Lock Rules】\n{GLOBAL_UNIFIED_RULES}\n"
        f"\n"
        f"Overall Theme: {theme}\n"
        f"Fixed Character Reference: {char_prompt}\n"
        f"Art Style: {style}\n"
        f"Core Emotion Mood: {mood}\n"
        f"Detailed Visual Style: {art_style}{music_note}{music_instruction}\n"
        f"\n"
        f"Lyric segments with timestamp:\n"
        f"{lyric_section}\n"
        f"\n"
        f"Requirements:\n"
        f"- Each prompt 20-25 concise English words.\n"
        f"- Fit lyric artistic conception and emotional atmosphere.\n"
        f"- Ensure full video style coherence, no style jumping.\n"
        f"- Output pure valid JSON array only, no markdown, no code block, no extra explanation.\n"
        f'Format: [{{"id": 1, "desc": "scene visual description"}}, {{"id": 2, "desc": "..."}}]'
    )
    payload = json.dumps({
        'model': LLM_MODEL,
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 2048,
    }).encode('utf-8')
    req = urllib.request.Request(
        LLM_API_URL, data=payload,
        headers={'Authorization': f'Bearer {LLM_TOKEN}', 'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with _call_llm(req) as r:
            d = json.loads(r.read())
        raw = _strip_think(d['choices'][0]['message']['content'])
        raw = extract_json_array(raw)
        if raw.startswith('```'):
            lines = raw.split('\n')
            raw = '\n'.join(lines[1:-1])
            raw = extract_json_array(raw)
        results = json.loads(raw)
        ret = {}
        for item in results:
            sid = item["id"]
            desc = _strip_think(item.get("desc", "")) + QUALITY_SUFFIX
            ret[sid] = {"desc": desc}
        log = _get_logger()
        if log and project_dir:
            log(project_dir, "scene_desc_batch", LLM_MODEL, prompt,
                {"results_count": len(results), "scene_ids": list(ret.keys())},
                extra={"scene_count": len(scenes), "music_style": music_style})
        return ret
    except Exception as e:
        log = _get_logger()
        if log and project_dir:
            log(project_dir, "scene_desc_batch", LLM_MODEL, prompt, None, error=str(e))
        print(f"   batch desc failed: {e}")
        return {}

def generate_batch_variant_descs(scenes, style, mood, char_prompt, art_style=None, music_style='', project_dir=None):
    if not LLM_TOKEN:
        raise ValueError("LLM_TOKEN (MINIMAX_TOKEN) environment variable not set")

    if art_style is None:
        art_style = get_art_style(style)

    variant_scenes = []
    for s in scenes:
        if s.get('is_repeated') and s.get('duration', 0) > 4:
            scene_variants = s.get('variants', [])
            n_needed = max(2, min(3, -(-int(s['duration']) // 5)))
            if len(scene_variants) < n_needed - 1:
                variant_scenes.append(s)

    if not variant_scenes:
        return {}

    var_requests = []
    for s in variant_scenes:
        n_needed = max(2, min(3, -(-int(s['duration']) // 5))) - 1
        for vi in range(1, n_needed + 1):
            vtype, vrule = VARIANT_TYPES[vi % len(VARIANT_TYPES)]
            var_requests.append({
                "scene_id": s["id"],
                "variant_idx": vi,
                "vtype": vtype,
                "base_desc": s['desc'],
                "lyrics": s['text_preview'],
                "rule": vrule
            })

    var_section = "\n".join(
        f'[scene {r["scene_id"]} var{r["variant_idx"]}] '
        f'Original: {r["base_desc"][:60]}... '
        f'Lyrics: {r["lyrics"]} '
        f'Variation type: {r["vtype"]} - {r["rule"][:50]}'
        for r in var_requests
    )

    prompt = (
        f"Generate unified subtle variant prompts for repeated chorus MV scenes.\n"
        f"\n"
        f"【Non-negotiable Immutable Lock】\n"
        f"{GLOBAL_CHAR_LOCK}\n"
        f"{GLOBAL_SCENE_LOCK}\n"
        f"No weather change, no background replacement, no style mutation.\n"
        f"Only allow tiny adjustment: emotion / gentle action / camera angle / subtle slow movement.\n"
        f"\n"
        f"Global Fixed Style: {style}\n"
        f"Core Mood Tone: {mood}\n"
        f"Unified Art Design: {art_style}\n"
        f"Music visual rhythm tone: {music_style}\n"
        f"\n"
        f"Variant production tasks:\n"
        f"{var_section}\n"
        f"\n"
        f"Standard: 20-25 English words per description.\n"
        f"Output pure JSON array only, no comments, no extra symbols."
    )
    payload = json.dumps({
        'model': LLM_MODEL,
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 2048,
    }).encode('utf-8')
    req = urllib.request.Request(
        LLM_API_URL, data=payload,
        headers={'Authorization': f'Bearer {LLM_TOKEN}', 'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with _call_llm(req) as r:
            d = json.loads(r.read())
        raw = _strip_think(d['choices'][0]['message']['content'])
        raw = extract_json_array(raw)
        if raw.startswith('```'):
            lines = raw.split('\n')
            raw = '\n'.join(lines[1:-1])
            raw = extract_json_array(raw)
        results = json.loads(raw)
        merged = {}
        for item in results:
            sid = item['scene_id']
            if sid not in merged:
                merged[sid] = []
            var_desc = _strip_think(item.get('desc', '')) + QUALITY_SUFFIX
            merged[sid].append(var_desc)
        log = _get_logger()
        if log and project_dir:
            log(project_dir, "variant_desc_batch", LLM_MODEL, prompt,
                {"results_count": len(results), "scene_ids": list(merged.keys())},
                extra={"variant_scene_ids": [s['id'] for s in variant_scenes], "music_style": music_style})
        return merged
    except Exception as e:
        log = _get_logger()
        if log and project_dir:
            log(project_dir, "variant_desc_batch", LLM_MODEL, prompt, None, error=str(e))
        print(f"   batch variant failed: {e}")
        return {}

# ── Base Character 生成 ──────────────────────────────────────
def generate_base_char(info):
    """生成角色描述 prompt（主题感知，不再硬编码）"""
    style = info.get('style', '儿童插画风')
    mood = info.get('mood', '欢快')
    theme = info.get('theme', '')
    ref = info.get('reference', '')
    if ref and len(ref) > 10:
        return ref
    return build_char_prompt(theme, style, mood)

# ── 场景描述有效性检测（前置定义，修复NameError）─────────────────────────────────────
OLD_TEMPLATES = {
    'intro': 'A cute child looking around with wonder',
    'verse1': 'A cute child exploring nature',
    'prechorus': 'A cute child watching small animals',
    'chorus': 'A cute child singing and dancing',
    'verse2': 'A cute child making new friends',
    'outro': 'A cute child gazing at the warm sunshine',
}

TRUNCATED_PREFIXES = frozenset([
    'the user wants me to create', 'user wants me to create',
    'let me analyze the requirements', 'here is the',
    'output only 20-25 word', 'professional mv cinematic designer',
    'analyzing the requirements', 'creating a 20-25',
    'let me analyze what i need', 'they gave a detailed request',
    'we have to produce a description', 'i need to create a subtle variant',
    'the user wants a professional mv cinematic designer',
])
OLD_TEMPLATE_TAILS = frozenset([
    'heartwarming', 'gentle spring rain', 'small creatures and plants',
    'energy of spring', 'full bloom', 'sunny meadow', 'warm golden sunshine',
])

LYRIC_KEYWORDS = frozenset([
    # 童年主题（原）
    'rain ribbons', 'baby grass', 'tiny mouths', 'tadpole', 'rainbow bridge',
    'snail', 'ant', 'rabbit', 'diamond', 'dewdrops', 'drums', 'sprouts',
    'soil', 'scent', 'sparkling', 'tadpoles',
    # 失恋/乡村MV主题
    'guitar', 'road', 'rain', 'coffee', 'city', 'tears', 'memory',
    'sunset', 'highway', 'river', 'melancholy', 'solo', 'nostalgic',
    'amber', 'withered', 'fade', 'cafe', 'dim', 'dusty', 'quiet',
    'heart', 'ache', 'whisper', 'empty', 'solitude', 'silent',
])

def is_valid_desc(desc, text_preview):
    """检测 desc 是否为有效 lyric 相关的 AI 生成描述"""
    if not desc or len(desc) < 15:
        return False
    if desc in OLD_TEMPLATES.values():
        return False
    # 检测截断型描述（LLM 输出被截断或格式错误）
    desc_stripped = desc.strip().lower()
    if any(desc_stripped.startswith(p) for p in TRUNCATED_PREFIXES):
        return False
    word_count = len(desc.split())
    has_old_tail = any(tail in desc.lower() for tail in OLD_TEMPLATE_TAILS)
    if word_count < 20 and has_old_tail:
        return False
    # 更严格的长度检查：有效描述应在 16-40 词之间
    if word_count < 8 or word_count > 45:
        return False
    matches = sum(1 for kw in LYRIC_KEYWORDS if kw.lower() in desc.lower())
    if matches >= 1 or word_count >= 8:
        return True
    return False

# ── 主程序 ───────────────────────────────────────────────────
def main():
    # 设置 no_proxy（支持 Python urllib 直连）
    os.environ['no_proxy'] = '*'
    os.environ['NO_PROXY'] = '*'

    if len(sys.argv) < 2:
        print("用法: python3 analyze_srt.py <project_dir>", file=sys.stderr)
        sys.exit(1)

    project_dir = sys.argv[1]
    srt_path = os.path.join(project_dir, 'audio', 'song.srt')
    info_path = os.path.join(project_dir, 'metadata', 'info.json')
    scenes_out = os.path.join(project_dir, 'metadata', 'scenes.json')
    base_out = os.path.join(project_dir, 'metadata', 'base_char.json')

    print("🎬 解析 SRT...")
    segments = parse_srt(srt_path)
    print(f"   {len(segments)} 行歌词, {segments[-1][2]:.1f}s")

    print("📊 分析歌曲结构...")
    paragraphs = analyze_structure(segments)
    scenes = name_scenes(paragraphs)
    if not scenes:
        print("⚠️  未解析到任何歌词场景，中止")
        sys.exit(1)

    print(f"   {len(scenes)} 个场景")

    # 读取配置
    info = {}
    if os.path.exists(info_path):
        with open(info_path, 'r', encoding='utf-8') as f:
            info = json.load(f)

    style = info.get('style', '儿童插画风')
    mood = info.get('mood', '欢快')
    theme = info.get('theme', '')
    music_style = info.get('music_style', '')

    art_style = get_art_style(style)

    # 生成 label + desc
    char_prompt = ''
    if os.path.exists(base_out):
        with open(base_out, 'r', encoding='utf-8') as f:
            bc = json.load(f)
            char_prompt = bc.get('prompt', '')

    if not scenes:
        print("⚠️  未解析到任何歌词场景，中止")
        sys.exit(1)

    # 生成中文标签（方案三智能标签）
    for s in scenes:
        s['label'] = generate_label(s['name'], theme, mood, s['text_preview'])

    # 批量生成 desc（1次API调用）
    print(f"\n🤖 AI 批量生成场景描述（MiniMax-M2.7）...")
    batch_results = {}
    batch_ok = False
    try:
        batch_results = generate_batch_scene_descs(scenes, style, mood, char_prompt, theme, music_style, project_dir=project_dir)
        if batch_results:
            batch_ok = True
            print(f"   ✅ 批量成功: {len(batch_results)} 个场景")
    except Exception as e:
        print(f"   ⚠️  批量失败，将逐个生成: {e}")

    # 逐个处理 desc（幂等 + fallback）
    for i, s in enumerate(scenes):
        existing = s.get('desc', '').strip()
        if is_valid_desc(existing, s['text_preview']):
            print(f"   [{i+1}/{len(scenes)}] {s['name']:10s} ✓ (reused)")
        elif batch_ok and s['id'] in batch_results and batch_results[s['id']].get('desc'):
            s['desc'] = batch_results[s['id']]['desc']
            print(f"   [{i+1}/{len(scenes)}] {s['name']:10s} ✓ (AI batch)")
        else:
            try:
                s['desc'] = generate_desc_ai(s['text_preview'], style, mood, char_prompt, art_style, music_style, project_dir=project_dir)
                print(f"   [{i+1}/{len(scenes)}] {s['name']:10s} ✓ (AI)")
            except Exception as e:
                print(f"   [{i+1}/{len(scenes)}] {s['name']:10s} fallback ({e})")
                s['desc'] = generate_desc(s['name'], s['text_preview'], theme, mood, char_prompt, art_style)

    # 批量生成变体 desc
    s_with_var = [s for s in scenes if s.get('is_repeated') and s.get('duration', 0) > 4]
    if s_with_var:
        print(f"\n🤖 AI 批量生成变体描述（MiniMax-M2.7）...")
        try:
            var_batch = generate_batch_variant_descs(scenes, style, mood, char_prompt, art_style, music_style, project_dir=project_dir)
            if var_batch:
                for s in scenes:
                    if s['id'] in var_batch and var_batch[s['id']]:
                        s['variants'] = var_batch[s['id']]
                        for vi, vd in enumerate(s['variants']):
                            vtype = VARIANT_TYPES[(vi+1) % len(VARIANT_TYPES)][0]
                            print(f"   [{s['id']}] {s['name']:10s} var{vi+1} ({vtype}) ✓ (AI batch)")
                print(f"   ✅ 批量变体成功")
            else:
                raise ValueError("empty batch result")
        except Exception as e:
            print(f"   ⚠️  批量变体失败，将逐个生成: {e}")
            for s in scenes:
                s['variants'] = []
                if s.get('is_repeated') and s.get('duration', 0) > 4:
                    n_variants = max(2, min(3, -(-int(s['duration']) // 5)))
                    for vi in range(1, n_variants):
                        try:
                            variant_desc = generate_variant_desc(
                                s['desc'], s['text_preview'], style, mood, char_prompt, vi, music_style, project_dir=project_dir
                            )
                            s['variants'].append(variant_desc)
                            vtype = VARIANT_TYPES[vi % len(VARIANT_TYPES)][0]
                            print(f"   [{s['id']}] {s['name']:10s} var{vi} ({vtype}) ✓ (AI)")
                        except Exception as e:
                            print(f"   [{s['id']}] {s['name']:10s} var{vi} ({e})")
                            s['variants'].append("")
    else:
        for s in scenes:
            s['variants'] = []

    print(f"\n📋 生成结果:")
    for s in scenes:
        rep = "🔁" if s['is_repeated'] else "  "
        print(f"   {rep} [{s['id']}] {s['name']:10s} [{s['label']}]  {s['start']:.0f}s→{s['end']:.0f}s  ({s['duration']:.0f}s)")
        print(f"         desc: {s['desc'][:65]}...")

    # 输出
    with open(scenes_out, 'w', encoding='utf-8') as f:
        json.dump(scenes, f, ensure_ascii=False, indent=2)

    char_prompt = generate_base_char(info)
    base_data = {
        'prompt': char_prompt,
        'style': style,
        'mood': mood,
        'theme': theme
    }
    with open(base_out, 'w', encoding='utf-8') as f:
        json.dump(base_data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 完成:")
    print(f"   场景: {scenes_out}")
    print(f"   角色: {base_out}")
    print(f"   角色描述: {char_prompt[:70]}...")

if __name__ == '__main__':
    import sys
    try:
        main()
    except Exception as e:
        print(f'FATAL: {e}')
        sys.exit(1)
