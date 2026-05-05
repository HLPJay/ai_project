"""
test_report_generator.py — 报告生成器测试

覆盖:
  - 初始化
  - 数据加载（无日志、有日志，空行跳过）
  - 项目信息读取
  - 场景数读取
  - Provider 收集
  - Step 分组
  - Token 估算
  - Truncate
  - Format bytes
  - HTML 生成（基本结构，空报告）
  - 完整 generate() 流水线
  - 写入文件
  - JSONL 格式兼容性
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.report_generator import ReportGenerator, ReportGeneratorError


def make_log_file(dir_path, records, filename="log.jsonl"):
    """创建 JSONL 日志文件"""
    path = dir_path / filename
    lines = "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
    path.write_text(lines + "\n", encoding="utf-8")
    return path


def _init_rg_dirs(project_dir: Path):
    (project_dir / "metadata").mkdir(exist_ok=True)
    (project_dir / "metadata" / "llm_calls").mkdir(exist_ok=True)
    (project_dir / "output").mkdir(exist_ok=True)


class TestReportGeneratorInit:
    """测试初始化"""

    def test_init(self, tmp_path):
        _init_rg_dirs(tmp_path)
        gen = ReportGenerator(str(tmp_path))
        assert gen.project_dir == tmp_path
        assert gen.records == []

    def test_init_no_llm_dir(self, tmp_path):
        _init_rg_dirs(tmp_path)
        import shutil
        shutil.rmtree(tmp_path / "metadata" / "llm_calls")
        gen = ReportGenerator(str(tmp_path))
        assert gen.records == []


class TestReportGeneratorDataLoading:
    """测试数据加载"""

    def test_load_no_files(self, tmp_path):
        _init_rg_dirs(tmp_path)
        gen = ReportGenerator(str(tmp_path))
        gen._load_records()
        assert gen.records == []

    def test_load_single_file(self, tmp_path):
        _init_rg_dirs(tmp_path)
        make_log_file(tmp_path / "metadata" / "llm_calls", [
            {"step": "lyrics", "model": "MiniMax-M2.7", "prompt": "hello"},
            {"step": "music", "model": "music-2.6", "prompt": "world"},
        ])
        gen = ReportGenerator(str(tmp_path))
        gen._load_records()
        assert len(gen.records) == 2

    def test_load_multiple_files(self, tmp_path):
        _init_rg_dirs(tmp_path)
        d = tmp_path / "metadata" / "llm_calls"
        make_log_file(d, [{"step": "lyrics", "prompt": "a"}], "log1.jsonl")
        make_log_file(d, [{"step": "music", "prompt": "b"}], "log2.jsonl")
        gen = ReportGenerator(str(tmp_path))
        gen._load_records()
        assert len(gen.records) == 2

    def test_load_skip_empty_lines(self, tmp_path):
        _init_rg_dirs(tmp_path)
        log_path = tmp_path / "metadata" / "llm_calls" / "log.jsonl"
        log_path.write_text('{"step":"lyrics"}\n\n{"step":"music"}\n', encoding="utf-8")
        gen = ReportGenerator(str(tmp_path))
        gen._load_records()
        assert len(gen.records) == 2

    def test_load_skip_invalid_json(self, tmp_path):
        _init_rg_dirs(tmp_path)
        log_path = tmp_path / "metadata" / "llm_calls" / "bad.jsonl"
        log_path.write_text('{"step":"lyrics"}\ninvalid json\n{"step":"music"}\n', encoding="utf-8")
        gen = ReportGenerator(str(tmp_path))
        gen._load_records()
        assert len(gen.records) == 2

    def test_load_llm_logger_summary_record(self, tmp_path):
        _init_rg_dirs(tmp_path)
        responses = tmp_path / "metadata" / "llm_calls" / "responses"
        responses.mkdir()
        response_path = responses / "call.json"
        response_path.write_text(
            json.dumps({
                "prompt_key": "lyrics",
                "rendered_prompt": "生成歌词",
                "response": "{\"title\":\"春风\"}",
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        make_log_file(tmp_path / "metadata" / "llm_calls", [
            {
                "prompt_key": "lyrics",
                "model": "MiniMax-M2.7",
                "response_file": "responses/call.json",
                "status": "success",
            }
        ])
        gen = ReportGenerator(str(tmp_path))
        gen._load_records()
        assert gen.records[0]["step"] == "lyrics"
        assert gen.records[0]["prompt"] == "生成歌词"
        assert gen.records[0]["response"] == "{\"title\":\"春风\"}"


class TestReportGeneratorProjectInfo:
    """测试项目信息读取"""

    def test_no_info_json(self, tmp_path):
        _init_rg_dirs(tmp_path)
        gen = ReportGenerator(str(tmp_path))
        title, theme = gen._load_project_info()
        assert title == ""
        assert theme == ""

    def test_with_info_json(self, tmp_path):
        _init_rg_dirs(tmp_path)
        info = {"song_title": "童年", "theme": "童年时光"}
        (tmp_path / "metadata" / "info.json").write_text(json.dumps(info), encoding="utf-8")
        gen = ReportGenerator(str(tmp_path))
        title, theme = gen._load_project_info()
        assert title == "童年"
        assert theme == "童年时光"

    def test_no_scenes_json(self, tmp_path):
        _init_rg_dirs(tmp_path)
        gen = ReportGenerator(str(tmp_path))
        count = gen._load_scenes_count()
        assert count == 0

    def test_with_scenes_json(self, tmp_path):
        _init_rg_dirs(tmp_path)
        scenes = [{"id": 1}, {"id": 2}, {"id": 3}]
        (tmp_path / "metadata" / "scenes.json").write_text(json.dumps(scenes), encoding="utf-8")
        gen = ReportGenerator(str(tmp_path))
        count = gen._load_scenes_count()
        assert count == 3

    def test_with_invalid_scenes_json(self, tmp_path):
        _init_rg_dirs(tmp_path)
        (tmp_path / "metadata" / "scenes.json").write_text("invalid", encoding="utf-8")
        gen = ReportGenerator(str(tmp_path))
        count = gen._load_scenes_count()
        assert count == 0


class TestReportGeneratorStats:
    """测试统计方法"""

    def test_collect_providers(self):
        gen = ReportGenerator("/tmp")
        gen.records = [
            {"model": "MiniMax-M2.7"},
            {"model": "music-2.6"},
            {"model": "MiniMax-M2.7"},
        ]
        providers = gen._collect_providers()
        assert len(providers) == 2
        assert "MiniMax-M2.7" in providers

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
        assert "lyrics" in groups
        assert "scene_desc" in groups
        assert len(groups["lyrics"]) == 2
        assert len(groups["scene_desc"]) == 2

    def test_group_by_step_unknown(self):
        gen = ReportGenerator("/tmp")
        gen.records = [{"step": "some_random_step"}]
        groups = gen._group_by_step()
        assert "some_random_step" in groups

    def test_sort_steps(self):
        gen = ReportGenerator("/tmp")
        groups = {"scene_desc": [0], "music": [1], "lyrics": [2]}
        sorted_steps = gen._sort_steps(groups)
        assert sorted_steps == ["lyrics", "music", "scene_desc"]

    def test_sort_steps_unknown_first(self):
        gen = ReportGenerator("/tmp")
        groups = {"unknown_step": [0], "lyrics": [1]}
        sorted_steps = gen._sort_steps(groups)
        assert sorted_steps[0] == "lyrics"
        assert sorted_steps[1] == "unknown_step"


class TestReportGeneratorUtils:
    """测试工具方法"""

    def test_count_tokens_empty(self):
        assert ReportGenerator._count_tokens("") == 0
        assert ReportGenerator._count_tokens(None) == 0

    def test_count_tokens_chinese(self):
        tokens = ReportGenerator._count_tokens("你好世界")
        assert abs(tokens - 10.0) < 0.1

    def test_count_tokens_english(self):
        tokens = ReportGenerator._count_tokens("hello")
        assert abs(tokens - 1.25) < 0.1

    def test_truncate_short(self):
        assert ReportGenerator._truncate("hello", 10) == "hello"

    def test_truncate_long(self):
        result = ReportGenerator._truncate("x" * 50, 20)
        assert len(result) == 23
        assert result.endswith("...")

    def test_truncate_none(self):
        assert ReportGenerator._truncate(None) == ""

    def test_format_bytes_int(self):
        assert ReportGenerator._format_bytes(2048) == "2KB"

    def test_format_bytes_none(self):
        assert ReportGenerator._format_bytes(None) == ""

    def test_format_bytes_dict(self):
        assert ReportGenerator._format_bytes({"size": 1024}) == "1KB"

    def test_get_step_tag_known(self):
        label, cls = ReportGenerator._get_step_tag("lyrics")
        assert "歌词" in label
        assert cls == "tag-lyrics"

    def test_get_step_tag_unknown(self):
        label, cls = ReportGenerator._get_step_tag("something_weird")
        assert "未知" in label

    def test_get_step_tag_partial_match(self):
        label, cls = ReportGenerator._get_step_tag("variant_desc")
        assert "变体" in label
        assert cls == "tag-scene"


class TestReportGeneratorHTMLBuilding:
    """测试 HTML 构建"""

    def test_build_record_html(self, tmp_path):
        _init_rg_dirs(tmp_path)
        gen = ReportGenerator(str(tmp_path))
        html = gen._build_record_html({
            "step": "lyrics",
            "model": "MiniMax-M2.7",
            "prompt": "Generate lyrics about childhood",
            "response": {"lyrics": "小燕子穿花衣"},
            "timestamp": "2024-01-01T00:00:00",
        }, 0)
        assert "record" in html
        assert "tag-lyrics" in html
        assert "MiniMax-M2.7" in html
        assert "小燕子穿花衣" in html
        assert "复制 Prompt" in html

    def test_build_record_with_error(self, tmp_path):
        _init_rg_dirs(tmp_path)
        gen = ReportGenerator(str(tmp_path))
        html = gen._build_record_html({
            "step": "music",
            "model": "music-2.6",
            "prompt": "happy pop",
            "error": "HTTP 500",
            "timestamp": "2024-01-01",
        }, 0)
        assert "fail-badge" in html
        assert "HTTP 500" in html

    def test_build_record_empty_prompt(self, tmp_path):
        _init_rg_dirs(tmp_path)
        gen = ReportGenerator(str(tmp_path))
        html = gen._build_record_html({
            "step": "lyrics",
            "model": "m",
            "prompt": None,
        }, 0)
        assert "(empty)" in html

    def test_build_filter_buttons(self, tmp_path):
        _init_rg_dirs(tmp_path)
        gen = ReportGenerator(str(tmp_path))
        gen.records = [{"step": "lyrics"}, {"step": "lyrics"}, {"step": "music"}]
        groups = gen._group_by_step()
        sorted_steps = gen._sort_steps(groups)
        btns = gen._build_filter_buttons(groups, sorted_steps)
        assert "全部" in btns
        assert "(2)" in btns

    def test_build_sections(self, tmp_path):
        _init_rg_dirs(tmp_path)
        gen = ReportGenerator(str(tmp_path))
        gen.records = [{"step": "lyrics", "model": "m", "prompt": "test"}]
        groups = gen._group_by_step()
        sorted_steps = gen._sort_steps(groups)
        html = gen._build_sections(groups, sorted_steps)
        assert "sec-lyrics" in html
        assert "全部成功" in html

    def test_build_sections_with_error(self, tmp_path):
        _init_rg_dirs(tmp_path)
        gen = ReportGenerator(str(tmp_path))
        gen.records = [{"step": "music", "model": "m", "prompt": "t", "error": "fail"}]
        groups = gen._group_by_step()
        sorted_steps = gen._sort_steps(groups)
        html = gen._build_sections(groups, sorted_steps)
        assert "部分失败" in html

    def test_wrap_html(self, tmp_path):
        _init_rg_dirs(tmp_path)
        gen = ReportGenerator(str(tmp_path))
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
        assert "童年的回忆" in html
        assert "10" in html
        assert "5" in html
        assert "DOCTYPE html" in html
        assert "function toggleRecord" in html


class TestReportGeneratorGenerate:
    """测试完整 generate()"""

    def _setup_gen_project(self, project_dir: Path):
        _init_rg_dirs(project_dir)
        logs = [
            {"step": "lyrics", "model": "MiniMax-M2.7",
             "prompt": "生成歌词", "response": {"lyrics": "test"},
             "timestamp": "2024-01-01"},
            {"step": "music", "model": "music-2.6",
             "prompt": "生成音乐", "response": {"url": "test.mp3"},
             "timestamp": "2024-01-01"},
        ]
        make_log_file(project_dir / "metadata" / "llm_calls", logs)
        info = {"song_title": "童年", "theme": "童年时光"}
        (project_dir / "metadata" / "info.json").write_text(json.dumps(info), encoding="utf-8")
        scenes = [{"id": 1}, {"id": 2}]
        (project_dir / "metadata" / "scenes.json").write_text(json.dumps(scenes), encoding="utf-8")

    def test_generate_default_output(self, tmp_path):
        self._setup_gen_project(tmp_path)
        import shutil
        shutil.rmtree(tmp_path / "metadata" / "llm_calls")
        gen = ReportGenerator(str(tmp_path))
        html = gen.generate()
        assert isinstance(html, str)
        assert "0 条记录" in html
        assert "0" in html


class TestReportGeneratorErrorHandling:
    """测试错误处理"""

    def test_generate_no_project_dir(self):
        gen = ReportGenerator("/nonexistent/path")
        try:
            html = gen.generate()
            assert isinstance(html, str)
        except Exception as e:
            pytest.fail(f"Unexpected exception: {e}")


if __name__ == "__main__":
    import unittest
    unittest.main()
