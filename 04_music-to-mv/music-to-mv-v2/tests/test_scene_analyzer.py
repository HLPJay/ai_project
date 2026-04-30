"""
test_scene_analyzer.py — SRT 场景分析器测试

覆盖:
  - 初始化与配置加载
  - SRT 解析（标准格式、逗号/点分隔、无空行）
  - 结构分析（重复检测、场景划分）
  - 场景命名
  - 标签生成
  - 描述有效性检查
  - scenes.json 写入
  - 完整 analyze() 流水线
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.scene_analyzer import (
    SceneAnalyzer, SceneAnalyzerError,
    QUALITY_SUFFIX, VARIANT_TYPES,
)


def make_test_srt(lines_data, srt_path):
    """创建测试用 SRT 文件

    lines_data: [(start_sec, end_sec, text), ...]
    """
    def _to_srt_ts(sec):
        h = int(sec) // 3600
        m = int(sec) // 60 % 60
        s = sec % 60
        return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")

    blocks = []
    for i, (start, end, text) in enumerate(lines_data, 1):
        blocks.append(f"{i}\n{_to_srt_ts(start)} --> {_to_srt_ts(end)}\n{text}")

    srt_path.write_text("\n\n".join(blocks), encoding="utf-8")
    return srt_path


class TestSceneAnalyzerInit(unittest.TestCase):
    """测试初始化"""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_sa_init_"))
        self._init_dirs()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _init_dirs(self):
        (self.test_dir / "metadata").mkdir()
        (self.test_dir / "audio").mkdir()

    def _create_info(self, theme="童年", style="动漫风", mood="欢快"):
        info = {"theme": theme, "style": style, "mood": mood,
                "music_style": "流行", "song_title": "测试"}
        (self.test_dir / "metadata" / "info.json").write_text(
            json.dumps(info, ensure_ascii=False), encoding="utf-8"
        )

    def _create_base_char(self, prompt="A cute boy"):
        bc = {"prompt": prompt, "style": "动漫风", "mood": "欢快"}
        (self.test_dir / "metadata" / "base_char.json").write_text(
            json.dumps(bc), encoding="utf-8"
        )

    def test_init_with_files(self):
        self._create_info()
        self._create_base_char()
        analyzer = SceneAnalyzer(str(self.test_dir))
        self.assertEqual(analyzer._theme, "童年")
        self.assertEqual(analyzer._char_prompt, "A cute boy")

    def test_init_no_files(self):
        analyzer = SceneAnalyzer(str(self.test_dir))
        self.assertEqual(analyzer._theme, "")
        self.assertEqual(analyzer._style, "动漫风")

    def test_init_no_base_char(self):
        self._create_info()
        analyzer = SceneAnalyzer(str(self.test_dir))
        self.assertEqual(analyzer._char_prompt, "")


class TestSceneAnalyzerParseSRT(unittest.TestCase):
    """测试 SRT 解析"""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_sa_srt_"))
        self.srt_file = self.test_dir / "test.srt"

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_parse_standard(self):
        """标准 SRT 格式"""
        lines_data = [
            (0.5, 4.2, "今天天气真好"),
            (4.5, 8.1, "我们一起出去玩"),
            (8.5, 12.0, "看那美丽的花朵"),
        ]
        make_test_srt(lines_data, self.srt_file)

        segments = SceneAnalyzer.parse_srt(str(self.srt_file))
        self.assertEqual(len(segments), 3)
        self.assertEqual(segments[0][0], 1)  # idx
        self.assertAlmostEqual(segments[0][1], 0.5, places=1)
        self.assertAlmostEqual(segments[0][2], 4.2, places=1)
        self.assertEqual(segments[0][3], "今天天气真好")

    def test_parse_dot_separator(self):
        """点号分隔符也兼容"""
        content = "1\n00:00:00.500 --> 00:00:04.200\nHello World\n"
        self.srt_file.write_text(content, encoding="utf-8")
        segments = SceneAnalyzer.parse_srt(str(self.srt_file))
        self.assertEqual(len(segments), 1)
        self.assertAlmostEqual(segments[0][1], 0.5, places=1)

    def test_parse_no_empty_lines(self):
        """无空行的 SRT"""
        lines = [
            "1",
            "00:00:00,500 --> 00:00:04,200",
            "Line one",
            "2",
            "00:00:05,000 --> 00:00:10,000",
            "Line two",
        ]
        self.srt_file.write_text("\n".join(lines), encoding="utf-8")
        segments = SceneAnalyzer.parse_srt(str(self.srt_file))
        self.assertEqual(len(segments), 2)

    def test_parse_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            SceneAnalyzer.parse_srt(str(self.test_dir / "nonexistent.srt"))

    def test_parse_multiline_text(self):
        """多行歌词"""
        content = "1\n00:00:00,000 --> 00:00:05,000\nFirst line\nSecond line\nThird\n"
        self.srt_file.write_text(content, encoding="utf-8")
        segments = SceneAnalyzer.parse_srt(str(self.srt_file))
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0][3], "First line\nSecond line\nThird")


class TestSceneAnalyzerStructure(unittest.TestCase):
    """测试结构分析"""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_sa_struct_"))

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _make_segments(self, texts):
        """创建简单 segments（每个 4 秒）"""
        segs = []
        for i, text in enumerate(texts):
            segs.append((i + 1, i * 4.0, i * 4.0 + 3.5, text))
        return segs

    def test_empty_segments(self):
        result = SceneAnalyzer.analyze_structure([])
        self.assertEqual(result, [])

    def test_no_repeat(self):
        """无重复歌词"""
        segs = self._make_segments([
            "开始", "故事展开", "继续前进",
            "情感加深", "慢慢结束",
        ])
        paragraphs = SceneAnalyzer.analyze_structure(segs)
        self.assertGreater(len(paragraphs), 0)
        for p in paragraphs:
            self.assertFalse(p["is_repeated"])

    def test_repeat_detection(self):
        """重复歌词 → is_repeated"""
        segs = self._make_segments([
            "副歌副歌", "主歌", "副歌副歌", "主歌2", "副歌副歌",
        ])
        paragraphs = SceneAnalyzer.analyze_structure(segs)
        repeat_paras = [p for p in paragraphs if p["is_repeated"]]
        self.assertGreater(len(repeat_paras), 0)

    def test_scene_count_by_duration(self):
        """短歌 → 10 场景，长歌 → 22 场景"""
        # 150s 长歌（22 场景）
        texts = [f"line_{i}" for i in range(100)]
        segs = [(i + 1, i * 1.5, i * 1.5 + 1.3, texts[i]) for i in range(100)]
        paragraphs = SceneAnalyzer.analyze_structure(segs)
        self.assertLessEqual(len(paragraphs), 22)

        # 30s 短歌（10 场景）
        texts2 = [f"short_{i}" for i in range(20)]
        segs2 = [(i + 1, i * 1.5, i * 1.5 + 1.3, texts2[i]) for i in range(20)]
        paragraphs2 = SceneAnalyzer.analyze_structure(segs2)
        self.assertLessEqual(len(paragraphs2), 10)

    def test_paragraph_fields(self):
        segs = self._make_segments(["hello", "world"])
        paragraphs = SceneAnalyzer.analyze_structure(segs)
        p = paragraphs[0]
        self.assertIn("start", p)
        self.assertIn("end", p)
        self.assertIn("duration", p)
        self.assertIn("text", p)
        self.assertIn("is_repeated", p)
        self.assertIn("start_seg", p)
        self.assertIn("end_seg", p)
        self.assertIn("segment_count", p)
        self.assertGreater(p["duration"], 0)


class TestSceneAnalyzerNaming(unittest.TestCase):
    """测试场景命名"""

    def test_intro_outro(self):
        paragraphs = [
            {"is_repeated": False},
            {"is_repeated": False, "duration": 10},
            {"is_repeated": False, "duration": 8},
            {"is_repeated": False, "duration": 6},
        ]
        scenes = SceneAnalyzer.name_scenes(paragraphs)
        self.assertEqual(scenes[0]["name"], "intro")
        self.assertEqual(scenes[-1]["name"], "outro")

    def test_chorus_detection(self):
        paragraphs = [
            {"is_repeated": False, "duration": 10},
            {"is_repeated": True, "duration": 10},
            {"is_repeated": True, "duration": 10},
            {"is_repeated": False, "duration": 8},
        ]
        scenes = SceneAnalyzer.name_scenes(paragraphs)
        chorus = [s for s in scenes if s["name"] == "chorus"]
        self.assertGreater(len(chorus), 0)

    def test_verse_bridge(self):
        paragraphs = [
            {"is_repeated": False, "duration": 10},
            {"is_repeated": False, "duration": 10},
            {"is_repeated": True, "duration": 10},
            {"is_repeated": False, "duration": 8},
            {"is_repeated": False, "duration": 6},
        ]
        scenes = SceneAnalyzer.name_scenes(paragraphs)
        names = [s["name"] for s in scenes]
        self.assertIn("verse1", names)
        self.assertIn("verse2", names)
        self.assertIn("chorus", names)

    def test_scene_structure(self):
        paragraphs = [
            {"is_repeated": False, "duration": 5},
        ]
        scenes = SceneAnalyzer.name_scenes(paragraphs)
        self.assertEqual(len(scenes), 1)
        s = scenes[0]
        self.assertIn("id", s)
        self.assertIn("name", s)
        self.assertIn("start", s)
        self.assertIn("end", s)
        self.assertIn("duration", s)
        self.assertIn("text_preview", s)
        self.assertIn("is_repeated", s)


class TestSceneAnalyzerLabel(unittest.TestCase):
    """测试标签生成"""

    def test_label_with_match(self):
        """匹配到主题词"""
        label = SceneAnalyzer.generate_label(
            "chorus", "童年", "欢快", "一起去放风筝"
        )
        self.assertIn("童年", label)
        self.assertIn("欢快", label)

    def test_label_no_match(self):
        """未匹配则用默认标签"""
        label = SceneAnalyzer.generate_label(
            "intro", "未知主题_xy", "平静", "一些文字"
        )
        self.assertEqual(label, "序幕")

    def test_label_outro_default(self):
        label = SceneAnalyzer.generate_label(
            "outro", "xyz", "温柔", "nothing"
        )
        self.assertEqual(label, "尾声")

    def test_label_keyword_matching(self):
        """从 text_preview 匹配主题"""
        label = SceneAnalyzer.generate_label(
            "verse1", "成长", "希望", "春天来了花朵盛开"
        )
        # "春天" 在 THEME_VISUALS 中
        self.assertIn("春天", label)


class TestSceneAnalyzerDescValidation(unittest.TestCase):
    """测试描述有效性"""

    def test_valid_desc(self):
        valid = "A boy running through a meadow under golden sunlight"
        self.assertTrue(SceneAnalyzer._is_valid_desc(valid, "running"))

    def test_invalid_short(self):
        self.assertFalse(SceneAnalyzer._is_valid_desc("Hi", "test"))

    def test_invalid_truncated_prefix(self):
        bad = "the user wants me to create a description for this scene"
        self.assertFalse(SceneAnalyzer._is_valid_desc(bad, "test"))

    def test_invalid_old_template(self):
        self.assertFalse(SceneAnalyzer._is_valid_desc(
            "A cute child looking around with wonder", "test"
        ))

    def test_edge_8_words(self):
        """正好 8 个词"""
        desc = "a b c d e f g h"
        self.assertTrue(SceneAnalyzer._is_valid_desc(desc, "test"))

    def test_edge_7_words(self):
        """7 个词（应无效）"""
        desc = "a b c d e f g"
        self.assertFalse(SceneAnalyzer._is_valid_desc(desc, "test"))


class TestSceneAnalyzerLocalDesc(unittest.TestCase):
    """测试本地 fallback 描述生成"""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_sa_local_"))
        (self.test_dir / "metadata").mkdir()
        (self.test_dir / "audio").mkdir()
        bc = {"prompt": "A cute Chinese boy", "style": "动漫风", "mood": "欢快"}
        info = {"theme": "童年", "style": "动漫风", "mood": "欢快",
                "music_style": "流行"}
        (self.test_dir / "metadata" / "base_char.json").write_text(
            json.dumps(bc), encoding="utf-8"
        )
        (self.test_dir / "metadata" / "info.json").write_text(
            json.dumps(info), encoding="utf-8"
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_generate_local_desc(self):
        analyzer = SceneAnalyzer(str(self.test_dir))
        scene = {
            "name": "intro",
            "text_preview": "今天天气真好",
            "start": 0.0, "end": 5.0, "duration": 5.0,
        }
        desc = analyzer._generate_local_desc(scene)
        self.assertIn("8k", desc)
        self.assertIn("cute", desc)
        self.assertGreater(len(desc), 30)
        self.assertTrue(desc.endswith(QUALITY_SUFFIX))

    def test_generate_local_desc_chorus(self):
        analyzer = SceneAnalyzer(str(self.test_dir))
        scene = {
            "name": "chorus",
            "text_preview": "副歌部分",
            "start": 10.0, "end": 25.0, "duration": 15.0,
        }
        desc = analyzer._generate_local_desc(scene)
        self.assertIn("8k", desc)


class TestSceneAnalyzerFullAnalyze(unittest.TestCase):
    """测试完整 analyze() 流水线"""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_sa_full_"))
        (self.test_dir / "metadata").mkdir()
        (self.test_dir / "audio").mkdir()

        bc = {"prompt": "A cute Chinese boy, 8 years old",
              "style": "动漫风", "mood": "欢快"}
        info = {"theme": "童年", "style": "动漫风", "mood": "欢快",
                "music_style": "流行", "song_title": "童年时光"}
        (self.test_dir / "metadata" / "base_char.json").write_text(
            json.dumps(bc), encoding="utf-8"
        )
        (self.test_dir / "metadata" / "info.json").write_text(
            json.dumps(info), encoding="utf-8"
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_file_not_found(self):
        analyzer = SceneAnalyzer(str(self.test_dir))
        with self.assertRaises(FileNotFoundError):
            analyzer.analyze("nonexistent.srt")

    def test_full_analyze_local(self):
        """纯本地模式（无 LLM 调用）"""
        lines_data = [
            (0.0, 4.0, "今天天气真好"),
            (4.5, 8.0, "我们一起出去玩"),
            (8.5, 12.0, "看那美丽的花朵"),
            (12.5, 16.0, "副歌副歌"),
            (16.5, 20.0, "继续前行"),
            (20.5, 24.0, "副歌副歌"),
            (24.5, 28.0, "慢慢告别"),
            (28.5, 32.0, "尾声"),
        ]
        srt_path = self.test_dir / "song.srt"
        make_test_srt(lines_data, srt_path)

        analyzer = SceneAnalyzer(str(self.test_dir))
        result = analyzer.analyze(str(srt_path))

        self.assertIn("scenes", result)
        self.assertIn("scene_count", result)
        self.assertGreater(result["scene_count"], 0)
        self.assertIn("total_duration", result)

        scenes = result["scenes"]
        for s in scenes:
            self.assertIn("id", s)
            self.assertIn("name", s)
            self.assertIn("label", s)
            self.assertIn("desc", s)
            self.assertIn("start", s)
            self.assertIn("end", s)
            self.assertIn("duration", s)
            self.assertIn("text_preview", s)
            self.assertIn("is_repeated", s)
            self.assertIn("segment_count", s)
            self.assertGreater(s["duration"], 0)
            self.assertGreater(len(s["desc"]), 30)

        # scenes.json 已写入
        scenes_json = self.test_dir / "metadata" / "scenes.json"
        self.assertTrue(scenes_json.exists())

        loaded = json.loads(scenes_json.read_text(encoding="utf-8"))
        self.assertEqual(len(loaded), result["scene_count"])

    def test_repeated_scenes_have_variants(self):
        """重复段应有 variants 字段"""
        lines_data = [
            (0.0, 4.0, "主歌"),
            (4.5, 15.0, "副歌副歌副歌"),  # 重复且 > 4s
            (15.5, 19.0, "主歌2"),
            (19.5, 30.0, "副歌副歌副歌"),  # 重复
            (30.5, 34.0, "尾声"),
        ]
        srt_path = self.test_dir / "song.srt"
        make_test_srt(lines_data, srt_path)

        analyzer = SceneAnalyzer(str(self.test_dir))
        result = analyzer.analyze(str(srt_path))

        for s in result["scenes"]:
            if s.get("is_repeated"):
                self.assertIn("variants", s)

    def test_local_variant_on_llm_failure(self):
        """LLM 失败时使用本地变体"""
        lines_data = [
            (0.0, 4.0, "主歌"),
            (4.5, 15.0, "副歌副歌"),
            (15.5, 30.0, "副歌副歌"),
        ]
        srt_path = self.test_dir / "song.srt"
        make_test_srt(lines_data, srt_path)

        analyzer = SceneAnalyzer(str(self.test_dir))
        result = analyzer.analyze(str(srt_path))

        for s in result["scenes"]:
            if s.get("is_repeated"):
                # 至少应该有 variants 列表
                self.assertIsInstance(s.get("variants", []), list)


class TestSceneAnalyzerClean(unittest.TestCase):
    """测试 _clean 工具函数"""

    def test_clean_text(self):
        result = SceneAnalyzer._clean("Hello, World! 你好世界")
        self.assertEqual(result, "HelloWorld你好世界")

    def test_clean_chinese_only(self):
        result = SceneAnalyzer._clean("今天天气真好！")
        self.assertEqual(result, "今天天气真好")


class TestSceneAnalyzerStripThink(unittest.TestCase):
    """测试 _strip_think"""

    def test_strip_think(self):
        raw = "Some text <think>inner thoughts</think> more text"
        result = SceneAnalyzer._strip_think(raw)
        self.assertEqual(result, "Some text  more text")

    def test_no_think_tag(self):
        raw = "just normal text"
        self.assertEqual(SceneAnalyzer._strip_think(raw), "just normal text")


class TestSceneAnalyzerExtractJson(unittest.TestCase):
    """测试 _extract_json_array"""

    def test_extract_json(self):
        raw = 'Here is your result: [{"id": 1, "desc": "hello"}] Thank you'
        result = SceneAnalyzer._extract_json_array(raw)
        self.assertEqual(result, '[{"id": 1, "desc": "hello"}]')

    def test_no_json(self):
        raw = "no json here"
        result = SceneAnalyzer._extract_json_array(raw)
        self.assertEqual(result, "no json here")


if __name__ == "__main__":
    unittest.main()
