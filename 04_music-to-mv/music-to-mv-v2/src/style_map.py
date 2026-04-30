"""
style_map.py — MV 风格/情绪/主题映射统一管理

集中管理所有绘画风格、情绪描述、角色描述等映射。
这是从原版 style_map.py 移植过来的数据层，供 v2 所有模块使用。

用法：
    from src.style_map import ART_STYLES, get_art_style, ...

CLI 用法：
    python -m src.style_map get-art-style <style_name>
"""

import json
import re
import sys


# ════════════════════════════════════════════════════════════
# 统一风格字典（art / render / character / api / negative）
# 新增风格只需在此处添加一个条目
# ════════════════════════════════════════════════════════════

STYLES = {
    "国风": {
        "art": (
            "traditional Chinese ink wash painting, xuan paper texture, elegant brush strokes, "
            "Shan Shui landscape, misty ethereal atmosphere, low saturation, classical oriental aesthetic, "
            "minimal blank space, cinematic soft lighting, poetic subject focus, clean composition"
        ),
        "render": (
            "ink wash painting aesthetic, xuan paper texture, misty Shan Shui background, "
            "elegant classical atmosphere, stable low saturation, clean composition"
        ),
        "character": (
            "A cute Chinese boy in traditional Hanfu clothing, 8 years old, "
            "with classic bun hairstyle, gentle expression, elegant classical Chinese attire"
        ),
        "api": "traditional_chinese_art",
        "negative": "text, watermark, signature, frame, border, overexposed, too bright, messy composition, multiple subjects",
    },
    "动漫风": {
        "art": (
            "high-quality Japanese anime, clean crisp line art, soft cel shading, "
            "Studio Ghibli gentle atmosphere, balanced vibrant colors, cinematic composition, "
            "simple clean background, soft focus, perfect facial features, varied scene composition"
        ),
        "render": (
            "Japanese anime cel shading, soft color transition, neat line art, "
            "simple clean background, youthful gentle tone, perfect character proportions"
        ),
        "character": (
            "A cute Chinese anime boy, 8 years old, with spiky black hair, "
            "large expressive eyes, cheerful smile, wearing casual colorful t-shirt and shorts"
        ),
        "api": "anime",
        "negative": "text, watermark, signature, frame, ugly, deformed, blurry, low quality, messy background, extra characters",
    },
    "写实摄影风": {
        "art": (
            "natural candid photography, golden hour soft light, shallow depth of field, "
            "muted realistic color grading, clean environment, portrait priority, "
            "cinematic white balance, low noise, gentle natural shadows, no clutter"
        ),
        "render": (
            "natural photography, golden hour light, soft bokeh blur, "
            "realistic skin texture, stable white balance, portrait focused"
        ),
        "character": (
            "A real Chinese boy, 7-8 years old, natural portrait, "
            "short black hair, genuine smile, casual comfortable daily wear"
        ),
        "api": "photography",
        "negative": "text, watermark, signature, frame, cartoon, illustration, painting, deformed face, blurry",
    },
    "水彩插画风": {
        "art": (
            "soft hand-painted watercolor, delicate paper texture, gentle color blending, "
            "pastel low-saturation palette, dreamy hazy atmosphere, minimalist layout, "
            "healing visual sense, clean edges, single main subject"
        ),
        "render": (
            "watercolor illustration, soft brush texture, pastel color palette, "
            "dreamy ethereal tone, clean edges, minimalist scene"
        ),
        "character": (
            "A cute little boy, 7-8 years old, watercolor illustration style, "
            "soft features, gentle smile, wearing light colored casual clothes"
        ),
        "api": "watercolor",
        "negative": "text, watermark, signature, frame, messy splashes, over wet, bleeding colors, messy composition",
    },
    "像素游戏风": {
        "art": (
            "refined 16-bit pixel art, neat pixel grid, unified color palette, "
            "retro game aesthetic, clean scene layering, soft ambient light, "
            "clear character design, no messy pixels"
        ),
        "render": (
            "pixel art rendering, retro game palette, clean pixel edges, "
            "consistent resolution, simple background elements"
        ),
        "character": None,
        "api": "pixel_art",
        "negative": None,
    },
    "电影感写实风": {
        "art": (
            "35mm cinematic film still, anamorphic lens, shallow depth of field, "
            "desaturated film color grading, subtle film grain, soft dramatic lighting, "
            "professional MV composition, clean background"
        ),
        "render": (
            "cinematic film rendering, soft dramatic contrast, shallow depth of field, "
            "35mm film texture, professional color grading"
        ),
        "character": None,
        "api": "cinematic",
        "negative": None,
    },
    "极简几何风": {
        "art": (
            "minimalist geometric illustration, flat solid colors, clean sharp lines, "
            "unified color system, blank space composition, modern Bauhaus style, "
            "uncluttered, abstract elegant visual"
        ),
        "render": (
            "geometric flat illustration, solid color blocks, clean sharp geometry, "
            "minimalist composition, modern aesthetic"
        ),
        "character": None,
        "api": "minimalist",
        "negative": None,
    },
    "浮世绘和风": {
        "art": (
            "refined ukiyo-e woodblock print, flat color layering, elegant outlines, "
            "traditional Japanese tone, soft gradient, classic Edo aesthetic, "
            "clean composition, single figure"
        ),
        "render": (
            "ukiyo-e woodblock print style, flat colors, elegant line work, "
            "traditional Japanese aesthetic, soft atmospheric tone"
        ),
        "character": None,
        "api": "ukiyo_e",
        "negative": None,
    },
    "复古胶片风": {
        "art": (
            "vintage 35mm film photography, Kodak Portra warm tone, natural film grain, "
            "nostalgic analog atmosphere, muted contrast, soft light, "
            "clean frame, no overexposure"
        ),
        "render": (
            "vintage film photography, warm analog tones, soft grain, "
            "Kodak Portra aesthetic, nostalgic atmosphere"
        ),
        "character": None,
        "api": "retro_film",
        "negative": None,
    },
    "漫画美式涂鸦风": {
        "art": (
            "American comic book art, bold black outlines, moderate halftone dots, "
            "pop art color palette, clean graphic style, concise composition, "
            "clear focal subject, no messy elements"
        ),
        "render": (
            "American comic book style, bold outlines, halftone dots, "
            "pop art colors, dynamic clean composition"
        ),
        "character": None,
        "api": "comic_book",
        "negative": None,
    },
    "蒸汽朋克风": {
        "art": (
            "retro steampunk aesthetic, delicate brass machinery, warm amber tones, "
            "soft industrial light, intricate clockwork details, clean Victorian scene, "
            "clear focal subject, no extra clutter"
        ),
        "render": (
            "steampunk aesthetic, brass and copper details, warm amber glow, "
            "Victorian era atmosphere, mechanical elegance"
        ),
        "character": None,
        "api": "steampunk",
        "negative": None,
    },
    "赛博朋克风": {
        "art": (
            "high-quality cyberpunk scene, restrained neon glow, wet street reflections, "
            "dark moody cityscape, cyan magenta tones, Blade Runner atmosphere, "
            "clean composition, strong visual focal point"
        ),
        "render": (
            "cyberpunk aesthetic, neon highlights, dark urban atmosphere, "
            "rain reflections, futuristic cityscape"
        ),
        "character": (
            "A cute boy in cyberpunk world, 8 years old, with glowing cybernetic accessories, "
            "neon light reflections, futuristic streetwear, determined expression"
        ),
        "api": "cyberpunk",
        "negative": None,
    },
    # 主题叠加风格（仅 character 字段，无完整画风参数）
    "古风": {
        "art": None,
        "render": None,
        "character": (
            "A cute Chinese boy in ancient style, 8 years old, "
            "wearing traditional robes, classical scholar appearance, gentle refined expression"
        ),
        "api": None,
        "negative": None,
    },
    "童话": {
        "art": None,
        "render": None,
        "character": (
            "A cute little boy with fairy tale charm, 8 years old, "
            "messy hair, curious expression, wearing storybook style adventure clothes"
        ),
        "api": None,
        "negative": None,
    },
}

_DEFAULT_STYLE = "动漫风"
_DEFAULT_CHARACTER = (
    "A cute Chinese boy, 7-8 years old, with short black slightly curly hair, "
    "big bright eyes, warm smile, wearing simple white t-shirt and dark shorts"
)
_DEFAULT_NEGATIVE = (
    "text, watermark, signature, frame, border, deformed, blurry, "
    "low quality, ugly, multiple subjects, messy composition, "
    "extra limbs, bad anatomy, disfigured, mutation"
)

# 向后兼容别名（供需要直接访问旧字典的代码使用）
ART_STYLES = {k: v["art"] for k, v in STYLES.items() if v["art"]}
STYLE_RENDER_TEMPLATES = {k: v["render"] for k, v in STYLES.items() if v["render"]}


# ════════════════════════════════════════════════════════════
# 情绪 → 描述
# ════════════════════════════════════════════════════════════

MOOD_DESCRIPTIONS = {
    "欢快": "bright joyful atmosphere, warm golden sunlight, smiling expressions, energetic vibe",
    "温柔": "soft warm atmosphere, gentle pastel tones, tender expressions, peaceful calm",
    "史诗": "epic grand atmosphere, dramatic wide landscape, majestic lighting, heroic presence",
    "忧伤": "melancholic tender atmosphere, soft blue-grey tones, gentle sad expressions, rainy misty",
    "热血": "dynamic energetic atmosphere, vivid red-orange tones, determined expressions, action pose",
    "梦幻": "dreamy ethereal atmosphere, soft glowing light, pastel iridescent tones, magical vibe",
    "浪漫": "romantic warm atmosphere, soft pink-gold light, gentle intimate expressions, cherry blossoms",
    "怀旧": "nostalgic warm atmosphere, vintage sepia tones, soft glowing memories, golden hour",
    "希望": "hopeful bright atmosphere, warm sunrise light, optimistic expressions, open space",
    "暗黑": "dark mysterious atmosphere, deep shadows, cool blue-black tones, dramatic contrast",
    "宁静": "serene calm atmosphere, soft morning light, still water reflections, peaceful scene",
    "慵懒": "lazy relaxed atmosphere, warm afternoon sun, soft comfortable vibe, slow gentle mood",
    "清新": "fresh clean atmosphere, morning dew, spring green tones, light airy feeling",
    "叛逆": "rebellious energetic atmosphere, bold contrast, edgy composition, defiant attitude",
    "孤独": "lonely quiet atmosphere, empty space, single figure, soft cool tones, vast background",
    "悬疑": "suspenseful mysterious atmosphere, dim lighting, foggy environment, intriguing shadows",
    "魔幻": "magical fantasy atmosphere, glowing elements, mystical lights, enchanted forest vibe",
}


# ════════════════════════════════════════════════════════════
# 主题 → 视觉关键词
# ════════════════════════════════════════════════════════════

THEME_VISUALS = {
    # 自然场景
    "春天": "spring cherry blossoms, green meadows, blooming flowers, gentle breeze, warm sunlight, clear blue sky",
    "夏天": "summer beach, sparkling ocean, golden sunset, palm trees, ice cream, vibrant green leaves",
    "秋天": "autumn maple leaves, golden forest, harvest scene, misty morning, fallen leaves carpet",
    "冬天": "snowy winter landscape, sparkling snowflakes, warm cabin, bare trees, frozen lake",
    "星空": "night sky, countless stars, Milky Way, glowing moonlight, silhouettes, deep blue purple gradient",
    "大海": "vast ocean, rolling waves, white foam, seabirds flying, dramatic sunset horizon, deep blue",
    "森林": "deep mysterious forest, sun rays through trees, mossy ground, wild flowers, gentle stream",
    "花园": "beautiful garden, colorful flowers, butterflies, fountain, stone path, romantic atmosphere",
    "彩虹": "rainbow across the sky, fresh after rain, colorful gradient, bright blue sky, white clouds",
    "落日": "majestic sunset, warm golden red sky, silhouettes against sun, calm peaceful atmosphere",
    "极光": "aurora borealis, green purple dancing lights, starry night, snow reflection, magical atmosphere",
    "山川": "majestic mountain range, snow capped peaks, deep valley, morning mist, alpine meadow",
    "河流": "meandering river, crystal clear water, reflections of trees, peaceful countryside, gentle flow",
    "田园": "peaceful countryside, farm house, rolling hills, golden wheat field, blue sky white clouds",
    "湖泊": "calm mountain lake, perfect mirror reflection, surrounding forest, misty morning, pristine nature",

    # 城市与生活
    "城市": "modern cityscape, tall buildings, street lights, night neon, busy streets, urban energy",
    "小镇": "charming small town, cobblestone streets, cozy cafes, old buildings, warm community vibe",
    "校园": "school campus, cherry blossom trees, classroom windows, playground, youthful energy",
    "图书馆": "grand library, floor to ceiling bookshelves, warm reading lamps, quiet atmosphere, knowledge",
    "咖啡厅": "cozy coffee shop, warm lighting, latte art, window view, relaxing afternoon vibe",
    "花园派对": "elegant garden party, string lights, picnic tables, festive decorations, joyful gathering",

    # 文化与情感
    "童年": "childhood memories, old toys, crayon drawings, treehouse, backyard adventures, innocence",
    "梦想": "dream pursuing, open horizon, looking up at sky, symbolic light, hopeful expression",
    "希望": "new beginning, sunrise horizon, open window, blooming flower, light through darkness",
    "旅行": "travel adventure, old map, vintage suitcase, train ride, mountain hiking, road trip",
    "勇气": "standing tall, mountain climbing, overcoming obstacles, determined figure, sunrise ahead",
    "友谊": "friendship, two silhouettes, walking together, sharing umbrella, sunset beach, joyful laugh",
    "家庭": "family gathering, warm home, dinner table, cozy living room, grandparents smile, love",
    "思念": "missing someone, writing letters, staring at moon, empty chair, distant silhouette",
    "成长": "growing up, measuring height on wall, old and new shoes, small to big, passing time",
    "时光": "time passing, old clock gears, fading memories, photo album, sunset time lapse",
    "回忆": "faded memories, old photograph, vintage filter, warm glow, nostalgic dreamy atmosphere",
    "童话": "fairy tale world, magical forest, storybook castle, mystical creatures, wonder and magic",

    # 节日
    "春节": "Chinese New Year, red lanterns, fireworks, family reunion dinner, lucky money, joy",
    "圣诞": "Christmas, decorated tree, snow, warm fireplace, gifts, Santa, cozy holiday spirit",
    "中秋": "Mid Autumn Festival, full moon, mooncakes, family gathering, lanterns, reunion",
    "生日": "birthday celebration, cake with candles, party decorations, gifts, happy smiles",

    # 中国风
    "江南": "Jiangnan water town, traditional bridges, willow trees, misty rain, ancient buildings, boat",
    "武侠": "martial arts world, ancient Chinese, bamboo forest, mountain temple, flying figure, wuxia",
    "古风": "ancient China style, classical dress, traditional architecture, poetry atmosphere, elegant",
    "山水": "Chinese landscape painting, mountains and water, mist, pavilion, boat, classical beauty",
    "敦煌": "Dunhuang, desert oasis, ancient Silk Road, mural art, sand dunes, sunset glow",
    "故宫": "Forbidden City, imperial palace, red walls, golden roof, snow scene, grand historical",
    "剪纸": "Chinese paper cutting, red art, intricate patterns, traditional folk art, festive decoration",

    # 幻想
    "星际": "deep space, colorful nebula, distant galaxy, astronaut silhouette, stars, cosmic wonder",
    "魔法": "magical realm, sparkling spells, wizard tower, glowing potion, enchanted forest, fantasy",
    "龙": "majestic dragon, soaring above clouds, mythical creature, golden scales, fantasy sky",
    "美人鱼": "mermaid in ocean, coral reef, underwater castle, glowing bubbles, mystical sea",
    "仙境": "fairyland, floating islands, crystal waterfalls, magical light, ethereal beauty, wonderland",
}


# 向后兼容别名
CHARACTER_DESCRIPTIONS = {
    "default": _DEFAULT_CHARACTER,
    **{k: v["character"] for k, v in STYLES.items() if v["character"]},
}


# ════════════════════════════════════════════════════════════
# 音乐风格 → 编曲细节
# ════════════════════════════════════════════════════════════

MUSIC_PROMPT_DETAILS = {
    "流行": "典型的流行歌曲结构，主歌节奏明快，副歌旋律抓耳，和弦进行清晰",
    "说唱": "Hip Hop beat，节奏感强，鼓点清晰，808 bass，flow流畅",
    "民谣": "民谣吉他为基底，和弦温暖，叙事性强，节奏舒缓",
    "电子": "电子合成器音色，律动感强，bassline突出，节奏层次丰富",
    "摇滚": "电吉他驱动，鼓点有力，能量充沛，副歌爆发力强",
    "古典": "管弦乐编曲，钢琴主导，层次丰富，宏大叙事感",
    "爵士": "爵士和弦，即兴感，钢琴或萨克斯主导，节奏律动轻松",
    "R&B": "R&B节奏，律动感强，人声转音丰富，编曲细腻",
    "中国风": "中国民族乐器（古筝、笛子、二胡），五声音阶，古风韵味",
    "新世纪NewAge": "空灵缥缈的氛围音乐，钢琴为主，自然音效，治愈系",
    "EDM舞曲": "电子舞曲节奏，drop段落爆发力强，bass重，适合派对",
    "乡村Country": "乡村吉他，节奏轻快，旋律简单上口，阳光向上",
    "朋克Punk": "快节奏，电吉他失真，鼓点密集，反叛精神",
    "HipHop": "鲜明的beat，采样丰富，节奏有力度，flow多变",
}


# 向后兼容别名
API_STYLES = {k: v["api"] for k, v in STYLES.items() if v["api"]}
NEGATIVE_PROMPTS = {
    "default": _DEFAULT_NEGATIVE,
    **{k: v["negative"] for k, v in STYLES.items() if v["negative"]},
}


# ════════════════════════════════════════════════════════════
# 公共辅助函数
# ════════════════════════════════════════════════════════════

def get_art_style(style_name: str) -> str:
    """获取指定风格的英文美术描述"""
    s = STYLES.get(style_name) or STYLES[_DEFAULT_STYLE]
    return s["art"] or STYLES[_DEFAULT_STYLE]["art"]


def get_render_template(style_name: str) -> str:
    """获取指定风格的渲染模板"""
    s = STYLES.get(style_name) or STYLES[_DEFAULT_STYLE]
    return s["render"] or STYLES[_DEFAULT_STYLE]["render"]


def get_mood_desc(mood_name: str) -> str:
    """获取指定情绪的英文描述"""
    return MOOD_DESCRIPTIONS.get(mood_name, MOOD_DESCRIPTIONS.get("欢快", ""))


def get_theme_visual(theme: str) -> str:
    """获取指定主题的视觉关键词"""
    return THEME_VISUALS.get(theme, "")


def get_char_prompt(style_name: str) -> str:
    """获取指定风格的角色描述"""
    s = STYLES.get(style_name)
    if s and s["character"]:
        return s["character"]
    return _DEFAULT_CHARACTER


def get_music_style_desc(music_style: str) -> str:
    """获取指定音乐风格的编曲细节"""
    return MUSIC_PROMPT_DETAILS.get(music_style, "")


def get_label(name: str) -> str:
    """获取场景标签中文名"""
    LABEL_MAP = {
        "intro": "序幕", "verse1": "故事", "verse2": "延续",
        "prechorus": "蓄势", "chorus": "高潮", "bridge": "转折",
        "outro": "尾声",
    }
    return LABEL_MAP.get(name, "片段")


def get_theme_visuals(theme: str, text_preview: str) -> str:
    """获取匹配主题的视觉关键词"""
    found = []
    for keyword, visual in THEME_VISUALS.items():
        if keyword in theme or keyword in text_preview:
            found.append(visual)
    return " ".join(found) if found else THEME_VISUALS.get(
        theme, "beautiful scenery"
    )


def get_fallback_desc(name: str, char_prompt: str, theme: str,
                      text_preview: str, mood_desc: str,
                      art_style: str) -> str:
    """生成场景描述（fallback 模式，无需 LLM）"""
    FALLBACK_DESC_TEMPLATES = {
        "intro": "scenic establishing wide shot with symbolic atmosphere",
        "verse1": "observational slice of life or environmental storytelling moment",
        "verse2": "detail-rich lyrical scene with objects, traces, or spatial memory",
        "prechorus": "compressed emotional close detail, tension building in the frame",
        "chorus": "grand cinematic release, landscape or symbolic centerpiece, epic feeling",
        "bridge": "quiet reflective image, solitude, distance, or metaphorical transition",
        "outro": "afterglow wide shot, lingering absence or soft departure in golden light",
    }
    template = FALLBACK_DESC_TEMPLATES.get(name, "experiencing a beautiful moment")
    visuals = get_theme_visuals(theme, text_preview)
    human_hint_terms = (
        "I ", "you ", "we ", "he ", "she ", "they ", "love", "kiss", "hand",
        "face", "eyes", "walk", "wait", "hold", "embrace", "alone", "smile",
    )
    preview_lower = f" {text_preview.lower()} "
    needs_human_presence = any(term.lower() in preview_lower for term in human_hint_terms)
    focal_subject = char_prompt[:80] if (char_prompt and needs_human_presence) else "poetic visual focal point"
    desc = f"{focal_subject}, {template}, {mood_desc}"
    if visuals:
        desc += f", {visuals}"
    desc += f", {art_style}"
    return desc


def get_api_style(style_name: str) -> str:
    """获取指定风格对应的 MiniMax API style 参数"""
    s = STYLES.get(style_name)
    return (s["api"] if s else None) or ""


def get_negative_prompt(style_name: str) -> str:
    """获取指定风格的 negative prompt"""
    s = STYLES.get(style_name)
    return (s["negative"] if s else None) or _DEFAULT_NEGATIVE


def build_char_prompt(style_name: str, theme: str, song_title: str = "",
                      mood: str = "", art_suffix: str = None) -> str:
    """构建完整的角色 prompt

    将角色描述 + 风格 + 主题 + 情绪组合为最终的图片 prompt
    """
    char_desc = get_char_prompt(style_name)
    art_style = get_art_style(style_name)
    mood_desc = get_mood_desc(mood) if mood else ""
    theme_visual = get_theme_visual(theme)

    parts = [char_desc]

    if theme:
        if song_title:
            parts.append(f"in a scene representing the song '{song_title}'")
        else:
            parts.append(f"in a {theme} scene")

    if theme_visual:
        parts.append(theme_visual)

    if mood_desc:
        parts.append(mood_desc)

    if art_suffix:
        parts.append(art_suffix)
    else:
        parts.append(art_style)

    return ", ".join(parts)


# ════════════════════════════════════════════════════════════
# CLI 入口
# ════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 3:
        print("用法: python -m src.style_map <command> <name>")
        print("命令: get-art-style, get-char-style, get-mood-desc, "
              "get-theme-visual, get-music-desc")
        print("示例: python -m src.style_map get-art-style 动漫风")
        sys.exit(1)

    cmd = sys.argv[1]
    name = sys.argv[2]

    handlers = {
        "get-art-style": get_art_style,
        "get-render-template": get_render_template,
        "get-char-style": get_char_prompt,
        "get-mood-desc": get_mood_desc,
        "get-theme-visual": get_theme_visual,
        "get-music-desc": get_music_style_desc,
        "get-api-style": get_api_style,
        "get-negative-prompt": get_negative_prompt,
    }

    handler = handlers.get(cmd)
    if handler:
        print(handler(name))
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
