"""
scene_generator.py — 场景图生成模块

纯 Python 实现，替代原版 scripts/generate_scene_imgs.py。
无需 bash，直接调用 LLMClient 的图片 API。

功能：
  - Step ④: 基础角色图生成（base_character.png）
  - Step ⑤-⑦: 批量场景图生成（segN_scene.png + variants）
  - 变体图策略（重复段自动生成多张图）
  - variants.json 生成
  - 图片 API 多 Provider 支持（minimax/alibaba/pollinations/dall-e）

用法：
    from src.scene_generator import SceneImageGenerator
    gen = SceneImageGenerator(project_dir)
    result = gen.generate_all(parallel=2)
"""

import json
import os
import sys
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from src.config_manager import ConfigManager
from src.llm.client import LLMClient, RetryConfig
from src.style_map import (
    ART_STYLES, get_mood_desc, get_api_style, get_negative_prompt,
    build_char_prompt, get_theme_visual,
)


# ── 图片生成常量（集中管理所有魔数）──────────────────────
VARIANT_THRESHOLD = 4        # 秒：重复段超过此时长才生成变体图
VARIANT_SECS_PER_STEP = 5    # 每增加 N 秒，变体数 +1
VARIANT_MIN = 2              # 最少变体数
VARIANT_MAX = 3              # 最多变体数

MAX_RETRY = 3                # 单张图片最大重试次数
RETRY_DELAY = 2              # 重试基础延迟（秒），实际延迟 = RETRY_DELAY * attempt

MIN_IMAGE_SIZE = 1000        # bytes：有效图片的最小阈值
MIN_VALID_IMAGE_SIZE = 500000  # bytes：500KB，生成验证用

PROMPT_MAX_LEN = 1400        # MiniMax prompt 最大长度（留 100 字符余量）
PROMPT_CHAR_MAX = 600        # 角色描述最大字符数
PROMPT_DESC_MAX = 700        # 场景描述最大字符数


class SceneImageError(Exception):
    """场景图生成错误"""
    pass


class SceneImageGenerator:
    """场景图片生成器

    处理 Step ④（角色图）+ Step ⑤-⑦（场景图+变体图）

    Attributes:
        project_dir: 项目目录
        images_dir: 图片输出目录
        metadata_dir: 元数据目录
        client: LLMClient 实例
        cfg: ConfigManager 实例
        dry_run: 如果 True，跳过真实 API 调用，只生成规划元数据
    """

    def __init__(self, project_dir: str, dry_run: bool = False):
        self.project_dir = Path(project_dir)
        self.images_dir = self.project_dir / "images"
        self.metadata_dir = self.project_dir / "metadata"
        self.clips_dir = self.project_dir / "clips"
        self.dry_run = dry_run

        self.images_dir.mkdir(exist_ok=True)
        self.clips_dir.mkdir(exist_ok=True)

        self.cfg = ConfigManager()
        self.client = LLMClient(project_dir=str(self.project_dir))

        # 从 info.json 读取固定 seed（角色一致性）
        self._image_seed = 0
        info_path = self.metadata_dir / "info.json"
        if info_path.exists():
            info = json.loads(info_path.read_text(encoding="utf-8"))
            self._image_seed = info.get("image_seed", 0)

        # 从 base_char.json 或 style_map 读取风格参数
        self._load_style_params()

    def _load_style_params(self):
        """加载风格参数（角色描述、艺术风格、情绪等）"""
        base_char_path = self.metadata_dir / "base_char.json"

        self._char_prompt = ""
        self._art_style = ""
        self._mood_desc = ""
        self._api_style = ""
        self._negative_prompt = ""
        self._visual_bible = {}
        self._visual_bible_prompt = ""
        self._style = "动漫风"
        self._mood = "欢快"
        self._character_policy = "optional protagonist"
        self._visual_mode = "mixed"
        self._do_not_do = ""
        self._theme = ""
        self._song_title = ""

        if base_char_path.exists():
            bc = json.loads(base_char_path.read_text(encoding="utf-8"))
            self._char_prompt = bc.get("prompt", "")
            self._style = bc.get("style", "动漫风")
            self._mood = bc.get("mood", "欢快")
        else:
            # 从 info.json 读取
            info_path = self.metadata_dir / "info.json"
            if info_path.exists():
                info = json.loads(info_path.read_text(encoding="utf-8"))
                self._theme = info.get("theme", "")
                self._song_title = info.get("song_title", "")
                self._style = info.get("style", "动漫风")
                self._mood = info.get("mood", "欢快")
                self._character_policy = info.get("character_policy", "optional protagonist")
                self._visual_mode = info.get("visual_mode", "mixed")
                # 读取 do_not_do
                dnd = info.get("do_not_do", [])
                if isinstance(dnd, list) and dnd:
                    self._do_not_do = " | ".join(dnd)
                self._char_prompt = build_char_prompt(
                    self._style, self._theme,
                    self._song_title, self._mood,
                )

        self._art_style = ART_STYLES.get(self._style,
                                         "illustration style, soft warm colors")
        self._mood_desc = get_mood_desc(self._mood)
        self._api_style = get_api_style(self._style)
        self._negative_prompt = get_negative_prompt(self._style)
        self._load_visual_bible()

    def _load_visual_bible(self):
        self._visual_bible = {}
        self._visual_bible_prompt = ""
        path = self.metadata_dir / "visual_bible.json"
        if not path.exists():
            return

        try:
            self._visual_bible = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            self._visual_bible = {}
            return

        parts = []
        if self._visual_bible.get("world_style"):
            parts.append(self._visual_bible["world_style"])
        palette = self._visual_bible.get("palette") or []
        if palette:
            parts.append("palette: " + ", ".join(palette[:3]))
        if self._visual_bible.get("lighting"):
            parts.append(self._visual_bible["lighting"])
        if self._visual_bible.get("texture"):
            parts.append(self._visual_bible["texture"])
        if self._visual_bible.get("camera_language"):
            parts.append(self._visual_bible["camera_language"])

        self._visual_bible_prompt = ", ".join(parts)

    # ══════════════════════════════════════════════════════
    # 公开 API
    # ══════════════════════════════════════════════════════

    def generate_base_character(self, theme: str = "",
                                song_title: str = "",
                                override_prompt: str = None) -> bool:
        """生成基础视觉参考图（Step ④）

        历史文件名仍为 base_character.png，但除 fixed protagonist 外，
        默认生成与歌词主题相关的环境/象征参考图，避免全片被人物主体绑架。

        Args:
            theme: 主题（用于 prompt 构建）
            song_title: 歌曲标题（用于 prompt 构建）
            override_prompt: 完全覆盖的 prompt（用于外部 LLM 生图）

        Returns:
            True 成功, False 失败
        """
        output = self.images_dir / "base_character.png"

        if self.dry_run:
            print(f"  [Step ④][dry_run] 跳过 base_character.png 生成")
            # dry_run 模式：生成带风格标注的占位图
            try:
                from PIL import Image, ImageDraw
                img = Image.new("RGB", (1080, 1920), (60, 80, 110))
                draw = ImageDraw.Draw(img)
                draw.text((540, 800), f"BASE VISUAL REFERENCE", fill=(255, 255, 200),
                          anchor="mm", font_size=42)
                draw.text((540, 870), f"style: {self._style}", fill=(200, 200, 200),
                          anchor="ma", font_size=24)
                draw.text((540, 910), f"mood: {self._mood}", fill=(180, 180, 180),
                          anchor="ma", font_size=20)
                img.save(str(output))
                return True
            except Exception:
                output.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 1000)
                return True

        # 幂等：已有且大小正常则跳过
        if output.exists() and output.stat().st_size > MIN_IMAGE_SIZE:
            print(f"  [Step ④] base_character.png 已存在，跳过")
            return True

        # 构建 prompt
        if override_prompt:
            prompt = override_prompt
        else:
            prompt = self._build_base_reference_prompt(theme, song_title)

        print(f"  [Step ④] 生成基础视觉参考图...")

        try:
            self.client.call_image_api(
                prompt=prompt,
                output_path=str(output),
                style=self._api_style,
                negative_prompt=self._negative_prompt,
                seed=self._image_seed,
            )

            if output.exists() and output.stat().st_size > MIN_IMAGE_SIZE:
                print(f"  [Step ④] 完成: {output.stat().st_size // 1024}KB")
                return True
            return False
        except Exception as e:
            print(f"  [Step ④] 失败: {e}")
            return False

    def _build_base_reference_prompt(self, theme: str = "",
                                     song_title: str = "") -> str:
        """构建 Step ④ 的基础参考图 prompt。

        fixed protagonist 生成角色参考；其余按主题主体类型生成参考：
        人物关系、人物行动/群像、非人物主体、宇宙/自然环境、意境象征。
        """
        theme_ = theme or self._load_theme()
        character_led = (
            self._character_policy == "fixed protagonist"
            or self._visual_mode == "character-led"
        )
        if character_led:
            return build_char_prompt(self._style, theme_, song_title, self._mood)

        reference_mode = self._infer_base_reference_mode(
            theme_, song_title, visual_anchors=self._load_visual_anchors()
        )
        theme_visual = self._build_theme_visual_hint(theme_, song_title, reference_mode)
        visual_anchors = self._load_visual_anchors()
        bible_parts = []
        if self._visual_bible.get("world_style"):
            bible_parts.append(self._visual_bible["world_style"])
        if self._visual_bible.get("palette"):
            palette = self._visual_bible["palette"]
            if isinstance(palette, list):
                bible_parts.append("palette: " + ", ".join(str(p) for p in palette[:5]))
        if self._visual_bible.get("lighting"):
            bible_parts.append("lighting: " + str(self._visual_bible["lighting"]))
        if self._visual_bible.get("texture"):
            bible_parts.append("texture: " + str(self._visual_bible["texture"]))

        if reference_mode == "relation":
            parts = [
                f"relationship-centered visual reference image for the song '{song_title or theme_}'",
                f"core theme: {theme_}",
                f"mood: {self._mood}",
                self._mood_desc,
                theme_visual,
                visual_anchors,
                "two human subjects or a poetic couple silhouette may be the emotional focal point",
                "show intimacy, distance, longing, hand gesture, shared umbrella, back view, or side profile",
                "avoid generic empty scenery; environment should support the relationship emotion",
                "not a solo portrait, not a fashion character sheet, no close-up face dominance",
                "keep identities softly defined for continuity across later human shots",
                " ".join(p for p in bible_parts if p),
                self._art_style,
            ]
        elif reference_mode == "human_action":
            parts = [
                f"human action and world reference image for the song '{song_title or theme_}'",
                f"core theme: {theme_}",
                f"mood: {self._mood}",
                self._mood_desc,
                theme_visual,
                visual_anchors,
                "human figures, groups, uniforms, silhouettes, or action traces may be the emotional focal point",
                "show the pressure, conflict, courage, separation, or aftermath through cinematic composition",
                "avoid empty postcard scenery; the scene should reveal human stakes and story scale",
                "not a clean fashion portrait, not a character sheet, no close-up face dominance",
                "keep subject design coherent enough for later people-centered shots",
                " ".join(p for p in bible_parts if p),
                self._art_style,
            ]
        elif reference_mode == "nonhuman_subject":
            parts = [
                f"subject-centered visual reference image for the song '{song_title or theme_}'",
                f"core theme: {theme_}",
                f"mood: {self._mood}",
                self._mood_desc,
                theme_visual,
                visual_anchors,
                "the named non-human subject should be the main visual anchor",
                "show body language, texture, scale, surroundings, and emotional tone clearly",
                "no human protagonist, no portrait of a person, environment supports the subject instead of replacing it",
                "not a generic landscape, not a decorative still life unless the subject is an object",
                "suitable as a continuity reference for later subject-centered shots",
                " ".join(p for p in bible_parts if p),
                self._art_style,
            ]
        elif reference_mode == "cosmic_environment":
            parts = [
                f"cosmic environment visual reference image for the song '{song_title or theme_}'",
                f"core theme: {theme_}",
                f"mood: {self._mood}",
                self._mood_desc,
                theme_visual,
                visual_anchors,
                "vast galaxy, star fields, nebula structure, planetary scale, light and depth as the main subject",
                "no human protagonist, no portrait, no centered face",
                "show spatial grandeur and coherent celestial geography, not a random abstract texture",
                "suitable as a global MV visual reference for cosmic scenes",
                " ".join(p for p in bible_parts if p),
                self._art_style,
            ]
        elif reference_mode == "poetic_imagery":
            parts = [
                f"classical poetic imagery reference image for the song '{song_title or theme_}'",
                f"core theme: {theme_}",
                f"mood: {self._mood}",
                self._mood_desc,
                theme_visual,
                visual_anchors,
                "build the image from poetic Chinese imagery: season, moonlight, river, mountains, pavilion, boat, flowers, rain, snow, wind, mist, distance, and empty space as needed",
                "the emotional subject is the poetic atmosphere, not a literal illustration of every word",
                "human figures may appear only as tiny silhouettes, back views, travelers, poets, or distant presences when the poem needs them",
                "avoid generic scenery; every object should carry mood, time, place, and cultural symbolism",
                "suitable as a global MV visual reference for ancient poem or lyrical imagery",
                " ".join(p for p in bible_parts if p),
                self._art_style,
            ]
        elif reference_mode == "festival_culture":
            parts = [
                f"festival and cultural ritual visual reference image for the song '{song_title or theme_}'",
                f"core theme: {theme_}",
                f"mood: {self._mood}",
                self._mood_desc,
                theme_visual,
                visual_anchors,
                "show cultural objects, ritual details, architecture, food, lanterns, gathering traces, costume fragments, and seasonal atmosphere",
                "human presence may appear as family silhouettes, crowds, hands, or ritual actions when relevant",
                "avoid empty decorative still life; connect symbols to lived cultural emotion",
                "not a tourist postcard, not a product photo",
                " ".join(p for p in bible_parts if p),
                self._art_style,
            ]
        elif reference_mode == "urban_life":
            parts = [
                f"urban life visual reference image for the song '{song_title or theme_}'",
                f"core theme: {theme_}",
                f"mood: {self._mood}",
                self._mood_desc,
                theme_visual,
                visual_anchors,
                "show streets, windows, lights, transit, rooms, crowds, signage, weather, and daily objects as emotional anchors",
                "human figures may appear naturally in the scene, but avoid generic posed portraits",
                "make the place feel lived-in and specific, not an empty skyline",
                " ".join(p for p in bible_parts if p),
                self._art_style,
            ]
        elif reference_mode == "object_symbol":
            parts = [
                f"symbolic object visual reference image for the song '{song_title or theme_}'",
                f"core theme: {theme_}",
                f"mood: {self._mood}",
                self._mood_desc,
                theme_visual,
                visual_anchors,
                "one or several meaningful objects should carry the emotion: letters, clock, umbrella, lamp, old photo, toy, instrument, flower, cup, window, or keepsake as relevant",
                "no human protagonist; if body parts appear, use only hands or partial traces to support the symbol",
                "avoid generic landscape; make the object, texture, light, and surrounding space tell the story",
                " ".join(p for p in bible_parts if p),
                self._art_style,
            ]
        elif reference_mode == "fantasy_myth":
            parts = [
                f"fantasy myth visual reference image for the song '{song_title or theme_}'",
                f"core theme: {theme_}",
                f"mood: {self._mood}",
                self._mood_desc,
                theme_visual,
                visual_anchors,
                "show mythical creatures, enchanted landscape, sacred architecture, floating islands, magic light, ancient symbols, or legendary scale as relevant",
                "human heroes may appear only if the theme calls for them; keep the world and mythic subject primary",
                "avoid generic fantasy noise; keep a coherent cultural and visual logic",
                " ".join(p for p in bible_parts if p),
                self._art_style,
            ]
        else:
            parts = [
                f"theme-centered visual reference image for the song '{song_title or theme_}'",
                f"core theme: {theme_}",
                f"mood: {self._mood}",
                self._mood_desc,
                theme_visual,
                visual_anchors,
                "infer the most important visual subject from the theme instead of defaulting to generic scenery",
                "use environment and symbolic motifs as the main anchor; avoid a centered human unless the theme clearly needs one",
                "show the recurring lyric imagery as the main subject, cinematic establishing composition",
                "use objects, weather, architecture, landscape, light, water, plants, and atmosphere to express the song",
                "suitable as a global MV visual reference, not a character sheet",
                " ".join(p for p in bible_parts if p),
                self._art_style,
        ]
        return ", ".join(p for p in parts if p)[:PROMPT_MAX_LEN]

    @staticmethod
    def _infer_base_reference_mode(theme: str = "", song_title: str = "",
                                   visual_anchors: str = "") -> str:
        """推断 Step ④ 基础参考图主体类型。"""
        text = f"{theme} {song_title} {visual_anchors}".lower()

        relation_keywords = (
            "爱情", "恋爱", "相爱", "爱人", "情侣", "恋人", "情人",
            "思念", "想你", "等你", "离别", "重逢", "告白", "心动",
            "拥抱", "牵手", "誓言", "婚礼", "love", "lover", "romance",
            "romantic", "couple", "kiss", "embrace",
        )
        if any(k in text for k in relation_keywords):
            return "relation"

        human_action_keywords = (
            "战争", "战场", "士兵", "军队", "英雄", "战火", "冲锋",
            "革命", "逃亡", "灾难", "末日", "人群", "城市逃离",
            "war", "battle", "soldier", "army", "hero", "crowd",
            "conflict", "battlefield",
        )
        if any(k in text for k in human_action_keywords):
            return "human_action"

        nonhuman_subject_keywords = (
            "小狗", "狗", "猫", "小猫", "宠物", "狐狸", "鹿", "马",
            "鸟", "蝴蝶", "鱼", "鲸", "兔", "熊猫", "龙猫", "机器人", "玩偶", "娃娃",
            "puppy", "dog", "cat", "pet", "fox", "deer", "horse",
            "bird", "butterfly", "fish", "whale", "rabbit", "panda", "robot", "doll",
        )
        if any(k in text for k in nonhuman_subject_keywords):
            return "nonhuman_subject"

        cosmic_keywords = (
            "星系", "银河", "宇宙", "星云", "星际", "行星", "太空",
            "galaxy", "cosmos", "universe", "nebula", "planet", "space",
            "interstellar",
        )
        if any(k in text for k in cosmic_keywords):
            return "cosmic_environment"

        poetic_keywords = (
            "古诗", "诗词", "唐诗", "宋词", "诗意", "意境", "山水", "江南",
            "烟雨", "春江", "花月夜", "明月", "月下", "孤舟", "寒江",
            "落霞", "秋水", "长亭", "古道", "西风", "瘦马", "边塞",
            "故乡", "乡愁", "清明", "上河", "兰亭", "桃花源", "滕王阁",
            "poem", "poetry", "poetic", "ancient poem", "moonlit", "misty river",
        )
        if any(k in text for k in poetic_keywords):
            return "poetic_imagery"

        festival_keywords = (
            "春节", "新年", "元宵", "清明", "端午", "七夕", "中秋", "重阳",
            "节日", "灯会", "庙会", "烟花", "灯笼", "团圆", "festival",
            "lantern", "new year", "mid autumn",
        )
        if any(k in text for k in festival_keywords):
            return "festival_culture"

        urban_keywords = (
            "城市", "都市", "街道", "地铁", "车站", "夜市", "咖啡厅", "房间",
            "窗边", "霓虹", "校园", "图书馆", "办公室", "city", "urban",
            "street", "subway", "station", "cafe", "room", "campus",
        )
        if any(k in text for k in urban_keywords):
            return "urban_life"

        object_keywords = (
            "信", "书信", "旧照片", "相册", "时钟", "钟表", "雨伞", "灯",
            "窗", "酒杯", "茶", "琴", "古筝", "笛", "玩具", "纸船", "风铃",
            "letter", "photo", "clock", "umbrella", "lamp", "window",
            "instrument", "toy", "keepsake",
        )
        if any(k in text for k in object_keywords):
            return "object_symbol"

        fantasy_keywords = (
            "神话", "传说", "仙", "仙境", "龙", "凤凰", "妖", "魔法", "奇幻",
            "精灵", "梦境", "幻境", "山海经", "fantasy", "myth", "dragon",
            "phoenix", "fairy", "magic", "dreamland",
        )
        if any(k in text for k in fantasy_keywords):
            return "fantasy_myth"

        return "environment_symbolic"

    @staticmethod
    def _build_theme_visual_hint(theme: str, song_title: str = "",
                                 reference_mode: str = "") -> str:
        """为开放主题补充视觉意象提示，避免未知主题退化成空泛风景。"""
        exact = get_theme_visual(theme)
        if exact:
            return exact

        text = f"{theme} {song_title}".lower()
        hint_groups = [
            (("春", "spring"), "spring rain, tender new leaves, flowers, wet stone path, soft mist"),
            (("夏", "summer", "炙热"), "scorching sunlight, heat shimmer, cicadas, deep shade, bright leaves, sweat, open sky"),
            (("秋", "autumn"), "falling leaves, golden fields, cool wind, distant mountains, dusk light"),
            (("冬", "winter", "雪"), "snow, cold air, bare branches, white silence, warm window light"),
            (("月", "moon"), "moonlight, long shadows, quiet water, distant pavilion, night mist"),
            (("雨", "rain"), "rain threads, wet reflections, ripples, umbrella, mist, softened distance"),
            (("风", "wind"), "moving fabric, bending grass, drifting petals, clouds, hair or leaves in motion"),
            (("江", "河", "水", "river"), "riverbank, boat, reflections, bridge, reeds, flowing water"),
            (("山", "mountain"), "layered mountains, mist, pine trees, cliff path, distant temple"),
            (("花", "flower"), "falling petals, blooming branches, delicate foreground flowers, soft fragrance atmosphere"),
            (("梦", "dream"), "surreal soft light, floating particles, blurred boundary between memory and reality"),
            (("故乡", "乡愁", "home"), "old doorway, village path, cooking smoke, distant lights, remembered home"),
        ]
        hints = [hint for keys, hint in hint_groups if any(k in text for k in keys)]

        mode_hints = {
            "poetic_imagery": "classical Chinese poetic imagery, season, moon, river, mountain, mist, pavilion, boat, empty space",
            "festival_culture": "festival objects, ritual details, lanterns, family gathering traces, seasonal cultural atmosphere",
            "urban_life": "lived-in street, window light, transit, room details, city weather, everyday objects",
            "object_symbol": "symbolic object close detail, texture, light, shadow, surrounding memory space",
            "fantasy_myth": "mythic world, enchanted light, legendary creatures, ancient symbols, sacred landscape",
            "cosmic_environment": "galaxy, nebula, stars, planets, deep space, vast celestial scale",
            "nonhuman_subject": "clear non-human subject, expressive body language, texture, surrounding environment",
            "human_action": "human stakes, group movement, conflict traces, aftermath, scale, cinematic tension",
            "relation": "two-person relationship, distance and intimacy, gesture, shared space, emotional atmosphere",
        }
        mode_hint = mode_hints.get(reference_mode, "")
        if mode_hint and hints:
            return ", ".join([mode_hint, *hints[:2]])
        if hints:
            return ", ".join(hints[:3])
        return mode_hint or "theme-specific visual subject, symbolic objects, atmosphere, place, light, texture"

    def generate_anchors(self, scenes: List[Dict] = None) -> Dict[str, Any]:
        """生成全局锚定图（environment + symbolic anchor）

        Anchor 定义全局视觉基调，供 shot prompt 注入使用。
        仅当 visual_bible.json 存在时才会调用 LLM。

        Args:
            scenes: 可选场景列表（用于提取 visual_anchors）

        Returns:
            {"environment_anchor": str, "symbolic_anchor": str}
        """
        if not self._visual_bible:
            print("  [Anchors] visual_bible.json 不存在，跳过 anchor 生成")
            return {}

        output_env = self.images_dir / "environment_anchor.png"
        output_sym = self.images_dir / "symbolic_anchor.png"

        # 幂等检查：已存在的 anchor 不重新生成
        env_done = output_env.exists() and output_env.stat().st_size > MIN_IMAGE_SIZE
        sym_done = output_sym.exists() and output_sym.stat().st_size > MIN_IMAGE_SIZE
        if env_done and sym_done:
            print("  [Anchors] 锚定图已存在，跳过")
            result = {}
            if self.metadata_dir.joinpath("anchors.json").exists():
                result = json.loads(self.metadata_dir.joinpath("anchors.json").read_text(encoding="utf-8"))
            return result

        # 提取 visual_anchors
        visual_anchors = self._load_visual_anchors(scenes)

        # 读取 bible 字段
        bible = self._visual_bible
        world_style = bible.get("world_style", "")
        palette = bible.get("palette", [])
        lighting = bible.get("lighting", "")
        texture = bible.get("texture", "")

        palette_str = ", ".join(palette[:4]) if palette else ""

        result = {}

        # 1. Environment anchor
        if not env_done:
            try:
                from src.llm.registry import PromptRegistry
                registry = PromptRegistry()
                prompt = registry.render("image.environment_anchor", {
                    "theme": self._load_theme(),
                    "mood": self._mood,
                    "style": self._style,
                    "world_style": world_style,
                    "palette": palette_str,
                    "lighting": lighting,
                    "texture": texture,
                    "visual_anchors": visual_anchors,
                })
                anchor_prompt = self._call_anchor_llm(prompt)
                if anchor_prompt:
                    if not self.dry_run:
                        self.client.call_image_api(
                            prompt=anchor_prompt,
                            output_path=str(output_env),
                            style=self._api_style,
                            negative_prompt=self._negative_prompt,
                            seed=self._image_seed + 9000,
                        )
                    result["environment_anchor"] = anchor_prompt
                    print(f"  [Anchor][env] {'[dry_run] ' if self.dry_run else ''}生成完成")
            except Exception as e:
                print(f"  [Anchor][env] 失败: {e}")

        # 2. Symbolic anchor
        if not sym_done:
            try:
                from src.llm.registry import PromptRegistry
                registry = PromptRegistry()
                prompt = registry.render("image.symbolic_anchor", {
                    "theme": self._load_theme(),
                    "mood": self._mood,
                    "style": self._style,
                    "visual_anchors": visual_anchors,
                })
                anchor_prompt = self._call_anchor_llm(prompt)
                if anchor_prompt:
                    if not self.dry_run:
                        self.client.call_image_api(
                            prompt=anchor_prompt,
                            output_path=str(output_sym),
                            style=self._api_style,
                            negative_prompt=self._negative_prompt,
                            seed=self._image_seed + 9001,
                        )
                    result["symbolic_anchor"] = anchor_prompt
                    print(f"  [Anchor][sym] {'[dry_run] ' if self.dry_run else ''}生成完成")
            except Exception as e:
                print(f"  [Anchor][sym] 失败: {e}")

        # 持久化 anchors.json
        if result:
            self.metadata_dir.mkdir(parents=True, exist_ok=True)
            (self.metadata_dir / "anchors.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        return result

    def _load_visual_anchors(self, scenes: List[Dict] = None) -> str:
        """从 info.json 或场景列表提取 visual_anchors 字段"""
        # 优先使用 Creative Brief 的 visual_anchors
        info_path = self.metadata_dir / "info.json"
        if info_path.exists():
            try:
                info = json.loads(info_path.read_text(encoding="utf-8"))
                va = info.get("visual_anchors", "")
                if va and isinstance(va, str):
                    return va
            except Exception:
                pass

        # 次优：从 scenes.json 提取 symbolic_objects
        if scenes:
            all_objects = set()
            for s in scenes:
                objs = s.get("symbolic_objects") or []
                if isinstance(objs, list):
                    for o in objs:
                        all_objects.add(str(o))
            if all_objects:
                return ", ".join(sorted(all_objects)[:5])

        return getattr(self, "_theme", "")

    def _call_anchor_llm(self, prompt: str) -> Optional[str]:
        """调用 LLM 生成 anchor prompt，返回解析后的 prompt 字符串"""
        token = self.cfg.get("minimax_token", "")
        if not token:
            return None

        api_url = "https://api.minimaxi.com/v1/chat/completions"
        payload = json.dumps({
            "model": self.cfg.get("llm_model", "MiniMax-M2.7"),
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 512,
        }).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        resp_data = self.client._call_raw_api(
            api_url, payload, headers,
            prompt_key="anchor_generation",
            model=self.cfg.get("llm_model", "MiniMax-M2.7"),
            prompt_text=prompt,
        )
        raw = resp_data.get("choices", [{}])[0].get("message", {}).get("content", "")

        # 解析 JSON
        import re
        json_match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', raw, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            brace_start = raw.find("{")
            brace_end = raw.rfind("}")
            json_str = raw[brace_start:brace_end + 1] if brace_start != -1 and brace_end > brace_start else raw

        try:
            data = json.loads(json_str)
            anchor_prompt = data.get("prompt", "")
            if anchor_prompt and len(anchor_prompt) > 10:
                return anchor_prompt
        except Exception:
            pass

        return None

    def _load_theme(self) -> str:
        """从 info.json 加载 theme"""
        info_path = self.metadata_dir / "info.json"
        if info_path.exists():
            try:
                return json.loads(info_path.read_text(encoding="utf-8")).get("theme", "")
            except Exception:
                pass
        return ""

    def generate_all(self, parallel: int = None) -> Dict[str, Any]:
        """生成所有场景图（Step ⑤-⑦）

        包括变体图分析、并行生成、variants.json 写入。

        Args:
            parallel: 并发数，None 时读取 IMAGE_PARALLEL 配置

        Returns:
            {"total": int, "succeeded": int, "failed": int,
             "skipped": int, "variant_scenes": dict, "results": list}
        """
        scenes = self._load_scenes()
        if not scenes:
            raise SceneImageError("scenes.json 为空或不存在")
        parallel = max(1, parallel or self.cfg.get_int("image_parallel", 1))

        print(f"  [Steps ⑤-⑦] {len(scenes)} 个场景，并发数={parallel}")

        # 分析变体图需求
        all_tasks, variants_map = self._analyze_variants(scenes)

        if self.dry_run:
            # dry_run 模式：不调用任何 API，只写 variants.json，生成文本标注占位图
            print(f"  [dry_run] 跳过真实图片 API 调用，生成占位图")
            self._generate_placeholder_images(scenes, variants_map)

            if variants_map:
                self._write_variants_json(variants_map)

            return {
                "total": len(all_tasks),
                "succeeded": len(all_tasks),
                "failed": 0,
                "skipped": 0,
                "variant_scenes": variants_map,
                "results": [{"sid": s[0], "variant_index": s[1],
                             "status": "ok", "size": 0} for s in all_tasks],
            }

        # 幂等跳过检查
        # 主图已存在 -> 跳过整个场景
        # 变体图已存在 -> 跳过
        tasks_to_run = []
        skipped = []
        for sid, vi, desc, output_path in all_tasks:
            p = Path(output_path)
            if p.exists() and p.stat().st_size > MIN_IMAGE_SIZE:
                skipped.append((sid, vi))
                continue
            tasks_to_run.append((sid, vi, desc, output_path))

        if skipped:
            skipped_ids = sorted(set(s[0] for s in skipped))
            print(f"  [..] 跳过（已存在）: {skipped_ids}")

        if not tasks_to_run:
            print(f"  [OK] 全部场景图已存在")
            if variants_map:
                self._write_variants_json(variants_map)
            return {
                "total": len(all_tasks),
                "succeeded": len(skipped),
                "failed": 0,
                "skipped": len(skipped),
                "variant_scenes": variants_map,
                "results": [{"sid": s[0], "status": "skipped"} for s in skipped],
            }

        # 并行生成
        print(f"  [..] 生成 {len(tasks_to_run)} 张图片...")
        results = self._run_parallel(tasks_to_run, parallel)

        # 统计
        ok = sum(1 for r in results if r.get("status") == "ok")
        fail = sum(1 for r in results if r.get("status") == "failed")

        print(f"  [OK] 场景图完成: {ok}/{len(results)} 成功 ({fail} 失败)")

        # 写入 variants.json
        if variants_map:
            self._write_variants_json(variants_map)

        return {
            "total": len(all_tasks),
            "succeeded": ok + len(skipped),
            "failed": fail,
            "skipped": len(skipped),
            "variant_scenes": variants_map,
            "results": results + [{"sid": s[0], "variant_index": s[1],
                                    "status": "skipped"} for s in skipped],
        }

    # ══════════════════════════════════════════════════════
    # 内部方法
    # ══════════════════════════════════════════════════════

    def _load_scenes(self) -> List[Dict]:
        """加载场景配置"""
        scenes_path = self.metadata_dir / "scenes.json"
        if not scenes_path.exists():
            raise FileNotFoundError(f"scenes.json not found: {scenes_path}")
        return json.loads(scenes_path.read_text(encoding="utf-8"))

    def _generate_placeholder_images(self, scenes: List[Dict],
                                      variants_map: Dict[int, int]):
        """dry_run 模式：生成带文本标注的占位图

        每张图片标注：场景编号、名称、歌词预览、时长、风格标签
        颜色按段落类型区分（Verse/Chorus/Bridge/Outro）
        """
        from PIL import Image, ImageDraw

        # 段落类型 → 背景色
        section_colors = {
            "verse": (60, 90, 140),
            "chorus": (140, 80, 60),
            "bridge": (80, 120, 80),
            "outro": (100, 70, 120),
            "intro": (70, 100, 130),
        }
        default_color = (80, 80, 100)

        # 收集所有变体描述
        all_variants = {}
        for s in scenes:
            if isinstance(s.get("variants"), list):
                for vi, vdesc in enumerate(s["variants"]):
                    all_variants[(s["id"], vi + 1)] = vdesc

        # 构建 scenes 的 id->scene 映射
        scenes_map = {s["id"]: s for s in scenes}

        for sid, vi, desc, out_path_str in self._analyze_variants(scenes)[0]:
            p = Path(out_path_str)
            if p.exists() and p.stat().st_size > MIN_IMAGE_SIZE:
                continue

            scene = scenes_map.get(sid, {})
            name = scene.get("name", f"scene {sid}")
            display_name = scene.get("display_name", name)
            text_preview = scene.get("text_preview", "")
            dur = scene.get("duration", 5)
            label = scene.get("label", "")
            is_rep = scene.get("is_repeated", False)

            # 段落类型判断
            section_type = "verse"
            if name in ("intro", "outro"):
                section_type = name
            elif "chorus" in name:
                section_type = "chorus"
            elif "bridge" in name:
                section_type = "bridge"

            bg_color = section_colors.get(section_type, default_color)

            # 如果是变体图，亮度微调
            if vi > 0:
                bg_color = tuple(min(255, c + 30) for c in bg_color)

            try:
                img = Image.new("RGB", (1080, 1920), bg_color)
                draw = ImageDraw.Draw(img)

                # 顶部信息栏
                top_bar_color = tuple(max(0, c - 40) for c in bg_color)
                draw.rectangle([(0, 0), (1080, 120)], fill=top_bar_color)

                # 场景编号（左上）
                sid_text = f"#{sid}"
                draw.text((30, 15), sid_text, fill=(255, 255, 200))

                # 段落类型标签（右上）
                section_label = section_type.upper()
                draw.text((1050, 15), section_label, fill=(200, 200, 255), anchor="ra")

                # 场景名称（顶中）
                draw.text((540, 50), display_name, fill=(255, 255, 255), anchor="ma")

                # 时长 + 重复标记（顶中偏下）
                meta_parts = [f"{dur:.1f}s"]
                if is_rep:
                    meta_parts.append("REPEAT")
                if vi > 0:
                    meta_parts.append(f"variant {vi}")
                meta_text = " | ".join(meta_parts)
                draw.text((540, 80), meta_text, fill=(200, 200, 200), anchor="ma")

                # 中央 - 歌词预览（大字）
                if text_preview:
                    # 分行（最多两行）
                    words = text_preview
                    if len(words) > 20:
                        # 尝试在中间分割
                        mid = len(words) // 2
                        # 找到标点或空格分割
                        split_pos = -1
                        for sep in "，。！？；,.;!? ":
                            pos = words.rfind(sep, 0, mid)
                            if pos > split_pos:
                                split_pos = pos
                        if split_pos > 5:
                            line1 = words[:split_pos + 1]
                            line2 = words[split_pos + 1:]
                            draw.text((540, 850), line1, fill=(255, 255, 255),
                                      anchor="mb", font_size=48)
                            draw.text((540, 920), line2, fill=(255, 255, 255),
                                      anchor="ma", font_size=48)
                        else:
                            draw.text((540, 880), words, fill=(255, 255, 255),
                                      anchor="mm", font_size=48)
                    else:
                        draw.text((540, 880), words, fill=(255, 255, 255),
                                  anchor="mm", font_size=48)

                # 底部 - 标签
                if label:
                    draw.text((540, 1850), label, fill=(200, 200, 150),
                              anchor="ma", font_size=20)

                # 底部 - 风格信息
                style_info = f"style: {self._style} | mood: {self._mood}"
                draw.text((540, 1880), style_info, fill=(160, 160, 160),
                          anchor="ma", font_size=16)

                # 保存
                img.save(str(p))

            except Exception:
                # PIL 版本可能不支持 font_size 参数
                try:
                    img = Image.new("RGB", (1080, 1920), bg_color)
                    draw = ImageDraw.Draw(img)
                    draw.text((30, 20), f"Scene #{sid}: {display_name}",
                              fill=(255, 255, 255))
                    if text_preview:
                        draw.text((540, 960), text_preview, fill=(255, 255, 255),
                                  anchor="mm")
                    draw.text((540, 1880), f"{dur:.1f}s | {self._style}",
                              fill=(200, 200, 200), anchor="ma")
                    img.save(str(p))
                except Exception:
                    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 1000)

    @staticmethod
    def _calc_variant_count(dur: float) -> int:
        """重复段落的变体数（VARIANT_MIN ~ VARIANT_MAX），时长越长变体越多"""
        import math
        return max(VARIANT_MIN, min(VARIANT_MAX, math.ceil(dur / VARIANT_SECS_PER_STEP)))

    def _analyze_variants(self, scenes: List[Dict]) -> Tuple[List, Dict]:
        """分析变体图需求，构建任务列表

        Returns:
            (tasks, variants_map)
            tasks: [(sid, vi, desc, output_path), ...]
            variants_map: {sid: num_variants}
        """
        tasks = []
        variants_map = {}

        for s in scenes:
            sid = s["id"]
            dur = s.get("duration", 0)
            is_rep = s.get("is_repeated", False)

            # 变体数量
            scene_variants = s.get("variants", [])
            n_variants = 1

            if isinstance(scene_variants, list) and scene_variants:
                n_variants = len(scene_variants) + 1
                variants_map[sid] = n_variants
            elif is_rep and dur > VARIANT_THRESHOLD:
                n_variants = self._calc_variant_count(dur)
                variants_map[sid] = n_variants

            # 主图和每个变体
            for vi in range(n_variants):
                if vi == 0:
                    out_path = self.images_dir / f"seg{sid}_scene.png"
                    desc = self._augment_scene_desc(s.get("desc", ""), s)
                else:
                    out_path = self.images_dir / f"seg{sid}_variant{vi}.png"
                    if vi - 1 < len(scene_variants):
                        desc = self._augment_scene_desc(scene_variants[vi - 1], s)
                    else:
                        desc = self._augment_scene_desc(s.get("desc", ""), s)

                tasks.append((sid, vi, desc, str(out_path)))

        return tasks, variants_map

    def _run_parallel(self, tasks: List[Tuple], parallel: int) -> List[Dict]:
        """并行执行图片生成任务"""
        results = []
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = {}

            for sid, vi, desc, out_path in tasks:
                future = executor.submit(
                    self._generate_single, sid, vi, desc, out_path
                )
                futures[future] = (sid, vi)

            for future in as_completed(futures):
                sid, vi = futures[future]
                try:
                    result = future.result()
                except Exception as e:
                    result = {"sid": sid, "variant_index": vi,
                              "status": "failed", "error": str(e)}

                if not isinstance(result, dict) or "status" not in result:
                    result = {"sid": sid, "variant_index": vi,
                              "status": "failed",
                              "error": f"invalid result type: {type(result).__name__}"}

                results.append(result)

                # 打印进度
                tag = f"var{vi}" if vi > 0 else ""
                if result.get("status") == "ok":
                    size_kb = result.get("size", 0) // 1024
                    print(f"     [OK] scene {sid}{tag}: {size_kb}KB")
                else:
                    err = result.get("error", "")
                    print(f"     [FAIL] scene {sid}{tag}: {err}")

        return results

    def _generate_single(self, sid: int, vi: int, desc: str,
                         output_path: str) -> Dict[str, Any]:
        """生成单张场景图（带重试）

        Args:
            sid: 场景 ID
            vi: 变体索引（0=主图）
            desc: 场景描述
            output_path: 输出路径

        Returns:
            {"sid": int, "variant_index": int, "status": str, "size": int, ...}
        """
        # 构建完整 prompt
        provider = self.cfg.get("image_api_provider", "minimax")
        prompt = self._build_scene_prompt(desc, provider=provider)

        for attempt in range(1, MAX_RETRY + 1):
            try:
                self.client.call_image_api(
                    prompt=prompt,
                    output_path=output_path,
                    style=self._api_style,
                    negative_prompt=self._negative_prompt,
                    seed=self._image_seed if vi == 0 else self._image_seed + vi,
                )

                if not os.path.exists(output_path):
                    raise ValueError(f"文件未创建: {output_path}")

                file_size = os.path.getsize(output_path)
                if file_size < MIN_IMAGE_SIZE:
                    raise ValueError(f"图片太小: {file_size} bytes")

                return {
                    "sid": sid,
                    "variant_index": vi,
                    "status": "ok",
                    "size": file_size,
                    "attempt": attempt,
                }

            except Exception as e:
                err_msg = str(e)
                if attempt == MAX_RETRY:
                    return {
                        "sid": sid,
                        "variant_index": vi,
                        "status": "failed",
                        "error": err_msg,
                        "attempt": attempt,
                    }
                print(f"     [WARN] scene {sid} var{vi} 尝试 {attempt}/{MAX_RETRY}"
                      f" 失败: {err_msg}, 重试...")
                time.sleep(RETRY_DELAY * attempt)

        return {
            "sid": sid,
            "variant_index": vi,
            "status": "failed",
            "error": "unknown",
            "attempt": MAX_RETRY,
        }

    @staticmethod
    def _needs_character_anchor(desc: str) -> bool:
        """Only inject character continuity when the shot clearly involves a person."""
        if not desc:
            return False

        lower = desc.lower()
        subject_tokens = (
            "person", "people", "character", "girl", "boy", "woman", "man",
            "child", "face", "portrait", "figure", "couple", "singer",
            "dancer", "hands", "eyes", "walking", "standing", "looking",
        )
        return any(token in lower for token in subject_tokens)

    @staticmethod
    def _augment_scene_desc(desc: str, scene: Dict) -> str:
        extras = []

        visual_focus = scene.get("visual_focus")
        shot_type = scene.get("shot_type")
        motion_hint = scene.get("motion_hint")
        symbolic_objects = scene.get("symbolic_objects") or []

        if visual_focus:
            extras.append(f"{visual_focus} focused shot")
        if shot_type:
            extras.append(f"{shot_type} framing")
        if motion_hint:
            extras.append(motion_hint)
        if symbolic_objects:
            extras.append("symbolic elements: " + ", ".join(symbolic_objects[:3]))
        if scene.get("character_needed") is False:
            extras.append("no centered human subject")

        extra_text = ", ".join(extras)
        if not extra_text:
            return desc
        if not desc:
            return extra_text
        return f"{desc}, {extra_text}"

    def _build_scene_prompt(self, desc: str, provider: str = "") -> str:
        """构建场景图片 prompt（MiniMax 要求 <= 1500 字符）"""
        desc_part = desc[:PROMPT_DESC_MAX] if desc else ""
        subject_part = self._build_subject_anchor_prompt()
        char_part = ""
        if self._char_prompt and self._needs_character_anchor(desc_part):
            char_part = (
                "maintain recurring subject continuity when a human appears, "
                + self._char_prompt[:PROMPT_CHAR_MAX]
            )
        # 根据 character_policy 决定是否注入角色
        if self._character_policy == "no fixed protagonist":
            char_part = ""

        parts = [
            p for p in [
                subject_part,
                desc_part,
                self._visual_bible_prompt,
                char_part,
                self._mood_desc,
                self._art_style,
                self._do_not_do,
            ] if p
        ]
        prompt = ", ".join(parts)
        if provider == "pollinations":
            prompt = self._compact_pollinations_prompt(prompt, subject_part, desc_part)
        if len(prompt) > PROMPT_MAX_LEN:
            prompt = prompt[:PROMPT_MAX_LEN - 20] + ", anime style, 8k"
        return prompt

    def _build_subject_anchor_prompt(self) -> str:
        """构建强主体锚点，主要给 Pollinations/Flux 这类弱约束模型使用。"""
        theme = self._theme or self._load_theme()
        song_title = self._song_title
        mode = self._infer_base_reference_mode(
            theme, song_title, visual_anchors=self._load_visual_anchors()
        )
        if mode == "nonhuman_subject":
            return (
                f"MAIN SUBJECT MUST BE: {theme}. The named non-human subject is the protagonist "
                "in every applicable scene. No human protagonist. Do not replace the subject with scenery."
            )
        if mode == "cosmic_environment":
            return f"MAIN SUBJECT MUST BE: {theme}. Cosmic space, galaxy, nebula, stars and planets dominate."
        if mode == "relation":
            return f"MAIN SUBJECT MUST BE: {theme}. A two-person relationship or couple presence drives the image."
        if mode == "human_action":
            return f"MAIN SUBJECT MUST BE: {theme}. Human action, group stakes, conflict or aftermath drives the image."
        if mode == "poetic_imagery":
            return f"MAIN SUBJECT MUST BE: {theme}. Classical poetic imagery and symbolic atmosphere dominate."
        return f"MAIN SUBJECT MUST BE: {theme}. Keep the image centered on this theme, not a generic background."

    def _compact_pollinations_prompt(self, prompt: str, subject_part: str,
                                     desc_part: str) -> str:
        """Pollinations 对长 prompt 遵循较弱，使用更短且主体前置的版本。"""
        parts = [
            subject_part,
            desc_part[:420] if desc_part else "",
            self._mood_desc,
            self._art_style,
            "clear main subject, coherent composition, high quality",
        ]
        compact = ", ".join(p for p in parts if p)
        return compact[:900]

    def _write_variants_json(self, variants_map: Dict[int, int]):
        """写入 variants.json，记录每个场景的变体数量"""
        variants_path = self.metadata_dir / "variants.json"
        variants_path.write_text(
            json.dumps({"variant_scenes": variants_map},
                       ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        total = sum(variants_map.values())
        print(f"  [OK] variants.json 已写入: {total} 变体图")
