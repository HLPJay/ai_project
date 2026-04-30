"""
align.py — 歌词时间轴对齐模块（纯 Python，替代原版 align_lyrics.sh）

工作流程：
  ① 人声分离（Demucs，可选）→ ② Whisper ASR 转写 → ③ 两遍匹配对齐
  → ④ 后处理修正 → ⑤ 生成 SRT

核心算法：两遍贪心匹配 + 中文重叠评分 + 后处理插值

用法：
    from src.align import LyricsAligner

    aligner = LyricsAligner()
    result = aligner.run(project_dir="...", align_mode="auto")
    # result.srt_path, result.aligned_lines, result.total_lines
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any


# ════════════════════════════════════════════════════════════
# 相似度评分器
# ════════════════════════════════════════════════════════════

class SimilarityScorer:
    """中日文歌词相似度评分"""

    @staticmethod
    def similarity(a: str, b: str) -> float:
        """整体相似度"""
        a = re.sub(r'[^\w\s]', '', a.lower())
        b = re.sub(r'[^\w\s]', '', b.lower())
        return SequenceMatcher(None, a, b).ratio()

    @staticmethod
    def chinese_overlap(a: str, b: str) -> float:
        """中文字符重叠率（对中文歌词更鲁棒）"""
        ca = set(re.findall(r'[\u4e00-\u9fff]', a))
        cb = set(re.findall(r'[\u4e00-\u9fff]', b))
        return len(ca & cb) / len(ca) if ca else 0

    @staticmethod
    def score_pair(asr_text: str, lyric: str) -> float:
        """综合评分（重叠率加权）"""
        return max(
            SimilarityScorer.similarity(asr_text, lyric),
            SimilarityScorer.chinese_overlap(asr_text, lyric) * 1.2
        )


# ════════════════════════════════════════════════════════════
# Whisper 转写器
# ════════════════════════════════════════════════════════════

class WhisperTranscriber:
    """调用 OpenAI Whisper 进行语音转写

    支持：
    - small / base 模型自动降级
    - 缓存机制（按音频文件 hash）
    - 中文 (zh) 语言指定
    """

    @staticmethod
    def is_available() -> bool:
        """检查 whisper 是否已安装"""
        try:
            import whisper
            return True
        except ImportError:
            return False

    @staticmethod
    def _get_file_hash(file_path: str) -> str:
        """计算文件哈希（用于缓存）"""
        import hashlib
        hasher = hashlib.md5()
        with open(file_path, "rb") as f:
            # 只读前 64KB 加速
            hasher.update(f.read(65536))
        return hasher.hexdigest()

    def transcribe(self, audio_path: str, temp_dir: str,
                   cache: bool = True) -> dict:
        """执行 Whisper 转写

        参数:
            audio_path: MP3/WAV 音频路径
            temp_dir: 临时目录
            cache: 是否使用缓存

        返回:
            whisper 完整输出（含 segments 列表）
        """
        import whisper

        output_json = Path(temp_dir) / "song.json"
        audio_hash = self._get_file_hash(audio_path)

        # 缓存命中
        if cache and output_json.exists() and output_json.stat().st_size > 0:
            try:
                cached = json.loads(output_json.read_text(encoding="utf-8"))
                if cached.get("_source_hash") == audio_hash:
                    print(f"  [OK] Whisper 缓存命中，跳过转写")
                    return cached
            except (json.JSONDecodeError, KeyError):
                pass

        print(f"  [..] Whisper 转写中（small 模型）...")
        print(f"  [..] 音频: {audio_path}")

        # 尝试 small 模型
        model_sizes = ["small", "base", "tiny"]
        last_error = None

        for model_size in model_sizes:
            try:
                print(f"      {model_size} 模型...")
                model = whisper.load_model(model_size)
                result = model.transcribe(
                    audio_path,
                    language="zh",
                    verbose=False,
                )

                # 验证结果
                if not result or not result.get("segments"):
                    print(f"      {model_size} 结果为空，尝试下一个模型")
                    continue

                # 写缓存
                if cache:
                    result["_source_hash"] = audio_hash
                    output_json.write_text(
                        json.dumps(result, ensure_ascii=False),
                        encoding="utf-8"
                    )

                print(f"      [OK] Whisper {model_size}: "
                      f"{len(result['segments'])} 段, "
                      f"{result.get('text', '')[:50]}...")
                return result

            except Exception as e:
                last_error = e
                print(f"      {model_size} 失败: {e}")
                continue

        raise RuntimeError(
            f"Whisper 转写失败（尝试了所有模型）: {last_error}"
        )


# ════════════════════════════════════════════════════════════
# Demucs 人声分离器
# ════════════════════════════════════════════════════════════

class DemucsVocalSeparator:
    """调用 Demucs 分离人声

    输入: song.mp3
    输出: 人声 WAV 文件

    可选依赖，若不可用则使用原始音频。
    """

    @staticmethod
    def is_available() -> bool:
        """检查 demucs 是否可调用"""
        try:
            result = subprocess.run(
                ["demucs", "--help"],
                capture_output=True, text=True, timeout=10
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def separate(self, audio_path: str, temp_dir: str,
                 timeout: int = 600) -> Optional[str]:
        """执行人声分离

        返回:
            人声 WAV 路径，或 None 表示失败
        """
        print(f"  [..] Demucs 人声分离中...")

        demucs_out = Path(temp_dir) / "demucs_out"
        demucs_out.mkdir(parents=True, exist_ok=True)
        log_path = Path(temp_dir) / "demucs.log"

        try:
            result = subprocess.run(
                ["demucs", "--two-stems", "vocals",
                 "-o", str(demucs_out),
                 "--device", "cpu",
                 str(audio_path)],
                capture_output=True, text=True,
                timeout=timeout,
            )

            if result.returncode != 0:
                log_path.write_text(result.stderr, encoding="utf-8")
                print(f"  [!] Demucs 失败 (code={result.returncode}), 使用原始音频")
                return None

            # 查找分离后的人声文件
            basename = Path(audio_path).stem
            candidate = (demucs_out / "htdemucs" / "separated"
                         / basename / "vocals.wav")

            if candidate.exists():
                print(f"  [OK] 人声分离完成: {candidate}")
                return str(candidate)

            print(f"  [!] Demucs 输出未找到: {candidate}")
            return None

        except FileNotFoundError:
            print(f"  [!] demucs 命令未找到，使用原始音频")
            return None
        except subprocess.TimeoutExpired:
            print(f"  [!] Demucs 超时 ({timeout}s)，使用原始音频")
            return None
        except Exception as e:
            print(f"  [!] Demucs 异常: {e}")
            return None


# ════════════════════════════════════════════════════════════
# 时间戳工具
# ════════════════════════════════════════════════════════════

def format_srt_time(seconds: float) -> str:
    """格式化 SRT 时间戳: 00:00:00,000"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_srt_time(timestr: str) -> float:
    """解析 SRT 时间戳为秒"""
    h, m, rest = timestr.split(":")
    s, ms = rest.replace(",", ".").split(".")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_lyrics(lyrics_path: str) -> Tuple[List[str], List[str]]:
    """解析歌词文件

    返回:
        (所有行（含标记）, 纯歌词行（不含段落标记）)
    """
    lines = []
    with open(lyrics_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("## "):
                lines.append(line)

    # 纯歌词行（不含段落标记）
    clean_lines = [
        line for line in lines
        if not re.match(r'^\[.+\]$', line)
    ]
    return lines, clean_lines


# ════════════════════════════════════════════════════════════
# 核心对齐算法
# ════════════════════════════════════════════════════════════

class LyricsAligner:
    """歌词 → SRT 对齐器

    两遍贪心匹配算法：
    - 第一遍：顺序匹配，窗口搜索（找到最佳歌词行）
    - 第二遍：补漏未匹配的歌词行
    - 后处理：插值填充跳行
    """

    def __init__(self, threshold_1: float = 0.25,
                 threshold_2: float = 0.20,
                 search_window: int = 8):
        self.threshold_1 = threshold_1
        self.threshold_2 = threshold_2
        self.search_window = search_window

    def run(self, project_dir: str, align_mode: str = "auto",
            srt_file: str = "", timeout: int = 600) -> Dict[str, Any]:
        """执行完整对齐流程

        参数:
            project_dir: 项目目录
            align_mode: "auto" | "manual"
            srt_file: manual 模式下提供的 SRT 文件路径
            timeout: Demucs/Whisper 超时

        返回:
            {
                "srt_path": str,
                "aligned_lines": int,
                "total_lines": int,
                "srt_entries": int,
                "alignment": List[Dict],
                "status": str,
            }
        """
        project_dir = Path(project_dir)
        audio_path = project_dir / "audio" / "song.mp3"
        lyrics_path = project_dir / "audio" / "lyrics.txt"
        output_srt = project_dir / "audio" / "song.srt"
        temp_dir = project_dir / "temp"

        # 前置检查
        if not audio_path.exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")
        if not lyrics_path.exists():
            raise FileNotFoundError(f"歌词文件不存在: {lyrics_path}")

        temp_dir.mkdir(parents=True, exist_ok=True)

        # ── manual 模式：直接复制 ──
        if align_mode == "manual":
            if not srt_file:
                raise ValueError("manual 模式需要提供 srt_file 参数")
            srt_path = Path(srt_file)
            if not srt_path.exists():
                raise FileNotFoundError(f"SRT 文件不存在: {srt_file}")

            # 解析 SRT 验证格式
            srt_content = srt_path.read_text(encoding="utf-8")
            srt_entries = srt_content.strip().split("\n\n")
            valid_entries = [e for e in srt_entries if " --> " in e]

            output_srt.write_text(srt_content, encoding="utf-8")
            _, clean_lines = parse_lyrics(str(lyrics_path))

            print(f"  [OK] 手动模式 SRT 已复制")
            print(f"  [OK] SRT 条目: {len(valid_entries)}")

            return {
                "srt_path": str(output_srt),
                "aligned_lines": len(valid_entries),
                "total_lines": len(clean_lines),
                "srt_entries": len(valid_entries),
                "alignment": [],
                "status": "completed",
            }

        # ── auto 模式 ──
        start_time = time.time()

        # ① 人声分离（可选）
        if DemucsVocalSeparator.is_available():
            vocal_path = DemucsVocalSeparator().separate(
                str(audio_path), str(temp_dir), timeout
            )
            audio_for_asr = vocal_path or str(audio_path)
        else:
            audio_for_asr = str(audio_path)
            print(f"  [..] Demucs 未安装，使用原始音频")

        # ② Whisper 转写
        if not WhisperTranscriber.is_available():
            raise RuntimeError(
                "Whisper 未安装。请执行: pip install openai-whisper\n"
                "或在 --align-mode manual 下提供 SRT 文件跳过 ASR"
            )

        whisper_result = WhisperTranscriber().transcribe(
            audio_for_asr, str(temp_dir)
        )

        # ③ 两遍匹配对齐
        _, clean_lyrics = parse_lyrics(str(lyrics_path))
        asr_segments = whisper_result.get("segments", [])

        print(f"  [..] 对齐中: {len(clean_lyrics)} 行歌词 ↔ "
              f"{len(asr_segments)} 段 ASR...")

        alignments = self._align(
            clean_lyrics, asr_segments
        )

        # ④ 生成 SRT
        srt_content = self._generate_srt(alignments, clean_lyrics)
        output_srt.write_text(srt_content, encoding="utf-8")

        # 统计
        matched = sum(1 for a in alignments if a["matched"])
        elapsed = time.time() - start_time
        srt_entries = len([a for a in alignments if a["matched"]])

        print(f"")
        print(f"  [OK] 对齐完成 ({elapsed:.1f}s)")
        print(f"  [OK] 对齐: {matched}/{len(clean_lyrics)} 行")
        print(f"  [OK] SRT: {srt_entries} 条目")
        print(f"  [OK] 输出: {output_srt}")
        print(f"")

        # 打印后处理修正信息
        for a in alignments:
            if a.get("interpolated"):
                print(f"      插值行 {a['idx']+1}: "
                      f"~{a['start']:.1f}s-{a['end']:.1f}s "
                      f"\"{a['text'][:20]}...\"")

        return {
            "srt_path": str(output_srt),
            "aligned_lines": matched,
            "total_lines": len(clean_lyrics),
            "srt_entries": srt_entries,
            "alignment": alignments,
            "status": "completed",
        }

    def _align(self, lyrics: List[str],
               asr_segments: List[dict]) -> List[Dict]:
        """两遍对齐算法

        返回:
            [{"idx": int, "text": str, "start": float, "end": float,
              "score": float, "matched": bool, "interpolated": bool}, ...]
        """
        M, N = len(lyrics), len(asr_segments)
        asr_entries = [
            (seg["start"], seg["end"], seg["text"].strip())
            for seg in asr_segments
        ]

        result = []
        for i in range(M):
            result.append({
                "idx": i,
                "text": lyrics[i],
                "start": 0.0,
                "end": 0.0,
                "score": 0.0,
                "matched": False,
                "interpolated": False,
            })

        lyric_assigned = [False] * M
        asr_assigned = [False] * N
        align_map = {}  # lyric_idx -> (start, end, total_score, count)

        # ── 第一遍：顺序贪心匹配 ──
        lyric_idx = 0
        for i, (start, end, text) in enumerate(asr_entries):
            if lyric_idx >= M:
                break
            if len(text) < 2:
                continue

            best_score = 0
            best_li = -1
            for j in range(lyric_idx, min(lyric_idx + self.search_window, M)):
                if lyric_assigned[j]:
                    continue
                s = SimilarityScorer.score_pair(text, lyrics[j])
                if s > best_score:
                    best_score = s
                    best_li = j

            if best_score >= self.threshold_1 and best_li >= 0:
                if best_li in align_map:
                    a = align_map[best_li]
                    align_map[best_li] = (a[0], end, a[2] + best_score, a[3] + 1)
                else:
                    align_map[best_li] = (start, end, best_score, 1)
                lyric_assigned[best_li] = True
                asr_assigned[i] = True
                lyric_idx = best_li + 1

        # ── 第二遍：补漏 ──
        unassigned_asr = [
            (i, asr_entries[i][0], asr_entries[i][1], asr_entries[i][2])
            for i in range(N) if not asr_assigned[i]
        ]

        for j in range(M):
            if lyric_assigned[j]:
                continue
            best_score = 0
            best_entry = None
            for _, start, end, text in unassigned_asr:
                s = SimilarityScorer.score_pair(text, lyrics[j])
                if s > best_score:
                    best_score = s
                    best_entry = (start, end)
            if best_score >= self.threshold_2 and best_entry:
                start, end = best_entry
                if j in align_map:
                    a = align_map[j]
                    align_map[j] = (a[0], end, a[2] + best_score, a[3] + 1)
                else:
                    align_map[j] = (start, end, best_score, 1)
                lyric_assigned[j] = True

        # ── 后处理修正 ──
        # 修正1: 第一行未匹配 → 分配第一个有效 ASR 时间
        if not lyric_assigned[0] and asr_entries:
            for start, end, text in asr_entries:
                if len(text) >= 2:
                    align_map[0] = (start, end, 0.0, 0)
                    lyric_assigned[0] = True
                    print(f"      [post] 第1行分配到首个ASR ({start:.1f}s)")
                    break

        # 修正2: 插值填充跳行
        for j in range(1, M):
            if not lyric_assigned[j]:
                prev_li = -1
                next_li = -1
                for k in range(j - 1, -1, -1):
                    if lyric_assigned[k]:
                        prev_li = k
                        break
                for k in range(j + 1, M):
                    if lyric_assigned[k]:
                        next_li = k
                        break

                if prev_li >= 0 and next_li >= 0:
                    prev_start, prev_end = (
                        align_map[prev_li][0], align_map[prev_li][1]
                    )
                    next_start = align_map[next_li][0]
                    gap = (next_start - prev_end) / (next_li - prev_li + 1)
                    fill_start = prev_end + gap * (j - prev_li)
                    fill_end = fill_start + (prev_end - prev_start)
                    align_map[j] = (fill_start, fill_end, 0.0, 0)
                    lyric_assigned[j] = True

        # ── 填入结果 ──
        for i in range(M):
            if i in align_map:
                start, end, score, count = align_map[i]
                result[i]["start"] = start
                result[i]["end"] = end
                result[i]["score"] = score / max(count, 1)
                result[i]["matched"] = True

        return result

    def _generate_srt(self, alignments: List[Dict],
                      lyrics: List[str]) -> str:
        """生成 SRT 格式内容"""
        srt_parts = []
        for i, a in enumerate(alignments):
            if not a["matched"]:
                continue
            srt_parts.append(
                f"{len(srt_parts) + 1}\n"
                f"{format_srt_time(a['start'])} --> "
                f"{format_srt_time(a['end'])}\n"
                f"{a['text']}\n"
            )
        return "\n".join(srt_parts)


# ════════════════════════════════════════════════════════════
# 便捷函数
# ════════════════════════════════════════════════════════════

def align_lyrics(project_dir: str, align_mode: str = "auto",
                 srt_file: str = "") -> Dict[str, Any]:
    """便捷对齐入口

    参数:
        project_dir: 项目目录
        align_mode: "auto" | "manual"
        srt_file: manual 模式下的 SRT 路径

    返回:
        {"srt_path", "aligned_lines", "total_lines", "srt_entries", "alignment", "status"}
    """
    aligner = LyricsAligner()
    return aligner.run(project_dir, align_mode, srt_file)


def generate_basic_srt(lyrics_text: str, total_duration: float,
                       output_path: str) -> int:
    """生成基础 SRT（均匀分配时间戳，不依赖 ASR）

    用于测试或手动模式下的 fallback。

    返回: SRT 条目数
    """
    _, clean_lines = parse_lyrics_from_text(lyrics_text)

    if not clean_lines:
        return 0

    line_duration = total_duration / len(clean_lines)
    srt_lines = []

    for i, text in enumerate(clean_lines):
        start = i * line_duration
        end = (i + 1) * line_duration
        if end - start < 1.0:
            end = start + 1.0
        srt_lines.append(str(i + 1))
        srt_lines.append(
            f"{format_srt_time(start)} --> {format_srt_time(end)}"
        )
        srt_lines.append(text)
        srt_lines.append("")

    Path(output_path).write_text("\n".join(srt_lines), encoding="utf-8")
    return len(clean_lines)


def parse_lyrics_from_text(lyrics_text: str) -> Tuple[List[str], List[str]]:
    """从文本解析歌词"""
    lines = []
    for line in lyrics_text.strip().split("\n"):
        line = line.strip()
        if line and not line.startswith("## "):
            lines.append(line)

    clean_lines = [
        line for line in lines
        if not re.match(r'^\[.+\]$', line)
    ]
    return lines, clean_lines


# ════════════════════════════════════════════════════════════
# CLI 入口
# ════════════════════════════════════════════════════════════

def main():
    """命令行用法: python -m src.align <project_dir> [--align-mode auto|manual]"""
    import argparse

    parser = argparse.ArgumentParser(
        description="歌词时间轴对齐（替代 align_lyrics.sh）"
    )
    parser.add_argument("project_dir", help="项目目录")
    parser.add_argument("--align-mode", default="auto",
                        choices=["auto", "manual"])
    parser.add_argument("--srt-file", default="",
                        help="manual 模式下的 SRT 文件路径")
    parser.add_argument("--timeout", type=int, default=600,
                        help="Demucs/Whisper 超时秒数")

    args = parser.parse_args()

    print(f"\n{'='*55}")
    print(f"  歌词时间轴对齐 v2 (Python)")
    print(f"  模式: {args.align_mode}")
    print(f"{'='*55}\n")

    result = align_lyrics(
        project_dir=args.project_dir,
        align_mode=args.align_mode,
        srt_file=args.srt_file,
    )

    print(f"\n{'='*55}")
    print(f"  对齐完成!")
    print(f"  SRT: {result['srt_path']}")
    print(f"  对齐: {result['aligned_lines']}/{result['total_lines']} 行")
    print(f"  SRT条目: {result['srt_entries']}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
