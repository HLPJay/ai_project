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
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.exporter import MVExporter, ExporterError


class TestMVExporterInit(unittest.TestCase):
    """测试导出器初始化"""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_exporter_"))
        # 创建必要的子目录
        (self.test_dir / "audio").mkdir()
        (self.test_dir / "clips").mkdir()
        (self.test_dir / "temp").mkdir()
        (self.test_dir / "output").mkdir()
        (self.test_dir / "metadata").mkdir()
        (self.test_dir / "images").mkdir()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_init_basic(self):
        exporter = MVExporter(str(self.test_dir))
        self.assertEqual(exporter.project_dir, self.test_dir)
        self.assertEqual(exporter.ffmpeg, "ffmpeg")
        self.assertEqual(exporter.ffprobe, "ffprobe")

    def test_init_custom_ffmpeg(self):
        exporter = MVExporter(str(self.test_dir), ffmpeg="/usr/bin/ffmpeg")
        self.assertEqual(exporter.ffmpeg, "/usr/bin/ffmpeg")

    def test_init_dirs_created(self):
        """部分目录不存在时应自动创建"""
        (self.test_dir / "temp").rmdir()
        (self.test_dir / "output").rmdir()
        exporter = MVExporter(str(self.test_dir))
        self.assertTrue((self.test_dir / "temp").exists())
        self.assertTrue((self.test_dir / "output").exists())


class TestMVExporterQualityReport(unittest.TestCase):
    """测试质量报告生成"""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_exporter_report_"))
        self._init_dirs()
        self._create_minimal_files()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _init_dirs(self):
        (self.test_dir / "audio").mkdir()
        (self.test_dir / "clips").mkdir()
        (self.test_dir / "output").mkdir()
        (self.test_dir / "metadata").mkdir()
        (self.test_dir / "images").mkdir()

    def _create_minimal_files(self):
        """创建最小的模拟文件"""
        # info.json
        info = {
            "song_title": "测试歌曲",
            "theme": "童年",
            "alignment": {"aligned_lines": 18, "total_lyrics_lines": 20},
            "audio_duration_sec": 120,
            "created_at": "2026-04-30T00:00:00",
        }
        (self.test_dir / "metadata" / "info.json").write_text(
            json.dumps(info, ensure_ascii=False), encoding="utf-8"
        )

        # scenes.json
        scenes = [{"id": 1}, {"id": 2}, {"id": 3}]
        (self.test_dir / "metadata" / "scenes.json").write_text(
            json.dumps(scenes), encoding="utf-8"
        )

    def test_generate_quality_report_basic(self):
        exporter = MVExporter(str(self.test_dir))
        report = exporter.generate_quality_report()

        self.assertEqual(report["song_title"], "测试歌曲")
        self.assertEqual(report["theme"], "童年")
        self.assertEqual(report["alignment_rate"], "18/20 (90%)")
        self.assertEqual(report["scene_count"], 3)
        self.assertEqual(report["audio_duration_sec"], 120)

    def test_quality_report_saved_to_file(self):
        exporter = MVExporter(str(self.test_dir))
        exporter.generate_quality_report()

        report_path = self.test_dir / "metadata" / "quality_report.json"
        self.assertTrue(report_path.exists())

        saved = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["song_title"], "测试歌曲")
        self.assertEqual(saved["alignment_rate"], "18/20 (90%)")

    def test_quality_report_no_info(self):
        """缺少 info.json 时应优雅处理"""
        (self.test_dir / "metadata" / "info.json").unlink()

        exporter = MVExporter(str(self.test_dir))
        report = exporter.generate_quality_report()

        self.assertEqual(report["song_title"], "N/A")

    def test_quality_report_no_alignment(self):
        """没有对齐数据时的处理"""
        info = {"song_title": "测试", "theme": ""}
        (self.test_dir / "metadata" / "info.json").write_text(
            json.dumps(info, ensure_ascii=False), encoding="utf-8"
        )

        exporter = MVExporter(str(self.test_dir))
        report = exporter.generate_quality_report()

        self.assertEqual(report["alignment_rate"], "0/0 (0%)")

    def test_quality_report_no_scenes(self):
        """缺少 scenes.json 时应返回场景数为0"""
        (self.test_dir / "metadata" / "scenes.json").unlink()

        exporter = MVExporter(str(self.test_dir))
        report = exporter.generate_quality_report()

        self.assertEqual(report["scene_count"], 0)


class TestMVExporterErrorHandling(unittest.TestCase):
    """测试错误处理"""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_exporter_err_"))
        self.test_dir.mkdir(exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_concat_no_clips(self):
        """没有视频片段时应返回错误"""
        exporter = MVExporter(str(self.test_dir))
        result = exporter.concat_clips()

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["clip_count"], 0)

    def test_concat_missing_dir(self):
        """clips 目录不存在时应返回错误"""
        exporter = MVExporter(str(self.test_dir))
        result = exporter.concat_clips()

        self.assertEqual(result["status"], "failed")

    def test_merge_no_video_raw(self):
        """没有 video_raw 时应返回错误"""
        exporter = MVExporter(str(self.test_dir))
        result = exporter.merge_audio_subtitles()

        self.assertEqual(result["status"], "failed")
        self.assertIn("video_raw", result.get("error", ""))

    def test_export_no_final(self):
        """没有 final.mp4 时应返回错误"""
        exporter = MVExporter(str(self.test_dir))
        result = exporter.export_versions()

        self.assertEqual(result["status"], "failed")


if __name__ == "__main__":
    unittest.main()
