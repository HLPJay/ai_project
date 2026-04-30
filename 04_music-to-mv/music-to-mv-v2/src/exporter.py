"""
exporter.py — 视频合成与导出模块

替代原版 scripts/merge_and_export.sh 的纯 Python 实现。
无需 bash，直接调用 ffmpeg 子进程。

功能：
  - Step ⑨: 视频拼接（concat）
  - Step ⑩: 音视频合并 + 字幕叠加
  - Step ⑪: 导出 TikTok / 竖屏版本
  - 质量报告生成

用法：
    from src.exporter import MVExporter
    exporter = MVExporter(project_dir)
    result = exporter.export_all()
"""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Any


class ExporterError(Exception):
    """导出错误"""
    pass


class MVExporter:
    """MV 合成导出器

    处理 Step ⑨-⑪:
      ⑨ 拼接 KB 视频片段
      ⑩ 合并音频 + 叠加字幕
      ⑪ 导出 TikTok/竖屏版本 + 质量报告
    """

    def __init__(self, project_dir: str, ffmpeg: str = "ffmpeg",
                 ffprobe: str = "ffprobe"):
        self.project_dir = Path(project_dir)
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe

        # 路径快捷方式
        self.audio_dir = self.project_dir / "audio"
        self.clips_dir = self.project_dir / "clips"
        self.temp_dir = self.project_dir / "temp"
        self.output_dir = self.project_dir / "output"
        self.metadata_dir = self.project_dir / "metadata"
        self.images_dir = self.project_dir / "images"

        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ══════════════════════════════════════════════════════
    # 公开 API
    # ══════════════════════════════════════════════════════

    def export_all(self) -> Dict[str, Any]:
        """执行完整导出流程（Step ⑨ → ⑩ → ⑪）

        返回:
            {"concat": dict, "merge": dict, "export": dict, "quality_report": dict}
        """
        print("\n  [Step ⑨] 拼接视频片段...")
        concat_result = self.concat_clips()

        if concat_result["status"] != "ok":
            raise ExporterError(f"视频拼接失败: {concat_result.get('error', 'unknown')}")

        print(f"  [OK] 拼接完成: {concat_result.get('size_mb', 0):.1f}MB, "
              f"{concat_result.get('duration_sec', 0)}s")

        print("\n  [Step ⑩] 合并音视频 + 字幕...")
        merge_result = self.merge_audio_subtitles()

        if merge_result["status"] != "ok":
            raise ExporterError(f"音视频合并失败: {merge_result.get('error', 'unknown')}")

        print(f"  [OK] 合并完成: {merge_result.get('size_mb', 0):.1f}MB, "
              f"{merge_result.get('duration_sec', 0)}s")

        print("\n  [Step ⑪] 导出 TikTok/竖屏版本...")
        export_result = self.export_versions()

        print(f"  [OK] TikTok: {export_result.get('tiktok_size_mb', 0):.1f}MB")
        print(f"  [OK] 竖屏: {export_result.get('vertical_size_mb', 0):.1f}MB")

        # 质量报告
        report = self.generate_quality_report()

        return {
            "concat": concat_result,
            "merge": merge_result,
            "export": export_result,
            "quality_report": report,
        }

    # ══════════════════════════════════════════════════════
    # Step ⑨: 视频拼接
    # ══════════════════════════════════════════════════════

    def concat_clips(self) -> Dict[str, Any]:
        """拼接 KB 视频片段

        从 clips/ 目录收集所有 *_scene_kb.mp4 文件，
        使用 ffmpeg concat demuxer 按文件名顺序拼接。

        返回:
            {"status": "ok"|"failed", "clip_count": int,
             "size_mb": float, "duration_sec": int,
             "output": str, "error": str}
        """
        # 收集所有 KB 片段（按文件名排序）
        pattern = "*_scene_kb.mp4"
        clips = sorted(self.clips_dir.glob(pattern))

        if not clips:
            return {"status": "failed", "error": "no clips found",
                    "clip_count": 0}

        # 写入 concat list
        concat_list = self.temp_dir / "concat_list.txt"
        with open(concat_list, "w", encoding="utf-8") as f:
            for clip in clips:
                abs_path = os.path.abspath(str(clip))
                f.write(f"file '{abs_path}'\n")

        video_raw = self.temp_dir / "video_raw.mp4"

        # ffmpeg concat
        cmd = [
            self.ffmpeg, "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            str(video_raw)
        ]

        success, error = self._run_ffmpeg(cmd, log_tag="⑨ concat")
        if not success:
            return {"status": "failed", "error": error, "clip_count": len(clips)}

        if not video_raw.exists():
            return {"status": "failed", "error": "output not created",
                    "clip_count": len(clips)}

        size_mb = video_raw.stat().st_size / (1024 * 1024)
        duration = self._get_duration(str(video_raw))

        return {
            "status": "ok",
            "clip_count": len(clips),
            "size_mb": round(size_mb, 1),
            "duration_sec": duration,
            "output": str(video_raw),
        }

    # ══════════════════════════════════════════════════════
    # Step ⑩: 合并音视频 + 字幕
    # ══════════════════════════════════════════════════════

    def merge_audio_subtitles(self) -> Dict[str, Any]:
        """合并视频、音频和字幕

        输入:
          - temp/video_raw.mp4 (拼接后的无声音视频)
          - audio/song.mp3 (音频)
          - audio/song.srt (字幕，可选)

        输出:
          - output/final.mp4

        返回:
            {"status": "ok"|"failed", "size_mb": float,
             "duration_sec": int, "output": str, "error": str}
        """
        video_raw = self.temp_dir / "video_raw.mp4"
        audio_file = self.audio_dir / "song.mp3"
        srt_file = self.audio_dir / "song.srt"
        final_output = self.output_dir / "final.mp4"

        if not video_raw.exists():
            return {"status": "failed", "error": f"video_raw not found: {video_raw}"}
        if not audio_file.exists():
            return {"status": "failed", "error": f"audio not found: {audio_file}"}

        # 构建 ffmpeg 命令
        cmd = [self.ffmpeg, "-y"]
        cmd += ["-i", str(video_raw)]
        cmd += ["-i", str(audio_file)]

        if srt_file.exists():
            cmd += ["-i", str(srt_file)]
            # 使用字幕流（mov_text 格式，适合 MP4）
            cmd += ["-c:v", "copy", "-c:a", "aac",
                    "-c:s", "mov_text",
                    "-metadata:s:s:0", "language=chi"]
        else:
            cmd += ["-c:v", "copy", "-c:a", "aac"]

        cmd += [str(final_output)]

        success, error = self._run_ffmpeg(cmd, log_tag="⑩ merge")
        if not success or not final_output.exists():
            # 降级：不用字幕流，直接用 -vf subtitles 滤镜
            return self._merge_with_vf_subtitle(video_raw, audio_file, srt_file, final_output)

        size_mb = final_output.stat().st_size / (1024 * 1024)
        duration = self._get_duration(str(final_output))

        # 清理临时文件
        try:
            video_raw.unlink()
        except OSError:
            pass

        return {
            "status": "ok",
            "size_mb": round(size_mb, 1),
            "duration_sec": duration,
            "output": str(final_output),
        }

    def _merge_with_vf_subtitle(self, video_raw: Path, audio_file: Path,
                                 srt_file: Path, final_output: Path) -> Dict[str, Any]:
        """降级方法：使用 subtitles 滤镜烧录字幕（cwd + 相对路径）"""
        if srt_file.exists():
            # 复制到 temp 目录，用 cwd + 相对路径
            temp_video = self.temp_dir / "merge_video.mp4"
            temp_audio = self.temp_dir / "merge_audio.mp3"
            temp_srt = self.temp_dir / "merge_sub.srt"
            temp_out = self.temp_dir / "merge_out.mp4"
            shutil.copy2(str(video_raw), str(temp_video))
            shutil.copy2(str(audio_file), str(temp_audio))
            shutil.copy2(str(srt_file), str(temp_srt))

            cmd = [
                self.ffmpeg, "-y",
                "-i", "merge_video.mp4",
                "-i", "merge_audio.mp3",
                "-vf", "subtitles=merge_sub.srt",
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "merge_out.mp4"
            ]
            success, error = self._run_ffmpeg_cwd(
                cmd, cwd=str(self.temp_dir), log_tag="⑩ merge (vf subtitle cwd)"
            )
            if success and temp_out.exists():
                shutil.move(str(temp_out), str(final_output))
            else:
                success = False
        else:
            success = False

        if not srt_file.exists() or not success or not final_output.exists():
            # 终极降级：无字幕
            cmd2 = [self.ffmpeg, "-y",
                    "-i", str(video_raw),
                    "-i", str(audio_file),
                    "-c:v", "copy", "-c:a", "aac",
                    str(final_output)]
            success2, error2 = self._run_ffmpeg(cmd2, log_tag="⑩ merge (no sub)")

            if not success2 or not final_output.exists():
                return {"status": "failed", "error": error2 or "unknown"}

        size_mb = final_output.stat().st_size / (1024 * 1024)
        duration = self._get_duration(str(final_output))

        try:
            video_raw.unlink()
        except OSError:
            pass

        return {
            "status": "ok",
            "size_mb": round(size_mb, 1),
            "duration_sec": duration,
            "output": str(final_output),
        }

    # ══════════════════════════════════════════════════════
    # Step ⑪: 导出版本
    # ══════════════════════════════════════════════════════

    def export_versions(self) -> Dict[str, Any]:
        """导出 TikTok（横屏字幕版）和竖屏版本

        输入:
          - output/final.mp4
          - audio/song.srt（字幕）

        输出:
          - output/tiktok.mp4（横屏 + 字幕烧录）
          - output/vertical.mp4（竖屏 9:16）

        返回:
            {"status": "ok"|"partial", "tiktok_size_mb": float,
             "vertical_size_mb": float, "tiktok": str, "vertical": str}
        """
        final_output = self.output_dir / "final.mp4"
        srt_file = self.audio_dir / "song.srt"

        if not final_output.exists():
            return {"status": "failed", "error": "final.mp4 not found"}

        tiktok_output = self.output_dir / "tiktok.mp4"
        vertical_output = self.output_dir / "vertical.mp4"

        result = {"status": "ok"}

        # ── TikTok 版本（横屏 + 字幕） ──
        if srt_file.exists():
            # Windows 上 subtitles 滤镜对带盘符/反斜杠的路径非常敏感。
            # 方案：把 final.mp4 和 song.srt 软链接/复制到 temp 目录，
            # 用 subprocess cwd 参数让 ffmpeg 在当前目录工作，只用文件名。
            temp_srt = self.temp_dir / "subs.srt"
            temp_video = self.temp_dir / "input.mp4"
            shutil.copy2(str(final_output), str(temp_video))
            shutil.copy2(str(srt_file), str(temp_srt))

            font = "Microsoft YaHei"
            style = (f"FontName={font},FontSize=28,"
                     f"PrimaryColour=&HFFFFFF,"
                     f"OutlineColour=&H000000,Outline=2,Bold=1,"
                     f"Alignment=2,MarginV=20")
            # 用相对路径，ffmpeg 在 temp 目录下运行
            temp_out = self.temp_dir / "tiktok_tmp.mp4"
            cmd = [
                self.ffmpeg, "-y",
                "-i", "input.mp4",
                "-vf", f"subtitles=subs.srt:force_style='{style}'",
                "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-pix_fmt", "yuv420p",
                "-c:a", "copy",
                "tiktok_tmp.mp4"
            ]
            success, err = self._run_ffmpeg_cwd(
                cmd, cwd=str(self.temp_dir), log_tag="⑪ export tiktok"
            )
            if success and temp_out.exists():
                shutil.move(str(temp_out), str(tiktok_output))
            else:
                # 降级：无字幕直接复制
                print(f"  [!] tiktok 字幕导出失败, 降级为无字幕复制")
                shutil.copy(str(final_output), str(tiktok_output))
        else:
            # 无字幕则直接复制
            shutil.copy(str(final_output), str(tiktok_output))

        if tiktok_output.exists():
            result["tiktok"] = str(tiktok_output)
            result["tiktok_size_mb"] = round(
                tiktok_output.stat().st_size / (1024 * 1024), 1
            )
        else:
            result["tiktok"] = ""
            result["tiktok_size_mb"] = 0
            result["status"] = "partial"

        # ── 竖屏版本（9:16, 使用 TikTok 版本作为输入） ──
        if tiktok_output.exists() and tiktok_output.stat().st_size > 0:
            if tiktok_output.stat().st_size < 1024 * 1024 and final_output.exists():
                source_for_vertical = final_output
            else:
                source_for_vertical = tiktok_output

            cmd = [
                self.ffmpeg, "-y",
                "-i", str(source_for_vertical),
                "-vf", "scale=1080:-1,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
                "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-pix_fmt", "yuv420p",
                "-c:a", "copy",
                str(vertical_output)
            ]
            success_v, _ = self._run_ffmpeg(cmd, log_tag="⑪ export vertical")

        if vertical_output.exists() and vertical_output.stat().st_size > 0:
            result["vertical"] = str(vertical_output)
            result["vertical_size_mb"] = round(
                vertical_output.stat().st_size / (1024 * 1024), 1
            )
        else:
            result["vertical"] = ""
            result["vertical_size_mb"] = 0
            result["status"] = "partial"

        return result

    # ══════════════════════════════════════════════════════
    # 质量报告
    # ══════════════════════════════════════════════════════

    def generate_quality_report(self) -> Dict[str, Any]:
        """生成质量报告并保存到 metadata/quality_report.json

        返回:
            {"song_title": str, "theme": str, ...}
        """
        # 读取 info.json
        info_path = self.metadata_dir / "info.json"
        info = {}
        if info_path.exists():
            info = json.loads(info_path.read_text(encoding="utf-8"))

        # 统计数据
        alignment = info.get("alignment", {})
        aligned = alignment.get("aligned_lines", 0)
        total = alignment.get("total_lyrics_lines", 0)
        rate = round(aligned / total * 100) if total > 0 else 0

        audio_path = self.audio_dir / "song.mp3"
        audio_size_mb = audio_path.stat().st_size / (1024 * 1024) if audio_path.exists() else 0

        final_path = self.output_dir / "final.mp4"
        final_size_mb = final_path.stat().st_size / (1024 * 1024) if final_path.exists() else 0

        images = list(self.images_dir.glob("*.png"))
        clips = list(self.clips_dir.glob("*.mp4"))

        scenes_path = self.metadata_dir / "scenes.json"
        scene_count = 0
        if scenes_path.exists():
            scene_count = len(json.loads(scenes_path.read_text(encoding="utf-8")))

        report = {
            "song_title": info.get("song_title", "N/A"),
            "theme": info.get("theme", ""),
            "alignment_rate": f"{aligned}/{total} ({rate}%)",
            "audio_duration_sec": info.get("audio_duration_sec", 0),
            "audio_size_mb": round(audio_size_mb, 1),
            "final_mv_size_mb": round(final_size_mb, 1),
            "images_count": len(images),
            "clips_count": len(clips),
            "scene_count": scene_count,
            "generated_at": info.get("created_at", ""),
        }

        # 保存报告
        report_path = self.metadata_dir / "quality_report.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        # 打印报告
        print(f"\n  {'='*50}")
        print(f"  📊 MV 质量报告")
        print(f"  {'='*50}")
        print(f"    歌曲: {report['song_title']}")
        print(f"    主题: {report['theme']}")
        print(f"    歌词对齐率: {report['alignment_rate']}")
        print(f"    场景数: {report['scene_count']}")
        print(f"    音频时长: {report['audio_duration_sec']}s")
        print(f"    最终 MV: {report['final_mv_size_mb']}MB")
        print(f"    场景图: {report['images_count']} 张")
        print(f"    KB 片段: {report['clips_count']} 个")
        print(f"  {'='*50}\n")

        return report

    # ══════════════════════════════════════════════════════
    # 内部辅助方法
    # ══════════════════════════════════════════════════════

    def _run_ffmpeg(self, cmd: List[str],
                    log_tag: str = "ffmpeg") -> Tuple[bool, Optional[str]]:
        """执行 ffmpeg 命令，带日志记录

        返回:
            (success: bool, error_msg: Optional[str])
        """
        ffmpeg_log = self.metadata_dir / "ffmpeg.log"
        # 直接 join，日志文件用 UTF-8 编码写入，中文路径不会丢失
        log_line = f"[{log_tag}] {' '.join(cmd)}\n"

        try:
            # 将命令写入日志
            with open(ffmpeg_log, "a", encoding="utf-8") as log:
                log.write(log_line)

            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=600,
            )

            if proc.stdout:
                with open(ffmpeg_log, "a", encoding="utf-8") as log:
                    log.write(proc.stdout.decode("utf-8", errors="replace")[-2000:])
                    log.write("\n")

            if proc.returncode != 0:
                return False, f"ffmpeg exit code {proc.returncode}"

            return True, None

        except subprocess.TimeoutExpired:
            return False, "ffmpeg timed out after 600s"
        except FileNotFoundError:
            return False, f"ffmpeg not found: {self.ffmpeg}"
        except Exception as e:
            return False, str(e)

    def _get_duration(self, file_path: str) -> int:
        """获取媒体文件时长（秒）"""
        try:
            result = subprocess.run(
                [self.ffprobe, "-v", "error", "-show_entries",
                 "format=duration", "-of", "csv=p=0", file_path],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                return int(float(result.stdout.strip()))
        except Exception:
            pass
        return 0

    def _run_ffmpeg_cwd(self, cmd: List[str], cwd: str,
                        log_tag: str = "ffmpeg") -> Tuple[bool, Optional[str]]:
        """在工作目录下执行 ffmpeg，用于 subtitles 滤镜等需要相对路径的场景

        Windows 上 subtitles 滤镜对带盘符路径敏感，用 cwd + 相对路径避免问题。
        """
        ffmpeg_log = self.metadata_dir / "ffmpeg.log"
        log_line = f"[{log_tag}][cwd:{cwd}] {' '.join(cmd)}\n"

        try:
            with open(ffmpeg_log, "a", encoding="utf-8") as log:
                log.write(log_line)

            proc = subprocess.run(
                cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=600,
            )

            if proc.stdout:
                with open(ffmpeg_log, "a", encoding="utf-8") as log:
                    log.write(proc.stdout.decode("utf-8", errors="replace")[-2000:])
                    log.write("\n")

            if proc.returncode != 0:
                return False, f"ffmpeg exit code {proc.returncode}"

            return True, None

        except subprocess.TimeoutExpired:
            return False, "ffmpeg timed out after 600s"
        except FileNotFoundError:
            return False, f"ffmpeg not found: {self.ffmpeg}"
        except Exception as e:
            return False, str(e)
