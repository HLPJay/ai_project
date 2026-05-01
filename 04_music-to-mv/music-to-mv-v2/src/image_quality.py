"""
image_quality.py — 图片生成结果自动质检

当前版本做低成本、确定性的图片质量检查：
- 文件是否存在、大小是否过小
- 是否能被 Pillow 打开
- 图片尺寸是否低于阈值
- 是否接近全黑/全白
- 是否低方差、近似纯色或信息量过低

注意：这里不做语义主体识别，比如“图里是否真的有小狗”。这类检查需要视觉模型，
后续可以在本模块上扩展。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List


@dataclass
class ImageQualityThresholds:
    min_file_size: int = 1000
    min_width: int = 512
    min_height: int = 512
    dark_mean: float = 8.0
    bright_mean: float = 247.0
    min_stddev: float = 6.0


class ImageQualityChecker:
    """图片质量检查器。"""

    def __init__(self, project_dir: str,
                 thresholds: ImageQualityThresholds | None = None):
        self.project_dir = Path(project_dir)
        self.metadata_dir = self.project_dir / "metadata"
        self.thresholds = thresholds or ImageQualityThresholds()

    def validate_paths(self, paths: Iterable[str | Path],
                       write_report: bool = True) -> Dict[str, Any]:
        """检查指定图片路径并生成报告。"""
        items = [self.validate_image(Path(p)) for p in paths]
        summary = {
            "total": len(items),
            "passed": sum(1 for item in items if item["passed"]),
            "failed": sum(1 for item in items if not item["passed"]),
            "warnings": sum(len(item.get("warnings", [])) for item in items),
        }
        report = {
            "generated_at": datetime.now().isoformat(),
            "thresholds": asdict(self.thresholds),
            "summary": summary,
            "items": items,
        }
        if write_report:
            self.write_report(report)
        return report

    def validate_image(self, path: Path) -> Dict[str, Any]:
        """检查单张图片。"""
        item: Dict[str, Any] = {
            "path": str(path),
            "relative_path": self._relative(path),
            "passed": True,
            "errors": [],
            "warnings": [],
            "metrics": {},
        }

        if not path.exists():
            item["passed"] = False
            item["errors"].append("missing_file")
            return item

        file_size = path.stat().st_size
        item["metrics"]["file_size_bytes"] = file_size
        if file_size < self.thresholds.min_file_size:
            item["passed"] = False
            item["errors"].append("file_too_small")

        try:
            from PIL import Image, ImageStat
        except Exception as exc:
            item["warnings"].append(f"pillow_unavailable: {exc}")
            return item

        try:
            with Image.open(path) as img:
                img.verify()
            with Image.open(path) as img:
                width, height = img.size
                item["metrics"]["width"] = width
                item["metrics"]["height"] = height
                item["metrics"]["mode"] = img.mode
                item["metrics"]["format"] = img.format

                if width < self.thresholds.min_width or height < self.thresholds.min_height:
                    item["passed"] = False
                    item["errors"].append("resolution_too_small")

                sample = img.convert("L").resize((64, 64))
                stat = ImageStat.Stat(sample)
                mean = float(stat.mean[0])
                stddev = float(stat.stddev[0])
                item["metrics"]["luma_mean"] = round(mean, 3)
                item["metrics"]["luma_stddev"] = round(stddev, 3)

                if mean <= self.thresholds.dark_mean:
                    item["passed"] = False
                    item["errors"].append("image_too_dark")
                if mean >= self.thresholds.bright_mean:
                    item["passed"] = False
                    item["errors"].append("image_too_bright")
                if stddev < self.thresholds.min_stddev:
                    item["passed"] = False
                    item["errors"].append("low_visual_variance")

        except Exception as exc:
            item["passed"] = False
            item["errors"].append(f"cannot_open_image: {exc}")

        return item

    def write_report(self, report: Dict[str, Any]) -> Path:
        """写入 metadata/image_quality_report.json。"""
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        output = self.metadata_dir / "image_quality_report.json"
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output

    def _relative(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.project_dir.resolve()))
        except Exception:
            return str(path)
