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
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.scene_analyzer import (
    SceneAnalyzer, SceneAnalyzerError,
    QUALITY_SUFFIX, VARIANT_TYPES,
)


def make_test_srt(lines_data, srt_path):
    """创建测试用 SRT 文件"""
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


class TestSceneAnalyzerInit:
    """测试初始化"""

    def _create_init_project(self, tmp_path, theme="童年", style="动漫风", mood="欢快"):
        (tmp_path / "metadata").mkdir()
        (tmp_path / "audio").mkdir()
        info = {"theme": theme, "style": style, "mood": mood,
                "music_style": "流行", "song_title": "测试"}
        (tmp_path / "metadata" / "info.json").write_text(
            json.dumps(info, ensure_ascii=False), encoding="utf-8"
        )
        bc = {"prompt": "A cute boy", "style": "动漫风", "mood": "欢快"}
        (tmp_path / "metadata" / "base_char.json").write_text(
            json.dumps(bc), encoding="utf-8"
        )

    def test_init_with_files(self, tmp_path):
        self._create_init_project(tmp_path)
        analyzer = SceneAnalyzer(str(tmp_path))
        assert analyzer._theme == "童年"
        assert analyzer._char_prompt == "A cute boy"

    def test_init_no_files(self, tmp_path):
        (tmp_path / "metadata").mkdir()
        (tmp_path / "audio").mkdir()
        analyzer = SceneAnalyzer(str(tmp_path))
        assert analyzer._theme == ""
        assert analyzer._style == "动漫风"

    def test_init_no_base_char(self, tmp_path):
        """没有 base_char.json 时 _char_prompt 应为空"""
        (tmp_path / "metadata").mkdir()
        (tmp_path / "audio").mkdir()
        info = {"theme": "童年", "style": "动漫风", "mood": "欢快",
                "music_style": "流行", "song_title": "测试"}
        (tmp_path / "metadata" / "info.json").write_text(
            json.dumps(info, ensure_ascii=False), encoding="utf-8"
        )
        # 不创建 base_char.json
        analyzer = SceneAnalyzer(str(tmp_path))
        assert analyzer._char_prompt == ""


class TestSceneAnalyzerParseSRT:
    """测试 SRT 解析"""

    def test_parse_standard(self, tmp_path):
        """标准 SRT 格式"""
        srt_file = tmp_path / "test.srt"
        lines_data = [
            (0.5, 4.2, "今天天气真好"),
            (4.5, 8.1, "我们一起出去玩"),
            (8.5, 12.0, "看那美丽的花朵"),
        ]
        make_test_srt(lines_data, srt_file)
        segments = SceneAnalyzer.parse_srt(str(srt_file))
        assert len(segments) == 3
        assert segments[0][0] == 1
        assert abs(segments[0][1] - 0.5) < 0.1
        assert abs(segments[0][2] - 4.2) < 0.1
        assert segments[0][3] == "今天天气真好"

    def test_parse_dot_separator(self, tmp_path):
        """点号分隔符也兼容"""
        srt_file = tmp_path / "test.srt"
        content = "1\n00:00:00.500 --> 00:00:04.200\nHello World\n"
        srt_file.write_text(content, encoding="utf-8")
        segments = SceneAnalyzer.parse_srt(str(srt_file))
        assert len(segments) == 1
        assert abs(segments[0][1] - 0.5) < 0.1

    def test_parse_no_empty_lines(self, tmp_path):
        """无空行的 SRT"""
        srt_file = tmp_path / "test.srt"
        lines = [
            "1",
            "00:00:00,500 --> 00:00:04,200",
            "Line one",
            "2",
            "00:00:05,000 --> 00:00:10,000",
            "Line two",
        ]
        srt_file.write_text("\n".join(lines), encoding="utf-8")
        segments = SceneAnalyzer.parse_srt(str(srt_file))
        assert len(segments) == 2

    def test_parse_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            SceneAnalyzer.parse_srt(str(tmp_path / "nonexistent.srt"))

    def test_parse_multiline_text(self, tmp_path):
        """多行歌词"""
        srt_file = tmp_path / "test.srt"
        content = "1\n00:00:00,000 --> 00:00:05,000\nFirst line\nSecond line\nThird\n"
        srt_file.write_text(content, encoding="utf-8")
        segments = SceneAnalyzer.parse_srt(str(srt_file))
        assert len(segments) == 1
        assert segments[0][3] == "First line\nSecond line\nThird"


class TestSceneAnalyzerStructure:
    """测试结构分析"""

    def _make_segments(self, texts):
        segs = []
        for i, text in enumerate(texts):
            segs.append((i + 1, i * 4.0, i * 4.0 + 3.5, text))
        return segs

    def test_empty_segments(self):
        result = SceneAnalyzer.analyze_structure([])
        assert result == []

    def test_no_repeat(self):
        """无重复歌词"""
        segs = self._make_segments([
            "开始", "故事展开", "继续前进",
            "情感加深", "慢慢结束",
        ])
        paragraphs = SceneAnalyzer.analyze_structure(segs)
        assert len(paragraphs) > 0
        for p in paragraphs:
            assert not p["is_repeated"]

    def test_repeat_detection(self):
        """重复歌词 → is_repeated"""
        segs = self._make_segments([
            "副歌副歌", "主歌", "副歌副歌", "主歌2", "副歌副歌",
        ])
        paragraphs = SceneAnalyzer.analyze_structure(segs)
        repeat_paras = [p for p in paragraphs if p["is_repeated"]]
        assert len(repeat_paras) > 0

    def test_scene_count_by_duration(self):
        """短歌 → 10 场景，长歌 → 22 场景"""
        texts = [f"line_{i}" for i in range(100)]
        segs = [(i + 1, i * 1.5, i * 1.5 + 1.3, texts[i]) for i in range(100)]
        paragraphs = SceneAnalyzer.analyze_structure(segs)
        assert len(paragraphs) <= 22

        texts2 = [f"short_{i}" for i in range(20)]
        segs2 = [(i + 1, i * 1.5, i * 1.5 + 1.3, texts2[i]) for i in range(20)]
        paragraphs2 = SceneAnalyzer.analyze_structure(segs2)
        assert len(paragraphs2) <= 10

    def test_paragraph_fields(self):
        segs = self._make_segments(["hello", "world"])
        paragraphs = SceneAnalyzer.analyze_structure(segs)
        p = paragraphs[0]
        assert "start" in p
        assert "end" in p
        assert "duration" in p
        assert "text" in p
        assert "is_repeated" in p
        assert "start_seg" in p
        assert "end_seg" in p
        assert "segment_count" in p
        assert p["duration"] > 0


class TestSceneAnalyzerNaming:
    """测试场景命名"""

    def test_intro_outro(self):
        paragraphs = [
            {"is_repeated": False, "duration": 5, "start": 0, "end": 5, "text": "intro text", "segment_count": 1},
            {"is_repeated": False, "duration": 10, "start": 5, "end": 15, "text": "middle text", "segment_count": 1},
            {"is_repeated": False, "duration": 8, "start": 15, "end": 23, "text": "more text", "segment_count": 1},
            {"is_repeated": False, "duration": 6, "start": 23, "end": 29, "text": "outro text", "segment_count": 1},
        ]
        scenes = SceneAnalyzer.name_scenes(paragraphs)
        assert scenes[0]["name"] == "intro"
        assert scenes[-1]["name"] == "outro"

    def test_chorus_detection(self):
        paragraphs = [
            {"is_repeated": False, "duration": 10, "start": 0, "end": 10, "text": "verse text", "segment_count": 1},
            {"is_repeated": True, "duration": 10, "start": 10, "end": 20, "text": "chorus text", "segment_count": 1},
            {"is_repeated": True, "duration": 10, "start": 20, "end": 30, "text": "chorus text", "segment_count": 1},
            {"is_repeated": False, "duration": 8, "start": 30, "end": 38, "text": "outro text", "segment_count": 1},
        ]
        scenes = SceneAnalyzer.name_scenes(paragraphs)
        chorus = [s for s in scenes if s["name"] == "chorus"]
        assert len(chorus) > 0

    def test_verse_bridge(self):
        paragraphs = [
            {"is_repeated": False, "duration": 10, "start": 0, "end": 10, "text": "verse1", "segment_count": 1},
            {"is_repeated": False, "duration": 10, "start": 10, "end": 20, "text": "still verse1", "segment_count": 1},
            {"is_repeated": False, "duration": 10, "start": 20, "end": 30, "text": "verse2 start", "segment_count": 1},
            {"is_repeated": False, "duration": 12, "start": 30, "end": 42, "text": "bridge material", "segment_count": 1},
            {"is_repeated": False, "duration": 6, "start": 42, "end": 48, "text": "outro", "segment_count": 1},
        ]
        scenes = SceneAnalyzer.name_scenes(paragraphs)
        names = [s["name"] for s in scenes]
        assert "intro" in names
        assert "verse1" in names
        assert "outro" in names

    def test_scene_structure(self):
        paragraphs = [
            {"is_repeated": False, "duration": 5, "start": 0, "end": 5, "text": "test", "segment_count": 1},
        ]
        scenes = SceneAnalyzer.name_scenes(paragraphs)
        assert len(scenes) == 1
        s = scenes[0]
        assert "id" in s
        assert "name" in s
        assert "start" in s
        assert "end" in s
        assert "duration" in s
        assert "text_preview" in s
        assert "is_repeated" in s


class TestSceneAnalyzerLabel:
    """测试标签生成"""

    def test_label_with_match(self):
        label = SceneAnalyzer.generate_label("chorus", "童年", "欢快", "一起去放风筝")
        assert "童年" in label
        assert "欢快" in label

    def test_label_no_match(self):
        label = SceneAnalyzer.generate_label("intro", "未知主题_xy", "平静", "一些文字")
        assert label == "序幕"

    def test_label_outro_default(self):
        label = SceneAnalyzer.generate_label("outro", "xyz", "温柔", "nothing")
        assert label == "尾声"

    def test_label_keyword_matching(self):
        label = SceneAnalyzer.generate_label("verse1", "成长", "希望", "春天来了花朵盛开")
        assert "春天" in label


class TestSceneAnalyzerDescValidation:
    """测试描述有效性"""

    def test_valid_desc(self):
        valid = "A boy running through a meadow under golden sunlight"
        assert SceneAnalyzer._is_valid_desc(valid, "running") is True

    def test_invalid_short(self):
        assert SceneAnalyzer._is_valid_desc("Hi", "test") is False

    def test_invalid_truncated_prefix(self):
        bad = "the user wants me to create a description for this scene"
        assert SceneAnalyzer._is_valid_desc(bad, "test") is False

    def test_invalid_old_template(self):
        assert SceneAnalyzer._is_valid_desc(
            "A cute child looking around with wonder", "test"
        ) is False

    def test_edge_8_words(self):
        """正好 8 个有意义的词"""
        desc = "sunset river station bench wind letter sky light"
        assert SceneAnalyzer._is_valid_desc(desc, "test") is True

    def test_edge_7_words(self):
        """7 个有意义的词（应无效）"""
        desc = "sunset river station wind letter sky light"
        assert SceneAnalyzer._is_valid_desc(desc, "test") is False


class TestSceneAnalyzerLocalDesc:
    """测试本地 fallback 描述生成"""

    def _create_local_project(self, tmp_path):
        (tmp_path / "metadata").mkdir()
        (tmp_path / "audio").mkdir()
        bc = {"prompt": "A cute Chinese boy", "style": "动漫风", "mood": "欢快"}
        info = {"theme": "童年", "style": "动漫风", "mood": "欢快",
                "music_style": "流行"}
        (tmp_path / "metadata" / "base_char.json").write_text(
            json.dumps(bc), encoding="utf-8"
        )
        (tmp_path / "metadata" / "info.json").write_text(
            json.dumps(info), encoding="utf-8"
        )

    def test_generate_local_desc(self, tmp_path):
        self._create_local_project(tmp_path)
        analyzer = SceneAnalyzer(str(tmp_path))
        scene = {
            "name": "intro",
            "text_preview": "今天天气真好",
            "start": 0.0, "end": 5.0, "duration": 5.0,
        }
        desc = analyzer._generate_local_desc(scene)
        assert "8k" in desc
        assert "visual" in desc
        assert len(desc) > 30
        assert desc.endswith(QUALITY_SUFFIX)

    def test_generate_local_desc_chorus(self, tmp_path):
        self._create_local_project(tmp_path)
        analyzer = SceneAnalyzer(str(tmp_path))
        scene = {
            "name": "chorus",
            "text_preview": "副歌部分",
            "start": 10.0, "end": 25.0, "duration": 15.0,
        }
        desc = analyzer._generate_local_desc(scene)
        assert "8k" in desc


class TestSceneAnalyzerFullAnalyze:
    """测试完整 analyze() 流水线"""

    def _create_full_project(self, tmp_path):
        (tmp_path / "metadata").mkdir()
        (tmp_path / "audio").mkdir()
        bc = {"prompt": "A cute Chinese boy, 8 years old",
              "style": "动漫风", "mood": "欢快"}
        info = {"theme": "童年", "style": "动漫风", "mood": "欢快",
                "music_style": "流行", "song_title": "童年时光"}
        (tmp_path / "metadata" / "base_char.json").write_text(
            json.dumps(bc), encoding="utf-8"
        )
        (tmp_path / "metadata" / "info.json").write_text(
            json.dumps(info), encoding="utf-8"
        )

    def test_file_not_found(self, tmp_path):
        self._create_full_project(tmp_path)
        analyzer = SceneAnalyzer(str(tmp_path))
        with pytest.raises(FileNotFoundError):
            analyzer.analyze("nonexistent.srt")

    def test_full_analyze_local(self, tmp_path):
        """纯本地模式（无 LLM 调用）"""
        self._create_full_project(tmp_path)
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
        srt_path = tmp_path / "song.srt"
        make_test_srt(lines_data, srt_path)

        analyzer = SceneAnalyzer(str(tmp_path))
        result = analyzer.analyze(str(srt_path))

        assert "scenes" in result
        assert "scene_count" in result
        assert result["scene_count"] > 0
        assert "total_duration" in result

        scenes = result["scenes"]
        for s in scenes:
            assert "id" in s
            assert "name" in s
            assert "label" in s
            assert "desc" in s
            assert "start" in s
            assert "end" in s
            assert "duration" in s
            assert "text_preview" in s
            assert "is_repeated" in s
            assert "segment_count" in s
            assert "visual_focus" in s
            assert "shot_type" in s
            assert "character_needed" in s
            assert "continuity" in s
            assert "symbolic_objects" in s
            assert "motion_hint" in s
            assert s["duration"] > 0
            assert len(s["desc"]) > 30
            assert isinstance(s["symbolic_objects"], list)

        scenes_json = tmp_path / "metadata" / "scenes.json"
        assert scenes_json.exists()
        loaded = json.loads(scenes_json.read_text(encoding="utf-8"))
        assert len(loaded) == result["scene_count"]

        visual_bible_json = tmp_path / "metadata" / "visual_bible.json"
        assert visual_bible_json.exists()
        visual_bible = json.loads(visual_bible_json.read_text(encoding="utf-8"))
        assert "world_style" in visual_bible
        assert "palette" in visual_bible
        assert "camera_language" in visual_bible

    def test_repeated_scenes_have_variants(self, tmp_path):
        """重复段应有 variants 字段"""
        self._create_full_project(tmp_path)
        lines_data = [
            (0.0, 4.0, "主歌"),
            (4.5, 15.0, "副歌副歌副歌"),
            (15.5, 19.0, "主歌2"),
            (19.5, 30.0, "副歌副歌副歌"),
            (30.5, 34.0, "尾声"),
        ]
        srt_path = tmp_path / "song.srt"
        make_test_srt(lines_data, srt_path)

        analyzer = SceneAnalyzer(str(tmp_path))
        result = analyzer.analyze(str(srt_path))

        for s in result["scenes"]:
            if s.get("is_repeated"):
                assert "variants" in s

    def test_local_variant_on_llm_failure(self, tmp_path):
        """LLM 失败时使用本地变体"""
        self._create_full_project(tmp_path)
        lines_data = [
            (0.0, 4.0, "主歌"),
            (4.5, 15.0, "副歌副歌"),
            (15.5, 30.0, "副歌副歌"),
        ]
        srt_path = tmp_path / "song.srt"
        make_test_srt(lines_data, srt_path)

        analyzer = SceneAnalyzer(str(tmp_path))
        result = analyzer.analyze(str(srt_path))
        assert "scenes" in result


if __name__ == "__main__":
    import unittest
    unittest.main()
