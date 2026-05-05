"""
test_ken_burns.py — Ken Burns 生成器测试

覆盖:
  - 单图 KB 生成（需要 ffmpeg）
  - 场景级批量处理（需要场景文件）
  - 参数配置验证
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.ken_burns import KenBurnsGenerator, KenBurnsError


class TestKenBurnsConfig:
    """测试 Ken Burns 配置和参数"""

    def test_init_defaults(self):
        kb = KenBurnsGenerator()
        assert kb.fps == 25
        assert kb.ffmpeg == "ffmpeg"

    def test_init_custom(self):
        kb = KenBurnsGenerator(fps=30, ffmpeg_path="/usr/bin/ffmpeg")
        assert kb.fps == 30
        assert kb.ffmpeg == "/usr/bin/ffmpeg"


def _make_dummy_png(path: Path):
    """创建一个最小有效 PNG 文件（1x1 像素）"""
    import struct
    import zlib

    def _chunk(chunk_type, data):
        c = chunk_type + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    signature = b'\x89PNG\r\n\x1a\n'
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr = _chunk(b'IHDR', ihdr_data)
    raw_data = b'\x00\xff\x00\x00'
    idat_data = zlib.compress(raw_data)
    idat = _chunk(b'IDAT', idat_data)
    iend = _chunk(b'IEND', b'')
    path.write_bytes(signature + ihdr + idat + iend)


def _setup_kb_project(tmp_path):
    """创建标准 KB 测试项目结构"""
    metadata_dir = tmp_path / "metadata"
    images_dir = tmp_path / "images"
    clips_dir = tmp_path / "clips"
    metadata_dir.mkdir()
    images_dir.mkdir()
    clips_dir.mkdir()

    scenes = [
        {"id": 1, "label": "intro", "duration": 10,
         "desc": "A beautiful sunset", "style": "动漫风", "mood": "宁静"},
        {"id": 2, "label": "verse1", "duration": 15,
         "desc": "A child running", "style": "动漫风", "mood": "欢快"},
    ]
    (metadata_dir / "scenes.json").write_text(json.dumps(scenes, ensure_ascii=False), encoding="utf-8")
    _make_dummy_png(images_dir / "seg1_scene.png")
    _make_dummy_png(images_dir / "seg2_scene.png")
    return metadata_dir, images_dir, clips_dir


class TestKenBurnsProcessing:
    """测试 KB 处理逻辑（不实际生成视频）"""

    def test_process_project_no_images(self, tmp_path):
        """处理无图片的项目应标记为 skipped"""
        metadata_dir, images_dir, _ = _setup_kb_project(tmp_path)
        for f in images_dir.glob("*"):
            f.unlink()

        kb = KenBurnsGenerator()
        result = kb.process_project(str(tmp_path))

        assert result["total"] == 2
        assert result["succeeded"] == 0
        assert result["failed"] == 0
        assert len(result["skipped"]) == 2

    def test_process_project_no_metadata(self, tmp_path):
        """缺少 scenes.json 时应出错"""
        metadata_dir, _, _ = _setup_kb_project(tmp_path)
        (metadata_dir / "scenes.json").unlink()

        kb = KenBurnsGenerator()
        with pytest.raises(FileNotFoundError):
            kb.process_project(str(tmp_path))

    def test_process_project_with_variants(self, tmp_path):
        """测试变体图片场景"""
        metadata_dir, images_dir, _ = _setup_kb_project(tmp_path)
        variants = {"variant_scenes": {1: 2}}
        (metadata_dir / "variants.json").write_text(json.dumps(variants, ensure_ascii=False))
        _make_dummy_png(images_dir / "seg1_variant1.png")

        kb = KenBurnsGenerator()
        result = kb.process_project(str(tmp_path))

        assert result["total"] == 2
        assert "succeeded" in result

    def test_zoom_range_parsing(self, tmp_path):
        """测试 zoom_range 字符串解析"""
        _setup_kb_project(tmp_path)

        kb = KenBurnsGenerator()
        result = kb.process_project(
            str(tmp_path),
            zoom_range="1.0-1.3",
            sharpen="5:5:0.8:3:3:0.4",
            transition_ratio=0.25,
            min_img_dur=6.0,
        )
        assert "total" in result

    def test_generate_scene_no_image(self, tmp_path):
        """不存在的图片应返回 False"""
        clips_dir = tmp_path / "clips"
        clips_dir.mkdir()

        kb = KenBurnsGenerator()
        result = kb.generate_scene(
            "/nonexistent/image.png", 10.0,
            str(clips_dir / "test.mp4")
        )
        assert result is False

    def test_generate_scene_with_variants_single(self, tmp_path):
        """单张变体图应退化到单图 KB"""
        clips_dir = tmp_path / "clips"
        clips_dir.mkdir()

        kb = KenBurnsGenerator()
        result = kb.generate_scene_with_variants(
            ["/nonexistent/img.png"],
            10.0,
            str(clips_dir / "test.mp4")
        )
        assert result is False

    def test_generate_scene_with_variants_empty(self, tmp_path):
        """空图片列表应返回 False"""
        clips_dir = tmp_path / "clips"
        clips_dir.mkdir()

        kb = KenBurnsGenerator()
        result = kb.generate_scene_with_variants(
            [], 10.0, str(clips_dir / "test.mp4")
        )
        assert result is False


if __name__ == "__main__":
    import unittest
    unittest.main()
