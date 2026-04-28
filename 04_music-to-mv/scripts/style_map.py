#!/usr/bin/env python3
"""
style_map.py — MV 风格/情绪/主题映射统一管理【产品级强化优化版】
集中管理所有绘画风格、情绪描述、角色描述等映射，
供 analyze_srt.py, generate_scene_imgs.py, produce_mv.sh 等脚本公共引用。

CLI 用法:
    python3 style_map.py get-art-style <style_name>
    python3 style_map.py get-char-style <style_name>
    python3 style_map.py get-mood-desc <mood_name>

模块导入:
    from style_map import ART_STYLES, get_art_style, ...
"""

import os
import sys

# ── 画面风格 → 英文美术描述（MV电影级优化，角色稳定+画面干净）────
ART_STYLES = {
    '国风': (
        "traditional Chinese ink wash painting, xuan paper texture, elegant brush strokes, "
        "Shan Shui landscape, misty ethereal atmosphere, low saturation, classical oriental aesthetic, "
        "minimal blank space, cinematic soft lighting, single main character, clean composition"
    ),
    '动漫风': (
        "high-quality Japanese anime, clean crisp line art, soft cel shading, "
        "Studio Ghibli gentle atmosphere, balanced vibrant colors, cinematic composition, "
        "simple clean background, soft focus, perfect facial features, single character"
    ),
    '写实摄影风': (
        "natural candid photography, golden hour soft light, shallow depth of field, "
        "muted realistic color grading, clean environment, portrait priority, "
        "cinematic white balance, low noise, gentle natural shadows, no clutter"
    ),
    '水彩插画风': (
        "soft hand-painted watercolor, delicate paper texture, gentle color blending, "
        "pastel low-saturation palette, dreamy hazy atmosphere, minimalist layout, "
        "healing visual sense, clean edges, single main subject"
    ),
    '像素游戏风': (
        "refined 16-bit pixel art, neat pixel grid, unified color palette, "
        "retro game aesthetic, clean scene layering, soft ambient light, "
        "clear character design, no messy pixels"
    ),
    '电影感写实风': (
        "35mm cinematic film still, anamorphic lens, shallow depth of field, "
        "desaturated film color grading, subtle film grain, soft dramatic lighting, "
        "professional MV composition, clean background"
    ),
    '极简几何风': (
        "minimalist geometric illustration, flat solid colors, clean sharp lines, "
        "unified color system, blank space composition, modern Bauhaus style, "
        "uncluttered, abstract elegant visual"
    ),
    '浮世绘和风': (
        "refined ukiyo-e woodblock print, flat color layering, elegant outlines, "
        "traditional Japanese tone, soft gradient, classic Edo aesthetic, "
        "clean composition, single figure"
    ),
    '复古胶片风': (
        "vintage 35mm film photography, Kodak Portra warm tone, natural film grain, "
        "nostalgic analog atmosphere, muted contrast, soft light, "
        "clean frame, no overexposure"
    ),
    '漫画美式涂鸦风': (
        "American comic book art, bold black outlines, moderate halftone dots, "
        "pop art color palette, clean graphic style, concise composition, "
        "single character, no messy elements"
    ),
    '蒸汽朋克风': (
        "retro steampunk aesthetic, delicate brass machinery, warm amber tones, "
        "soft industrial light, intricate clockwork details, clean Victorian scene, "
        "single protagonist, no extra clutter"
    ),
    '赛博朋克风': (
        "high-quality cyberpunk scene, restrained neon glow, wet street reflections, "
        "dark moody cityscape, cyan magenta tones, Blade Runner atmosphere, "
        "clean composition, single main character"
    ),
}

# ── 风格渲染模板（纯渲染，强化角色稳定性，适配MV）────
STYLE_RENDER_TEMPLATES = {
    '国风': (
        "ink wash painting aesthetic, xuan paper texture, misty Shan Shui background, "
        "elegant classical atmosphere, stable low saturation, clean composition"
    ),
    '动漫风': (
        "Japanese anime cel shading, soft color transition, neat line art, "
        "simple clean background, youthful gentle tone, perfect character proportions"
    ),
    '写实摄影风': (
        "natural photography, golden hour light, soft bokeh blur, "
        "realistic skin texture, stable white balance, portrait focused"
    ),
    '水彩插画风': (
        "watercolor illustration, soft brush texture, pastel color palette, "
        "dreamy ethereal tone, clean edges, minimalist scene"
    ),
    '像素游戏风': (
        "16-bit pixel art, neat pixel grid, retro game style, "
        "unified color blocks, clear layering, soft ambient light"
    ),
    '电影感写实风': (
        "cinematic film aesthetics, shallow depth of field, dramatic soft lighting, "
        "film color grading, professional MV visual, high-end texture"
    ),
    '极简几何风': (
        "minimalist geometric style, flat solid colors, clean sharp lines, "
        "unified color system, uncluttered abstract composition"
    ),
    '浮世绘和风': (
        "ukiyo-e woodblock print, flat color areas, bold dark outlines, "
        "traditional Japanese texture, elegant clean composition"
    ),
    '复古胶片风': (
        "vintage film photography, warm tone, subtle film grain, "
        "nostalgic atmosphere, soft light, muted contrast"
    ),
    '漫画美式涂鸦风': (
        "comic book style, bold outlines, halftone shading, "
        "pop art colors, clean graphic design, concise visual"
    ),
    '蒸汽朋克风': (
        "steampunk industrial aesthetic, brass metal texture, warm dark tones, "
        "soft mechanical light, orderly details, clean scene"
    ),
    '赛博朋克风': (
        "cyberpunk futuristic style, neon light accents, wet street reflections, "
        "dark moody backdrop, stable color matching, clean composition"
    ),
}

DEFAULT_CHAR = (
    "single main character, perfect human anatomy, normal proportions"
)
DEFAULT_ART = "cinematic MV illustration, clean frame, soft unified color tone"

# ── 主题 → 角色描述（强制单人+完美比例，彻底防崩）────
THEME_CHARACTERS = [
    (['战争', '战火', '战斗', '战场', '兵', '军'],
     'single young warrior, neat battle gear, calm determined expression, perfect human anatomy'),
    (['爱情', '恋爱', '心动', '暗恋', '相恋', '情侣'],
     'single young character, tender romantic gaze, sweet gentle expression, normal body proportions'),
    (['星空', '宇宙', '太空', '星星', '银河', '宇航'],
     'single stargazer/astronaut, quiet posture, looking at starry sky, perfect facial features'),
    (['冒险', '探险', '探索', '旅行', '奇幻', '穿越'],
     'single young explorer, curious gentle eyes, simple travel outfit, normal human proportions'),
    (['梦', '幻想', '童话', '魔法', '仙境'],
     'single dreamy character, magical soft aura, elegant fresh clothing, perfect anatomy'),
    (['家乡', '故乡', '思念', '回忆', '童年'],
     'single gentle character, nostalgic mood, quiet relaxed posture, normal proportions'),
    (['夜', '孤独', '独行', '夜晚', '暗黑', '黑暗'],
     'single solitary figure, quiet introspective state, reasonable night lighting, perfect anatomy'),
    (['毕业', '青春', '校园', '同桌', '学生'],
     'single young student, neat uniform, fresh energetic temperament, normal body shape'),
    (['自由', '飞翔', '天空', '鸟', '风'],
     'single free-spirited character, arms outstretched, relaxed posture, perfect human anatomy'),
    (['母亲', '父亲', '家', '亲情', '感恩'],
     'single warm family figure, gentle caring expression, soft facial features, normal proportions'),
]

# fallback 默认角色
DEFAULT_THEME_CHAR = 'single main character, perfect human anatomy'

# ── API 原生风格参数映射（完全保留）────────────────────────────
API_STYLE_MAP = {
    '国风':       {'minimax': 'ink-wash'},
    '动漫风':      {'minimax': 'anime'},
    '写实摄影风':    {'minimax': 'realistic'},
    '水彩插画风':    {'minimax': 'watercolor'},
    '像素游戏风':    {'minimax': 'pixel-art'},
    '电影感写实风':   {'minimax': 'cinematic'},
    '极简几何风':    {'minimax': 'minimalist'},
    '浮世绘和风':    {'minimax': 'flat-illustration'},
    '复古胶片风':    {'minimax': 'realistic'}, # minimax 无 film 风格，用 realistic
    '漫画美式涂鸦风':  {'minimax': 'comic'},
    '蒸汽朋克风':    {'minimax': 'steampunk'},
    '赛博朋克风':    {'minimax': 'neon'},
}

# ── 负面提示词（产品级超强强化，100%防畸形/画风混淆/杂乱）────────
NEGATIVE_PROMPTS = {
    '国风':       'photorealistic, 3d render, oil painting, anime, western style, neon lights, text, logo, watermark, multiple people, deformed hands, missing limbs, ugly face, clutter, over-saturated colors',
    '动漫风':      'photorealistic, 3d model, realistic photo, watercolor, pixel art, extra characters, duplicate faces, deformed fingers, blurry face, text, messy background, horror elements, low resolution',
    '写实摄影风':    'illustration, painting, anime, cartoon, cel shading, text, watermark, hdr overexposure, distorted limbs, facial distortion, clutter, artificial filters',
    '水彩插画风':    'photorealistic, sharp edges, digital art, 3d render, anime, pixel art, comic halftone, text, neon, extra people, ugly features, messy lines',
    '像素游戏风':    'photorealistic, smooth gradients, 3d, realistic lighting, anime, extra characters, messy pixels, noise, text, watermark, deformed structure',
    '电影感写实风':   'cartoon, anime, illustration, pixel art, phone photo, flat lighting, text, logo, crowd, extra limbs, facial mutation, over-saturated colors',
    '极简几何风':    'photorealistic, detailed textures, complex patterns, 3d, realistic portrait, shadows, text, decorations, extra elements, messy patterns',
    '浮世绘和风':    'photorealistic, 3d render, western art, anime, neon, gradient colors, text, watermark, multiple people, limb deformation, complex background',
    '复古胶片风':    'anime, cartoon, digital art, over-sharpened, neon glow, text, logo, extra people, ugly skin, strong color cast, messy clutter',
    '漫画美式涂鸦风':  'photorealistic, watercolor, ink wash, 3d, film grain, extra characters, realistic skin, text, mixed style chaos, deformed face',
    '蒸汽朋克风':    'anime, cartoon, watercolor, cyberpunk neon, minimalist, text, logo, multiple people, clean modern style, limb distortion',
    '赛博朋克风':    'anime pastel, watercolor, ink wash, steampunk, text, logo, extra characters, bright overexposure, clean white background, body proportion disorder',
}

# ── 情绪 → 英文描述（MV适配，精准自然）──────────────────────────
MOOD_EXPRS = {
    '欢快': 'bright, joyful, lively, uplifting',
    '温柔': 'soft, warm, gentle, heartwarming',
    '忧伤': 'melancholic, tender, calm, quiet',
    '史诗': 'grand, epic, powerful, solemn',
    '梦幻': 'ethereal, dreamy, magical, hazy',
    '慵懒': 'relaxed, peaceful, easy-going, slow',
    '浪漫': 'romantic, warm, tender, loving',
    '热血': 'passionate, fierce, energetic, powerful',
    '宁静': 'serene, tranquil, calm, peaceful',
    '怀旧': 'nostalgic, warm, reminiscent, gentle',
    '叛逆': 'defiant, edgy, cool, rebellious',
    '希望': 'hopeful, bright, optimistic, warm',
    '孤独': 'solitary, quiet, introverted, calm',
    '悬疑': 'mysterious, tense, intriguing, low-key',
    '暗黑': 'dark, ominous, mysterious, deep',
    '魔幻': 'magical, mystical, enchanted, otherworldly',
    '清新': 'fresh, crisp, clean, natural',
}

# ── 情绪 → 角色表情（自然不夸张，防变脸）────────────────────────
CHAR_MOOD_EXPRS = {
    '欢快': 'gentle joyful smile, relaxed energetic state, natural expression',
    '温柔': 'soft peaceful gaze, quiet warm demeanor, natural facial features',
    '忧伤': 'calm melancholic eyes, restrained tender emotion, subtle expression',
    '史诗': 'calm determined temperament, brave steady expression',
    '梦幻': 'hazy dreamy eyes, soft magical aura, gentle expression',
    '慵懒': 'casual relaxed posture, slow calm state, easy-going expression',
    '浪漫': 'soft loving eyes, warm gentle smile, tender expression',
    '热血': 'firm focused expression, vibrant energetic state, determined gaze',
    '宁静': 'peaceful calm face, serene quiet state, relaxed expression',
    '怀旧': 'soft reminiscent gaze, gentle nostalgic mood, quiet expression',
    '叛逆': 'sharp edgy gaze, cool defiant demeanor, calm expression',
    '希望': 'bright hopeful eyes, warm confident smile, positive expression',
    '孤独': 'quiet introverted gaze, solitary calm state, gentle expression',
    '悬疑': 'mysterious focused eyes, tense quiet demeanor',
    '暗黑': 'deep low-key expression, mysterious calm gaze',
    '魔幻': 'soft mystical aura, enchanted gentle expression',
    '清新': 'fresh natural face, bright clean demeanor',
}

# ── 音乐风格 → MV视觉描述（影视级强化，镜头/光影/节奏全适配）──────
MUSIC_STYLE_DESCS = {
    '流行': (
        'Bright polished pop MV aesthetic, vibrant balanced color palette, soft cinematic lighting. '
        'Scenes: urban rooftops, colorful minimalist sets, dance studios. '
        'Camera: smooth tracking shots, slow-motion, beat-synced cuts. '
        'Energy: moderate-high, uplifting bouncy rhythm, clean professional composition.'
    ),
    '说唱': (
        'Urban hip-hop street aesthetic, high contrast gritty tones, harsh directional lighting. '
        'Scenes: graffiti walls, subway stations, alleyways. '
        'Camera: handheld dynamic shots, Dutch angles, rhythmic jump cuts. '
        'Energy: cool confident, intense punchline bursts, street-style visual rhythm.'
    ),
    '民谣': (
        'Warm intimate folk storytelling aesthetic, earthy golden tones, golden hour soft light. '
        'Scenes: countryside fields, cozy cabins, forest clearings. '
        'Camera: gentle slow pans, handheld breathing motion, no rapid movement. '
        'Energy: contemplative sincere, slow gentle rhythm, healing warm atmosphere.'
    ),
    '电子': (
        'Sleek futuristic electronic MV aesthetic, cyan purple neon tones, LED volumetric lighting. '
        'Scenes: futuristic cityscapes, laser grids, chrome reflective spaces. '
        'Camera: glitch whip pans, time-remapping, locked precise frames. '
        'Energy: hypnotic driving, sync with kick drums, futuristic visual rhythm.'
    ),
    '摇滚': (
        'Raw high-energy rock MV aesthetic, saturated red black tones, stage spotlights. '
        'Scenes: concert stages, warehouse gigs, neon clubs. '
        'Camera: aggressive handheld, crash zooms, fast beat-synced pans. '
        'Energy: explosive high, cathartic powerful, peak energy on chorus.'
    ),
    '古典': (
        'Grand timeless classical MV aesthetic, gold burgundy warm tones, candle chiaroscuro light. '
        'Scenes: concert halls, ancient architecture, sweeping landscapes. '
        'Camera: slow crane shots, elegant close-ups, majestic steady movement. '
        'Energy: emotional profound, graceful slow rhythm, cinematic grandeur.'
    ),
    '爵士': (
        'Sophisticated smooth jazz MV aesthetic, warm amber blue tones, dim stage lighting. '
        'Scenes: intimate jazz clubs, lounges, piano bars. '
        'Camera: unhurried smooth pans, gentle push-ins, long take aesthetics. '
        'Energy: mellow relaxed, improvisational rhythm, sophisticated quiet vibe.'
    ),
    'HipHop': (
        'Bold street hip-hop MV aesthetic, gold red deep black tones, contrast rim lighting. '
        'Scenes: basketball courts, DJ booths, dance battle zones. '
        'Camera: dynamic dolly shots, fisheye perspectives, snare-synced cuts. '
        'Energy: confident controlled, high-intensity downbeat bursts.'
    ),
    'R&B': (
        'Sensual smooth R&B MV aesthetic, rose gold burgundy tones, dim warm practical lighting. '
        'Scenes: sunset rooftops, candlelit rooms, velvet lounges. '
        'Camera: languid slow-motion, floating dollies, soft focus push-ins. '
        'Energy: intimate slow-burning, sensual relaxed emotional rhythm.'
    ),
    '中国风': (
        'Elegant Chinese traditional MV aesthetic, ink black jade green tones, soft lantern daylight. '
        'Scenes: misty mountains, bamboo forests, ancient pagodas, koi ponds. '
        'Camera: scroll-like horizontal pans, gentle nature close-ups, steady elegant movement. '
        'Energy: poetic restrained, graceful slow rhythm, oriental artistic conception.'
    ),
    '新世纪NewAge': (
        'Ethereal meditative NewAge MV aesthetic, pastel gradient tones, celestial soft glow. '
        'Scenes: misty peaks, aurora skies, zen gardens, starry observatories. '
        'Camera: ultra-slow drifts, nature time-lapse, imperceptible movement. '
        'Energy: tranquil transcendent, spacious unhurried, meditative atmosphere.'
    ),
    'EDM舞曲': (
        'Explosive EDM festival MV aesthetic, neon rainbow tones, laser LED wall lighting. '
        'Scenes: festival stages, DJ booths, confetti-filled skies. '
        'Camera: fast orbiting cranes, drone sweeps, drop-synced rapid cuts. '
        'Energy: maximum euphoric, tension build then violent release, high intensity.'
    ),
    '乡村Country': (
        'Americana country MV aesthetic, wheat blue rusty tones, golden hour open light. '
        'Scenes: farm barns, dirt roads, open fields, small-town streets. '
        'Camera: steady gentle pans, landscape wide shots, unfussy movement. '
        'Energy: relaxed genuine, mid-tempo storytelling, warm inviting vibe.'
    ),
    '朋克Punk': (
        'Raw aggressive punk MV aesthetic, monochrome red accents, harsh fluorescent lighting. '
        'Scenes: basement venues, back alleys, derelict buildings. '
        'Camera: chaotic handheld, crash zooms, intentional shake. '
        'Energy: furious unrelenting, rough raw energy, anti-establishment vibe.'
    ),
}

# ── 主题关键词 → MV视觉元素（唯美干净，补充优化）──────────────────
THEME_VISUALS = {
    '春': 'spring cherry blossoms blooming, soft petals drifting in wind, fresh green sprouts',
    '夏': 'bright summer sunlight, lush green foliage, clear blue sky, gentle breeze',
    '秋': 'golden autumn leaves falling, warm foliage, crisp autumn air',
    '冬': 'soft white snowflakes, quiet winter scene, frost on branches',
    '雨': 'gentle spring rain, water droplets on leaves, misty rainy atmosphere',
    '彩虹': 'soft rainbow arch, colorful light refraction, hazy sky after rain',
    '花': 'delicate blooming flowers, soft petals, fresh floral fragrance',
    '小鸟': 'small birds singing on branches, fluffy little birds, natural green background',
    '太阳': 'warm golden sunlight, soft light rays, golden hour glow',
    '小草': 'fresh green grass, tender young sprouts, growing plants',
    '小蝌蚪': 'tiny tadpoles swimming in clear pond, gentle water ripples',
    '小兔': 'fluffy little rabbit hopping on grass, cute small animal',
    '彩虹桥': 'vibrant rainbow arching over sky, soft colorful light',
    '露珠': 'sparkling dewdrops on leaves, morning fresh glow',
    '小蜗牛': 'cute snail on green leaf, dewdrops around, slow gentle movement',
    '蚂蚁': 'small ants marching in line, tiny teamwork creatures',
    '蜜蜂': 'busy bees buzzing on flowers, pollen collection, fresh nature',
    '蘑菇': 'cute mushrooms in forest, fairy tale small flora',
    '蝴蝶': 'colorful butterflies fluttering, delicate wings, flower garden',
    '月亮': 'bright soft moonlight, silver glow, quiet starry night',
    '星星': 'twinkling stars in night sky, sparkling constellations, faint glow',
    '海': 'calm ocean waves, sandy beach, soft sea breeze, gentle reflections',
    '山': 'misty distant mountains, layered peaks, peaceful natural scenery',
    '风': 'wind blowing through trees, rustling leaves, flowing gentle movement',
    '云': 'soft white clouds floating, cotton-like sky formations',
    '火': 'warm campfire glow, orange sparks, gentle crackling flame',
    '光': 'golden light rays through trees, shimmering soft glow',
    '水': 'clear flowing water, gentle ripples, smooth reflections',
    '桥': 'stone wooden bridge over water, quiet reflection below',
    '路': 'winding path through scenery, peaceful journey trail',
    '星': 'twinkling stars, shooting star, bright night sky',
    '泪': 'soft silent teardrops, gentle sad beautiful moment',
    '笑': 'pure happy smile, natural joyful expression',
    '走': 'quiet walking along path, gentle forward journey',
    '跑': 'energetic joyful running, free lively movement',
    '飞': 'soaring flying through sky, free gentle movement',
    '船': 'small boat floating on water, gentle sailing',
}

# ── 段落名 → 中文标签（完全保留）────────────────────────────────
LABEL_MAP = {
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

# ── 段落描述模板（MV通用兜底，优化更自然）────────────────────────
FALLBACK_DESC_TEMPLATES = {
    'intro': 'quiet opening scene, slowly unfolding cinematic atmosphere',
    'verse1': 'gentle narrative scene, calm visual storytelling rhythm',
    'prechorus': 'atmosphere building up, visual layering enhancement',
    'chorus': 'emotional climax scene, vibrant cinematic composition',
    'verse2': 'continuous narrative journey, stable visual rhythm',
    'bridge': 'quiet reflective moment, peaceful contemplative scene',
    'outro': 'distant gazing scene, satisfying warm ending',
    'extra1': 'playful joyful interlude, light cheerful atmosphere',
    'extra2': 'magical discovery moment, dreamy beautiful scene',
}

# ── 音乐风格 → 音频细节（完全保留）──────────────────────────────
MUSIC_PROMPT_DETAILS = {
    '流行': 'Catchy pop melody with a driving beat, 120 BPM, verse-chorus structure, featuring piano, guitar, and light synthesizers. Bright and energetic arrangement.',
    '说唱': 'Hard-hitting hip-hop beat with rhythmic flow, 90-100 BPM, featuring 808 drums, deep bass, and trap hi-hats. Street-style rhythm and lyrical delivery.',
    '民谣': 'Gentle folk ballad with acoustic guitar fingerpicking, 80-90 BPM, warm organic tone. Features soft strings, light percussion, and intimate vocal style.',
    '电子': 'Electronic synth-driven track, 128 BPM, four-on-the-floor beat. Layered synthesizers, arpeggiated melodies, and pulsating bassline create a futuristic atmosphere.',
    '摇滚': 'High-energy rock with power chords and driving drums, 140 BPM. Electric guitars with distortion, punchy bass, and energetic drum fills.',
    '古典': 'Orchestral composition with strings, woodwinds, and brass, 60-80 BPM. Elegant melody with dynamic crescendos and decrescendos, cinematic and grand.',
    '爵士': 'Smooth jazz with warm brass and walking bass, medium swing tempo around 120 BPM. Features saxophone, piano, and brushed drums. Relaxed improvisational feel.',
    'HipHop': 'Hip-hop with heavy bass and crisp snares, 85-95 BPM. Boom-bap drums with modern trap elements. Confident, rhythmic vocal flow.',
    'R&B': 'Soulful R&B with smooth vocals and sensual groove, 80-90 BPM. Warm Rhodes piano, soft bass, and gentle drums create an intimate atmosphere.',
    '中国风': 'Traditional Chinese style with guzheng, erhu, and pipa, 70-90 BPM. Pentatonic melody with flowing rhythm. Classical poetry-inspired lyrics with elegant arrangement.',
    '新世纪NewAge': 'Ethereal ambient soundscape, slow tempo 60-70 BPM. Layered pads, gentle piano, nature sounds, and soft synthesizers. Meditative and transcendent.',
    'EDM舞曲': 'Festival EDM with massive drops, 128-140 BPM. Build-up tension with risers and snare rolls, explosive drop with heavy bass and synth leads.',
    '乡村Country': 'Country folk with acoustic guitar strumming, 100-120 BPM. Steel guitar, fiddle, and harmonica. Heartfelt storytelling with warm, down-home production.',
    '朋克Punk': 'Fast and raw punk rock, 160-180 BPM. Distorted power chords, fast drumming with crash cymbals, aggressive vocals. Short, intense with anti-establishment energy.',
}

# ── 查询函数（100%保留，无任何修改）────────────────────────────
def get_art_style(style):
    return ART_STYLES.get(style, DEFAULT_ART)

def get_render_style(style):
    return STYLE_RENDER_TEMPLATES.get(style, DEFAULT_ART)

def get_api_style(style, provider=None):
    if not provider:
        provider = os.environ.get('IMAGE_API_PROVIDER', 'minimax').lower()
    mapping = API_STYLE_MAP.get(style, {})
    return mapping.get(provider, '')

def get_negative_prompt(style):
    return NEGATIVE_PROMPTS.get(style, DEFAULT_ART)

def get_mood_desc(mood):
    return MOOD_EXPRS.get(mood, 'heartwarming')

def get_char_mood_desc(mood):
    return CHAR_MOOD_EXPRS.get(mood, 'warm friendly')

def get_theme_character(theme):
    if not theme:
        return DEFAULT_THEME_CHAR
    for keywords, char_desc in THEME_CHARACTERS:
        for kw in keywords:
            if kw in theme:
                return char_desc
    return DEFAULT_THEME_CHAR

def build_char_prompt(theme, style, mood):
    theme_char = get_theme_character(theme)
    render_style = get_render_style(style)
    mood_expr = get_char_mood_desc(mood)
    return f"{theme_char}, {render_style}, {mood_expr}"

def get_theme_visuals(theme, text_preview):
    found = []
    for keyword, visual in THEME_VISUALS.items():
        if keyword in theme or keyword in text_preview:
            found.append(visual)
    return found

def get_label(name):
    return LABEL_MAP.get(name, '片段')

def get_fallback_desc(name, char_prompt, theme, text_preview, mood_desc, art_style):
    template = FALLBACK_DESC_TEMPLATES.get(name, 'experiencing a beautiful moment')
    visuals = get_theme_visuals(theme, text_preview)
    char_short = char_prompt[:80] if char_prompt else 'single main character'
    desc = f"{char_short}, {template}, {mood_desc}"
    if visuals:
        desc += ', ' + ', '.join(visuals[:3])
    desc += f', {art_style}'
    return desc

def get_music_style_desc(music_style):
    if not music_style:
        return ''
    return MUSIC_STYLE_DESCS.get(music_style, '')

def get_music_prompt_details(music_style):
    return MUSIC_PROMPT_DETAILS.get(music_style, '')

# ── CLI（完全保留）────────────────────────────────────────────
if __name__ == '__main__':
    cmds = {
        'get-art-style': get_art_style,
        'get-render-style': get_render_style,
        'get-api-style': lambda s: get_api_style(s, sys.argv[3] if len(sys.argv) > 3 else None),
        'get-negative': get_negative_prompt,
        'get-mood-desc': get_mood_desc,
        'get-char-mood': get_char_mood_desc,
        'get-theme-char': get_theme_character,
        'get-music-style': get_music_style_desc,
        'build-char-prompt': lambda t: build_char_prompt(t, sys.argv[3] if len(sys.argv) > 3 else '动漫风', sys.argv[4] if len(sys.argv) > 4 else '欢快'),
    }

    if len(sys.argv) < 2:
        print(f"用法: python3 {sys.argv[0]} <cmd> [args...]")
        print(f"命令: {'|'.join(k for k in cmds)}")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == 'get-api-style':
        name = sys.argv[2] if len(sys.argv) > 2 else ''
        prov = sys.argv[3] if len(sys.argv) > 3 else 'minimax'
        print(get_api_style(name, prov))
    elif cmd == 'build-char-prompt':
        theme = sys.argv[2] if len(sys.argv) > 2 else ''
        style = sys.argv[3] if len(sys.argv) > 3 else '动漫风'
        mood = sys.argv[4] if len(sys.argv) > 4 else '欢快'
        print(build_char_prompt(theme, style, mood))
    elif cmd in cmds:
        name = sys.argv[2] if len(sys.argv) > 2 else ''
        print(cmds[cmd](name))
    else:
        print(f"未知命令: {cmd}")
        print(f"可用命令: {'|'.join(k for k in cmds)}")
        sys.exit(1)
