"""
scene_generator.py — 场景图生成模块

纯 Python 实现，替代原版 scripts/generate_scene_imgs.py。
无需 bash，直接调用 LLMClient 的图片 API。

功能：
  - Step ④: 基础角色图生成（base_character.png）
  - Step ⑤-⑦: 批量场景图生成（segN_scene.png + variants）
  - 变体图策略（重复段自动生成多张图）
  - variants.json 生成
  - 图片 API 多 Provider 支持（minimax/alibaba/pollinations/dall-e）

用法：
    from src.scene_generator import SceneImageGenerator
    gen = SceneImageGenerator(project_dir)
    result = gen.generate_all(parallel=2)
"""

import json
import os
import sys
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from src.config_manager import ConfigManager
from src.llm.client import LLMClient, RetryConfig
from src.style_map import (
    ART_STYLES, get_mood_desc, get_api_style, get_negative_prompt,
    build_char_prompt,
)


# ── 变体图阈值 ──────────────────────────────────────────
VARIANT_THRESHOLD = 4        # 秒，超过此阈值的重复段生成变体
MAX_RETRY = 3
RETRY_DELAY = 2
MIN_IMAGE_SIZE = 1000        # bytes，有效图片的最小阈值
MIN_VALID_IMAGE_SIZE = 500000  # bytes, 500KB 阈值（生成验证用）


class SceneImageError(Exception):
    """场景图生成错误"""
    pass


class SceneImageGenerator:
    """场景图片生成器

    处理 Step ④（角色图）+ Step ⑤-⑦（场景图+变体图）

    Attributes:
        project_dir: 项目目录
        images_dir: 图片输出目录
        metadata_dir: 元数据目录
        client: LLMClient 实例
        cfg: ConfigManager 实例
        dry_run: 如果 True，跳过真实 API 调用，只生成规划元数据
    """

    def __init__(self, project_dir: str, dry_run: bool = False):
        self.project_dir = Path(project_dir)
        self.images_dir = self.project_dir / "images"
        self.metadata_dir = self.project_dir / "metadata"
        self.clips_dir = self.project_dir / "clips"
        self.dry_run = dry_run

        self.images_dir.mkdir(exist_ok=True)
        self.clips_dir.mkdir(exist_ok=True)

        self.cfg = ConfigManager()
        self.client = LLMClient(project_dir=str(self.project_dir))

        # 从 info.json 读取固定 seed（角色一致性）
        self._image_seed = 0
        info_path = self.metadata_dir / "info.json"
        if info_path.exists():
            info = json.loads(info_path.read_text(encoding="utf-8"))
            self._image_seed = info.get("image_seed", 0)

        # 从 base_char.json 或 style_map 读取风格参数
        self._load_style_params()

    def _load_style_params(self):
        """加载风格参数（角色描述、艺术风格、情绪等）"""
        base_char_path = self.metadata_dir / "base_char.json"

        self._char_prompt = ""
        self._art_style = ""
        self._mood_desc = ""
        self._api_style = ""
        self._negative_prompt = ""
        self._style = "动漫风"
        self._mood = "欢快"

        if base_char_path.exists():
            bc = json.loads(base_char_path.read_text(encoding="utf-8"))
            self._char_prompt = bc.get("prompt", "")
            self._style = bc.get("style", "动漫风")
            self._mood = bc.get("mood", "欢快")
        else:
            # 从 info.json 读取
            info_path = self.metadata_dir / "info.json"
            if info_path.exists():
                info = json.loads(info_path.read_text(encoding="utf-8"))
                self._style = info.get("style", "动漫风")
                self._mood = info.get("mood", "欢快")
                self._char_prompt = build_char_prompt(
                    self._style, info.get("theme", ""),
                    info.get("song_title", ""), self._mood,
                )

        self._art_style = ART_STYLES.get(self._style,
                                         "illustration style, soft warm colors")
        self._mood_desc = get_mood_desc(self._mood)
        self._api_style = get_api_style(self._style)
        self._negative_prompt = get_negative_prompt(self._style)

    # ══════════════════════════════════════════════════════
    # 公开 API
    # ══════════════════════════════════════════════════════

    def generate_base_character(self, theme: str = "",
                                song_title: str = "",
                                override_prompt: str = None) -> bool:
        """生成基础角色图（Step ④）

        Args:
            theme: 主题（用于 prompt 构建）
            song_title: 歌曲标题（用于 prompt 构建）
            override_prompt: 完全覆盖的 prompt（用于外部 LLM 生图）

        Returns:
            True 成功, False 失败
        """
        output = self.images_dir / "base_character.png"

        if self.dry_run:
            print(f"  [Step ④][dry_run] 跳过 base_character.png 生成")
            # dry_run 模式：生成带风格标注的占位图
            try:
                from PIL import Image, ImageDraw
                img = Image.new("RGB", (1080, 1920), (60, 80, 110))
                draw = ImageDraw.Draw(img)
                draw.text((540, 800), f"BASE CHARACTER", fill=(255, 255, 200),
                          anchor="mm", font_size=42)
                draw.text((540, 870), f"style: {self._style}", fill=(200, 200, 200),
                          anchor="ma", font_size=24)
                draw.text((540, 910), f"mood: {self._mood}", fill=(180, 180, 180),
                          anchor="ma", font_size=20)
                img.save(str(output))
                return True
            except Exception:
                output.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 1000)
                return True

        # 幂等：已有且大小正常则跳过
        if output.exists() and output.stat().st_size > MIN_IMAGE_SIZE:
            print(f"  [Step ④] base_character.png 已存在，跳过")
            return True

        # 构建 prompt
        if override_prompt:
            prompt = override_prompt
        elif self._char_prompt:
            theme_ = theme or self._load_theme()
            prompt = build_char_prompt(
                self._style, theme_, song_title, self._mood,
            )
        else:
            prompt = self._char_prompt

        print(f"  [Step ④] 生成基础角色图...")

        try:
            self.client.call_image_api(
                prompt=prompt,
                output_path=str(output),
                style=self._api_style,
                negative_prompt=self._negative_prompt,
                seed=self._image_seed,
            )

            if output.exists() and output.stat().st_size > MIN_IMAGE_SIZE:
                print(f"  [Step ④] 完成: {output.stat().st_size // 1024}KB")
                return True
            return False

        except Exception as e:
            print(f"  [Step ④] 失败: {e}")
            return False

    def generate_all(self, parallel: int = 2) -> Dict[str, Any]:
        """生成所有场景图（Step ⑤-⑦）

        包括变体图分析、并行生成、variants.json 写入。

        Args:
            parallel: 并发数

        Returns:
            {"total": int, "succeeded": int, "failed": int,
             "skipped": int, "variant_scenes": dict, "results": list}
        """
        scenes = self._load_scenes()
        if not scenes:
            raise SceneImageError("scenes.json 为空或不存在")

        print(f"  [Steps ⑤-⑦] {len(scenes)} 个场景，并发数={parallel}")

        # 分析变体图需求
        all_tasks, variants_map = self._analyze_variants(scenes)

        if self.dry_run:
            # dry_run 模式：不调用任何 API，只写 variants.json，生成文本标注占位图
            print(f"  [dry_run] 跳过真实图片 API 调用，生成占位图")
            self._generate_placeholder_images(scenes, variants_map)

            if variants_map:
                self._write_variants_json(variants_map)

            return {
                "total": len(all_tasks),
                "succeeded": len(all_tasks),
                "failed": 0,
                "skipped": 0,
                "variant_scenes": variants_map,
                "results": [{"sid": s[0], "variant_index": s[1],
                             "status": "ok", "size": 0} for s in all_tasks],
            }

        # 幂等跳过检查
        # 主图已存在 -> 跳过整个场景
        # 变体图已存在 -> 跳过
        tasks_to_run = []
        skipped = []
        for sid, vi, desc, output_path in all_tasks:
            p = Path(output_path)
            if p.exists() and p.stat().st_size > MIN_IMAGE_SIZE:
                skipped.append((sid, vi))
                continue
            tasks_to_run.append((sid, vi, desc, output_path))

        if skipped:
            skipped_ids = sorted(set(s[0] for s in skipped))
            print(f"  [..] 跳过（已存在）: {skipped_ids}")

        if not tasks_to_run:
            print(f"  [OK] 全部场景图已存在")
            if variants_map:
                self._write_variants_json(variants_map)
            return {
                "total": len(all_tasks),
                "succeeded": len(skipped),
                "failed": 0,
                "skipped": len(skipped),
                "variant_scenes": variants_map,
                "results": [{"sid": s[0], "status": "skipped"} for s in skipped],
            }

        # 并行生成
        print(f"  [..] 生成 {len(tasks_to_run)} 张图片...")
        results = self._run_parallel(tasks_to_run, parallel)

        # 统计
        ok = sum(1 for r in results if r.get("status") == "ok")
        fail = sum(1 for r in results if r.get("status") == "failed")

        print(f"  [OK] 场景图完成: {ok}/{len(results)} 成功 ({fail} 失败)")

        # 写入 variants.json
        if variants_map:
            self._write_variants_json(variants_map)

        return {
            "total": len(all_tasks),
            "succeeded": ok + len(skipped),
            "failed": fail,
            "skipped": len(skipped),
            "variant_scenes": variants_map,
            "results": results + [{"sid": s[0], "variant_index": s[1],
                                    "status": "skipped"} for s in skipped],
        }

    # ══════════════════════════════════════════════════════
    # 内部方法
    # ══════════════════════════════════════════════════════

    def _load_scenes(self) -> List[Dict]:
        """加载场景配置"""
        scenes_path = self.metadata_dir / "scenes.json"
        if not scenes_path.exists():
            raise FileNotFoundError(f"scenes.json not found: {scenes_path}")
        return json.loads(scenes_path.read_text(encoding="utf-8"))

    def _generate_placeholder_images(self, scenes: List[Dict],
                                      variants_map: Dict[int, int]):
        """dry_run 模式：生成带文本标注的占位图

        每张图片标注：场景编号、名称、歌词预览、时长、风格标签
        颜色按段落类型区分（Verse/Chorus/Bridge/Outro）
        """
        from PIL import Image, ImageDraw

        # 段落类型 → 背景色
        section_colors = {
            "verse": (60, 90, 140),
            "chorus": (140, 80, 60),
            "bridge": (80, 120, 80),
            "outro": (100, 70, 120),
            "intro": (70, 100, 130),
        }
        default_color = (80, 80, 100)

        # 收集所有变体描述
        all_variants = {}
        for s in scenes:
            if isinstance(s.get("variants"), list):
                for vi, vdesc in enumerate(s["variants"]):
                    all_variants[(s["id"], vi + 1)] = vdesc

        # 构建 scenes 的 id->scene 映射
        scenes_map = {s["id"]: s for s in scenes}

        for sid, vi, desc, out_path_str in self._analyze_variants(scenes)[0]:
            p = Path(out_path_str)
            if p.exists() and p.stat().st_size > MIN_IMAGE_SIZE:
                continue

            scene = scenes_map.get(sid, {})
            name = scene.get("name", f"scene {sid}")
            display_name = scene.get("display_name", name)
            text_preview = scene.get("text_preview", "")
            dur = scene.get("duration", 5)
            label = scene.get("label", "")
            is_rep = scene.get("is_repeated", False)

            # 段落类型判断
            section_type = "verse"
            if name in ("intro", "outro"):
                section_type = name
            elif "chorus" in name:
                section_type = "chorus"
            elif "bridge" in name:
                section_type = "bridge"

            bg_color = section_colors.get(section_type, default_color)

            # 如果是变体图，亮度微调
            if vi > 0:
                bg_color = tuple(min(255, c + 30) for c in bg_color)

            try:
                img = Image.new("RGB", (1080, 1920), bg_color)
                draw = ImageDraw.Draw(img)

                # 顶部信息栏
                top_bar_color = tuple(max(0, c - 40) for c in bg_color)
                draw.rectangle([(0, 0), (1080, 120)], fill=top_bar_color)

                # 场景编号（左上）
                sid_text = f"#{sid}"
                draw.text((30, 15), sid_text, fill=(255, 255, 200))

                # 段落类型标签（右上）
                section_label = section_type.upper()
                draw.text((1050, 15), section_label, fill=(200, 200, 255), anchor="ra")

                # 场景名称（顶中）
                draw.text((540, 50), display_name, fill=(255, 255, 255), anchor="ma")

                # 时长 + 重复标记（顶中偏下）
                meta_parts = [f"{dur:.1f}s"]
                if is_rep:
                    meta_parts.append("REPEAT")
                if vi > 0:
                    meta_parts.append(f"variant {vi}")
                meta_text = " | ".join(meta_parts)
                draw.text((540, 80), meta_text, fill=(200, 200, 200), anchor="ma")

                # 中央 - 歌词预览（大字）
                if text_preview:
                    # 分行（最多两行）
                    words = text_preview
                    if len(words) > 20:
                        # 尝试在中间分割
                        mid = len(words) // 2
                        # 找到标点或空格分割
                        split_pos = -1
                        for sep in "，。！？；,.;!? ":
                            pos = words.rfind(sep, 0, mid)
                            if pos > split_pos:
                                split_pos = pos
                        if split_pos > 5:
                            line1 = words[:split_pos + 1]
                            line2 = words[split_pos + 1:]
                            draw.text((540, 850), line1, fill=(255, 255, 255),
                                      anchor="mb", font_size=48)
                            draw.text((540, 920), line2, fill=(255, 255, 255),
                                      anchor="ma", font_size=48)
                        else:
                            draw.text((540, 880), words, fill=(255, 255, 255),
                                      anchor="mm", font_size=48)
                    else:
                        draw.text((540, 880), words, fill=(255, 255, 255),
                                  anchor="mm", font_size=48)

                # 底部 - 标签
                if label:
                    draw.text((540, 1850), label, fill=(200, 200, 150),
                              anchor="ma", font_size=20)

                # 底部 - 风格信息
                style_info = f"style: {self._style} | mood: {self._mood}"
                draw.text((540, 1880), style_info, fill=(160, 160, 160),
                          anchor="ma", font_size=16)

                # 保存
                img.save(str(p))

            except Exception:
                # PIL 版本可能不支持 font_size 参数
                try:
                    img = Image.new("RGB", (1080, 1920), bg_color)
                    draw = ImageDraw.Draw(img)
                    draw.text((30, 20), f"Scene #{sid}: {display_name}",
                              fill=(255, 255, 255))
                    if text_preview:
                        draw.text((540, 960), text_preview, fill=(255, 255, 255),
                                  anchor="mm")
                    draw.text((540, 1880), f"{dur:.1f}s | {self._style}",
                              fill=(200, 200, 200), anchor="ma")
                    img.save(str(p))
                except Exception:
                    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 1000)

    def _analyze_variants(self, scenes: List[Dict]) -> Tuple[List, Dict]:
        """分析变体图需求，构建任务列表

        Returns:
            (tasks, variants_map)
            tasks: [(sid, vi, desc, output_path), ...]
            variants_map: {sid: num_variants}
        """
        tasks = []
        variants_map = {}

        for s in scenes:
            sid = s["id"]
            dur = s.get("duration", 0)
            is_rep = s.get("is_repeated", False)

            # 变体数量
            scene_variants = s.get("variants", [])
            n_variants = 1

            if isinstance(scene_variants, list) and scene_variants:
                n_variants = len(scene_variants) + 1
                variants_map[sid] = n_variants
            elif is_rep and dur > VARIANT_THRESHOLD:
                n_variants = max(2, min(3, -(-int(dur) // 5)))
                variants_map[sid] = n_variants

            # 主图和每个变体
            for vi in range(n_variants):
                if vi == 0:
                    out_path = self.images_dir / f"seg{sid}_scene.png"
                    desc = s.get("desc", "")
                else:
                    out_path = self.images_dir / f"seg{sid}_variant{vi}.png"
                    if vi - 1 < len(scene_variants):
                        desc = scene_variants[vi - 1]
                    else:
                        desc = s.get("desc", "")

                tasks.append((sid, vi, desc, str(out_path)))

        return tasks, variants_map

    def _run_parallel(self, tasks: List[Tuple], parallel: int) -> List[Dict]:
        """并行执行图片生成任务"""
        results = []
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = {}

            for sid, vi, desc, out_path in tasks:
                future = executor.submit(
                    self._generate_single, sid, vi, desc, out_path
                )
                futures[future] = (sid, vi)

            for future in as_completed(futures):
                sid, vi = futures[future]
                try:
                    result = future.result()
                except Exception as e:
                    result = {"sid": sid, "variant_index": vi,
                              "status": "failed", "error": str(e)}

                if not isinstance(result, dict) or "status" not in result:
                    result = {"sid": sid, "variant_index": vi,
                              "status": "failed",
                              "error": f"invalid result type: {type(result).__name__}"}

                results.append(result)

                # 打印进度
                tag = f"var{vi}" if vi > 0 else ""
                if result.get("status") == "ok":
                    size_kb = result.get("size", 0) // 1024
                    print(f"     [OK] scene {sid}{tag}: {size_kb}KB")
                else:
                    err = result.get("error", "")
                    print(f"     [FAIL] scene {sid}{tag}: {err}")

        return results

    def _generate_single(self, sid: int, vi: int, desc: str,
                         output_path: str) -> Dict[str, Any]:
        """生成单张场景图（带重试）

        Args:
            sid: 场景 ID
            vi: 变体索引（0=主图）
            desc: 场景描述
            output_path: 输出路径

        Returns:
            {"sid": int, "variant_index": int, "status": str, "size": int, ...}
        """
        # 构建完整 prompt
        prompt = self._build_scene_prompt(desc)

        for attempt in range(1, MAX_RETRY + 1):
            try:
                self.client.call_image_api(
                    prompt=prompt,
                    output_path=output_path,
                    style=self._api_style,
                    negative_prompt=self._negative_prompt,
                    seed=self._image_seed if vi == 0 else self._image_seed + vi,
                )

                if not os.path.exists(output_path):
                    raise ValueError(f"文件未创建: {output_path}")

                file_size = os.path.getsize(output_path)
                if file_size < MIN_IMAGE_SIZE:
                    raise ValueError(f"图片太小: {file_size} bytes")

                return {
                    "sid": sid,
                    "variant_index": vi,
                    "status": "ok",
                    "size": file_size,
                    "attempt": attempt,
                }

            except Exception as e:
                err_msg = str(e)
                if attempt == MAX_RETRY:
                    return {
                        "sid": sid,
                        "variant_index": vi,
                        "status": "failed",
                        "error": err_msg,
                        "attempt": attempt,
                    }
                print(f"     [WARN] scene {sid} var{vi} 尝试 {attempt}/{MAX_RETRY}"
                      f" 失败: {err_msg}, 重试...")
                time.sleep(RETRY_DELAY * attempt)

        return {
            "sid": sid,
            "variant_index": vi,
            "status": "failed",
            "error": "unknown",
            "attempt": MAX_RETRY,
        }

    def _build_scene_prompt(self, desc: str) -> str:
        """构建场景图片 prompt

        组合：角色描述 + 场景描述 + 艺术风格 + 情绪
        注意：MiniMax 要求 prompt <= 1500 字符，各组件截断
        """
        MAX_LEN = 1400  # 留 100 字符余量给 API 端

        # 1. 角色描述：最多 600 字符
        char_part = self._char_prompt[:600] if self._char_prompt else ""

        # 2. 场景描述：最多 700 字符
        desc_part = desc[:700] if desc else ""

        # 3. 情绪
        mood_part = self._mood_desc if self._mood_desc else ""

        # 4. 艺术风格（总是最后加，短）
        style_part = self._art_style if self._art_style else ""

        # 组装
        parts = [p for p in [char_part, desc_part, mood_part, style_part] if p]
        prompt = ", ".join(parts)

        # 最终截断
        if len(prompt) > MAX_LEN:
            prompt = prompt[:MAX_LEN - 20] + ", anime style, 8k"

        return prompt

    def _write_variants_json(self, variants_map: Dict[int, int]):
        """写入 variants.json，记录每个场景的变体数量"""
        variants_path = self.metadata_dir / "variants.json"
        variants_path.write_text(
            json.dumps({"variant_scenes": variants_map},
                       ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        total = sum(variants_map.values())
        print(f"  [OK] variants.json 已写入: {total} 变体图")
