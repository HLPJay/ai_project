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
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.scene_generator import SceneImageGenerator, SceneImageError


def _init_sg_dirs(project_dir: Path):
    for subdir in ("images", "metadata", "clips", "audio"):
        (project_dir / subdir).mkdir(exist_ok=True)


def _create_minimal_sg_files(project_dir: Path):
    """创建标准 SG 测试项目文件"""
    info = {
        "theme": "童年",
        "style": "动漫风",
        "music_style": "流行",
        "mood": "欢快",
        "song_title": "测试歌曲",
        "image_seed": 42,
    }
    (project_dir / "metadata" / "info.json").write_text(
        json.dumps(info, ensure_ascii=False), encoding="utf-8"
    )
    scenes = [
        {"id": 1, "label": "intro", "duration": 8.0, "is_repeated": False,
         "desc": "morning scene, sunlight through window",
         "variants": ["golden light variant", "blue hour variant"]},
        {"id": 2, "label": "chorus", "duration": 12.0, "is_repeated": True,
         "desc": "wide landscape with character running", "variants": []},
        {"id": 3, "label": "outro", "duration": 6.0, "is_repeated": False,
         "desc": "sunset farewell scene", "variants": []},
    ]
    (project_dir / "metadata" / "scenes.json").write_text(json.dumps(scenes), encoding="utf-8")
    bc = {
        "prompt": "A cute Chinese boy, 8 years old, with big bright eyes",
        "style": "动漫风",
        "mood": "欢快",
    }
    (project_dir / "metadata" / "base_char.json").write_text(json.dumps(bc), encoding="utf-8")
    visual_bible = {
        "world_style": "nostalgic anime summer memory world",
        "palette": ["warm gold", "faded teal", "soft cream"],
        "lighting": "soft backlight haze",
        "texture": "airy film softness",
        "camera_language": "wide drifting frames with occasional close inserts",
    }
    (project_dir / "metadata" / "visual_bible.json").write_text(json.dumps(visual_bible), encoding="utf-8")


class TestSceneGeneratorInit:
    """测试初始化与风格参数加载"""

    def test_init_basic(self, tmp_path):
        _init_sg_dirs(tmp_path)
        _create_minimal_sg_files(tmp_path)
        gen = SceneImageGenerator(str(tmp_path))
        assert gen.project_dir == tmp_path
        assert "Chinese boy" in gen._char_prompt
        assert gen._style == "动漫风"
        assert gen._mood == "欢快"
        assert gen._art_style
        assert gen._mood_desc
        assert "nostalgic anime summer memory world" in gen._visual_bible_prompt

    def test_init_no_base_char(self, tmp_path):
        _init_sg_dirs(tmp_path)
        _create_minimal_sg_files(tmp_path)
        (tmp_path / "metadata" / "base_char.json").unlink()
        gen = SceneImageGenerator(str(tmp_path))
        assert gen._char_prompt
        assert gen._style == "动漫风"

    def test_init_images_dir_created(self, tmp_path):
        _init_sg_dirs(tmp_path)
        _create_minimal_sg_files(tmp_path)
        import shutil
        shutil.rmtree(tmp_path / "images")
        gen = SceneImageGenerator(str(tmp_path))
        assert (tmp_path / "images").exists()

    def test_init_no_info(self, tmp_path):
        _init_sg_dirs(tmp_path)
        _create_minimal_sg_files(tmp_path)
        (tmp_path / "metadata" / "info.json").unlink()
        gen = SceneImageGenerator(str(tmp_path))
        assert gen._style == "动漫风"
        assert gen._mood == "欢快"

    def test_visual_bible_loaded(self, tmp_path):
        _init_sg_dirs(tmp_path)
        _create_minimal_sg_files(tmp_path)
        gen = SceneImageGenerator(str(tmp_path))
        assert "nostalgic anime summer memory world" in gen._visual_bible_prompt
        assert "warm gold" in gen._visual_bible_prompt
        assert "soft backlight haze" in gen._visual_bible_prompt

    def test_visual_bible_missing(self, tmp_path):
        _init_sg_dirs(tmp_path)
        _create_minimal_sg_files(tmp_path)
        (tmp_path / "metadata" / "visual_bible.json").unlink()
        gen = SceneImageGenerator(str(tmp_path))
        assert gen._visual_bible == {}
        assert gen._visual_bible_prompt == ""


class TestSceneGeneratorVariantAnalysis:
    """测试变体分析逻辑"""

    def _setup_variant_project(self, project_dir: Path):
        _init_sg_dirs(project_dir)
        bc = {"prompt": "A cute boy", "style": "动漫风", "mood": "欢快"}
        (project_dir / "metadata" / "base_char.json").write_text(json.dumps(bc), encoding="utf-8")

    def test_variants_from_scenes_json(self, tmp_path):
        self._setup_variant_project(tmp_path)
        scenes = [
            {"id": 1, "label": "intro", "duration": 8.0, "is_repeated": False,
             "desc": "test", "variants": ["var1"]},
            {"id": 2, "label": "chorus", "duration": 12.0, "is_repeated": True,
             "desc": "test", "variants": []},
        ]
        (tmp_path / "metadata" / "scenes.json").write_text(json.dumps(scenes), encoding="utf-8")
        gen = SceneImageGenerator(str(tmp_path))
        tasks, variants_map = gen._analyze_variants(scenes)
        s1_tasks = [(sid, vi) for sid, vi, _, _ in tasks if sid == 1]
        assert len(s1_tasks) == 2, "1个变体应生成2任务"
        s2_tasks = [(sid, vi) for sid, vi, _, _ in tasks if sid == 2]
        assert len(s2_tasks) > 1, "重复段应生成变体"

    def test_variants_repeated_long(self, tmp_path):
        self._setup_variant_project(tmp_path)
        scenes = [
            {"id": 1, "label": "chorus", "duration": 20.0, "is_repeated": True,
             "desc": "test", "variants": []},
        ]
        (tmp_path / "metadata" / "scenes.json").write_text(json.dumps(scenes), encoding="utf-8")
        gen = SceneImageGenerator(str(tmp_path))
        tasks, variants_map = gen._analyze_variants(scenes)
        assert 1 in variants_map
        assert variants_map[1] >= 2
        assert variants_map[1] <= 3

    def test_variants_short_no_repeat(self, tmp_path):
        self._setup_variant_project(tmp_path)
        scenes = [
            {"id": 1, "label": "intro", "duration": 3.0, "is_repeated": False,
             "desc": "test", "variants": []},
        ]
        (tmp_path / "metadata" / "scenes.json").write_text(json.dumps(scenes), encoding="utf-8")
        gen = SceneImageGenerator(str(tmp_path))
        tasks, variants_map = gen._analyze_variants(scenes)
        assert len(tasks) == 1
        assert 1 not in variants_map


class TestSceneGeneratorPromptBuilding:
    """测试场景 prompt 构建"""

    def _setup_prompt_project(self, project_dir: Path):
        _init_sg_dirs(project_dir)
        bc = {"prompt": "A cute boy", "style": "动漫风", "mood": "温柔"}
        (project_dir / "metadata" / "base_char.json").write_text(json.dumps(bc), encoding="utf-8")
        (project_dir / "metadata" / "scenes.json").write_text(
            json.dumps([{"id": 1, "desc": "test scene", "duration": 5}]), encoding="utf-8"
        )
        (project_dir / "metadata" / "visual_bible.json").write_text(
            json.dumps({
                "world_style": "nostalgic anime summer memory world",
                "palette": ["warm gold", "faded teal", "soft cream"],
                "lighting": "soft backlight haze",
                "texture": "airy film softness",
                "camera_language": "wide drifting frames with occasional close inserts",
            }),
            encoding="utf-8",
        )

    def test_build_scene_prompt(self, tmp_path):
        self._setup_prompt_project(tmp_path)
        gen = SceneImageGenerator(str(tmp_path))
        prompt = gen._build_scene_prompt("a beautiful sunset with a boy by the river")
        assert "a beautiful sunset with a boy by the river" in prompt
        assert "gentle" in prompt
        assert "anime" in prompt.lower()
        assert "nostalgic anime summer memory world" in prompt
        assert "warm gold" in prompt
        assert "soft backlight haze" in prompt
        assert "wide drifting frames" in prompt

    def test_build_scene_prompt_empty_desc(self, tmp_path):
        self._setup_prompt_project(tmp_path)
        gen = SceneImageGenerator(str(tmp_path))
        prompt = gen._build_scene_prompt("")
        assert "cute boy" not in prompt
        assert len(prompt) > 10
        assert "warm gold" in prompt

    def test_build_scene_prompt_no_char(self, tmp_path):
        self._setup_prompt_project(tmp_path)
        gen = SceneImageGenerator(str(tmp_path))
        gen._char_prompt = ""
        prompt = gen._build_scene_prompt("sunset")
        assert "sunset" in prompt

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
        assert "environment focused shot" in desc
        assert "no centered human subject" in desc


class TestSceneGeneratorVariantsJson:
    """测试 variants.json 生成"""

    def test_write_variants_json(self, tmp_path):
        _init_sg_dirs(tmp_path)
        bc = {"prompt": "test", "style": "动漫风", "mood": "欢快"}
        (tmp_path / "metadata" / "base_char.json").write_text(json.dumps(bc), encoding="utf-8")
        (tmp_path / "metadata" / "scenes.json").write_text(
            json.dumps([{"id": 1, "desc": "t", "duration": 5}]), encoding="utf-8"
        )
        gen = SceneImageGenerator(str(tmp_path))
        gen._write_variants_json({1: 2, 3: 3})
        variants_path = tmp_path / "metadata" / "variants.json"
        assert variants_path.exists()
        data = json.loads(variants_path.read_text(encoding="utf-8"))
        assert "variant_scenes" in data
        assert data["variant_scenes"]["1"] == 2
        assert data["variant_scenes"]["3"] == 3


class TestSceneGeneratorGenerateBaseCharacter:
    """测试基础角色图生成"""

    def _setup_base_char_project(self, project_dir: Path, info: dict = None):
        _init_sg_dirs(project_dir)
        bc = {"prompt": "A cute boy", "style": "动漫风", "mood": "欢快"}
        (project_dir / "metadata" / "base_char.json").write_text(json.dumps(bc), encoding="utf-8")
        if info:
            (project_dir / "metadata" / "info.json").write_text(
                json.dumps(info, ensure_ascii=False), encoding="utf-8"
            )

    def test_base_character_already_exists(self, tmp_path):
        self._setup_base_char_project(tmp_path)
        (tmp_path / "images" / "base_character.png").write_bytes(b"x" * 50000)
        gen = SceneImageGenerator(str(tmp_path))
        result = gen.generate_base_character()
        assert result is True

    def test_base_character_no_info_json(self, tmp_path):
        self._setup_base_char_project(tmp_path)
        gen = SceneImageGenerator(str(tmp_path))
        try:
            result = gen.generate_base_character(theme="童年", song_title="测试")
            assert isinstance(result, bool)
        except Exception as e:
            pytest.fail(f"generate_base_character 抛出了异常: {e}")

    def test_base_character_custom_prompt(self, tmp_path):
        self._setup_base_char_project(tmp_path)
        gen = SceneImageGenerator(str(tmp_path))
        assert str(tmp_path / "images" / "base_character.png") == str(gen.images_dir / "base_character.png")

    def test_base_reference_prompt_environment_led(self, tmp_path):
        self._setup_base_char_project(tmp_path, {
            "theme": "春雨",
            "style": "国风",
            "music_style": "中国风",
            "mood": "梦幻",
            "song_title": "烟雨江南梦",
            "visual_mode": "environment-led",
            "character_policy": "optional protagonist",
            "visual_anchors": "spring rain, wet stone lane, willow, peach blossom",
        })
        gen = SceneImageGenerator(str(tmp_path))
        prompt = gen._build_base_reference_prompt("春雨", "烟雨江南梦")
        assert "core theme: 春雨" in prompt
        assert "no unrelated protagonist" in prompt
        assert "not a character sheet" not in prompt

    def test_base_reference_prompt_relation_theme(self, tmp_path):
        self._setup_base_char_project(tmp_path, {
            "theme": "爱情",
            "style": "国风",
            "music_style": "中国风",
            "mood": "浪漫",
            "song_title": "月下相思",
            "visual_mode": "environment-led",
            "character_policy": "optional protagonist",
            "visual_anchors": "moonlight, bridge, willow, shared umbrella",
        })
        gen = SceneImageGenerator(str(tmp_path))
        prompt = gen._build_base_reference_prompt("爱情", "月下相思")
        assert "relationship-centered" in prompt
        assert "two human subjects" in prompt
        assert "avoid generic empty scenery" in prompt
        assert "no protagonist" not in prompt

    def test_base_reference_prompt_fixed_protagonist(self, tmp_path):
        self._setup_base_char_project(tmp_path, {
            "theme": "童年",
            "style": "动漫风",
            "mood": "欢快",
            "song_title": "测试歌曲",
            "visual_mode": "character-led",
            "character_policy": "fixed protagonist",
        })
        gen = SceneImageGenerator(str(tmp_path))
        prompt = gen._build_base_reference_prompt("童年", "测试歌曲")
        assert "anime" in prompt.lower()
        assert "not a character sheet" in prompt


class TestSceneGeneratorErrorHandling:
    """测试错误处理"""

    def test_no_scenes_json(self, tmp_path):
        _init_sg_dirs(tmp_path)
        gen = SceneImageGenerator(str(tmp_path))
        with pytest.raises(FileNotFoundError):
            gen._load_scenes()

    def test_generate_all_no_scenes(self, tmp_path):
        _init_sg_dirs(tmp_path)
        gen = SceneImageGenerator(str(tmp_path))
        with pytest.raises((SceneImageError, FileNotFoundError)):
            gen.generate_all()

    def test_generate_all_empty_scenes(self, tmp_path):
        _init_sg_dirs(tmp_path)
        _create_minimal_sg_files(tmp_path)
        (tmp_path / "metadata" / "scenes.json").write_text("[]", encoding="utf-8")
        gen = SceneImageGenerator(str(tmp_path))
        with pytest.raises(SceneImageError):
            gen.generate_all()

    def test_generate_all_skip_existing(self, tmp_path):
        _init_sg_dirs(tmp_path)
        bc = {"prompt": "test", "style": "动漫风", "mood": "欢快"}
        (tmp_path / "metadata" / "base_char.json").write_text(json.dumps(bc), encoding="utf-8")
        scenes = [{"id": 1, "desc": "test", "duration": 5, "is_repeated": False,
                   "variants": []}]
        (tmp_path / "metadata" / "scenes.json").write_text(json.dumps(scenes), encoding="utf-8")
        gen = SceneImageGenerator(str(tmp_path))
        result = gen.generate_all(parallel=1)
        assert isinstance(result, dict)
        assert "total" in result
        assert "succeeded" in result
        assert "failed" in result


if __name__ == "__main__":
    import unittest
    unittest.main()
