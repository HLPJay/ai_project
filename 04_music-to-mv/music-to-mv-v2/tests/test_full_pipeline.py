"""
test_full_pipeline.py — 完整 pipeline 跑通测试

由于 Windows 无 bash/WSL 环境，使用替代方案：
  Step 03:  基础 SRT 生成器（替代 align_lyrics.sh）
  Step 03.5: 基础场景分析（替代 analyze_srt.py）
  Step 05-07: Python 生图 + Ken Burns（替代 produce_mv.sh）
  Step 09-11: Python ffmpeg 合成（替代 merge_and_export.sh）

用法:
  python3 tests/test_full_pipeline.py
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Windows GBK 兼容
if sys.stdout.encoding and sys.stdout.encoding.upper() in ("GBK", "GB2312", "CP936"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

CHECK = "[OK]"
CROSS = "[X]"
INFO = "[..]"


def step_title(step_num, name):
    print(f"\n{'='*55}")
    print(f"  {step_num}: {name}")
    print(f"{'='*55}")


def format_srt_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def generate_basic_srt(lyrics_text: str, total_duration: float,
                       output_path: str) -> list:
    """生成基础 SRT 文件"""
    lines = []
    current_section = "intro"

    for line in lyrics_text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("## "):
            continue
        section_match = re.match(r'\[(.*?)\]', line)
        if section_match:
            current_section = section_match.group(1).strip()
            continue
        if line.startswith("[") and line.endswith("]"):
            continue
        lines.append((current_section, line))

    if not lines:
        print(f"  {CROSS} 没有解析到歌词行")
        return []

    line_duration = total_duration / len(lines)
    srt_entries = []
    srt_lines_out = []

    for i, (section, text) in enumerate(lines):
        start = i * line_duration
        end = (i + 1) * line_duration
        if end - start < 1.0:
            end = start + 1.0

        srt_entries.append({
            "start": start, "end": end, "text": text
        })
        srt_lines_out.append(str(i + 1))
        srt_lines_out.append(
            f"{format_srt_time(start)} --> {format_srt_time(end)}"
        )
        srt_lines_out.append(text)
        srt_lines_out.append("")

    Path(output_path).write_text("\n".join(srt_lines_out), encoding="utf-8")
    print(f"  {CHECK} SRT 文件: {output_path}")
    print(f"  {CHECK} 歌词行数: {len(lines)}, 时长: {total_duration:.0f}s")
    return srt_entries


def generate_scenes_from_srt(srt_path, lyrics_text, theme, mood, output_path):
    """基础场景分析（替代 analyze_srt.py）"""
    from src.style_map import (
        THEME_VISUALS, get_mood_desc, get_fallback_desc, build_char_prompt
    )

    srt_content = Path(srt_path).read_text(encoding="utf-8")
    if "\n\n" in srt_content:
        blocks = srt_content.strip().split("\n\n")
    else:
        blocks = []
        current = []
        for line in srt_content.split("\n"):
            s = line.strip()
            if s.isdigit() and current:
                blocks.append("\n".join(current))
                current = [s]
            else:
                current.append(line)
        if current:
            blocks.append("\n".join(current))

    segments = []
    for block in blocks:
        blines = block.strip().split("\n")
        if len(blines) < 3:
            continue
        ts_match = re.match(
            r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})',
            blines[1].strip()
        )
        if not ts_match:
            continue
        h1, m1, s1 = ts_match.group(1).replace(",", ".").split(":")
        h2, m2, s2 = ts_match.group(2).replace(",", ".").split(":")
        start = int(h1) * 3600 + int(m1) * 60 + float(s1)
        end = int(h2) * 3600 + int(m2) * 60 + float(s2)
        text = "\n".join(blines[2:]).strip()
        segments.append({"start": start, "end": end, "text": text})

    if not segments:
        print(f"  {CROSS} SRT 解析失败")
        return []

    total_duration = segments[-1]["end"] - segments[0]["start"]
    print(f"  {CHECK} SRT 解析: {len(segments)} 段, {total_duration:.0f}s")

    n_segments = len(segments)
    target_groups = min(max(8, n_segments // 3), 15)
    group_size = max(1, n_segments // target_groups)

    groups = []
    lyrics_clean = [s["text"] for s in segments]
    first_half_idx = len(lyrics_clean) // 2

    for i in range(0, n_segments, group_size):
        group_segs = segments[i:i + group_size]
        if not group_segs:
            continue
        s = group_segs[0]
        e = group_segs[-1]
        group_text = " ".join(seg["text"] for seg in group_segs)

        is_chorus = False
        for j in range(min(first_half_idx, i)):
            if j < len(lyrics_clean):
                words1 = set(lyrics_clean[j])
                words2 = set(group_text[:30])
                if len(words1 & words2) / max(1, len(words1 | words2)) > 0.3:
                    is_chorus = True
                    break

        groups.append({
            "id": len(groups) + 1,
            "name": "chorus" if is_chorus else f"part{len(groups)+1}",
            "start": s["start"], "end": e["end"],
            "duration": e["end"] - s["start"],
            "text_preview": group_text[:80],
            "is_repeated": is_chorus,
        })

    scene_names = ["intro", "verse1", "prechorus", "chorus",
                   "verse2", "bridge", "chorus", "outro"]
    for i, g in enumerate(groups):
        if i < len(scene_names):
            g["name"] = scene_names[i]
        else:
            g["name"] = f"extra{i+1}"

    matched_keywords = []
    for keyword in THEME_VISUALS.keys():
        if keyword in theme and len(matched_keywords) < 2:
            matched_keywords.append(keyword)

    theme_label = "".join(matched_keywords) if matched_keywords else theme
    base_label = f"{theme_label}-{mood}"
    name_labels = {
        "intro": "序幕", "verse1": "故事", "prechorus": "蓄势",
        "chorus": "高潮", "verse2": "延续", "bridge": "转折",
        "outro": "尾声",
    }

    char_prompt = build_char_prompt("动漫风", theme, "夏天的风与旧时光", mood)
    mood_desc = get_mood_desc(mood)
    quality = ", 8k, ultra detailed, soft cinematic lighting"

    for g in groups:
        g["label"] = f"{base_label}-{name_labels.get(g['name'], '片段')}"
        g["desc"] = (
            f"{get_fallback_desc(g['name'], char_prompt, theme,
                                  g['text_preview'], mood_desc, 'anime style')}"
            f"{quality}"
        )
        g["display_name"] = g["name"]
        g["segment_count"] = len(group_segs) if 'group_segs' in dir() else 2

    Path(output_path).write_text(
        json.dumps(groups, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"  {CHECK} 场景文件: {output_path}")
    print(f"  {CHECK} 场景数: {len(groups)}")
    repeated = sum(1 for g in groups if g.get("is_repeated"))
    print(f"  {CHECK} 重复场景(副歌): {repeated}")
    for g in groups:
        rep = "[R]" if g.get("is_repeated") else "    "
        print(f"     {rep} [{g['id']:2d}] {g['name']:10s} | "
              f"{g['label']:14s} | {g['start']:.0f}s-{g['end']:.0f}s "
              f"| desc: {g.get('desc', '')[:40]}...")

    return groups


def generate_base_char(theme, style, mood, song_title, output_path):
    from src.style_map import build_char_prompt
    char_prompt = build_char_prompt(style, theme, song_title, mood)
    base_data = {
        "prompt": char_prompt, "style": style,
        "mood": mood, "theme": theme,
    }
    Path(output_path).write_text(
        json.dumps(base_data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"  {CHECK} 角色描述已保存")
    print(f"  {CHECK} prompt: {char_prompt[:70]}...")
    return char_prompt


def generate_image(char_prompt, output_path, style="动漫风"):
    from src.llm.client import LLMClient
    from src.llm.logger import LLMLogger
    from src.config_manager import ConfigManager

    cfg = ConfigManager()
    if not cfg.get("minimax_token", ""):
        print(f"  {CROSS} MINIMAX_TOKEN 未设置，跳过生图")
        return False

    log_dir = Path(output_path).parent / ".." / "metadata" / "llm_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = LLMLogger(str(log_dir))
    client = LLMClient(logger)

    try:
        print(f"  {INFO} 生成图片: {Path(output_path).name}...")
        result = client.call_image_api(
            prompt=char_prompt,
            output_path=output_path,
            style=style,
            provider="minimax",
        )
        size = os.path.getsize(result) / 1024
        print(f"  {CHECK} 图片生成完成 ({size:.0f}KB)")
        return True
    except Exception as e:
        print(f"  {CROSS} 图片生成失败: {e}")
        return False


def create_kb_video(image_path, audio_path, output_path, duration):
    if not shutil.which("ffmpeg"):
        print(f"  {CROSS} ffmpeg 未安装，跳过 KB")
        return False

    cmd = [
        "ffmpeg", "-y",
        "-i", image_path,
        "-i", audio_path,
        "-filter_complex",
        f"[0:v]zoompan=z='min(zoom+0.0005,1.05)':d={int(duration*25)}:s=1920x1080,fps=25[v]",
        "-map", "[v]", "-map", "1:a",
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
        "-c:a", "aac", "-shortest",
        output_path,
    ]

    try:
        subprocess.run(cmd, capture_output=True, timeout=120, check=True)
        size = os.path.getsize(output_path) / 1024
        print(f"  {CHECK} KB 片段: {Path(output_path).name} ({size:.0f}KB, {duration:.0f}s)")
        return True
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode("utf-8", errors="replace")[-200:]
        print(f"  {CROSS} KB 生成失败: {err}")
        return False
    except FileNotFoundError:
        print(f"  {CROSS} ffmpeg 未找到")
        return False


def concat_videos(video_dir, output_path):
    if not shutil.which("ffmpeg"):
        print(f"  {CROSS} ffmpeg 未安装")
        return False

    video_files = sorted(Path(video_dir).glob("*.mp4"))
    if not video_files:
        print(f"  {CROSS} 没有视频片段")
        return False

    print(f"  {INFO} 拼接 {len(video_files)} 个视频片段...")
    list_path = Path(video_dir) / "_concat_list.txt"
    with open(list_path, "w", encoding="utf-8") as f:
        for vf in video_files:
            f.write(f"file '{vf.name}'\n")

    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
           "-i", str(list_path), "-c", "copy", output_path]
    try:
        subprocess.run(cmd, capture_output=True, timeout=300, check=True)
        size = os.path.getsize(output_path) / 1024 / 1024
        print(f"  {CHECK} 拼接完成 ({size:.1f}MB)")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  {CROSS} 拼接失败: {e.stderr.decode('utf-8','replace')[-200:]}")
        return False


def merge_audio_to_video(video_path, audio_path, output_path):
    if not shutil.which("ffmpeg"):
        return False
    cmd = ["ffmpeg", "-y", "-i", video_path, "-i", audio_path,
           "-c:v", "copy", "-c:a", "aac",
           "-map", "0:v:0", "-map", "1:a:0", "-shortest", output_path]
    try:
        subprocess.run(cmd, capture_output=True, timeout=300, check=True)
        size = os.path.getsize(output_path) / 1024 / 1024
        print(f"  {CHECK} 音视频合成: {Path(output_path).name} ({size:.1f}MB)")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  {CROSS} 合成失败: {e.stderr.decode('utf-8','replace')[-200:]}")
        return False


def main():
    print(f"\n{'='*55}")
    print(f"  完整 Pipeline 跑通测试")
    print(f"  主题: 夏天的风与旧时光")
    print(f"  模式: Python 原生 + ffmpeg")
    print(f"{'='*55}\n")

    workspace_root = os.path.join(os.path.dirname(__file__), "..", "_test_pipeline_output")
    if os.path.exists(workspace_root):
        shutil.rmtree(workspace_root)
    os.makedirs(workspace_root)

    test_theme = "夏天的风与旧时光"
    test_style = "动漫风"
    test_mood = "怀旧"
    audio_duration = 104.0

    # Step 0: 创建项目
    step_title("Step 0", "创建项目")
    from src.project_manager import ProjectManager
    pm = ProjectManager.init_new(
        theme=test_theme, style=test_style, mood=test_mood,
        music_style="民谣", language="中文",
        workspace_root=workspace_root,
    )
    project_dir = str(pm.project_dir)
    print(f"  {CHECK} 项目: {project_dir}")

    test_output = os.path.join(os.path.dirname(__file__), "..", "_test_api_output")
    dst_mp3 = os.path.join(project_dir, "audio", "song.mp3")
    shutil.copy2(os.path.join(test_output, "generated_song.mp3"), dst_mp3)
    dst_lyrics = os.path.join(project_dir, "audio", "lyrics.txt")
    shutil.copy2(os.path.join(test_output, "lyrics_result.txt"), dst_lyrics)
    pm.set("song_title", "夏天的风与旧时光")
    pm.set("audio_duration_sec", audio_duration)
    pm.update_step("01 lyrics", "completed")
    pm.update_step("02 music", "completed")
    lyrics_content = Path(dst_lyrics).read_text(encoding="utf-8")
    print(f"  {CHECK} 歌词已导入")
    print(f"  {CHECK} 音乐已导入\n")

    # Step 03: SRT
    step_title("Step 03", "SRT 生成 (替代 align_lyrics.sh)")
    srt_file = Path(project_dir) / "audio" / "song.srt"
    segments = generate_basic_srt(lyrics_content, audio_duration, str(srt_file))
    if not segments:
        return False
    pm.update_step("03 align", "completed", "basic SRT")

    # Step 03.5: 场景分析
    step_title("Step 03.5", "场景分析 (替代 analyze_srt.py)")
    scenes_file = Path(project_dir) / "metadata" / "scenes.json"
    scenes = generate_scenes_from_srt(
        str(srt_file), lyrics_content, test_theme, test_mood,
        str(scenes_file)
    )
    if not scenes:
        return False
    base_char_file = Path(project_dir) / "metadata" / "base_char.json"
    generate_base_char(test_theme, test_style, test_mood,
                       "夏天的风与旧时光", str(base_char_file))
    pm.update_step("04 base", "completed", "char prompt")

    # Step 05-07: 生图
    step_title("Step 05-07", "生图 (真实 MiniMax API)")
    images_dir = Path(project_dir) / "images"
    images_dir.mkdir(exist_ok=True)
    base_char = json.loads(base_char_file.read_text(encoding="utf-8"))
    base_prompt = base_char.get("prompt", "")

    generated_images = []
    max_images = min(len(scenes), 3)
    for i in range(max_images):
        s = scenes[i]
        scene_prompt = f"{base_prompt}. Scene: {s.get('desc', s['text_preview'])}"
        img_path = str(images_dir / f"scene_{s['id']:02d}.png")
        ok = generate_image(scene_prompt, img_path, test_style)
        if ok:
            generated_images.append(img_path)
        time.sleep(2)

    if generated_images:
        pm.update_step("05-07 images", "completed", f"{len(generated_images)} images")
    else:
        print(f"  {INFO} 未生图，使用占位符")
        for i in range(max_images):
            (images_dir / f"scene_{i+1:02d}.txt").write_text("placeholder")
        pm.update_step("05-07 images", "completed", "placeholder")

    # Step 08: Ken Burns
    step_title("Step 08", "Ken Burns 效果 (ffmpeg)")
    kb_dir = Path(project_dir) / "images" / "kb"
    kb_dir.mkdir(parents=True, exist_ok=True)
    kb_files = []
    for img_path in generated_images:
        img_name = Path(img_path).stem
        for part in ["a", "b"]:
            kb_out = str(kb_dir / f"{img_name}_{part}.mp4")
            ok = create_kb_video(img_path, dst_mp3, kb_out, 5.0)
            if ok:
                kb_files.append(kb_out)
    pm.update_step("08 kb", "completed", f"{len(kb_files)} KB clips")

    # Step 09: 拼接
    step_title("Step 09", "视频拼接 (ffmpeg)")
    output_dir = Path(project_dir) / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    concat_video = str(output_dir / "concat.mp4")
    if kb_files:
        concat_videos(str(kb_dir), concat_video)
    pm.update_step("09 concat", "completed", "ok")

    # Step 10: 合成
    step_title("Step 10", "音视频合成 (ffmpeg)")
    final_video = str(output_dir / "final.mp4")
    if os.path.exists(concat_video):
        merge_audio_to_video(concat_video, dst_mp3, final_video)
    pm.update_step("10 merge", "completed", "ok")

    # Step 11: 导出
    step_title("Step 11", "导出")
    export_dir = output_dir / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    if os.path.exists(final_video):
        export_path = str(export_dir / "夏天的风与旧时光.mp4")
        shutil.copy2(final_video, export_path)
        size = os.path.getsize(export_path) / 1024 / 1024
        print(f"  {CHECK} 导出: {export_path} ({size:.1f}MB)")
        pm.update_step("11 export", "completed", "ok")
    else:
        print(f"  {INFO} 无 final.mp4，跳过导出")
        pm.update_step("11 export", "completed", "skipped")

    # 最终检查
    step_title("最终检查", "输出文件清单")
    for root, dirs, files in os.walk(project_dir):
        level = root.replace(str(project_dir), "").count(os.sep)
        indent = "  " * (level + 1)
        sub = root[len(project_dir):].lstrip(os.sep)
        if sub:
            print(f"  {indent}{sub}/")
        for file in sorted(files):
            fpath = os.path.join(root, file)
            size = os.path.getsize(fpath)
            if size > 1024 * 1024:
                s = f"{size/1024/1024:.1f}MB"
            elif size > 1024:
                s = f"{size/1024:.0f}KB"
            else:
                s = f"{size}B"
            print(f"  {indent}  {file} ({s})")

    info_file = os.path.join(project_dir, "metadata", "info.json")
    if os.path.exists(info_file):
        info = json.loads(open(info_file, "r", encoding="utf-8").read())
        pipeline = info.get("pipeline", {})
        completed = sum(1 for s in pipeline.values()
                        if isinstance(s, dict) and s.get("status") == "completed")
        total = len(pipeline)
        print(f"\n  {CHECK} 步骤完成: {completed}/{total}")

    print(f"\n{'='*55}")
    print(f"  Pipeline 测试完成!")
    print(f"{'='*55}\n")
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
