#!/usr/bin/env python3
"""
稳定版 Ken Burns 视频生成器（支持 crossfade）

修复点：
- ❌ zoompan 不支持 random() → ✅ Python 层生成随机轨迹
- ❌ concat 输入错误 → ✅ 多输入 + xfade
- ❌ filter_complex 拼接错误 → ✅ 正确链式构建
- ✅ 平滑镜头移动（真正 Ken Burns）
"""

import argparse
import json
import os
import subprocess
import random
from pathlib import Path
import shutil

fps = 25
temp_dir_base = "temp_kb"

DEFAULT_ZOOM_RANGE = "1.0-1.25"
DEFAULT_SHARPEN = "5:5:0.8:3:3:0.4"
DEFAULT_TRANSITION_RATIO = 0.2
DEFAULT_MIN_IMG_DUR = 5.0


# =========================
# Ken Burns 单图生成
# =========================
def generate_kb_single(image_path, duration_sec, output_path,
                       fps=25, zoom_start=1.0, zoom_end=1.25,
                       sharpen_params='5:5:0.8:3:3:0.4'):

    if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
        return True

    kb_frames = int(fps * duration_sec)
    fade_out_start = max(2.0, duration_sec - 2.0)

    # ✅ Python 层生成随机轨迹（关键修复）
    offset_x = random.uniform(-120, 120)
    offset_y = random.uniform(-80, 80)

    # ✅ 平滑移动（核心优化）
    vf = (
        f"scale=3200:-1:flags=lanczos,"
        f"pad=ceil(iw/2)*2:ceil(ih/2)*2,"
        f"crop=16/9*ih:ih:(iw-16/9*ih)/2:0,"
        f"zoompan="
        f"z='min(zoom+0.0004,{zoom_end})':"
        f"x='iw/2-(iw/zoom/2)+({offset_x}*on/{kb_frames})':"
        f"y='ih/2-(ih/zoom/2)+({offset_y}*on/{kb_frames})':"
        f"d={kb_frames}:"
        f"s=1280x720:fps={fps},"
        f"unsharp={sharpen_params},"
        f"fade=t=in:st=0:d=1.5,"
        f"fade=t=out:st={fade_out_start:.2f}:d=1.5"
    )

    cmd = [
        "ffmpeg", "-y",
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

    try:
        return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    except Exception:
        return False


# =========================
# 多片段 crossfade
# =========================
def crossfade_clips(clip_paths, duration_sec, output_path,
                    fps=25, fade_duration=1.0):

    if len(clip_paths) == 1:
        shutil.copy(clip_paths[0], output_path)
        return True

    cmd = ["ffmpeg", "-y"]

    # ✅ 正确多输入
    for p in clip_paths:
        cmd += ["-i", p]

    filter_parts = []

    # 标准化输入
    for i in range(len(clip_paths)):
        filter_parts.append(
            f"[{i}:v]fps={fps},scale=1280:720[v{i}]"
        )

    # xfade 链
    offset = 0
    dur_per_clip = duration_sec / len(clip_paths)

    # 显式断言：fade 不能超过 clip 时长，避免 xfade offset 负值
    if fade_duration >= dur_per_clip:
        raise ValueError(f"fade_duration ({fade_duration:.2f}s) must be < clip duration ({dur_per_clip:.2f}s)")

    for i in range(1, len(clip_paths)):
        offset += dur_per_clip - fade_duration

        filter_parts.append(
            f"[v{i-1}][v{i}]xfade=transition=fade:"
            f"duration={fade_duration}:offset={offset}[vx{i}]"
        )

    last_label = f"[vx{len(clip_paths)-1}]"

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
        return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    except Exception:
        return False


# =========================
# 主逻辑
# =========================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    parser.add_argument("--scene-ids", default="")
    parser.add_argument("--zoom-range", default=DEFAULT_ZOOM_RANGE)
    parser.add_argument("--sharpen", default=DEFAULT_SHARPEN)
    parser.add_argument("--transition-ratio", type=float, default=DEFAULT_TRANSITION_RATIO)
    parser.add_argument("--min-img-dur", type=float, default=DEFAULT_MIN_IMG_DUR)

    args = parser.parse_args()

    proj = Path(args.project_dir)

    scenes = json.loads((proj / "metadata/scenes.json").read_text())

    variant_scenes = {}
    vfile = proj / "metadata/variants.json"
    if vfile.exists():
        data = json.loads(vfile.read_text())
        variant_scenes = {int(k): v for k, v in data.get("variant_scenes", {}).items()}

    clips_dir = proj / "clips"
    clips_dir.mkdir(exist_ok=True)

    zoom_start, zoom_end = map(float, args.zoom_range.split("-"))

    skipped_scenes = []
    for s in scenes:
        sid = s["id"]
        dur = s.get("duration", 10)

        n_variants = variant_scenes.get(sid, 1)

        images = []
        for i in range(n_variants):
            if i == 0:
                p = proj / "images" / f"seg{sid}_scene.png"
            else:
                p = proj / "images" / f"seg{sid}_variant{i}.png"
            if p.exists():
                images.append(str(p))

        if not images:
            skipped_scenes.append(sid)
            print(f"⛔ scene {sid}: no images, skipping (scene will be missing from final MV)")
            continue

        output_path = clips_dir / f"seg{sid}_scene_kb.mp4"

        temp_dir = clips_dir / temp_dir_base
        temp_dir.mkdir(exist_ok=True)

        temp_clips = []

        dur_per_img = max(dur / len(images), args.min_img_dur)
        raw_fade = dur_per_img * args.transition_ratio
        fade_dur = min(max(0.3, raw_fade), dur_per_img * 0.8)  # 至少0.3s，不超过clip时长的80%

        print(f"🎬 scene {sid}: {len(images)} images")

        for i, img in enumerate(images):
            tmp = temp_dir / f"seg{sid}_{i}.mp4"

            ok = generate_kb_single(
                img, dur_per_img, str(tmp),
                zoom_start=zoom_start,
                zoom_end=zoom_end,
                sharpen_params=args.sharpen
            )

            if ok:
                temp_clips.append(str(tmp))
            else:
                print(f"   ❌ fail img {i}")

        if len(temp_clips) == 1:
            shutil.copy(temp_clips[0], output_path)
        else:
            ok = crossfade_clips(temp_clips, dur, str(output_path), fade_duration=fade_dur)
            if not ok:
                print(f"   ❌ crossfade failed, using first image as fallback")
                shutil.copy(temp_clips[0], output_path)

        # 清理
        for f in temp_clips:
            try:
                os.remove(f)
            except Exception as e:
                print(f"   ⚠️ cleanup warning: could not remove {f}: {e}")

        print(f"   ✅ done scene {sid}")

    if skipped_scenes:
        print(f"\n⚠️  警告：以下场景因无图片被跳过（最终 MV 会缺这些片段）: {skipped_scenes}")
    print("\n🎉 ALL DONE")


if __name__ == "__main__":
    main()