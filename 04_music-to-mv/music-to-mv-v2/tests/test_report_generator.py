"""
test_report_generator.py — 报告生成器测试

覆盖:
  - 初始化
  - 数据加载（无日志、有日志、空行跳过）
  - 项目信息读取
  - 场景数读取
  - Provider 收集
  - Step 分组
  - Token 估算
  - Truncate
  - Format bytes
  - HTML 生成（基本结构、空报告）
  - 完整 generate() 流水线
  - 写入文件
  - JSONL 格式兼容性
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.report_generator import ReportGenerator, ReportGeneratorError


def make_log_file(dir_path, records, filename="log.jsonl"):
    """创建 JSONL 日志文件"""
    path = dir_path / filename
    lines = "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
    path.write_text(lines + "\n", encoding="utf-8")
    return path


class TestReportGeneratorInit(unittest.TestCase):
    """测试初始化"""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_rpt_init_"))
        (self.test_dir / "metadata").mkdir()
        (self.test_dir / "metadata" / "llm_calls").mkdir()
        (self.test_dir / "output").mkdir()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_init(self):
        gen = ReportGenerator(str(self.test_dir))
        self.assertEqual(gen.project_dir, self.test_dir)
        self.assertEqual(gen.records, [])

    def test_init_no_llm_dir(self):
        """没有 llm_calls 目录也能初始化"""
        shutil.rmtree(self.test_dir / "metadata" / "llm_calls")
        gen = ReportGenerator(str(self.test_dir))
        self.assertEqual(gen.records, [])


class TestReportGeneratorDataLoading(unittest.TestCase):
    """测试数据加载"""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_rpt_load_"))
        (self.test_dir / "metadata" / "llm_calls").mkdir(parents=True)
        (self.test_dir / "output").mkdir()
        self.gen = ReportGenerator(str(self.test_dir))

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_load_no_files(self):
        self.gen._load_records()
        self.assertEqual(self.gen.records, [])

    def test_load_single_file(self):
        make_log_file(self.test_dir / "metadata" / "llm_calls", [
            {"step": "lyrics", "model": "MiniMax-M2.7", "prompt": "hello"},
            {"step": "music", "model": "music-2.6", "prompt": "world"},
        ])
        self.gen._load_records()
        self.assertEqual(len(self.gen.records), 2)

    def test_load_multiple_files(self):
        d = self.test_dir / "metadata" / "llm_calls"
        make_log_file(d, [{"step": "lyrics", "prompt": "a"}], "log1.jsonl")
        make_log_file(d, [{"step": "music", "prompt": "b"}], "log2.jsonl")
        self.gen._load_records()
        self.assertEqual(len(self.gen.records), 2)

    def test_load_skip_empty_lines(self):
        make_log_file(self.test_dir / "metadata" / "llm_calls", [
            {"step": "lyrics"},
            None,
        ])
        # 写入一个空行
        log_path = self.test_dir / "metadata" / "llm_calls" / "log.jsonl"
        log_path.write_text('{"step":"lyrics"}\n\n{"step":"music"}\n', encoding="utf-8")
        self.gen._load_records()
        self.assertEqual(len(self.gen.records), 2)

    def test_load_skip_invalid_json(self):
        log_path = self.test_dir / "metadata" / "llm_calls" / "bad.jsonl"
        log_path.write_text('{"step":"lyrics"}\ninvalid json\n{"step":"music"}\n', encoding="utf-8")
        self.gen._load_records()
        self.assertEqual(len(self.gen.records), 2)


class TestReportGeneratorProjectInfo(unittest.TestCase):
    """测试项目信息读取"""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_rpt_info_"))
        (self.test_dir / "metadata").mkdir()
        (self.test_dir / "output").mkdir()
        self.gen = ReportGenerator(str(self.test_dir))

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_no_info_json(self):
        title, theme = self.gen._load_project_info()
        self.assertEqual(title, "")
        self.assertEqual(theme, "")

    def test_with_info_json(self):
        info = {"song_title": "童年", "theme": "童年时光"}
        (self.test_dir / "metadata" / "info.json").write_text(
            json.dumps(info), encoding="utf-8"
        )
        title, theme = self.gen._load_project_info()
        self.assertEqual(title, "童年")
        self.assertEqual(theme, "童年时光")

    def test_no_scenes_json(self):
        count = self.gen._load_scenes_count()
        self.assertEqual(count, 0)

    def test_with_scenes_json(self):
        scenes = [{"id": 1}, {"id": 2}, {"id": 3}]
        (self.test_dir / "metadata" / "scenes.json").write_text(
            json.dumps(scenes), encoding="utf-8"
        )
        count = self.gen._load_scenes_count()
        self.assertEqual(count, 3)

    def test_with_invalid_scenes_json(self):
        (self.test_dir / "metadata" / "scenes.json").write_text(
            "invalid", encoding="utf-8"
        )
        count = self.gen._load_scenes_count()
        self.assertEqual(count, 0)


class TestReportGeneratorStats(unittest.TestCase):
    """测试统计方法"""

    def test_collect_providers(self):
        gen = ReportGenerator("/tmp")
        gen.records = [
            {"model": "MiniMax-M2.7"},
            {"model": "music-2.6"},
            {"model": "MiniMax-M2.7"},
        ]
        providers = gen._collect_providers()
        self.assertEqual(len(providers), 2)
        self.assertIn("MiniMax-M2.7", providers)

    def test_group_by_step(self):
        gen = ReportGenerator("/tmp")
        gen.records = [
            {"step": "lyrics"},
            {"step": "music"},
            {"step": "lyrics"},
            {"step": "scene_desc_batch"},
            {"step": "scene_desc_single"},
        ]
        groups = gen._group_by_step()
        self.assertIn("lyrics", groups)
        self.assertIn("scene_desc", groups)
        self.assertEqual(len(groups["lyrics"]), 2)
        self.assertEqual(len(groups["scene_desc"]), 2)

    def test_group_by_step_unknown(self):
        gen = ReportGenerator("/tmp")
        gen.records = [{"step": "some_random_step"}]
        groups = gen._group_by_step()
        self.assertIn("some_random_step", groups)

    def test_sort_steps(self):
        gen = ReportGenerator("/tmp")
        groups = {"scene_desc": [0], "music": [1], "lyrics": [2]}
        sorted_steps = gen._sort_steps(groups)
        self.assertEqual(sorted_steps, ["lyrics", "music", "scene_desc"])

    def test_sort_steps_unknown_first(self):
        gen = ReportGenerator("/tmp")
        groups = {"unknown_step": [0], "lyrics": [1]}
        sorted_steps = gen._sort_steps(groups)
        self.assertEqual(sorted_steps[0], "lyrics")
        self.assertEqual(sorted_steps[1], "unknown_step")


class TestReportGeneratorUtils(unittest.TestCase):
    """测试工具方法"""

    def test_count_tokens_empty(self):
        self.assertEqual(ReportGenerator._count_tokens(""), 0)
        self.assertEqual(ReportGenerator._count_tokens(None), 0)

    def test_count_tokens_chinese(self):
        # 每个中文字 ≈ 2.5 token
        tokens = ReportGenerator._count_tokens("你好世界")
        self.assertAlmostEqual(tokens, 10.0, places=1)

    def test_count_tokens_english(self):
        # 每个英文字 ≈ 0.25 token
        tokens = ReportGenerator._count_tokens("hello")
        self.assertAlmostEqual(tokens, 1.25, places=1)

    def test_truncate_short(self):
        self.assertEqual(ReportGenerator._truncate("hello", 10), "hello")

    def test_truncate_long(self):
        result = ReportGenerator._truncate("x" * 50, 20)
        self.assertEqual(len(result), 23)  # 20 + ...
        self.assertTrue(result.endswith("..."))

    def test_truncate_none(self):
        self.assertEqual(ReportGenerator._truncate(None), "")

    def test_format_bytes_int(self):
        self.assertEqual(ReportGenerator._format_bytes(2048), "2KB")

    def test_format_bytes_none(self):
        self.assertEqual(ReportGenerator._format_bytes(None), "")

    def test_format_bytes_dict(self):
        self.assertEqual(ReportGenerator._format_bytes({"size": 1024}), "1KB")

    def test_get_step_tag_known(self):
        label, cls = ReportGenerator._get_step_tag("lyrics")
        self.assertIn("歌词", label)
        self.assertEqual(cls, "tag-lyrics")

    def test_get_step_tag_unknown(self):
        label, cls = ReportGenerator._get_step_tag("something_weird")
        self.assertIn("未知", label)

    def test_get_step_tag_partial_match(self):
        """变体描述应匹配 scene"""
        label, cls = ReportGenerator._get_step_tag("variant_desc")
        self.assertIn("变体", label)
        self.assertEqual(cls, "tag-scene")


class TestReportGeneratorHTMLBuilding(unittest.TestCase):
    """测试 HTML 构建"""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_rpt_html_"))
        (self.test_dir / "metadata" / "llm_calls").mkdir(parents=True)
        (self.test_dir / "output").mkdir()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_build_record_html(self):
        gen = ReportGenerator(str(self.test_dir))
        html = gen._build_record_html({
            "step": "lyrics",
            "model": "MiniMax-M2.7",
            "prompt": "Generate lyrics about childhood",
            "response": {"lyrics": "小燕子穿花衣"},
            "timestamp": "2024-01-01T00:00:00",
        }, 0)
        self.assertIn("record", html)
        self.assertIn("tag-lyrics", html)
        self.assertIn("MiniMax-M2.7", html)
        self.assertIn("小燕子穿花衣", html)
        self.assertIn("复制 Prompt", html)

    def test_build_record_with_error(self):
        gen = ReportGenerator(str(self.test_dir))
        html = gen._build_record_html({
            "step": "music",
            "model": "music-2.6",
            "prompt": "happy pop",
            "error": "HTTP 500",
            "timestamp": "2024-01-01",
        }, 0)
        self.assertIn("fail-badge", html)
        self.assertIn("HTTP 500", html)

    def test_build_record_empty_prompt(self):
        gen = ReportGenerator(str(self.test_dir))
        html = gen._build_record_html({
            "step": "lyrics",
            "model": "m",
            "prompt": None,
        }, 0)
        self.assertIn("(empty)", html)

    def test_build_filter_buttons(self):
        gen = ReportGenerator(str(self.test_dir))
        gen.records = [{"step": "lyrics"}, {"step": "lyrics"}, {"step": "music"}]
        groups = gen._group_by_step()
        sorted_steps = gen._sort_steps(groups)
        btns = gen._build_filter_buttons(groups, sorted_steps)
        self.assertIn("全部", btns)
        self.assertIn("(2)", btns)  # lyrics 2条

    def test_build_sections(self):
        gen = ReportGenerator(str(self.test_dir))
        gen.records = [
            {"step": "lyrics", "model": "m", "prompt": "test"},
        ]
        groups = gen._group_by_step()
        sorted_steps = gen._sort_steps(groups)
        html = gen._build_sections(groups, sorted_steps)
        self.assertIn("sec-lyrics", html)
        self.assertIn("全部成功", html)

    def test_build_sections_with_error(self):
        gen = ReportGenerator(str(self.test_dir))
        gen.records = [
            {"step": "music", "model": "m", "prompt": "t", "error": "fail"},
        ]
        groups = gen._group_by_step()
        sorted_steps = gen._sort_steps(groups)
        html = gen._build_sections(groups, sorted_steps)
        self.assertIn("部分失败", html)

    def test_wrap_html(self):
        gen = ReportGenerator(str(self.test_dir))
        html = gen._wrap_html(
            project_name="test_proj",
            song_title="童年的回忆",
            total=10,
            provider_count=3,
            total_tokens=500,
            scenes_count=5,
            filter_btns="<button>全部</button>",
            sections_html="<div>sections</div>",
        )
        self.assertIn("童年的回忆", html)
        self.assertIn("10", html)
        self.assertIn("5", html)
        self.assertIn("DOCTYPE html", html)
        self.assertIn("function toggleRecord", html)


class TestReportGeneratorGenerate(unittest.TestCase):
    """测试完整 generate()"""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_rpt_gen_"))
        (self.test_dir / "metadata" / "llm_calls").mkdir(parents=True)
        (self.test_dir / "output").mkdir()

        # 创建一些日志
        logs = [
            {"step": "lyrics", "model": "MiniMax-M2.7",
             "prompt": "生成歌词", "response": {"lyrics": "test"},
             "timestamp": "2024-01-01"},
            {"step": "music", "model": "music-2.6",
             "prompt": "生成音乐", "response": {"url": "test.mp3"},
             "timestamp": "2024-01-01"},
        ]
        make_log_file(self.test_dir / "metadata" / "llm_calls", logs)

        # 创建项目信息
        info = {"song_title": "童年", "theme": "童年时光"}
        (self.test_dir / "metadata" / "info.json").write_text(
            json.dumps(info), encoding="utf-8"
        )
        scenes = [{"id": 1}, {"id": 2}]
        (self.test_dir / "metadata" / "scenes.json").write_text(
            json.dumps(scenes), encoding="utf-8"
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_generate_default_output(self):
        gen = ReportGenerator(str(self.test_dir))
        html = gen.generate()
        self.assertIsInstance(html, str)
        self.assertIn("童年", html)
        self.assertIn("2 条记录", html)
        self.assertIn("2", html)  # scenes_count
        self.assertIn("MiniMax-M2.7", html)

        # 检查文件是否写入
        output_path = self.test_dir / "output" / "llm_report.html"
        self.assertTrue(output_path.exists())
        written = output_path.read_text(encoding="utf-8")
        self.assertEqual(written, html)

    def test_generate_custom_output(self):
        custom_path = self.test_dir / "custom_report.html"
        gen = ReportGenerator(str(self.test_dir))
        html = gen.generate(str(custom_path))
        self.assertTrue(custom_path.exists())
        self.assertEqual(custom_path.read_text(encoding="utf-8"), html)

    def test_generate_empty(self):
        """无日志文件也能生成报告"""
        shutil.rmtree(self.test_dir / "metadata" / "llm_calls")
        gen = ReportGenerator(str(self.test_dir))
        html = gen.generate()
        self.assertIn("0 条记录", html)
        self.assertIn("0", html)


class TestReportGeneratorErrorHandling(unittest.TestCase):
    """测试错误处理"""

    def test_generate_no_project_dir(self):
        gen = ReportGenerator("/nonexistent/path")
        # 不应抛出异常
        try:
            html = gen.generate()
            self.assertIsInstance(html, str)
        except Exception as e:
            self.fail(f"Unexpected exception: {e}")


if __name__ == "__main__":
    unittest.main()
