"""
scripts_bridge.py — 与原版 Shell 脚本的桥接层

负责：
1. 调用原版 scripts/ 目录下的 Shell/Python 脚本
2. 传递正确的环境变量
3. 为 Step ③ 提供纯 Python fallback (align.py)
4. 错误处理

所有路径解析相对于项目根目录（04_music-to-mv/）
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, Any, List

from src.config_manager import ConfigManager


# Windows GBK 控制台兼容
if sys.stdout.encoding and sys.stdout.encoding.upper() in ("GBK", "GB2312", "CP936"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def _get_scripts_dir() -> Path:
    """获取原版 scripts/ 目录路径"""
    v2_root = Path(__file__).resolve().parent.parent
    mono_root = v2_root.parent

    candidates = [
        mono_root / "scripts",
        v2_root / "scripts",
        Path.cwd() / "scripts",
    ]

    for c in candidates:
        if c.exists():
            return c
    return mono_root / "scripts"


def _build_env(project_dir: str, extra_env: Dict = None) -> Dict:
    """构建传递给脚本的环境变量"""
    cfg = ConfigManager()
    env = os.environ.copy()

    env.update({
        "MINIMAX_TOKEN": cfg.get("minimax_token", ""),
        "IMAGE_API_PROVIDER": cfg.get("image_api_provider", "minimax"),
        "LLM_MODEL": cfg.get("llm_model", "MiniMax-M2.7"),
        "PROJECT_DIR": project_dir,
        "FFMPEG": "ffmpeg",
        "FFPROBE": "ffprobe",
    })

    if extra_env:
        env.update(extra_env)

    return env


# ── 脚本执行器 ──────────────────────────────────────────

def run_script(script_name: str, project_dir: str,
               args: List[str] = None, extra_env: Dict = None,
               timeout: int = 600, check: bool = True) -> subprocess.CompletedProcess:
    """运行原版 Shell 脚本（需要 bash）"""
    scripts_dir = _get_scripts_dir()
    script_path = scripts_dir / script_name

    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    env = _build_env(project_dir, extra_env)
    cmd = ["bash", str(script_path), project_dir]
    if args:
        cmd.extend(args)

    print(f"  -> run: {' '.join(cmd)}")

    result = subprocess.run(
        cmd, env=env, capture_output=True, text=True, timeout=timeout,
    )

    if result.stdout:
        lines = result.stdout.strip().split("\n")
        tail = "\n".join(lines[-20:]) if len(lines) > 20 else result.stdout
        for line in tail.split("\n"):
            if line.strip():
                print(f"     {line.strip()}")

    if result.returncode != 0:
        err = result.stderr[-500:] if result.stderr else "no stderr"
        print(f"  !!! returncode {result.returncode}: {err}")

    if check and result.returncode != 0:
        raise RuntimeError(
            f"'{script_name}' failed (code={result.returncode}): "
            f"{result.stderr[-300:] if result.stderr else 'unknown'}"
        )

    return result


def run_python_script(script_name: str, project_dir: str,
                      args: List[str] = None, extra_env: Dict = None,
                      timeout: int = 600) -> subprocess.CompletedProcess:
    """运行原版 Python 脚本"""
    scripts_dir = _get_scripts_dir()
    script_path = scripts_dir / script_name

    if not script_path.exists():
        raise FileNotFoundError(f"Python script not found: {script_path}")

    env = _build_env(project_dir, extra_env)
    cmd = [sys.executable, str(script_path), project_dir]
    if args:
        cmd.extend(args)

    print(f"  -> run: {' '.join(cmd)}")

    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout)

    if result.stdout:
        for line in result.stdout.strip().split("\n")[-15:]:
            if line.strip():
                print(f"     {line.strip()}")

    if result.returncode != 0:
        raise RuntimeError(
            f"'{script_name}' failed (code={result.returncode}): "
            f"{result.stderr[-300:] if result.stderr else 'unknown'}"
        )

    return result


# ── 内部辅助 ────────────────────────────────────────────

def _parse_lyrics_text(lyrics_text: str):
    """从文本解析纯歌词行"""
    lines = []
    for line in lyrics_text.strip().split("\n"):
        line = line.strip()
        if line and not line.startswith("## "):
            lines.append(line)
    clean = [l for l in lines if not re.match(r'^\[.+\]$', l)]
    return lines, clean


# ── 公开 API ────────────────────────────────────────────

def run_align_lyrics(project_dir: str, align_mode: str = "auto",
                     srt_file: str = "", timeout: int = 600) -> dict:
    """歌词时间轴对齐（Step 03）

    策略链：
      1. 原版 Shell (align_lyrics.sh, 需要 bash)
      2. -> Python + Whisper (src.align.LyricsAligner)
      3. -> 基础均匀时间戳 SRT

    返回:
        {"srt_path", "aligned_lines", "total_lines", "srt_entries", "status", "engine"}
    """
    # 策略 1: 原版 Shell
    try:
        shell_args = ["--align-mode", align_mode]
        if srt_file:
            shell_args += ["--srt-file", srt_file]
        result = run_script("align_lyrics.sh", project_dir, shell_args, timeout=timeout)
        if result and result.returncode == 0:
            srt_path = os.path.join(project_dir, "audio", "song.srt")
            if os.path.exists(srt_path):
                srt = open(srt_path, "r", encoding="utf-8").read()
                entries = [e for e in srt.strip().split("\n\n") if " --> " in e]
                lyrics_path = os.path.join(project_dir, "audio", "lyrics.txt")
                if os.path.exists(lyrics_path):
                    _, clean = _parse_lyrics_text(
                        open(lyrics_path, encoding="utf-8").read()
                    )
                    return {
                        "srt_path": srt_path,
                        "aligned_lines": len(entries),
                        "total_lines": len(clean),
                        "srt_entries": len(entries),
                        "status": "completed",
                        "engine": "shell",
                    }
    except (FileNotFoundError, RuntimeError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
        pass

    # 策略 2: Python + Whisper
    print("\n  [..] Try pure Python align (src.align)...")
    from src.align import LyricsAligner, generate_basic_srt

    lyrics_path = os.path.join(project_dir, "audio", "lyrics.txt")

    try:
        import whisper  # noqa: F401
        aligner = LyricsAligner()
        result = aligner.run(
            project_dir=project_dir,
            align_mode=align_mode,
            srt_file=srt_file if align_mode == "manual" else "",
            timeout=timeout,
        )
        result["engine"] = "python+whisper"
        return result
    except ImportError:
        pass

    # 策略 3: 基础 SRT
    from src.project_manager import ProjectManager
    pm = ProjectManager(project_dir)
    audio_duration = pm.get("audio_duration_sec", 0)

    if audio_duration > 0 and os.path.exists(lyrics_path):
        lyrics_text = open(lyrics_path, "r", encoding="utf-8").read()
        srt_path = os.path.join(project_dir, "audio", "song.srt")
        entries = generate_basic_srt(lyrics_text, float(audio_duration), srt_path)
        _, clean = _parse_lyrics_text(lyrics_text)
        print(f"  [OK] Basic SRT done (uniform timestamps)")
        print(f"  [OK] SRT: {srt_path} | entries: {entries}")
        return {
            "srt_path": srt_path,
            "aligned_lines": entries,
            "total_lines": len(clean),
            "srt_entries": entries,
            "status": "completed",
            "engine": "python+basic",
        }

    raise RuntimeError(
        "Lyrics alignment failed. No bash/Whisper/audio_duration available."
    )


def run_analyze_srt(project_dir: str, timeout: int = 180) -> subprocess.CompletedProcess:
    """调用 analyze_srt.py（Step 03.5）

    策略：
      1. 原版 analyze_srt.py（需要 bash/Python 环境）
      2. Python v2 SceneAnalyzer（新实现）
    """
    try:
        return run_python_script("analyze_srt.py", project_dir, timeout=timeout)
    except (FileNotFoundError, RuntimeError, subprocess.TimeoutExpired) as e:
        print(f"  [Bridge] analyze_srt.py 执行失败 ({type(e).__name__}), 回退到 Python v2...")

    try:
        from src.scene_analyzer import SceneAnalyzer
        analyzer = SceneAnalyzer(project_dir)
        analyzer.analyze()
        return subprocess.CompletedProcess(
            args=["python3", "src/scene_analyzer.py"],
            returncode=0,
        )
    except Exception as e2:
        raise RuntimeError(f"所有场景分析策略失败: {e2}") from e2


def run_produce_mv(project_dir: str, step: str = None, timeout: int = 600) -> subprocess.CompletedProcess:
    """调用 produce_mv.sh（Step 04-08）"""
    args = ["--step", step] if step else None
    return run_script("produce_mv.sh", project_dir, args, timeout=timeout)


def run_merge_and_export(project_dir: str, timeout: int = 600) -> subprocess.CompletedProcess:
    """调用 merge_and_export.sh（Step 09-11）

    策略：
      1. 原版 merge_and_export.sh（需要 bash）
      2. Python v2 MVExporter（新实现）
    """
    try:
        return run_script("merge_and_export.sh", project_dir, timeout=timeout)
    except (FileNotFoundError, RuntimeError, subprocess.TimeoutExpired) as e:
        print(f"  [Bridge] merge_and_export.sh 执行失败 ({type(e).__name__}), 回退到 Python v2...")

    try:
        from src.exporter import MVExporter
        exporter = MVExporter(project_dir)
        exporter.export_all()
        return subprocess.CompletedProcess(
            args=["python3", "-m", "src.exporter"],
            returncode=0,
        )
    except Exception as e2:
        raise RuntimeError(f"所有导出策略失败: {e2}") from e2


def run_generate_music(project_dir: str, timeout: int = 180) -> subprocess.CompletedProcess:
    """调用 generate_music.sh（Step 02）"""
    return run_script("generate_music.sh", project_dir, timeout=timeout)


def run_generate_lyrics(project_dir: str, timeout: int = 120) -> subprocess.CompletedProcess:
    """调用 generate_lyrics.sh（Step 01）"""
    return run_script("generate_lyrics.sh", project_dir, timeout=timeout)


def run_init_project(project_dir: str, theme: str, style: str = "动漫风",
                     music_style: str = "流行", mood: str = "温柔",
                     language: str = "中文") -> subprocess.CompletedProcess:
    """调用 init_project.sh"""
    args = [
        "--style", style,
        "--music-style", music_style,
        "--mood", mood,
        "--language", language,
    ]
    return run_script("init_project.sh", project_dir, args)
