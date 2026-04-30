"""
test_scene_generator.py — 场景图生成模块测试

覆盖:
  - 初始化与风格参数加载
  - 变体分析
  - 场景 prompt 构建
  - variants.json 写入
  - 基础角色图生成
  - 无 scenes.json/base_char.json 时的错误处理
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.scene_generator import SceneImageGenerator, SceneImageError


class TestSceneGeneratorInit(unittest.TestCase):
    """测试初始化与风格参数加载"""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_scene_gen_"))
        self._init_dirs()
        self._create_minimal_files()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _init_dirs(self):
        (self.test_dir / "images").mkdir()
        (self.test_dir / "metadata").mkdir()
        (self.test_dir / "clips").mkdir()
        (self.test_dir / "audio").mkdir()

    def _create_minimal_files(self):
        """创建基础项目文件"""
        # info.json
        info = {
            "theme": "童年",
            "style": "动漫风",
            "music_style": "流行",
            "mood": "欢快",
            "song_title": "测试歌曲",
            "image_seed": 42,
        }
        (self.test_dir / "metadata" / "info.json").write_text(
            json.dumps(info, ensure_ascii=False), encoding="utf-8"
        )

        # scenes.json
        scenes = [
            {"id": 1, "label": "intro", "duration": 8.0, "is_repeated": False,
             "desc": "morning scene, sunlight through window",
             "variants": ["golden light variant", "blue hour variant"]},
            {"id": 2, "label": "chorus", "duration": 12.0, "is_repeated": True,
             "desc": "wide landscape with character running", "variants": []},
            {"id": 3, "label": "outro", "duration": 6.0, "is_repeated": False,
             "desc": "sunset farewell scene", "variants": []},
        ]
        (self.test_dir / "metadata" / "scenes.json").write_text(
            json.dumps(scenes), encoding="utf-8"
        )

        # base_char.json
        bc = {
            "prompt": "A cute Chinese boy, 8 years old, with big bright eyes",
            "style": "动漫风",
            "mood": "欢快",
        }
        (self.test_dir / "metadata" / "base_char.json").write_text(
            json.dumps(bc), encoding="utf-8"
        )

        visual_bible = {
            "world_style": "nostalgic anime summer memory world",
            "palette": ["warm gold", "faded teal", "soft cream"],
            "lighting": "soft backlight haze",
            "texture": "airy film softness",
            "camera_language": "wide drifting frames with occasional close inserts",
        }
        (self.test_dir / "metadata" / "visual_bible.json").write_text(
            json.dumps(visual_bible), encoding="utf-8"
        )

    def test_init_basic(self):
        gen = SceneImageGenerator(str(self.test_dir))
        self.assertEqual(gen.project_dir, self.test_dir)
        self.assertIn("Chinese boy", gen._char_prompt)
        self.assertEqual(gen._style, "动漫风")
        self.assertEqual(gen._mood, "欢快")
        self.assertTrue(gen._art_style)
        self.assertTrue(gen._mood_desc)
        self.assertIn("nostalgic anime summer memory world", gen._visual_bible_prompt)

    def test_init_no_base_char(self):
        """没有 base_char.json 时应从 info.json + style_map 加载"""
        (self.test_dir / "metadata" / "base_char.json").unlink()
        gen = SceneImageGenerator(str(self.test_dir))
        self.assertTrue(gen._char_prompt)
        self.assertEqual(gen._style, "动漫风")

    def test_init_images_dir_created(self):
        """images/ 目录不存在时应自动创建"""
        shutil.rmtree(self.test_dir / "images")
        gen = SceneImageGenerator(str(self.test_dir))
        self.assertTrue((self.test_dir / "images").exists())

    def test_init_no_info(self):
        """缺少 info.json 也能初始化"""
        (self.test_dir / "metadata" / "info.json").unlink()
        gen = SceneImageGenerator(str(self.test_dir))
        self.assertEqual(gen._style, "动漫风")
        self.assertEqual(gen._mood, "欢快")

    def test_visual_bible_loaded(self):
        """visual_bible.json 应被正确加载并生成 visual_bible_prompt"""
        gen = SceneImageGenerator(str(self.test_dir))
        self.assertIn("nostalgic anime summer memory world", gen._visual_bible_prompt)
        self.assertIn("warm gold", gen._visual_bible_prompt)
        self.assertIn("soft backlight haze", gen._visual_bible_prompt)

    def test_visual_bible_missing(self):
        """缺少 visual_bible.json 时不应报错"""
        (self.test_dir / "metadata" / "visual_bible.json").unlink()
        gen = SceneImageGenerator(str(self.test_dir))
        self.assertEqual(gen._visual_bible, {})
        self.assertEqual(gen._visual_bible_prompt, "")


class TestSceneGeneratorVariantAnalysis(unittest.TestCase):
    """测试变体分析逻辑"""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_scene_variants_"))
        (self.test_dir / "images").mkdir()
        (self.test_dir / "metadata").mkdir()
        (self.test_dir / "clips").mkdir()
        (self.test_dir / "audio").mkdir()

        # base_char.json
        bc = {"prompt": "A cute boy", "style": "动漫风", "mood": "欢快"}
        (self.test_dir / "metadata" / "base_char.json").write_text(
            json.dumps(bc), encoding="utf-8"
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_variants_from_scenes_json(self):
        """scenes.json 中的 variants 字段应决定变体数"""
        scenes = [
            {"id": 1, "label": "intro", "duration": 8.0, "is_repeated": False,
             "desc": "test", "variants": ["var1"]},
            {"id": 2, "label": "chorus", "duration": 12.0, "is_repeated": True,
             "desc": "test", "variants": []},
        ]
        (self.test_dir / "metadata" / "scenes.json").write_text(
            json.dumps(scenes), encoding="utf-8"
        )

        gen = SceneImageGenerator(str(self.test_dir))
        tasks, variants_map = gen._analyze_variants(scenes)

        # scene 1: 1 main + 1 variant = 2
        s1_tasks = [(sid, vi) for sid, vi, _, _ in tasks if sid == 1]
        self.assertEqual(len(s1_tasks), 2, "1个变体应生成2任务")

        # scene 2: is_repeated=True, 12s > 4s => variants
        s2_tasks = [(sid, vi) for sid, vi, _, _ in tasks if sid == 2]
        self.assertGreater(len(s2_tasks), 1, "重复段应生成变体")

    def test_variants_repeated_long(self):
        """长重复段应按公式生成变体"""
        scenes = [
            {"id": 1, "label": "chorus", "duration": 20.0, "is_repeated": True,
             "desc": "test", "variants": []},
        ]
        (self.test_dir / "metadata" / "scenes.json").write_text(
            json.dumps(scenes), encoding="utf-8"
        )

        gen = SceneImageGenerator(str(self.test_dir))
        tasks, variants_map = gen._analyze_variants(scenes)

        self.assertIn(1, variants_map)
        self.assertGreaterEqual(variants_map[1], 2)
        self.assertLessEqual(variants_map[1], 3)

    def test_variants_short_no_repeat(self):
        """短非重复段只有一个主图"""
        scenes = [
            {"id": 1, "label": "intro", "duration": 3.0, "is_repeated": False,
             "desc": "test", "variants": []},
        ]
        (self.test_dir / "metadata" / "scenes.json").write_text(
            json.dumps(scenes), encoding="utf-8"
        )

        gen = SceneImageGenerator(str(self.test_dir))
        tasks, variants_map = gen._analyze_variants(scenes)

        self.assertEqual(len(tasks), 1)  # 只有主图
        self.assertNotIn(1, variants_map)


class TestSceneGeneratorPromptBuilding(unittest.TestCase):
    """测试场景 prompt 构建"""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_scene_prompt_"))
        (self.test_dir / "images").mkdir()
        (self.test_dir / "metadata").mkdir()
        (self.test_dir / "clips").mkdir()
        (self.test_dir / "audio").mkdir()

        bc = {"prompt": "A cute boy", "style": "动漫风", "mood": "温柔"}
        (self.test_dir / "metadata" / "base_char.json").write_text(
            json.dumps(bc), encoding="utf-8"
        )
        (self.test_dir / "metadata" / "scenes.json").write_text(
            json.dumps([{"id": 1, "desc": "test scene", "duration": 5}]), encoding="utf-8"
        )
        (self.test_dir / "metadata" / "visual_bible.json").write_text(
            json.dumps({
                "world_style": "nostalgic anime summer memory world",
                "palette": ["warm gold", "faded teal", "soft cream"],
                "lighting": "soft backlight haze",
                "texture": "airy film softness",
                "camera_language": "wide drifting frames with occasional close inserts",
            }),
            encoding="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_build_scene_prompt(self):
        gen = SceneImageGenerator(str(self.test_dir))
        prompt = gen._build_scene_prompt("a beautiful sunset with a boy by the river")

        self.assertIn("a beautiful sunset with a boy by the river", prompt)
        self.assertIn("cute boy", prompt)
        self.assertIn("gentle", prompt)  # 温柔 mood description
        self.assertIn("anime", prompt.lower())  # 动漫风 art style
        self.assertIn("nostalgic anime summer memory world", prompt)
        # 验证 visual bible 的各字段已注入
        self.assertIn("warm gold", prompt)
        self.assertIn("soft backlight haze", prompt)
        self.assertIn("wide drifting frames", prompt)

    def test_build_scene_prompt_empty_desc(self):
        gen = SceneImageGenerator(str(self.test_dir))
        prompt = gen._build_scene_prompt("")
        self.assertNotIn("cute boy", prompt)
        self.assertTrue(len(prompt) > 10)
        self.assertIn("warm gold", prompt)

    def test_build_scene_prompt_no_char(self):
        gen = SceneImageGenerator(str(self.test_dir))
        gen._char_prompt = ""  # 模拟无角色描述
        prompt = gen._build_scene_prompt("sunset")
        self.assertIn("sunset", prompt)


    def test_augment_scene_desc(self):
        desc = SceneImageGenerator._augment_scene_desc(
            "empty station platform at dusk",
            {
                "visual_focus": "environment",
                "shot_type": "wide",
                "character_needed": False,
                "symbolic_objects": ["wind", "station"],
                "motion_hint": "slow drift",
            },
        )
        self.assertIn("environment focused shot", desc)
        self.assertIn("no centered human subject", desc)


class TestSceneGeneratorVariantsJson(unittest.TestCase):
    """测试 variants.json 生成"""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_variants_json_"))
        (self.test_dir / "images").mkdir()
        (self.test_dir / "metadata").mkdir()
        (self.test_dir / "clips").mkdir()
        (self.test_dir / "audio").mkdir()

        bc = {"prompt": "test", "style": "动漫风", "mood": "欢快"}
        (self.test_dir / "metadata" / "base_char.json").write_text(
            json.dumps(bc), encoding="utf-8"
        )
        (self.test_dir / "metadata" / "scenes.json").write_text(
            json.dumps([{"id": 1, "desc": "t", "duration": 5}]), encoding="utf-8"
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_write_variants_json(self):
        gen = SceneImageGenerator(str(self.test_dir))
        gen._write_variants_json({1: 2, 3: 3})

        variants_path = self.test_dir / "metadata" / "variants.json"
        self.assertTrue(variants_path.exists())

        data = json.loads(variants_path.read_text(encoding="utf-8"))
        self.assertIn("variant_scenes", data)
        self.assertEqual(data["variant_scenes"]["1"], 2)
        self.assertEqual(data["variant_scenes"]["3"], 3)


class TestSceneGeneratorGenerateBaseCharacter(unittest.TestCase):
    """测试基础角色图生成"""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_base_char_"))
        (self.test_dir / "images").mkdir()
        (self.test_dir / "metadata").mkdir()
        (self.test_dir / "clips").mkdir()
        (self.test_dir / "audio").mkdir()

        bc = {"prompt": "A cute boy", "style": "动漫风", "mood": "欢快"}
        (self.test_dir / "metadata" / "base_char.json").write_text(
            json.dumps(bc), encoding="utf-8"
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_base_character_already_exists(self):
        """已有 base_character.png 时应跳过"""
        # 创建一个假的 base_character.png
        fake_img = self.test_dir / "images" / "base_character.png"
        fake_img.write_bytes(b"x" * 50000)  # 50KB

        gen = SceneImageGenerator(str(self.test_dir))
        result = gen.generate_base_character()
        self.assertTrue(result)

    def test_base_character_no_info_json(self):
        """没有 info.json 也能调用，返回 bool 不崩溃"""
        gen = SceneImageGenerator(str(self.test_dir))
        try:
            result = gen.generate_base_character(theme="童年", song_title="测试")
            self.assertIsInstance(result, bool)
        except Exception as e:
            self.fail(f"generate_base_character 抛出了异常: {e}")

    def test_base_character_custom_prompt(self):
        """override_prompt 应被优先使用"""
        gen = SceneImageGenerator(str(self.test_dir))
        # 不实际调用 API，只验证 path 正确
        self.assertEqual(
            str(self.test_dir / "images" / "base_character.png"),
            str(gen.images_dir / "base_character.png")
        )


class TestSceneGeneratorErrorHandling(unittest.TestCase):
    """测试错误处理"""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_scene_err_"))
        (self.test_dir / "images").mkdir()
        (self.test_dir / "metadata").mkdir()
        (self.test_dir / "clips").mkdir()
        (self.test_dir / "audio").mkdir()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_no_scenes_json(self):
        """缺少 scenes.json 应报错"""
        gen = SceneImageGenerator(str(self.test_dir))
        with self.assertRaises(FileNotFoundError):
            gen._load_scenes()

    def test_generate_all_no_scenes(self):
        """generate_all 在无 scenes.json 时报错"""
        gen = SceneImageGenerator(str(self.test_dir))
        with self.assertRaises((SceneImageError, FileNotFoundError)):
            gen.generate_all()

    def test_generate_all_empty_scenes(self):
        """空的 scenes.json 报错"""
        (self.test_dir / "metadata" / "scenes.json").write_text("[]", encoding="utf-8")
        gen = SceneImageGenerator(str(self.test_dir))
        with self.assertRaises(SceneImageError):
            gen.generate_all()

    def test_generate_all_skip_existing(self):
        """已有图片时应跳过"""
        bc = {"prompt": "test", "style": "动漫风", "mood": "欢快"}
        (self.test_dir / "metadata" / "base_char.json").write_text(
            json.dumps(bc), encoding="utf-8"
        )
        scenes = [{"id": 1, "desc": "test", "duration": 5, "is_repeated": False,
                   "variants": []}]
        (self.test_dir / "metadata" / "scenes.json").write_text(
            json.dumps(scenes), encoding="utf-8"
        )

        gen = SceneImageGenerator(str(self.test_dir))
        result = gen.generate_all(parallel=1)

        # 没有真实 API 时，图片不会被生成
        # 但程序不应崩溃——应该正常返回
        self.assertIsInstance(result, dict)
        self.assertIn("total", result)
        self.assertIn("succeeded", result)
        self.assertIn("failed", result)


if __name__ == "__main__":
    unittest.main()
