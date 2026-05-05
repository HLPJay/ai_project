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
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

from src.config_manager import ConfigManager

logger = logging.getLogger(__name__)

# ── Windows 控制台编码兼容 ──
# Windows 默认 GBK/cp936 编码无法处理某些 Unicode 字符（如 ↔ 箭头）
# 强制 stdout/stderr 使用 UTF-8，避免 UnicodeEncodeError 导致进程崩溃
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        # Python < 3.7 或非交互式环境，忽略
        pass

# ── JSON 安全序列化工具 ──
def _safe_json_default(obj):
    """处理 json.dumps 无法直接序列化的类型（如 numpy 类型）"""
    import numpy as np
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.ndarray,)):
        return obj.tolist()
    if isinstance(obj, (np.str_,)):
        return str(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

def _safe_json_dumps(obj, **kwargs):
    """json.dumps 的安全版本，兼容 numpy 类型。绝对不崩溃。"""
    try:
        return json.dumps(obj, default=_safe_json_default, **kwargs)
    except Exception:
        pass
    try:
        return json.dumps(_recursive_to_python(obj), default=_safe_json_default, **kwargs)
    except Exception:
        pass
    # 终极兜底：逐个字段构建安全的 JSON
    try:
        safe = _recursive_to_python(obj)
        return json.dumps(safe, ensure_ascii=False, skipkeys=True, default=str)
    except Exception as e:
        # 实在不行就返回空JSON，绝不崩溃
        return json.dumps({"error": f"JSON serialization failed: {str(e)[:50]}", "segments": []})

def _recursive_to_python(obj, _depth=0):
    """递归将对象中的所有值转换为纯 Python 类型。绝对安全不崩溃。"""
    if _depth > 100:
        return str(obj) if obj is not None else None
    import numpy as np
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: _recursive_to_python(v, _depth + 1) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_recursive_to_python(item, _depth + 1) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(_recursive_to_python(item, _depth + 1) for item in obj)
    elif isinstance(obj, np.ndarray):
        try:
            return obj.tolist()
        except Exception:
            return list(obj) if hasattr(obj, "__iter__") else [obj.item()]
    elif hasattr(obj, "dtype"):  # numpy 标量类型
        try:
            return obj.item() if hasattr(obj, "item") else str(obj)
        except Exception:
            return float(obj) if hasattr(obj, "__float__") else str(obj)
    if isinstance(obj, str) and len(obj) > 10000:
        return obj[:10000]
    return obj if isinstance(obj, (int, float, bool, str, bytes)) or obj is None else str(obj)


def _resolve_torch_device(config_value: str = "auto") -> str:
    """Resolve auto/cuda/cpu config to a torch-compatible device string."""
    value = (config_value or "auto").strip().lower()
    if value in ("cuda", "cpu"):
        return value
    if value.startswith("cuda:"):
        return value
    if value not in ("auto", ""):
        return value
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _configured_model_chain(primary: str, fallbacks: str) -> List[str]:
    """Build a de-duplicated Whisper model fallback chain."""
    chain = []
    for item in [primary, *(fallbacks or "").split(",")]:
        name = str(item).strip()
        if name and name not in chain:
            chain.append(name)
    return chain or ["medium", "small", "base", "tiny"]


def _run_faster_whisper_worker(audio_path: str,
                               model_sizes: List[str],
                               device: str,
                               language: str,
                               initial_prompt: str) -> dict:
    """Run faster-whisper in an isolated child process."""
    cfg = ConfigManager()
    compute_type = str(cfg.get("align_whisper_compute_type", "default") or "default")
    beam_size = int(cfg.get_int("align_whisper_beam_size", 5))
    vad_filter = bool(cfg.get_bool("align_whisper_vad_filter", True))
    word_timestamps = bool(cfg.get_bool("align_whisper_word_timestamps", False))
    timeout = int(cfg.get_int("align_timeout_sec", 600))

    output_path = Path(tempfile.gettempdir()) / f"mv_asr_{os.getpid()}_{int(time.time() * 1000)}.json"
    cmd = [
        sys.executable,
        "-X", "utf8",
        "-m", "src.align_asr_worker",
        "--audio", str(audio_path),
        "--output", str(output_path),
        "--models", ",".join(model_sizes),
        "--device", str(device),
        "--compute-type", compute_type,
        "--language", str(language or ""),
        "--beam-size", str(beam_size),
        "--initial-prompt", str(initial_prompt or ""),
    ]
    if vad_filter:
        cmd.append("--vad-filter")
    if word_timestamps:
        cmd.append("--word-timestamps")

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        cmd,
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
    )
    if result.stdout:
        logger.debug("faster-whisper worker stdout: %s", result.stdout.rstrip())
    if result.stderr:
        logger.debug("faster-whisper worker stderr: %s", result.stderr.rstrip())

    if output_path.exists() and output_path.stat().st_size > 0:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        try:
            output_path.unlink()
        except Exception:
            pass
        if payload.get("segments"):
            if result.returncode != 0:
                logger.warning("faster-whisper worker exited with code %s, using completed ASR output", result.returncode)
            return payload

    raise RuntimeError(
        f"faster-whisper worker failed with code {result.returncode}: "
        f"{(result.stderr or result.stdout or '')[-1000:]}"
    )


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
        """中文字符重叠率（对中文歌词更鲁棒）

        目标：容忍ASR识别误差，如"无垠"→"乌烟"
        当两个短语共享核心汉字时认为相似
        """
        ca = set(re.findall(r'[\u4e00-\u9fff]', a))
        cb = set(re.findall(r'[\u4e00-\u9fff]', b))
        if not cb:
            return 0.0
        overlap = len(ca & cb)
        # Recall\uff1ab \u7684\u5b57\u7b26\u5728 a \u4e2d\u7684\u8986\u76d6\u7387
        # \u5f53\u662f\u77ed\u6b4c\u8bcd\u884c\u65f6\uff0ca \u662f\u957fASR\u6bb5\u65f6\u6548\u679c\u6700\u597d
        return overlap / len(cb)

    @staticmethod
    def score_pair(asr_text: str, lyric: str) -> float:
        """综合评分（用于匹配ASR识别到原始歌词）

        策略：优先使用中文字符重叠率（对识别误差容忍度高）
        目的：确保即使ASR识别有误（如"无垠"→"乌烟"），
             仍能正确匹配到原始歌词行
        """
        seq_sim = SimilarityScorer.similarity(asr_text, lyric)
        chinese_sim = SimilarityScorer.chinese_overlap(asr_text, lyric)
        # 中文字符重叠率（召回率）权重更高，因为对ASR错误最容忍
        # 给予召回率更高权重以容忍识别误差
        return max(seq_sim * 0.4, chinese_sim * 2.0)


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
        print("  [..] 检查 Whisper 是否可用...", flush=True)
        cfg = ConfigManager()
        backend = str(cfg.get("align_asr_backend", "faster-whisper") or "faster-whisper").strip().lower()
        try:
            if backend in ("faster-whisper", "faster_whisper", "faster", "auto"):
                import faster_whisper  # noqa: F401
            else:
                import whisper  # noqa: F401
            return True
        except ImportError:
            if backend in ("faster-whisper", "faster_whisper", "faster", "auto"):
                try:
                    import whisper  # noqa: F401
                    return True
                except ImportError:
                    return False
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
                   cache: bool = True,
                   initial_prompt: str = "") -> dict:
        """执行 Whisper 转写

        参数:
            audio_path: MP3/WAV 音频路径
            temp_dir: 临时目录
            cache: 是否使用缓存
            initial_prompt: 提示Whisper使用简体中文，提高识别准确度

        返回:
            whisper 完整输出（含 segments 列表）
        """
        output_json = Path(temp_dir) / "song.json"
        audio_hash = self._get_file_hash(audio_path)
        cfg = ConfigManager()
        backend = str(cfg.get("align_asr_backend", "faster-whisper") or "faster-whisper").strip().lower()
        primary_model = str(cfg.get("align_whisper_model", "medium"))
        fallback_models = str(cfg.get("align_whisper_fallback_models", "small,base,tiny"))
        model_sizes = _configured_model_chain(primary_model, fallback_models)
        device = _resolve_torch_device(str(cfg.get("align_whisper_device", "auto")))
        language = str(cfg.get("align_whisper_language", "zh") or "zh")
        backend_cache_key = "faster-whisper" if backend in ("faster-whisper", "faster_whisper", "faster", "auto") else "openai-whisper"
        model_cache_key = ",".join(model_sizes)

        # 缓存命中
        if cache and output_json.exists() and output_json.stat().st_size > 0:
            try:
                cached = json.loads(output_json.read_text(encoding="utf-8"))
                if (
                    cached.get("_source_hash") == audio_hash
                    and cached.get("_asr_backend") == backend_cache_key
                    and cached.get("_asr_models") == model_cache_key
                ):
                    print(f"  [OK] Whisper 缓存命中，跳过转写")
                    return cached
            except (json.JSONDecodeError, KeyError):
                pass

        fp16 = device.startswith("cuda")

        # 默认使用简体中文 prompt 强制简体输出
        if not initial_prompt:
            initial_prompt = "以下是简体中文歌词的转写。"

        print(f"  [..] Whisper 转写中（模型链: {' -> '.join(model_sizes)}, device={device}）...")
        logger.debug("音频: %s", audio_path)
        logger.debug("Initial prompt: %s", initial_prompt[:50])

        if backend in ("faster-whisper", "faster_whisper", "faster", "auto"):
            try:
                result = self._transcribe_faster_whisper(
                    audio_path=audio_path,
                    model_sizes=model_sizes,
                    device=device,
                    language=language,
                    initial_prompt=initial_prompt,
                )
                if cache:
                    result["_source_hash"] = audio_hash
                    result["_asr_backend"] = "faster-whisper"
                    result["_asr_models"] = model_cache_key
                    try:
                        output_json.write_text(
                            _safe_json_dumps(result, ensure_ascii=False),
                            encoding="utf-8"
                        )
                    except Exception as cache_err:
                        logger.warning("缓存写入失败（非致命）: %s", cache_err)
                return result
            except ImportError:
                print("  [!] faster-whisper 未安装，回退到 openai-whisper")
            except Exception as e:
                if backend not in ("auto",):
                    raise
                print(f"  [!] faster-whisper 失败，回退到 openai-whisper: {e}")

        import whisper
        last_error = None
        # openai-whisper 默认不开 word_timestamps，时间戳粒度是 30s 窗口（粗）
        # 开启后基于 cross-attention 做 DTW，时间戳精度提升到词级别
        # 配合 ConfigManager 可以让用户关掉（如果遇到性能问题）
        ow_word_timestamps = bool(cfg.get_bool("align_whisper_word_timestamps", True))

        for model_size in model_sizes:
            try:
                logger.debug("%s 模型 (%s, word_timestamps=%s)...", model_size, device, ow_word_timestamps)
                model = whisper.load_model(model_size, device=device)
                result = model.transcribe(
                    audio_path,
                    language=language,
                    verbose=False,
                    fp16=fp16,
                    initial_prompt=initial_prompt,
                    word_timestamps=ow_word_timestamps,
                )

                # 验证结果
                if not result or not result.get("segments"):
                    logger.info("%s 结果为空，尝试下一个模型", model_size)
                    continue

                # 写缓存
                if cache:
                    result["_source_hash"] = audio_hash
                    result["_asr_backend"] = "openai-whisper"
                    result["_asr_models"] = model_cache_key
                    try:
                        output_json.write_text(
                            _safe_json_dumps(result, ensure_ascii=False),
                            encoding="utf-8"
                        )
                    except Exception as cache_err:
                        logger.warning("缓存写入失败（非致命）: %s", cache_err)

                logger.info("Whisper %s (%s): %d 段, %s...",
                            model_size, device, len(result["segments"]), result.get("text", "")[:50])
                return result

            except Exception as e:
                last_error = e
                logger.error("Whisper %s 失败: %s", model_size, e)
                continue

        raise RuntimeError(
            f"Whisper 转写失败（尝试了所有模型）: {last_error}"
        )


# ════════════════════════════════════════════════════════════
# Demucs 人声分离器
# ════════════════════════════════════════════════════════════

WhisperTranscriber._transcribe_faster_whisper = staticmethod(
    lambda audio_path, model_sizes, device, language, initial_prompt: _run_faster_whisper_worker(
        audio_path=audio_path,
        model_sizes=model_sizes,
        device=device,
        language=language,
        initial_prompt=initial_prompt,
    )
)


class DemucsVocalSeparator:
    """调用 Demucs 分离人声

    输入: song.mp3
    输出: 人声 WAV 文件

    可选依赖，若不可用则使用原始音频。
    """

    @staticmethod
    def is_available() -> bool:
        """检查 demucs 是否可调用"""
        cfg = ConfigManager()
        check_timeout = cfg.get_int("align_demucs_check_timeout_sec", 10)
        print(f"  [..] 检查 Demucs 是否可用（timeout={check_timeout}s）...", flush=True)
        try:
            result = subprocess.run(
                [sys.executable, "-m", "demucs", "--help"],
                capture_output=True, text=True, timeout=check_timeout
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
        cfg = ConfigManager()
        demucs_device = _resolve_torch_device(str(cfg.get("align_demucs_device", "auto")))
        print(f"  [..] Demucs 人声分离中（device={demucs_device}）...", flush=True)

        demucs_out = Path(temp_dir) / "demucs_out"
        demucs_out.mkdir(parents=True, exist_ok=True)
        log_path = Path(temp_dir) / "demucs.log"

        try:
            cmd = [
                sys.executable, "-m", "demucs",
                "--two-stems", "vocals",
                "-o", str(demucs_out),
                "--device", demucs_device,
                str(audio_path),
            ]
            logger.debug("demucs cmd: %s", " ".join(cmd))
            # 用 errors='replace' 避免 Demucs 进度条（GBK/cp936 编码的特殊字符）
            # 在子线程里抛 UnicodeDecodeError（虽然不致命但日志很乱）
            result = subprocess.run(
                cmd,
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=timeout,
            )
            log_path.write_text(
                "STDOUT:\n" + (result.stdout or "") + "\n\nSTDERR:\n" + (result.stderr or ""),
                encoding="utf-8",
            )

            if result.returncode != 0:
                print(f"  [!] Demucs 失败 (code={result.returncode}), 使用原始音频")
                print(f"  [!] Demucs 日志: {log_path}")
                return None

            # 查找分离后的人声文件。Demucs 不同版本/封装的输出目录略有差异。
            basename = Path(audio_path).stem
            candidates = [
                demucs_out / "htdemucs" / basename / "vocals.wav",
                demucs_out / "htdemucs" / "separated" / basename / "vocals.wav",
                demucs_out / basename / "vocals.wav",
            ]
            for candidate in candidates:
                if candidate.exists():
                    logger.info("人声分离完成: %s", candidate)
                    return str(candidate)

            found = list(demucs_out.rglob("vocals.wav"))
            if found:
                logger.info("人声分离完成: %s", found[0])
                return str(found[0])

            print(f"  [!] Demucs 输出未找到: {candidates[0]}")
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
                 search_window: int = 8,
                 max_gap_seconds: float = 5.0):
        self.threshold_1 = threshold_1
        self.threshold_2 = threshold_2
        self.search_window = search_window
        self.max_gap_seconds = max_gap_seconds  # 允许的最大时间间隙

    @staticmethod
    def _load_project_audio_duration(project_dir: Path) -> float:
        """Read the real audio duration recorded by the pipeline, if present."""
        info_path = Path(project_dir) / "metadata" / "info.json"
        try:
            info = json.loads(info_path.read_text(encoding="utf-8"))
            return float(info.get("audio_duration_sec", 0) or 0)
        except Exception:
            return 0.0

    @staticmethod
    def _build_whisper_prompt(lyrics: List[str], max_chars: int = 200) -> str:
        """构造 Whisper 的 initial_prompt

        作用：
        - 强制 Whisper 输出简体中文（避免繁简混杂）
        - 提供风格提示，但不包含具体歌词

        重要：不要在prompt中放具体歌词！
        Whisper会把prompt当作"已识别的前文"，可能跳过这些内容
        导致歌曲开头的几行被漏识别。

        参数:
            lyrics: （未使用，保留接口）
        """
        return "歌词转写，简体中文。"

    def _filter_misrecognized_asr(self, asr_segments: List[dict],
                                   lyrics: List[str],
                                   min_global_coverage: float = 0.35) -> List[dict]:
        """温和过滤 ASR 幻觉段，尽量保留真实时间戳。

        ASR 文本可能有错别字、繁简差异或近音字，但时间戳仍然很有价值。
        因此这里不再因为覆盖率略低就删除，只过滤非常明显的前奏/间奏幻觉：
        高 no_speech_prob、和歌词几乎无关、且文本呈重复无意义形态。
        """
        if not asr_segments or not lyrics:
            return asr_segments

        # 构建全部歌词的字符集（白名单）
        all_lyrics_chars = set()
        for lyric in lyrics:
            all_lyrics_chars.update(re.findall(r'[一-鿿]', lyric))

        if not all_lyrics_chars:
            return asr_segments

        filtered = []
        removed_segs = []

        for seg in asr_segments:
            text = seg.get("text", "").strip()
            asr_chars = re.findall(r'[一-鿿]', text)

            if len(asr_chars) < 3:
                # 太短的段保留
                filtered.append(seg)
                continue

            # 计算ASR段在全部歌词字符集中的覆盖率
            in_lyrics = sum(1 for c in asr_chars if c in all_lyrics_chars)
            coverage = in_lyrics / len(asr_chars)
            no_speech = float(seg.get("no_speech_prob", 0.0) or 0.0)

            if self._is_obvious_asr_hallucination(
                text,
                coverage=coverage,
                no_speech_prob=no_speech,
            ):
                removed_segs.append((seg, coverage))
            else:
                filtered.append(seg)

        if removed_segs:
            logger.info("温和过滤 %d 个明显ASR幻觉段", len(removed_segs))
            for seg, cov in removed_segs:
                logger.debug("  [%.1fs-%.1fs] \"%s\" (覆盖率=%.2f)",
                             seg.get("start", 0.0), seg.get("end", 0.0),
                             (seg.get("text", "") or "")[:30], cov)

        return filtered if filtered else asr_segments

    @staticmethod
    def _write_asr_raw_srt(asr_segments: List[dict], output_path: Path) -> None:
        """Write raw ASR subtitles before lyric-text synchronization.

        This file is the baseline for debugging timestamp issues: it contains
        the native faster-whisper segment times and recognized text, without
        replacing text with the generated lyrics.
        """
        try:
            parts = []
            for seg in sorted(asr_segments or [], key=lambda x: float(x.get("start", 0.0) or 0.0)):
                start = float(seg.get("start", 0.0) or 0.0)
                end = float(seg.get("end", 0.0) or 0.0)
                text = str(seg.get("text", "") or "").strip()
                if end <= start or not text:
                    continue
                parts.append(
                    f"{len(parts) + 1}\n"
                    f"{format_srt_time(start)} --> {format_srt_time(end)}\n"
                    f"{text}\n"
                )
            output_path.write_text("\n".join(parts), encoding="utf-8")
            if parts:
                logger.info("ASR 原生字幕: %s", output_path)
        except Exception as exc:
            logger.warning("ASR 原生字幕写入失败: %s", exc)

    @staticmethod
    def _is_obvious_asr_hallucination(text: str,
                                      coverage: float,
                                      no_speech_prob: float) -> bool:
        """Return True only for clear non-lyric ASR hallucinations."""
        chars = re.findall(r'[\u4e00-\u9fff]', text)
        if len(chars) < 3:
            return False

        unique_ratio = len(set(chars)) / max(1, len(chars))
        repeated_noise = (
            len(chars) >= 5 and unique_ratio <= 0.35
        )
        near_unrelated = coverage < 0.20
        mostly_silence = no_speech_prob >= 0.60
        production_credit = any(
            marker in text
            for marker in (
                "编曲", "作曲", "作词", "演唱", "原唱", "制作人",
                "出品", "发行", "字幕", "词曲", "Composer", "Lyrics",
            )
        ) and coverage < 0.50

        return production_credit or (
            mostly_silence and (near_unrelated or repeated_noise)
        )

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
        cfg = ConfigManager()
        if not cfg.get_bool("align_asr_enabled", True):
            raise ImportError("ALIGN_ASR_ENABLED=false")

        demucs_enabled = cfg.get_bool("align_demucs_enabled", True)
        if demucs_enabled and DemucsVocalSeparator.is_available():
            vocal_path = DemucsVocalSeparator().separate(
                str(audio_path), str(temp_dir), timeout
            )
            audio_for_asr = vocal_path or str(audio_path)
        elif not demucs_enabled:
            audio_for_asr = str(audio_path)
            print(f"  [..] Demucs 已通过配置关闭，使用原始音频")
        else:
            audio_for_asr = str(audio_path)
            print(f"  [..] Demucs 未安装，使用原始音频")

        # ② Whisper 转写
        if not WhisperTranscriber.is_available():
            raise RuntimeError(
                "Whisper 未安装。请执行: pip install openai-whisper\n"
                "或在 --align-mode manual 下提供 SRT 文件跳过 ASR"
            )

        # 提前加载歌词，用于构造 initial_prompt（提高ASR准确度，强制简体）
        _, clean_lyrics = parse_lyrics(str(lyrics_path))
        initial_prompt = self._build_whisper_prompt(clean_lyrics)

        whisper_result = WhisperTranscriber().transcribe(
            audio_for_asr, str(temp_dir),
            initial_prompt=initial_prompt,
        )

        # ③ 两遍匹配对齐
        asr_segments = whisper_result.get("segments", [])
        logger.debug("ASR segments: %d 段", len(asr_segments))
        if asr_segments:
            logger.debug("第一段 keys: %s", list(asr_segments[0].keys()))
            logger.debug("第一段 text: %s", asr_segments[0].get("text", "")[:30])
            logger.debug("第一段 start: %s", asr_segments[0].get("start"))
            logger.debug("第一段 end: %s", asr_segments[0].get("end"))
            import json as _json
            try:
                _json.dumps(asr_segments[0])
                logger.debug("第一段 JSON 序列化 OK")
            except Exception as _je:
                logger.debug("第一段 JSON 序列化失败: %s", _je)
        logger.debug("clean_lyrics: %d 行", len(clean_lyrics))

        # 过滤ASR误识别段（不在歌词中的"幻觉"段，如前奏被识别成奇怪文字）
        print(f"  [..] 过滤 ASR 幻觉段...")
        asr_segments = self._filter_misrecognized_asr(asr_segments, clean_lyrics)
        logger.debug("过滤后: %d 段", len(asr_segments))
        raw_srt_path = project_dir / "audio" / "asr_raw.srt"
        self._write_asr_raw_srt(asr_segments, raw_srt_path)

        # 获取音频总时长（优先使用音乐生成阶段记录的真实音频时长）
        audio_duration = 0.0
        metadata_duration = self._load_project_audio_duration(project_dir)
        if metadata_duration > 0:
            audio_duration = metadata_duration
        elif asr_segments:
            audio_duration = max(seg.get("end", 0.0) for seg in asr_segments)

        print(f"  [..] 对齐中: {len(clean_lyrics)} 行歌词 <-> "
            f"{len(asr_segments)} 段 ASR...")
        print(f"  [..] 音频时长: {audio_duration:.1f}s")

        alignments = self._align(
            clean_lyrics, asr_segments
        )
        self._repair_alignment_timeline(alignments, audio_duration=audio_duration)
        timeline_fallback = False
        timeline_strategy = "asr_line_match"
        if alignments and any(a.get("matched") for a in alignments) and all(
            a.get("fallback") in (
                "asr_segment_timeline",
                "asr_native_timeline",
                "asr_word_timeline",
            )
            for a in alignments
            if a.get("matched")
        ):
            timeline_strategy = "asr_native_sync"
        if self._alignment_timeline_is_suspicious(
            alignments, audio_duration=audio_duration
        ):
            timeline_fallback = True
            if self._apply_asr_segment_timeline(
                alignments, clean_lyrics, asr_segments,
                audio_duration=audio_duration,
            ):
                timeline_strategy = "asr_segment_rebuild"
                logger.info("已按 ASR 段真实时间戳重建原始歌词字幕")
            else:
                timeline_strategy = "uniform_timeline"
                logger.warning("ASR 段不可用，回退到均匀字幕时间轴")
                self._apply_uniform_timeline(
                    alignments, clean_lyrics, audio_duration=audio_duration
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
                logger.debug("插值行 %d: ~%.1fs-%.1fs \"%s...\"",
                             a["idx"] + 1, a["start"], a["end"], a["text"][:20])

        return {
            "srt_path": str(output_srt),
            "aligned_lines": matched,
            "total_lines": len(clean_lyrics),
            "srt_entries": srt_entries,
            "asr_raw_srt_path": str(raw_srt_path),
            "alignment": alignments,
            "timeline_fallback": timeline_fallback,
            "timeline_strategy": timeline_strategy,
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

        if self._apply_asr_segment_timeline(result, lyrics, asr_segments):
            return result

        lyric_assigned = [False] * M
        asr_assigned = [False] * N
        align_map = {}  # lyric_idx -> (start, end, total_score, count)

        # ── 第一遍：顺序贪心匹配（带互为最佳验证） ──
        # 互为最佳：ASR段i 选择的歌词行j，必须 j 选择的最佳ASR段也是 i 附近
        # 否则跳过，避免 ASR 误识别段抢占真实歌词行
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
                # 互为最佳验证：检查所选歌词行 best_li 是否真的最适合 ASR段 i
                # 如果存在另一个更晚的ASR段匹配 best_li 的分数显著更高，跳过
                lyric_text = lyrics[best_li]
                better_match_exists = False
                for k in range(i + 1, min(i + self.search_window + 2, N)):
                    if asr_assigned[k]:
                        continue
                    other_text = asr_entries[k][2]
                    if len(other_text) < 2:
                        continue
                    other_score = SimilarityScorer.score_pair(other_text, lyric_text)
                    # 显著更高（>1.3倍）才认为更好的匹配存在
                    if other_score > best_score * 1.3:
                        better_match_exists = True
                        logger.debug("ASR段%d \"%s\"(%.2f) 放弃匹配行%d，让位给更佳的ASR段%d(%.2f)",
                                     i, text[:20], best_score, best_li + 1, k, other_score)
                        break

                if not better_match_exists:
                    if best_li in align_map:
                        a = align_map[best_li]
                        align_map[best_li] = (a[0], end, a[2] + best_score, a[3] + 1)
                    else:
                        align_map[best_li] = (start, end, best_score, 1)
                    lyric_assigned[best_li] = True
                    asr_assigned[i] = True
                    lyric_idx = best_li + 1

        # ── 第二遍：补漏（包括已分配的ASR段用于多行匹配） ──
        for j in range(M):
            if lyric_assigned[j]:
                continue

            best_score = 0
            best_entry = None

            # 首先在未分配的ASR段中查找
            for i in range(N):
                if asr_assigned[i]:
                    continue
                start, end, text = asr_entries[i]
                s = SimilarityScorer.score_pair(text, lyrics[j])
                if s > best_score:
                    best_score = s
                    best_entry = (i, start, end)

            # 如果未找到，对于最后几行，允许匹配到已分配的ASR段
            # （处理"一个ASR段包含多行歌词"的情况）
            if j >= M - 3 and (best_score < 0.15 or best_entry is None):
                for i in range(N):
                    start, end, text = asr_entries[i]
                    s = SimilarityScorer.score_pair(text, lyrics[j])
                    if s > best_score:
                        best_score = s
                        best_entry = (i, start, end)

            # 宽松阈值：对最后几行的歌词降低门槛
            threshold = self.threshold_2
            if j >= M - 3:  # 最后三行更容易匹配
                threshold = max(self.threshold_2 * 0.5, 0.10)
            if best_score >= threshold and best_entry:
                asr_i, start, end = best_entry
                if j in align_map:
                    a = align_map[j]
                    align_map[j] = (a[0], end, a[2] + best_score, a[3] + 1)
                else:
                    align_map[j] = (start, end, best_score, 1)
                lyric_assigned[j] = True
                # 仅在匹配到未分配的ASR时标记为已分配
                if not asr_assigned[asr_i]:
                    asr_assigned[asr_i] = True

        # ── 后处理修正 ──
        # 修正1: 第一行未匹配 → 分配第一个有效 ASR 时间
        if not lyric_assigned[0] and asr_entries:
            for start, end, text in asr_entries:
                if len(text) >= 2:
                    align_map[0] = (start, end, 0.0, 0)
                    lyric_assigned[0] = True
                    logger.debug("第1行分配到首个ASR (%.1fs)", start)
                    break

        # 修正2: 处理多个歌词行在同一ASR段的情况
        # 如果有相邻的歌词都匹配到同一ASR段，按比例分割时间
        for j in range(M - 1):
            if lyric_assigned[j] and lyric_assigned[j + 1]:
                a_j = align_map[j]
                a_j_next = align_map[j + 1]
                # 如果两行分配到完全相同的时间段，则分割
                if abs(a_j[0] - a_j_next[0]) < 0.01 and abs(a_j[1] - a_j_next[1]) < 0.01:
                    duration = a_j[1] - a_j[0]
                    mid_point = a_j[0] + duration / 2
                    align_map[j] = (a_j[0], mid_point, a_j[2], a_j[3])
                    align_map[j + 1] = (mid_point, a_j[1], a_j_next[2], a_j_next[3])
                    logger.debug("行 %d 和 %d 共享ASR段，已分割时间", j + 1, j + 2)

        # 修正3: 插值填充跳行
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
                # 如果是最后一行且仍未匹配，尝试使用最后一个已匹配行的时间
                elif j == M - 1 and prev_li >= 0:
                    prev_start, prev_end = (
                        align_map[prev_li][0], align_map[prev_li][1]
                    )
                    duration = prev_end - prev_start
                    # 在最后一行分配一段合理的时间
                    align_map[j] = (prev_end, prev_end + duration, 0.0, 0)
                    lyric_assigned[j] = True
                    logger.debug("最后一行 %d 使用插值分配 (%.1fs-%.1fs)", j + 1, prev_end, prev_end + duration)

        # ── 填入结果 ──
        for i in range(M):
            if i in align_map:
                start, end, score, count = align_map[i]
                result[i]["start"] = start
                result[i]["end"] = end
                result[i]["score"] = score / max(count, 1)
                result[i]["matched"] = True

        return result

    @staticmethod
    def _repair_alignment_timeline(alignments: List[Dict],
                                   min_gap: float = 0.05,
                                   min_duration: float = 0.6,
                                   fallback_duration: float = 2.0,
                                   audio_duration: float = 0.0) -> None:
        """Ensure SRT entries follow lyric order on a monotonic timeline.

        Whisper matching can occasionally attach a later lyric line to an
        earlier ASR segment, especially with repeated chorus lines. SRT players
        render by timestamp, so non-monotonic or overlapping entries make
        multi-line captions appear out of order. Keep lyric order authoritative
        and repair timestamps in place.

        参数:
            alignments: 对齐结果列表
            audio_duration: 音频总时长（秒），用于扩展最后一行到音频末尾
        """
        matched = [a for a in alignments if a.get("matched")]
        if not matched:
            return

        repaired = 0
        for a in matched:
            start = float(a.get("start", 0.0) or 0.0)
            end = float(a.get("end", 0.0) or 0.0)
            if end <= start:
                a["end"] = start + fallback_duration
                a["interpolated"] = True
                repaired += 1

        for prev, cur in zip(matched, matched[1:]):
            prev_start = float(prev["start"])
            prev_end = float(prev["end"])
            cur_start = float(cur["start"])
            cur_end = float(cur["end"])

            if cur_start < prev_end + min_gap:
                if prev_end - prev_start > min_duration:
                    prev["end"] = max(prev_start + min_duration, cur_start - min_gap)
                    prev_end = float(prev["end"])

                if cur_start < prev_end + min_gap:
                    shift = prev_end + min_gap - cur_start
                    cur["start"] = cur_start + shift
                    cur["end"] = max(cur_end + shift, cur["start"] + min_duration)
                    cur["interpolated"] = True
                    repaired += 1

            if cur["end"] <= cur["start"]:
                cur["end"] = cur["start"] + fallback_duration
                cur["interpolated"] = True
                repaired += 1

        # 不再把最后一句字幕强行扩展到音频末尾。
        # 音频尾部可能是尾奏/纯音乐，字幕应保留 ASR 的真实演唱时间。
        if matched and audio_duration > 0:
            last = matched[-1]
            last_end = float(last.get("end", 0.0) or 0.0)
            if last_end > audio_duration + 0.5:
                last_start = float(last.get("start", 0.0) or 0.0)
                if last_start >= audio_duration:
                    last["start"] = max(0.0, audio_duration - min_duration)
                last["end"] = audio_duration
                last["interpolated"] = True
                logger.debug("裁剪最后一行到音频末尾 (%.1fs)", audio_duration)
                repaired += 1

        if repaired:
            logger.info("修正 %d 个非单调/重叠字幕时间戳", repaired)

    @staticmethod
    def _alignment_timeline_is_suspicious(alignments: List[Dict],
                                          audio_duration: float = 0.0) -> bool:
        """Detect globally drifted alignments before writing SRT.

        A technically monotonic timeline can still be unusable when repeated
        chorus lines are matched to a late ASR segment. In that case all lyric
        entries are present, but the first subtitle starts near the end of the
        song and the lyric span covers only a small part of the audio.
        """
        if audio_duration <= 0:
            return False

        matched = [a for a in alignments if a.get("matched")]
        if len(matched) < 3:
            return False

        first_start = float(matched[0].get("start", 0.0) or 0.0)
        last_end = max(float(a.get("end", 0.0) or 0.0) for a in matched)
        span = max(0.0, last_end - first_start)
        max_gap = 0.0
        max_gap_after_idx = 0
        short_count = 0
        for idx, (prev, cur) in enumerate(zip(matched, matched[1:]), start=1):
            prev_end = float(prev.get("end", 0.0) or 0.0)
            cur_start = float(cur.get("start", 0.0) or 0.0)
            if float(prev.get("end", 0.0) or 0.0) - float(prev.get("start", 0.0) or 0.0) <= 0.7:
                short_count += 1
            gap = cur_start - prev_end
            if gap > max_gap:
                max_gap = gap
                max_gap_after_idx = idx
        last = matched[-1]
        if float(last.get("end", 0.0) or 0.0) - float(last.get("start", 0.0) or 0.0) <= 0.7:
            short_count += 1

        if first_start > max(30.0, audio_duration * 0.45):
            logger.warning("字幕首句过晚: %.1fs / %.1fs", first_start, audio_duration)
            return True

        if span < audio_duration * 0.35 and first_start > audio_duration * 0.25:
            logger.warning("字幕覆盖范围过窄且整体偏后: span=%.1fs, first=%.1fs, audio=%.1fs",
                           span, first_start, audio_duration)
            return True

        if max_gap > max(12.0, audio_duration * 0.18):
            remaining = len(matched) - max_gap_after_idx
            if remaining >= max(3, len(matched) // 5):
                logger.warning("字幕局部断层过大: gap=%.1fs, after_line=%d, remaining=%d",
                               max_gap, max_gap_after_idx, remaining)
                return True

        if short_count >= max(4, int(len(matched) * 0.25)):
            logger.warning("短字幕过多: %d/%d (<=0.7s)，疑似长 ASR 段拆分失败",
                           short_count, len(matched))
            return True

        if last_end > audio_duration + 5.0:
            logger.warning("字幕末句超出音频过多: %.1fs / %.1fs", last_end, audio_duration)
            return True

        return False

    @staticmethod
    def _apply_asr_segment_timeline(alignments: List[Dict],
                                    lyrics: List[str],
                                    asr_segments: List[dict],
                                    audio_duration: float = 0.0) -> bool:
        """Rebuild lyric-line timestamps from ASR segment timings.

        This keeps the final subtitle text authoritative from the original
        lyrics, while using Whisper only for the real sung time ranges. It is
        safer than a full-song uniform fallback when the line-level matcher has
        drifted to a repeated late chorus.
        """
        if not lyrics or not asr_segments:
            return False

        valid_segments = []
        for seg in sorted(asr_segments, key=lambda x: float(x.get("start", 0.0) or 0.0)):
            start = float(seg.get("start", 0.0) or 0.0)
            end = float(seg.get("end", 0.0) or 0.0)
            text = str(seg.get("text", "") or "").strip()
            if end <= start or len(text) < 2:
                continue
            if audio_duration > 0:
                start = max(0.0, min(start, audio_duration))
                end = max(start + 0.1, min(end, audio_duration))
            valid_segments.append({
                "start": start,
                "end": end,
                "text": text,
                "words": seg.get("words") or [],
            })

        if not valid_segments:
            return False

        lyric_idx = 0
        total_lyrics = len(lyrics)
        total_segments = len(valid_segments)

        if total_segments >= total_lyrics:
            return LyricsAligner._apply_asr_groups_to_lyrics(
                alignments, lyrics, valid_segments
            )

        for seg_idx, seg in enumerate(valid_segments):
            if lyric_idx >= total_lyrics:
                break

            remaining_lyrics = total_lyrics - lyric_idx
            remaining_segments = total_segments - seg_idx
            if remaining_segments <= 1:
                group_size = remaining_lyrics
            else:
                max_group = min(8, remaining_lyrics - (remaining_segments - 1))
                max_group = max(1, max_group)
                target_group = remaining_lyrics / max(1, remaining_segments)
                group_size = LyricsAligner._best_lyric_group_size(
                    seg["text"], lyrics, lyric_idx, max_group,
                    target_size=target_group,
                )

            group = lyrics[lyric_idx: lyric_idx + group_size]
            LyricsAligner._assign_group_to_segment(
                alignments, group, lyric_idx,
                float(seg["start"]), float(seg["end"]),
                seg=seg,
            )
            lyric_idx += group_size

        if lyric_idx < total_lyrics:
            start = valid_segments[-1]["end"]
            end = audio_duration if audio_duration > start else start + max(0.6, total_lyrics - lyric_idx)
            remaining = lyrics[lyric_idx:]
            LyricsAligner._assign_group_to_segment(
                alignments, remaining, lyric_idx, start, end,
                seg=None,
            )

        return all(
            i < len(alignments) and alignments[i].get("matched")
            for i in range(total_lyrics)
        ) and lyric_idx >= total_lyrics

    @staticmethod
    def _apply_asr_groups_to_lyrics(alignments: List[Dict],
                                    lyrics: List[str],
                                    valid_segments: List[dict]) -> bool:
        """Assign consecutive ASR segment groups to consecutive lyric lines.

        When Whisper returns more segments than lyric lines, consuming one lyric
        per ASR segment makes subtitles end too early and discards the later
        native speech timeline. This path keeps every ASR segment in order and
        only decides how many neighboring segments belong to the current lyric.
        """
        total_lyrics = len(lyrics)
        total_segments = len(valid_segments)
        if total_lyrics <= 0 or total_segments < total_lyrics:
            return False

        seg_idx = 0
        for lyric_idx, lyric in enumerate(lyrics):
            remaining_lyrics = total_lyrics - lyric_idx
            remaining_segments = total_segments - seg_idx
            if remaining_lyrics <= 1:
                take = remaining_segments
            else:
                max_take = max(1, remaining_segments - (remaining_lyrics - 1))
                min_take = max(1, remaining_segments - (remaining_lyrics - 1) * 6)
                max_take = min(max_take, max(min_take, 6))
                target_take = remaining_segments / remaining_lyrics
                take = LyricsAligner._best_asr_group_size_for_lyric(
                    lyric, valid_segments, seg_idx, min_take, max_take, target_take
                )

            group = valid_segments[seg_idx: seg_idx + take]
            if not group:
                return False

            start = float(group[0]["start"])
            end = float(group[-1]["end"])
            if end <= start:
                end = start + 0.1
            alignments[lyric_idx].update({
                "idx": lyric_idx,
                "text": lyric,
                "start": start,
                "end": end,
                "score": 0.0,
                "matched": True,
                "interpolated": True,
                "fallback": "asr_native_timeline",
            })
            seg_idx += take

        if seg_idx < total_segments:
            appended = LyricsAligner._append_repeated_tail_segments(
                alignments, lyrics, valid_segments, seg_idx
            )
            if appended:
                logger.info("追加重复歌词字幕: %d 行", appended)

        return all(
            i < len(alignments) and alignments[i].get("matched")
            for i in range(total_lyrics)
        )

    @staticmethod
    def _append_repeated_tail_segments(alignments: List[Dict],
                                       lyrics: List[str],
                                       valid_segments: List[dict],
                                       start_seg_idx: int) -> int:
        """Append ASR tail segments that repeat earlier lyrics.

        Generated songs often repeat the final chorus even when the original
        lyrics file contains it only once. The native ASR timeline is correct,
        so preserve those extra sung segments by mapping each tail ASR segment
        back to the most similar original lyric line and appending a new SRT row.
        """
        appended = 0
        next_idx = len(alignments)
        recent_window_start = max(0, len(lyrics) - 10)
        candidates = list(range(recent_window_start, len(lyrics)))

        for seg in valid_segments[start_seg_idx:]:
            text = str(seg.get("text", "") or "").strip()
            if len(text) < 2:
                continue

            best_idx = -1
            best_score = 0.0
            for lyric_idx in candidates:
                score = SimilarityScorer.score_pair(text, lyrics[lyric_idx])
                if score > best_score:
                    best_score = score
                    best_idx = lyric_idx

            if best_idx < 0 or best_score < 0.20:
                continue

            start = float(seg.get("start", 0.0) or 0.0)
            end = float(seg.get("end", 0.0) or 0.0)
            if end <= start:
                continue

            alignments.append({
                "idx": next_idx,
                "source_idx": best_idx,
                "text": lyrics[best_idx],
                "start": start,
                "end": end,
                "score": best_score,
                "matched": True,
                "interpolated": True,
                "fallback": "asr_repeated_tail",
            })
            next_idx += 1
            appended += 1

        return appended

    @staticmethod
    def _best_asr_group_size_for_lyric(lyric: str,
                                       valid_segments: List[dict],
                                       start_idx: int,
                                       min_take: int,
                                       max_take: int,
                                       target_take: float) -> int:
        """Choose a local consecutive ASR group for one lyric line."""
        best_take = min_take
        best_score = -1.0
        lyric_chars = max(1, len(re.findall(r'[\u4e00-\u9fff]', lyric)) or len(lyric))

        for take in range(min_take, max_take + 1):
            group_text = "".join(
                str(seg.get("text", "") or "")
                for seg in valid_segments[start_idx: start_idx + take]
            )
            asr_chars = max(1, len(re.findall(r'[\u4e00-\u9fff]', group_text)) or len(group_text))
            raw_score = SimilarityScorer.score_pair(group_text, lyric)
            length_ratio = min(asr_chars, lyric_chars) / max(asr_chars, lyric_chars)
            cadence_delta = abs(take - target_take) / max(1.0, target_take)
            cadence_factor = 1.0 - min(0.25, cadence_delta * 0.25)
            score = raw_score * (0.65 + 0.35 * length_ratio) * cadence_factor
            if score > best_score:
                best_score = score
                best_take = take

        return best_take

    @staticmethod
    def _best_lyric_group_size(asr_text: str, lyrics: List[str],
                               start_idx: int, max_group: int,
                               target_size: float = 0.0) -> int:
        """Choose how many original lyric lines belong to one ASR segment."""
        best_size = 1
        best_score = -1.0
        asr_chars = max(1, len(re.findall(r'[\u4e00-\u9fff]', asr_text)))
        target_size = float(target_size or 0.0)

        for size in range(1, max_group + 1):
            candidate = "".join(lyrics[start_idx:start_idx + size])
            lyric_chars = max(1, len(re.findall(r'[\u4e00-\u9fff]', candidate)))
            raw_score = SimilarityScorer.score_pair(asr_text, candidate)
            length_ratio = min(asr_chars, lyric_chars) / max(asr_chars, lyric_chars)
            target_score = 0.0
            if target_size > 0:
                target_score = max(
                    0.0,
                    1.0 - abs(size - target_size) / max(1.0, target_size),
                )

            # ASR often returns long segments containing several lyric lines.
            # Pure similarity over-favors the first line in that segment; blend
            # in length coverage and the expected remaining lyrics/segments
            # cadence so long ASR segments are split into realistic line groups.
            score = raw_score * 0.50 + length_ratio * 0.35 + target_score * 0.15
            if score > best_score:
                best_score = score
                best_size = size

        return best_size

    @staticmethod
    def _assign_group_to_segment(alignments: List[Dict],
                                 group: List[str],
                                 start_idx: int,
                                 seg_start: float,
                                 seg_end: float,
                                 seg: Optional[dict] = None) -> None:
        """Distribute lyric lines inside one ASR segment by text length."""
        if not group:
            return

        if seg and LyricsAligner._assign_group_to_segment_by_words(
            alignments, group, start_idx, seg_start, seg_end, seg
        ):
            return

        duration = max(0.1, seg_end - seg_start)
        weights = [
            max(1, len(re.findall(r'[\u4e00-\u9fff]', text)) or len(text))
            for text in group
        ]
        total_weight = max(1, sum(weights))
        cursor = seg_start

        for offset, text in enumerate(group):
            idx = start_idx + offset
            if offset == len(group) - 1:
                line_end = seg_end
            else:
                line_end = cursor + duration * weights[offset] / total_weight
            if line_end <= cursor:
                line_end = cursor + 0.1
            if idx >= len(alignments):
                alignments.append({"idx": idx})
            alignments[idx].update({
                "idx": idx,
                "text": text,
                "start": cursor,
                "end": line_end,
                "score": 0.0,
                "matched": True,
                "interpolated": True,
                "fallback": "asr_segment_timeline",
            })
            cursor = line_end

    @staticmethod
    def _assign_group_to_segment_by_words(alignments: List[Dict],
                                          group: List[str],
                                          start_idx: int,
                                          seg_start: float,
                                          seg_end: float,
                                          seg: dict) -> bool:
        """Distribute lyric lines with faster-whisper word timestamps."""
        raw_words = seg.get("words") or []
        words = []
        for word in raw_words:
            try:
                start = float(word.get("start"))
                end = float(word.get("end"))
            except Exception:
                continue
            text = str(word.get("word", "") or "").strip()
            if not text or end <= start:
                continue
            units = len(re.findall(r'[\u4e00-\u9fff]', text)) or len(text)
            if units <= 0:
                continue
            words.append({
                "start": max(seg_start, min(start, seg_end)),
                "end": max(seg_start, min(end, seg_end)),
                "text": text,
                "units": units,
            })

        if len(words) < max(2, len(group)):
            return False

        line_units = [
            max(1, len(re.findall(r'[\u4e00-\u9fff]', text)) or len(text))
            for text in group
        ]
        total_line_units = max(1, sum(line_units))
        total_word_units = max(1, sum(word["units"] for word in words))

        boundaries = [0]
        consumed_line_units = 0
        word_unit_cursor = 0
        word_idx = 0
        for units in line_units[:-1]:
            consumed_line_units += units
            target_units = consumed_line_units / total_line_units * total_word_units
            while (
                word_idx < len(words) - 1
                and word_unit_cursor + words[word_idx]["units"] < target_units
            ):
                word_unit_cursor += words[word_idx]["units"]
                word_idx += 1
            boundary = max(boundaries[-1] + 1, min(word_idx + 1, len(words) - 1))
            boundaries.append(boundary)
        boundaries.append(len(words))

        previous_end = seg_start
        for offset, text in enumerate(group):
            idx = start_idx + offset
            begin = boundaries[offset]
            end_idx = boundaries[offset + 1]
            slice_words = words[begin:end_idx]
            if slice_words:
                line_start = max(previous_end, float(slice_words[0]["start"]))
                line_end = float(slice_words[-1]["end"])
            else:
                portion_start = sum(line_units[:offset]) / total_line_units
                portion_end = sum(line_units[:offset + 1]) / total_line_units
                line_start = seg_start + (seg_end - seg_start) * portion_start
                line_end = seg_start + (seg_end - seg_start) * portion_end

            if offset == 0:
                line_start = min(line_start, seg_start)
            if offset == len(group) - 1:
                line_end = max(line_end, seg_end)
            if line_end <= line_start:
                line_end = min(seg_end, line_start + 0.25)
                if line_end <= line_start:
                    line_end = line_start + 0.25

            if idx >= len(alignments):
                alignments.append({"idx": idx})
            alignments[idx].update({
                "idx": idx,
                "text": text,
                "start": line_start,
                "end": line_end,
                "score": 0.0,
                "matched": True,
                "interpolated": True,
                "fallback": "asr_word_timeline",
            })
            previous_end = max(previous_end, line_end)

        return True

    @staticmethod
    def _apply_uniform_timeline(alignments: List[Dict],
                                lyrics: List[str],
                                audio_duration: float = 0.0) -> None:
        """Replace a bad ASR timeline with evenly distributed lyric timing."""
        clean_count = len(lyrics)
        if clean_count <= 0 or audio_duration <= 0:
            return

        line_duration = max(0.6, audio_duration / clean_count)
        for i, text in enumerate(lyrics):
            start = min(i * line_duration, max(0.0, audio_duration - 0.6))
            end = min((i + 1) * line_duration, audio_duration)
            if end <= start:
                end = min(start + 0.6, audio_duration)
            if i >= len(alignments):
                alignments.append({
                    "idx": i,
                    "text": text,
                    "score": 0.0,
                })
            alignments[i].update({
                "idx": i,
                "text": text,
                "start": start,
                "end": end,
                "score": 0.0,
                "matched": True,
                "interpolated": True,
                "fallback": "uniform_timeline",
            })

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
