"""
test_exporter.py — MV 合成导出器测试

覆盖:
  - 初始化与路径配置
  - 导出流程编排
  - 质量报告生成
  - 缺少文件时的错误处理
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.exporter import MVExporter, ExporterError


def _init_exporter_dirs(project_dir: Path):
    for subdir in ("audio", "clips", "temp", "output", "metadata", "images"):
        (project_dir / subdir).mkdir(exist_ok=True)


class TestMVExporterInit:
    """测试导出器初始化"""

    def test_init_basic(self, tmp_path):
        _init_exporter_dirs(tmp_path)
        exporter = MVExporter(str(tmp_path))
        assert exporter.project_dir == tmp_path
        assert exporter.ffmpeg == "ffmpeg"
        assert exporter.ffprobe == "ffprobe"

    def test_init_custom_ffmpeg(self, tmp_path):
        _init_exporter_dirs(tmp_path)
        exporter = MVExporter(str(tmp_path), ffmpeg="/usr/bin/ffmpeg")
        assert exporter.ffmpeg == "/usr/bin/ffmpeg"

    def test_init_dirs_created(self, tmp_path):
        """部分目录不存在时应自动创建"""
        _init_exporter_dirs(tmp_path)
        (tmp_path / "temp").rmdir()
        (tmp_path / "output").rmdir()
        exporter = MVExporter(str(tmp_path))
        assert (tmp_path / "temp").exists()
        assert (tmp_path / "output").exists()


class TestMVExporterQualityReport:
    """测试质量报告生成"""

    def _setup_quality_report_project(self, project_dir: Path):
        """创建质量报告测试所需的标准项目结构"""
        _init_exporter_dirs(project_dir)
        info = {
            "song_title": "测试歌曲",
            "theme": "童年",
            "alignment": {"aligned_lines": 18, "total_lyrics_lines": 20},
            "audio_duration_sec": 120,
            "created_at": "2026-04-30T00:00:00",
        }
        (project_dir / "metadata" / "info.json").write_text(
            json.dumps(info, ensure_ascii=False), encoding="utf-8"
        )
        scenes = [{"id": 1}, {"id": 2}, {"id": 3}]
        (project_dir / "metadata" / "scenes.json").write_text(
            json.dumps(scenes), encoding="utf-8"
        )

    def test_generate_quality_report_basic(self, tmp_path):
        self._setup_quality_report_project(tmp_path)
        exporter = MVExporter(str(tmp_path))
        report = exporter.generate_quality_report()

        assert report["song_title"] == "测试歌曲"
        assert report["theme"] == "童年"
        assert report["alignment_rate"] == "18/20 (90%)"
        assert report["scene_count"] == 3
        assert report["audio_duration_sec"] == 120

    def test_quality_report_saved_to_file(self, tmp_path):
        self._setup_quality_report_project(tmp_path)
        exporter = MVExporter(str(tmp_path))
        exporter.generate_quality_report()

        report_path = tmp_path / "metadata" / "quality_report.json"
        final_report_path = tmp_path / "output" / "final_report.json"
        assert report_path.exists()
        assert final_report_path.exists()

        saved = json.loads(report_path.read_text(encoding="utf-8"))
        assert saved["song_title"] == "测试歌曲"
        assert saved["alignment_rate"] == "18/20 (90%)"

    def test_quality_report_accepts_total_lines(self, tmp_path):
        self._setup_quality_report_project(tmp_path)
        info = {
            "song_title": "测试歌曲",
            "theme": "童年",
            "alignment": {"aligned_lines": 18, "total_lines": 20},
            "audio_duration_sec": 120,
        }
        (tmp_path / "metadata" / "info.json").write_text(
            json.dumps(info, ensure_ascii=False), encoding="utf-8"
        )
        exporter = MVExporter(str(tmp_path))
        report = exporter.generate_quality_report()
        assert report["alignment_rate"] == "18/20 (90%)"

    def test_quality_report_no_info(self, tmp_path):
        """缺少 info.json 时应优雅处理"""
        self._setup_quality_report_project(tmp_path)
        (tmp_path / "metadata" / "info.json").unlink()
        exporter = MVExporter(str(tmp_path))
        report = exporter.generate_quality_report()
        assert report["song_title"] == "N/A"

    def test_quality_report_no_alignment(self, tmp_path):
        """没有对齐数据时的处理"""
        self._setup_quality_report_project(tmp_path)
        info = {"song_title": "测试", "theme": ""}
        (tmp_path / "metadata" / "info.json").write_text(
            json.dumps(info, ensure_ascii=False), encoding="utf-8"
        )
        exporter = MVExporter(str(tmp_path))
        report = exporter.generate_quality_report()
        assert report["alignment_rate"] == "0/0 (0%)"

    def test_quality_report_no_scenes(self, tmp_path):
        """缺少 scenes.json 时应返回场景数为0"""
        self._setup_quality_report_project(tmp_path)
        (tmp_path / "metadata" / "scenes.json").unlink()
        exporter = MVExporter(str(tmp_path))
        report = exporter.generate_quality_report()
        assert report["scene_count"] == 0


class TestMVExporterErrorHandling:
    """测试错误处理"""

    def test_concat_no_clips(self, tmp_path):
        """没有视频片段时应返回错误"""
        exporter = MVExporter(str(tmp_path))
        result = exporter.concat_clips()
        assert result["status"] == "failed"
        assert result["clip_count"] == 0

    def test_concat_missing_dir(self, tmp_path):
        """clips 目录不存在时应返回错误"""
        exporter = MVExporter(str(tmp_path))
        result = exporter.concat_clips()
        assert result["status"] == "failed"

    def test_merge_no_video_raw(self, tmp_path):
        """没有 video_raw 时应返回错误"""
        exporter = MVExporter(str(tmp_path))
        result = exporter.merge_audio_subtitles()
        assert result["status"] == "failed"
        assert "video_raw" in result.get("error", "")

    def test_export_no_final(self, tmp_path):
        """没有 final.mp4 时应返回错误"""
        exporter = MVExporter(str(tmp_path))
        result = exporter.export_versions()
        assert result["status"] == "failed"


if __name__ == "__main__":
    import unittest
    unittest.main()
