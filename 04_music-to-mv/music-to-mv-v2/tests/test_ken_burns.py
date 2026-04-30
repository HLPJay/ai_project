"""
test_ken_burns.py — Ken Burns 生成器测试

覆盖:
  - 单图 KB 生成（需要 ffmpeg）
  - 场景级批量处理（需要场景文件）
  - 参数配置验证
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.ken_burns import KenBurnsGenerator, KenBurnsError


class TestKenBurnsConfig(unittest.TestCase):
    """测试 Ken Burns 配置和参数"""

    def test_init_defaults(self):
        kb = KenBurnsGenerator()
        self.assertEqual(kb.fps, 25)
        self.assertEqual(kb.ffmpeg, "ffmpeg")

    def test_init_custom(self):
        kb = KenBurnsGenerator(fps=30, ffmpeg_path="/usr/bin/ffmpeg")
        self.assertEqual(kb.fps, 30)
        self.assertEqual(kb.ffmpeg, "/usr/bin/ffmpeg")


class TestKenBurnsProcessing(unittest.TestCase):
    """测试 KB 处理逻辑（不实际生成视频）"""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_kb_"))
        self.metadata_dir = self.test_dir / "metadata"
        self.images_dir = self.test_dir / "images"
        self.clips_dir = self.test_dir / "clips"
        self.metadata_dir.mkdir(parents=True)
        self.images_dir.mkdir(parents=True)
        self.clips_dir.mkdir(parents=True)

        # 创建测试场景文件
        self.scenes = [
            {"id": 1, "label": "intro", "duration": 10,
             "desc": "A beautiful sunset",
             "style": "动漫风", "mood": "宁静"},
            {"id": 2, "label": "verse1", "duration": 15,
             "desc": "A child running",
             "style": "动漫风", "mood": "欢快"},
        ]
        scenes_path = self.metadata_dir / "scenes.json"
        scenes_path.write_text(json.dumps(self.scenes, ensure_ascii=False), encoding="utf-8")

        # 创建模拟图片（最小有效 PNG）
        self._create_dummy_png(self.images_dir / "seg1_scene.png")
        self._create_dummy_png(self.images_dir / "seg2_scene.png")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _create_dummy_png(self, path: Path):
        """创建一个最小有效 PNG 文件（1x1 像素）"""
        # Minimal valid PNG: 8-byte signature + IHDR + IDAT + IEND
        import struct
        import zlib

        def _chunk(chunk_type, data):
            c = chunk_type + data
            return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

        signature = b'\x89PNG\r\n\x1a\n'
        ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)  # 1x1 RGB
        ihdr = _chunk(b'IHDR', ihdr_data)

        # IDAT: one row filter byte (0) + one pixel (RGB)
        raw_data = b'\x00\xff\x00\x00'  # filter byte + red pixel
        idat_data = zlib.compress(raw_data)
        idat = _chunk(b'IDAT', idat_data)

        iend = _chunk(b'IEND', b'')

        path.write_bytes(signature + ihdr + idat + iend)

    def test_process_project_no_images(self):
        """处理无图片的项目应标记为 skipped"""
        # 删除所有图片
        for f in self.images_dir.glob("*"):
            f.unlink()

        kb = KenBurnsGenerator()
        result = kb.process_project(str(self.test_dir))

        self.assertEqual(result["total"], 2)
        self.assertEqual(result["succeeded"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(len(result["skipped"]), 2)

    def test_process_project_no_metadata(self):
        """缺少 scenes.json 时应出错"""
        (self.metadata_dir / "scenes.json").unlink()

        kb = KenBurnsGenerator()
        with self.assertRaises(FileNotFoundError):
            kb.process_project(str(self.test_dir))

    def test_process_project_with_variants(self):
        """测试变体图片场景"""
        # 创建 variants.json
        variants = {"variant_scenes": {1: 2}}
        (self.metadata_dir / "variants.json").write_text(
            json.dumps(variants, ensure_ascii=False)
        )

        # 创建变体图
        self._create_dummy_png(self.images_dir / "seg1_variant1.png")

        kb = KenBurnsGenerator()
        result = kb.process_project(str(self.test_dir))

        # 场景1 有 2 张图（主图 + 变体），场景2 有 1 张图
        # 但因为ffmpeg不一定可用，status可能是skipped
        self.assertEqual(result["total"], 2)
        # 至少没有抛出异常
        self.assertIn("succeeded", result)

    def test_zoom_range_parsing(self):
        """测试 zoom_range 字符串解析"""
        kb = KenBurnsGenerator()
        # 不实际生成，只测试 process_project 能正常处理参数
        result = kb.process_project(
            str(self.test_dir),
            zoom_range="1.0-1.3",
            sharpen="5:5:0.8:3:3:0.4",
            transition_ratio=0.25,
            min_img_dur=6.0,
        )
        self.assertIn("total", result)

    def test_generate_scene_no_image(self):
        """不存在的图片应返回 False"""
        kb = KenBurnsGenerator()
        result = kb.generate_scene(
            "/nonexistent/image.png", 10.0,
            str(self.clips_dir / "test.mp4")
        )
        self.assertFalse(result)

    def test_generate_scene_with_variants_single(self):
        """单张变体图应退化到单图 KB"""
        kb = KenBurnsGenerator()
        # 图片不存在，应返回 False
        result = kb.generate_scene_with_variants(
            ["/nonexistent/img.png"],
            10.0,
            str(self.clips_dir / "test.mp4")
        )
        self.assertFalse(result)

    def test_generate_scene_with_variants_empty(self):
        """空图片列表应返回 False"""
        kb = KenBurnsGenerator()
        result = kb.generate_scene_with_variants(
            [], 10.0, str(self.clips_dir / "test.mp4")
        )
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
