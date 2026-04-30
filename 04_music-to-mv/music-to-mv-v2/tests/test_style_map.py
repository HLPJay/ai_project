"""style_map 专项测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.style_map import (
    ART_STYLES, STYLE_RENDER_TEMPLATES, MOOD_DESCRIPTIONS,
    THEME_VISUALS, CHARACTER_DESCRIPTIONS, MUSIC_PROMPT_DETAILS,
    API_STYLES, NEGATIVE_PROMPTS,
    get_art_style, get_render_template, get_mood_desc,
    get_theme_visual, get_char_prompt, get_music_style_desc,
    get_api_style, get_negative_prompt, build_char_prompt,
)


def test_art_styles():
    """验证所有绘画风格都有对应的英文描述"""
    required_styles = ["国风", "动漫风", "写实摄影风", "水彩插画风",
                       "像素游戏风", "电影感写实风", "极简几何风",
                       "浮世绘和风", "复古胶片风", "漫画美式涂鸦风",
                       "蒸汽朋克风", "赛博朋克风"]

    for style in required_styles:
        desc = ART_STYLES.get(style)
        assert desc and len(desc) > 30, f"ART_STYLES 缺失或过短: {style}"
        assert get_art_style(style) == desc, f"get_art_style 不匹配: {style}"

    # Fallback
    assert get_art_style("不存在的风格") == ART_STYLES["动漫风"]

    print(f"  [OK] ART_STYLES: {len(ART_STYLES)} 种风格")


def test_render_templates():
    """验证渲染模板"""
    assert len(STYLE_RENDER_TEMPLATES) <= len(ART_STYLES) + 1
    for style in ART_STYLES:
        template = STYLE_RENDER_TEMPLATES.get(style, "")
        if template:
            assert isinstance(template, str) and len(template) > 10
    print(f"  [OK] STYLE_RENDER_TEMPLATES: {len(STYLE_RENDER_TEMPLATES)} 个模板")


def test_mood_descriptions():
    """验证情绪描述"""
    required_moods = ["欢快", "温柔", "史诗", "忧伤", "梦幻"]

    for mood in required_moods:
        desc = MOOD_DESCRIPTIONS.get(mood)
        assert desc and len(desc) > 20, f"MOOD_DESCRIPTIONS 缺失: {mood}"
        assert get_mood_desc(mood) == desc

    assert get_mood_desc("不存在的情绪") == MOOD_DESCRIPTIONS["欢快"]

    print(f"  [OK] MOOD_DESCRIPTIONS: {len(MOOD_DESCRIPTIONS)} 种情绪")


def test_theme_visuals():
    """验证主题视觉"""
    required_themes = ["春天", "童年", "古风", "城市", "星空"]

    for theme in required_themes:
        visual = THEME_VISUALS.get(theme)
        assert visual and len(visual) > 10, f"THEME_VISUALS 缺失: {theme}"
        assert get_theme_visual(theme) == visual

    print(f"  [OK] THEME_VISUALS: {len(THEME_VISUALS)} 个主题")


def test_character_descriptions():
    """验证角色描述"""
    required_styles = ["default", "动漫风", "国风"]
    for style in required_styles:
        desc = CHARACTER_DESCRIPTIONS.get(style)
        assert desc and len(desc) > 20, f"CHARACTER_DESCRIPTIONS 缺失: {style}"
        assert get_char_prompt(style) == desc

    assert get_char_prompt("不存在的风格") == CHARACTER_DESCRIPTIONS["default"]

    print(f"  [OK] CHARACTER_DESCRIPTIONS: {len(CHARACTER_DESCRIPTIONS)} 种风格")


def test_api_styles():
    """验证 API 风格映射"""
    required_styles = ["国风", "动漫风", "水彩插画风"]

    for style in required_styles:
        api_style = API_STYLES.get(style)
        assert api_style, f"API_STYLES 缺失: {style}"
        assert get_api_style(style) == api_style

    print(f"  [OK] API_STYLES: {len(API_STYLES)} 种映射")


def test_negative_prompts():
    """验证 Negative Prompt"""
    required_styles = ["国风", "动漫风", "default"]
    for style in required_styles:
        neg = NEGATIVE_PROMPTS.get(style)
        assert neg and len(neg) > 20, f"NEGATIVE_PROMPTS 缺失: {style}"
        assert get_negative_prompt(style) == neg

    assert get_negative_prompt("不存在的风格") == NEGATIVE_PROMPTS["default"]

    print(f"  [OK] NEGATIVE_PROMPTS: {len(NEGATIVE_PROMPTS)} 种风格")


def test_build_char_prompt():
    """验证角色 prompt 构建"""
    # 完整参数
    result = build_char_prompt(
        style_name="动漫风",
        theme="春天",
        song_title="春天的歌",
        mood="欢快",
    )
    assert "anime" in result or "Japanese" in result
    assert "spring" in result or "春天" in result
    assert "song" in result or "歌" in result
    assert "joyful" in result or "bright" in result

    # 最小参数
    result_min = build_char_prompt("国风", "山水")
    assert len(result_min) > 30

    # 带艺术后缀
    result_suffix = build_char_prompt("动漫风", "夏天", art_suffix="custom art style, extra detail")
    assert "custom art style" in result_suffix

    print(f"  [OK] build_char_prompt: 参数组合测试通过")


def test_music_style_details():
    """验证音乐风格编曲细节"""
    required_music_styles = ["流行", "说唱", "民谣", "电子", "中国风"]
    for style in required_music_styles:
        desc = MUSIC_PROMPT_DETAILS.get(style)
        assert desc and len(desc) > 10, f"MUSIC_PROMPT_DETAILS 缺失: {style}"
        assert get_music_style_desc(style) == desc

    # Fallback
    assert get_music_style_desc("不存在的风格") == ""

    print(f"  [OK] MUSIC_PROMPT_DETAILS: {len(MUSIC_PROMPT_DETAILS)} 种风格")


if __name__ == "__main__":
    print("\n=== style_map 专项测试 ===\n")

    tests = [
        ("艺术风格", test_art_styles),
        ("渲染模板", test_render_templates),
        ("情绪描述", test_mood_descriptions),
        ("主题视觉", test_theme_visuals),
        ("角色描述", test_character_descriptions),
        ("API 风格映射", test_api_styles),
        ("Negative Prompt", test_negative_prompts),
        ("角色prompt构建", test_build_char_prompt),
        ("音乐风格细节", test_music_style_details),
    ]

    passed = 0
    failed = 0

    for name, func in tests:
        try:
            print(f"\n-- {name} --")
            func()
            print(f"  [PASS] {name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*50}")
    print(f"  测试结果: {passed} 通过, {failed} 失败")
    print(f"{'='*50}")
    sys.exit(0 if failed == 0 else 1)
