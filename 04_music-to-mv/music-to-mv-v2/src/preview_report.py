"""
preview_report.py — 测试产物 HTML 预览页

用于 reference/batch 测试项目，展示：
- 项目主题、风格、主体类型
- 主参考图 base_character.png
- 场景图/变体图
- scenes.json 文案
- image_quality_report.json 质检结果
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from src.scene_generator import SceneImageGenerator


CSS = """
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #111318; color: #e8eaed; }
header { padding: 24px 32px; background: #181b22; border-bottom: 1px solid #2a2f3a; }
h1 { margin: 0 0 8px; font-size: 24px; }
.sub { color: #a9b0bd; font-size: 13px; }
main { padding: 24px 32px 40px; }
.stats { display: flex; gap: 12px; flex-wrap: wrap; margin: 18px 0 8px; }
.stat { background: #1a1f29; border: 1px solid #2d3544; border-radius: 8px; padding: 10px 14px; min-width: 120px; }
.stat .num { font-size: 22px; font-weight: 700; color: #8ab4ff; }
.stat .label { font-size: 12px; color: #9aa4b2; margin-top: 2px; }
section { margin-top: 28px; }
h2 { font-size: 17px; margin: 0 0 14px; color: #dbe7ff; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }
.card { background: #171b24; border: 1px solid #2b3240; border-radius: 8px; overflow: hidden; }
.card img { display: block; width: 100%; aspect-ratio: 16 / 9; object-fit: cover; background: #0b0d12; }
.body { padding: 12px; }
.title { font-weight: 650; margin-bottom: 6px; }
.meta { color: #9aa4b2; font-size: 12px; line-height: 1.45; }
.ok { color: #8ee59d; }
.bad { color: #ff8c8c; }
.warn { color: #ffd37a; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; background: #0f1218; border: 1px solid #2b3240; padding: 12px; border-radius: 8px; color: #c8d2e0; }
table { width: 100%; border-collapse: collapse; background: #171b24; border: 1px solid #2b3240; border-radius: 8px; overflow: hidden; }
th, td { text-align: left; padding: 9px 10px; border-bottom: 1px solid #2b3240; font-size: 13px; }
th { color: #bcd1ff; background: #1d2430; }
td { color: #d7dde8; }
"""


class PreviewReport:
    """生成测试项目预览 HTML。"""

    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir)
        self.metadata_dir = self.project_dir / "metadata"
        self.images_dir = self.project_dir / "images"

    def generate(self, output_path: str | None = None) -> Path:
        output = Path(output_path) if output_path else self.project_dir / "preview.html"
        output.write_text(self.render(), encoding="utf-8")
        return output

    def render(self) -> str:
        info = self._read_json("info.json", {})
        scenes = self._read_json("scenes.json", [])
        quality = self._read_json("image_quality_report.json", {})
        mode = SceneImageGenerator._infer_base_reference_mode(
            info.get("theme", ""),
            info.get("song_title", ""),
            info.get("visual_anchors", ""),
        )
        images = self._collect_images()
        q_by_rel = {
            item.get("relative_path"): item
            for item in quality.get("items", [])
            if isinstance(item, dict)
        }
        summary = quality.get("summary", {})

        cards = "\n".join(self._render_image_card(path, q_by_rel) for path in images)
        scene_rows = "\n".join(self._render_scene_row(scene) for scene in scenes)
        quality_rows = "\n".join(self._render_quality_row(item) for item in quality.get("items", []))

        return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{self._esc(info.get("project_name", self.project_dir.name))} Preview</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>{self._esc(info.get("project_name", self.project_dir.name))}</h1>
  <div class="sub">生成时间: {self._esc(datetime.now().isoformat(timespec="seconds"))}</div>
  <div class="sub">项目目录: {self._esc(str(self.project_dir))}</div>
  <div class="stats">
    <div class="stat"><div class="num">{self._esc(mode)}</div><div class="label">主题主体类型</div></div>
    <div class="stat"><div class="num">{len(images)}</div><div class="label">图片数</div></div>
    <div class="stat"><div class="num">{summary.get("passed", "-")}/{summary.get("total", "-")}</div><div class="label">质检通过</div></div>
    <div class="stat"><div class="num">{summary.get("failed", "-")}</div><div class="label">质检失败</div></div>
  </div>
</header>
<main>
  <section>
    <h2>基础信息</h2>
    <pre>{self._esc(json.dumps(info, ensure_ascii=False, indent=2))}</pre>
  </section>
  <section>
    <h2>图片预览</h2>
    <div class="grid">{cards or "<p>暂无图片</p>"}</div>
  </section>
  <section>
    <h2>场景数据</h2>
    <table>
      <thead><tr><th>ID</th><th>Label</th><th>歌词/文案</th><th>描述</th><th>时长</th></tr></thead>
      <tbody>{scene_rows or "<tr><td colspan='5'>暂无 scenes.json</td></tr>"}</tbody>
    </table>
  </section>
  <section>
    <h2>图片质检</h2>
    <table>
      <thead><tr><th>图片</th><th>状态</th><th>错误</th><th>指标</th></tr></thead>
      <tbody>{quality_rows or "<tr><td colspan='4'>暂无质检报告</td></tr>"}</tbody>
    </table>
  </section>
</main>
</body>
</html>"""

    def _collect_images(self) -> List[Path]:
        if not self.images_dir.exists():
            return []
        images = list(self.images_dir.glob("base_character.png"))
        images += sorted(p for p in self.images_dir.glob("seg*.png") if p not in images)
        images += sorted(
            p for p in self.images_dir.glob("*.png")
            if p not in images and not p.name.startswith("seg")
        )
        return images

    def _render_image_card(self, path: Path, q_by_rel: Dict[str, Dict[str, Any]]) -> str:
        rel = path.relative_to(self.project_dir).as_posix()
        q = q_by_rel.get(rel, {})
        passed = q.get("passed")
        status = "未质检" if passed is None else ("通过" if passed else "失败")
        cls = "warn" if passed is None else ("ok" if passed else "bad")
        metrics = q.get("metrics", {})
        errors = ", ".join(q.get("errors", []))
        return f"""
<div class="card">
  <img src="{self._esc(rel)}" alt="{self._esc(path.name)}">
  <div class="body">
    <div class="title">{self._esc(path.name)}</div>
    <div class="meta">质检: <span class="{cls}">{self._esc(status)}</span> {self._esc(errors)}</div>
    <div class="meta">{self._esc(self._format_metrics(metrics))}</div>
  </div>
</div>"""

    def _render_scene_row(self, scene: Dict[str, Any]) -> str:
        return (
            "<tr>"
            f"<td>{self._esc(scene.get('id', ''))}</td>"
            f"<td>{self._esc(scene.get('label', scene.get('name', '')))}</td>"
            f"<td>{self._esc(scene.get('text_preview', ''))}</td>"
            f"<td>{self._esc(scene.get('desc', ''))}</td>"
            f"<td>{self._esc(scene.get('duration', ''))}</td>"
            "</tr>"
        )

    def _render_quality_row(self, item: Dict[str, Any]) -> str:
        passed = item.get("passed")
        status = "通过" if passed else "失败"
        cls = "ok" if passed else "bad"
        return (
            "<tr>"
            f"<td>{self._esc(item.get('relative_path', ''))}</td>"
            f"<td class='{cls}'>{status}</td>"
            f"<td>{self._esc(', '.join(item.get('errors', [])))}</td>"
            f"<td>{self._esc(self._format_metrics(item.get('metrics', {})))}</td>"
            "</tr>"
        )

    def _read_json(self, name: str, default: Any) -> Any:
        path = self.metadata_dir / name
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    @staticmethod
    def _format_metrics(metrics: Dict[str, Any]) -> str:
        if not metrics:
            return ""
        keys = ["width", "height", "file_size_bytes", "luma_mean", "luma_stddev"]
        return " | ".join(f"{k}={metrics[k]}" for k in keys if k in metrics)

    @staticmethod
    def _esc(value: Any) -> str:
        return html.escape(str(value), quote=True)
