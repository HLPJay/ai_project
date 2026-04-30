"""
ken_burns.py — 纯 Python Ken Burns 视频生成器

替代原版 scripts/generate_kb_video.py 的纯 Python 实现。
无需 bash，直接调用 ffmpeg 子进程。

功能：
  - 单图 Ken Burns 动效（缩放 + 平移 + 淡入淡出）
  - 多图 crossfade（变体图之间平滑过渡）
  - 随机镜头轨迹（每个场景不同）
  - 自动重试

用法：
    kb = KenBurnsGenerator()
    result = kb.generate_scene(
        image_path="images/seg1_scene.png",
        duration_sec=10.0,
        output_path="clips/seg1_scene_kb.mp4"
    )
"""

import json
import os
import random
import subprocess
import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# ── 默认参数 ──────────────────────────────────────────
FPS = 25
DEFAULT_ZOOM_RANGE = (1.0, 1.25)          # (start, end)
DEFAULT_SHARPEN = "5:5:0.8:3:3:0.4"       # unsharp 滤镜参数
DEFAULT_TRANSITION_RATIO = 0.2             # crossfade 占每片段比例
DEFAULT_MIN_IMG_DUR = 5.0                  # 单图最短时长（秒）
DEFAULT_FADE_DUR = 1.5                     # 淡入淡出时长（秒）
KB_MAX_RETRIES = 3


class KenBurnsError(Exception):
    """Ken Burns 生成错误"""
    pass


class KenBurnsGenerator:
    """Ken Burns 视频生成器"""

    def __init__(self, fps: int = FPS, ffmpeg_path: str = "ffmpeg"):
        self.fps = fps
        self.ffmpeg = ffmpeg_path

    # ══════════════════════════════════════════════════════
    # 公开 API
    # ══════════════════════════════════════════════════════

    def generate_scene(self, image_path: str, duration_sec: float,
                       output_path: str,
                       zoom_range: Tuple[float, float] = DEFAULT_ZOOM_RANGE,
                       sharpen_params: str = DEFAULT_SHARPEN,
                       fade_duration: float = DEFAULT_FADE_DUR) -> bool:
        """为单张图片生成 Ken Burns 视频片段

        参数:
            image_path: 输入图片路径
            duration_sec: 片段时长（秒）
            output_path: 输出视频路径
            zoom_range: (起始缩放, 结束缩放)
            sharpen_params: unsharp 滤镜参数
            fade_duration: 淡入淡出时长（秒）

        返回:
            True 成功, False 失败
        """
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            return True

        kb_frames = int(self.fps * duration_sec)
        if kb_frames < 1:
            return False

        zoom_start, zoom_end = zoom_range
        zoom_step = (zoom_end - 1.0) / max(kb_frames, 1)
        zoom_end_actual = 1.0 + zoom_step * kb_frames

        # 先缩放到标准 1280x720（横屏），适配任意方向图片
        vf_prefix = (
            "scale=1280:720:force_original_aspect_ratio=decrease,"
            "pad=1280:720:(ow-iw)/2:(oh-ih)/2,"
        )

        # 随机镜头偏移（使每个场景的镜头移动不同）
        offset_x = random.uniform(-120, 120)
        offset_y = random.uniform(-80, 80)

        # 淡出起始时间
        fade_out_start = max(fade_duration, duration_sec - fade_duration)

        # zoompan：注意表达式不能包含逗号（逗号会被 ffmpeg 解析为滤镜分隔符）
        # 使用 z=1 + step*on 的线性缩放代替 min(zoom+step, max)
        vf = (
            f"{vf_prefix}"
            f"zoompan="
            f"z=1+{zoom_step:.6f}*on:"
            f"x=iw/2-(iw/zoom/2)+{offset_x:.0f}*on/{kb_frames}:"
            f"y=ih/2-(ih/zoom/2)+{offset_y:.0f}*on/{kb_frames}:"
            f"d={kb_frames}:"
            f"s=1280x720:fps={self.fps},"
            f"unsharp={sharpen_params},"
            f"fade=t=in:st=0:d={min(fade_duration, duration_sec*0.3):.2f},"
            f"fade=t=out:st={fade_out_start:.2f}:d={min(fade_duration, duration_sec*0.3):.2f}"
        )

        cmd = [
            self.ffmpeg, "-y",
            "-loop", "1",
            "-i", image_path,
            "-vf", vf,
            "-t", str(duration_sec),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "fast",
            "-crf", "23",
            output_path
        ]

        for attempt in range(KB_MAX_RETRIES):
            try:
                result = subprocess.run(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                    timeout=duration_sec + 30
                )
                if result.returncode == 0 and os.path.getsize(output_path) > 1000:
                    return True
                if result.returncode != 0 and attempt == 0:
                    err_text = result.stderr.decode("utf-8", errors="replace")[-200:]
                    print(f"     [KB ffmpeg err] {err_text.strip()}")
            except subprocess.TimeoutExpired:
                pass
            except Exception:
                pass
            if attempt < KB_MAX_RETRIES - 1:
                time.sleep(1)

        return False

    def generate_scene_with_variants(self, image_paths: List[str],
                                     total_duration: float,
                                     output_path: str,
                                     zoom_range: Tuple[float, float] = DEFAULT_ZOOM_RANGE,
                                     sharpen_params: str = DEFAULT_SHARPEN,
                                     transition_ratio: float = DEFAULT_TRANSITION_RATIO,
                                     min_img_dur: float = DEFAULT_MIN_IMG_DUR,
                                     fade_duration: float = DEFAULT_FADE_DUR) -> bool:
        """为多张变体图生成 Ken Burns 视频（带 crossfade）

        参数:
            image_paths: 图片路径列表（主图 + 变体图）
            total_duration: 片段总时长（秒）
            output_path: 输出视频路径
            zoom_range: (起始缩放, 结束缩放)
            sharpen_params: unsharp 滤镜参数
            transition_ratio: crossfade 占每片段的比例
            min_img_dur: 单图最短时长
            fade_duration: 淡入淡出时长

        返回:
            True 成功, False 失败
        """
        if not image_paths:
            return False

        # 只有一张图 -> 直接生成单图 KB
        if len(image_paths) == 1:
            return self.generate_scene(
                image_paths[0], total_duration, output_path,
                zoom_range, sharpen_params, fade_duration
            )

        # 多图 -> 先为每张图生成单图 KB，再 crossfade
        dur_per_img = max(total_duration / len(image_paths), min_img_dur)
        raw_fade = dur_per_img * transition_ratio
        cf_fade = min(max(0.3, raw_fade), dur_per_img * 0.8)

        # 生成每张图的 KB 片段
        temp_dir = Path(output_path).parent / "_kb_temp"
        temp_dir.mkdir(exist_ok=True)
        temp_clips = []

        try:
            for i, img_path in enumerate(image_paths):
                tmp = temp_dir / f"tmp_{Path(output_path).stem}_{i}.mp4"
                ok = self.generate_scene(
                    img_path, dur_per_img, str(tmp),
                    zoom_range, sharpen_params, fade_duration
                )
                if ok:
                    temp_clips.append(str(tmp))
                else:
                    print(f"   [WARN] 变体图 {i} KB 生成失败")

            if not temp_clips:
                return False

            # 只有一个成功 -> 直接复制
            if len(temp_clips) == 1:
                shutil.copy(temp_clips[0], output_path)
                return True

            # 多个 -> crossfade 拼接
            return self._crossfade_clips(temp_clips, total_duration, output_path, cf_fade)

        finally:
            # 清理临时文件
            for f in temp_clips:
                try:
                    os.remove(f)
                except OSError:
                    pass
            try:
                shutil.rmtree(str(temp_dir))
            except OSError:
                pass

    # ══════════════════════════════════════════════════════
    # 场景级批量处理
    # ══════════════════════════════════════════════════════

    def process_project(self, project_dir: str, zoom_range: str = "1.0-1.25",
                        sharpen: str = DEFAULT_SHARPEN,
                        transition_ratio: float = DEFAULT_TRANSITION_RATIO,
                        min_img_dur: float = DEFAULT_MIN_IMG_DUR) -> Dict[str, Any]:
        """处理项目中的所有场景，生成 KB 视频片段

        参数:
            project_dir: 项目目录
            zoom_range: "start-end" 格式的缩放范围字符串
            sharpen: unsharp 参数
            transition_ratio: crossfade 比例
            min_img_dur: 单图最短时长

        返回:
            {"total": int, "succeeded": int, "failed": int,
             "skipped": List[int], "results": List[dict]}
        """
        proj = Path(project_dir)
        scenes_path = proj / "metadata" / "scenes.json"
        variants_path = proj / "metadata" / "variants.json"
        images_dir = proj / "images"
        clips_dir = proj / "clips"
        clips_dir.mkdir(exist_ok=True)

        # 读取场景配置
        scenes = json.loads(scenes_path.read_text(encoding="utf-8"))

        # 读取变体配置
        variant_scenes: Dict[int, int] = {}
        if variants_path.exists():
            data = json.loads(variants_path.read_text(encoding="utf-8"))
            variant_scenes = {int(k): v for k, v in data.get("variant_scenes", {}).items()}

        zoom_start, zoom_end = map(float, zoom_range.split("-"))
        zoom = (zoom_start, zoom_end)

        results = []
        skipped = []

        for s in scenes:
            sid = s["id"]
            dur = s.get("duration", 10)
            n_variants = variant_scenes.get(sid, 1)

            # 收集图片路径
            image_paths = []
            for i in range(n_variants):
                if i == 0:
                    p = images_dir / f"seg{sid}_scene.png"
                else:
                    p = images_dir / f"seg{sid}_variant{i}.png"
                if p.exists() and p.stat().st_size > 1000:
                    image_paths.append(str(p))

            if not image_paths:
                skipped.append(sid)
                results.append({"sid": sid, "status": "skipped", "reason": "no images"})
                continue

            output_path = clips_dir / f"seg{sid}_scene_kb.mp4"

            # 幂等：已有且大小正常则跳过
            if output_path.exists() and output_path.stat().st_size > 1000:
                results.append({"sid": sid, "status": "skipped", "reason": "already exists"})
                continue

            print(f"  [KB] scene {sid}: {len(image_paths)} image(s), {dur}s")

            ok = self.generate_scene_with_variants(
                image_paths, dur, str(output_path),
                zoom_range=zoom,
                sharpen_params=sharpen,
                transition_ratio=transition_ratio,
                min_img_dur=min_img_dur,
            )

            status = "ok" if ok else "failed"
            results.append({"sid": sid, "status": status})
            print(f"     {'[OK]' if ok else '[FAIL]'} done scene {sid}")

        # 统计
        succeeded = sum(1 for r in results if r["status"] == "ok")
        failed = sum(1 for r in results if r["status"] == "failed")

        print(f"  [KB] Ken Burns 完成: {succeeded}/{len(results)} 成功 ({failed} 失败)")
        if skipped:
            print(f"  [WARN] 因无图片跳过: {skipped}")

        return {
            "total": len(results),
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
            "results": results,
        }

    # ══════════════════════════════════════════════════════
    # 内部方法
    # ══════════════════════════════════════════════════════

    def _crossfade_clips(self, clip_paths: List[str], total_duration: float,
                         output_path: str, fade_duration: float = 1.0) -> bool:
        """多 clip crossfade 拼接"""
        if len(clip_paths) == 1:
            shutil.copy(clip_paths[0], output_path)
            return True

        cmd = [self.ffmpeg, "-y"]
        for p in clip_paths:
            cmd += ["-i", p]

        n = len(clip_paths)
        dur_per_clip = total_duration / n

        if fade_duration >= dur_per_clip:
            fade_duration = dur_per_clip * 0.5  # 自动降级

        # 构建 filter_complex
        filter_parts = []
        for i in range(n):
            filter_parts.append(f"[{i}:v]fps={self.fps},scale=1280:720[v{i}]")

        offset = 0
        for i in range(1, n):
            offset += dur_per_clip - fade_duration
            filter_parts.append(
                f"[v{i-1}][v{i}]xfade=transition=fade:"
                f"duration={fade_duration}:offset={offset}[vx{i}]"
            )

        last_label = f"[vx{n-1}]"

        cmd += [
            "-filter_complex", ";".join(filter_parts),
            "-map", last_label,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "fast",
            "-crf", "23",
            output_path
        ]

        try:
            result = subprocess.run(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=total_duration + 30
            )
            return result.returncode == 0
        except Exception:
            return False
