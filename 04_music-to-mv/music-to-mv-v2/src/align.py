"""
align.py — 歌词时间轴对齐模块（纯 Python，替代原版 align_lyrics.sh）

工作流程：
  ① 人声分离（Demucs，可选）→ ② Whisper ASR 转写 → ③ 两遍匹配对齐
  → ④ 后处理修正 → ⑤ 生成 SRT

核心算法：连续歌词块匹配 + 相邻 ASR 区间合并 + weak sequential anchor + 时长约束

用法：
    from src.align import LyricsAligner

    aligner = LyricsAligner()
    result = aligner.run(project_dir="...", align_mode="auto")
    # result.srt_path, result.aligned_lines, result.total_lines
"""

import bisect
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
    try:
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
    except ImportError:
        pass
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

def _safe_json_dumps(obj, **kwargs):
    """json.dumps 的安全版本，兼容 numpy 类型。绝对不崩溃。"""
    try:
        return json.dumps(obj, default=_safe_json_default, **kwargs)
    except Exception as e:
        logger.debug("json.dumps 第1次失败，降级到 _recursive_to_python: %s", e)
    try:
        return json.dumps(_recursive_to_python(obj), default=_safe_json_default, **kwargs)
    except Exception as e:
        logger.debug("json.dumps 第2次失败，降级到终极兜底: %s", e)
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
    try:
        import numpy as np
        _has_numpy = True
    except ImportError:
        _has_numpy = False
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: _recursive_to_python(v, _depth + 1) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_recursive_to_python(item, _depth + 1) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(_recursive_to_python(item, _depth + 1) for item in obj)
    elif _has_numpy and isinstance(obj, np.ndarray):
        try:
            return obj.tolist()
        except Exception:
            return list(obj) if hasattr(obj, "__iter__") else [obj.item()]
    elif _has_numpy and hasattr(obj, "dtype"):  # numpy 标量类型
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
                               initial_prompt: str,
                               force_no_vad: bool = False) -> dict:
    """Run faster-whisper in an isolated child process."""
    cfg = ConfigManager()
    compute_type = str(cfg.get("align_whisper_compute_type", "default") or "default")
    beam_size = int(cfg.get_int("align_whisper_beam_size", 5))
    # force_no_vad=True 时忽略配置，Demucs 已分离人声后不需要 VAD
    vad_filter = bool(cfg.get_bool("align_whisper_vad_filter", True)) and not force_no_vad
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
        except Exception as e:
            logger.warning("清理 faster-whisper 输出文件失败: %s", e)
        if payload.get("segments"):
            if result.returncode != 0:
                _win_codes = {
                    3221225477: "ACCESS_VIOLATION (0xC0000005)",
                    3221226505: "STACK_BUFFER_OVERRUN (0xC0000409) — 建议升级 faster-whisper",
                    3221225725: "UNEXPECTED_ERROR (0xC000009D, 常见 CUDA 崩溃)",
                }
                code_desc = _win_codes.get(result.returncode, f"code={result.returncode}")
                logger.warning(
                    "faster-whisper worker 异常退出 [%s]，但已获取完整 ASR 输出，继续处理",
                    code_desc,
                )
            return payload

    raise RuntimeError(
        f"faster-whisper worker failed with code {result.returncode}: "
        f"{(result.stderr or result.stdout or '')[-1000:]}"
    )


# ════════════════════════════════════════════════════════════
# 相似度评分器
# ════════════════════════════════════════════════════════════

class SimilarityScorer:
    """歌词/ASR 相似度评分器。

    歌曲 ASR 的文本经常有错字、漏字、合并句子。这里的评分目标不是
    判断文本是否完全相同，而是判断一个 ASR 片段是否可作为某段歌词的
    时间锚点。

    分数统一归一到 0~1，避免旧版 chinese_overlap * 2.0 导致阈值语义混乱。
    """

    @staticmethod
    def normalize(text: str) -> str:
        """保留有助于歌词匹配的字符，去掉标点和空白。"""
        if not text:
            return ""
        return "".join(
            re.findall(
                r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7afA-Za-z0-9]',
                str(text).lower(),
            )
        )

    @staticmethod
    def similarity(a: str, b: str) -> float:
        """顺序相似度。"""
        a = SimilarityScorer.normalize(a)
        b = SimilarityScorer.normalize(b)
        if not a or not b:
            return 0.0
        return SequenceMatcher(None, a, b).ratio()

    @staticmethod
    def char_recall(asr_text: str, lyric_text: str) -> float:
        """歌词字符被 ASR 覆盖的比例，保留重复字符影响。

        不使用 set overlap，避免“我/你/的/心/梦”等常见字把不相关句子
        误判成高相似度。
        """
        a = SimilarityScorer.normalize(asr_text)
        b = SimilarityScorer.normalize(lyric_text)
        if not a or not b:
            return 0.0

        counts = {}
        for ch in a:
            counts[ch] = counts.get(ch, 0) + 1

        hit = 0
        for ch in b:
            if counts.get(ch, 0) > 0:
                hit += 1
                counts[ch] -= 1
        return hit / max(1, len(b))

    @staticmethod
    def len_ratio(a: str, b: str) -> float:
        """长度匹配度，防止极短文本吃掉过长歌词块。"""
        a = SimilarityScorer.normalize(a)
        b = SimilarityScorer.normalize(b)
        if not a or not b:
            return 0.0
        return min(len(a), len(b)) / max(len(a), len(b))

    @staticmethod
    def chinese_overlap(a: str, b: str) -> float:
        """兼容旧调用：返回 0~1 的中文字符召回率。"""
        return SimilarityScorer.char_recall(a, b)

    @staticmethod
    def score_pair(asr_text: str, lyric: str) -> float:
        """综合评分，返回 0~1。

        - seq: 连续顺序相似度，抑制常见字误匹配。
        - recall: 容忍同音错字/漏字。
        - length: 防止一个短 ASR 片段误匹配很长歌词块。
        """
        seq = SimilarityScorer.similarity(asr_text, lyric)
        recall = SimilarityScorer.char_recall(asr_text, lyric)
        length = SimilarityScorer.len_ratio(asr_text, lyric)
        return 0.50 * seq + 0.35 * recall + 0.15 * length


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
        logger.info("检查 Whisper 是否可用...")
        cfg = ConfigManager()
        backend = cfg.get_str("align_asr_backend", "faster-whisper").lower()
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
        """计算文件哈希（用于缓存）。

        使用完整文件内容 + 文件大小 + 修改时间做哈希，
        避免仅读前64KB导致的缓存误命中。
        """
        import hashlib
        import os
        path = Path(file_path)
        hasher = hashlib.md5()
        # 加入文件大小和修改时间作为哈希的一部分
        stat = path.stat()
        hasher.update(f"{stat.st_size}-{stat.st_mtime}".encode())
        # 读取完整文件内容（音频文件通常几十MB，读完比误判缓存好）
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def transcribe(self, audio_path: str, temp_dir: str,
                   cache: bool = True,
                   initial_prompt: str = "",
                   force_no_vad: bool = False) -> dict:
        """执行 Whisper 转写

        参数:
            audio_path: MP3/WAV 音频路径
            temp_dir: 临时目录
            cache: 是否使用缓存
            initial_prompt: 提示Whisper使用简体中文，提高识别准确度
            force_no_vad: 强制关闭 VAD（Demucs 已分离人声时使用，避免误过滤古典唱腔）

        返回:
            whisper 完整输出（含 segments 列表）
        """
        output_json = Path(temp_dir) / "song.json"
        audio_hash = self._get_file_hash(audio_path)
        cfg = ConfigManager()
        backend = cfg.get_str("align_asr_backend", "faster-whisper").lower()
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
                    logger.info("Whisper 缓存命中，跳过转写")
                    return cached
            except (json.JSONDecodeError, KeyError):
                pass

        fp16 = device.startswith("cuda")

        logger.info("Whisper 转写中（模型链: %s, device=%s）...", f" -> ".join(model_sizes), device)
        logger.debug("音频: %s", audio_path)
        if initial_prompt:
            logger.debug("Initial prompt: %s", initial_prompt[:50])

        if backend in ("faster-whisper", "faster_whisper", "faster", "auto"):
            try:
                result = self._transcribe_faster_whisper(
                    audio_path=audio_path,
                    model_sizes=model_sizes,
                    device=device,
                    language=language,
                    initial_prompt=initial_prompt,
                    force_no_vad=force_no_vad,
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
                logger.warning("faster-whisper 未安装，回退到 openai-whisper")
            except Exception as e:
                if backend not in ("auto",):
                    raise
                logger.warning("faster-whisper 失败，回退到 openai-whisper: %s", e)

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

    @staticmethod
    def _transcribe_faster_whisper(audio_path: str, model_sizes: List[str],
                                   device: str, language: str,
                                   initial_prompt: str,
                                   force_no_vad: bool = False) -> dict:
        """调用 faster-whisper 进行语音转写（子进程模式）"""
        return _run_faster_whisper_worker(
            audio_path=audio_path,
            model_sizes=model_sizes,
            device=device,
            language=language,
            initial_prompt=initial_prompt,
            force_no_vad=force_no_vad,
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
        """检查 demucs 是否已安装（用 importlib 检查，避免启动子进程触发 torch 冷启动超时）"""
        import importlib.util
        logger.info("检查 Demucs 是否可用...")
        return importlib.util.find_spec("demucs") is not None

    def separate(self, audio_path: str, temp_dir: str,
                 timeout: int = 600) -> Optional[str]:
        """执行人声分离

        返回:
            人声 WAV 路径，或 None 表示失败（自动回退原始音频）
        """
        cfg = ConfigManager()
        demucs_device = _resolve_torch_device(str(cfg.get("align_demucs_device", "auto")))
        logger.info("Demucs 人声分离中（device=%s）...", demucs_device)

        demucs_out = Path(temp_dir) / "demucs_out"
        demucs_out.mkdir(parents=True, exist_ok=True)
        log_path = Path(temp_dir) / "demucs.log"

        _win_crash_codes = {
            3221225477,   # 0xC0000005 ACCESS_VIOLATION
            3221226505,   # 0xC0000409 STACK_BUFFER_OVERRUN
            3221225725,   # 0xC000009D UNEXPECTED_ERROR (常见 CUDA 崩溃)
        }

        max_retries = 2
        for attempt in range(max_retries + 1):
            cmd = [
                sys.executable, "-m", "demucs",
                "--two-stems", "vocals",
                "-o", str(demucs_out),
                "--device", demucs_device,
                str(audio_path),
            ]
            logger.debug("demucs cmd (attempt %d): %s", attempt + 1, " ".join(cmd))

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                    timeout=timeout,
                )
                log_path.write_text(
                    f"[attempt {attempt + 1}]\n"
                    f"STDOUT:\n{result.stdout or ''}\n\nSTDERR:\n{result.stderr or ''}",
                    encoding="utf-8",
                )

                if result.returncode == 0:
                    break  # 成功，跳出重试循环

                # 非零退出码，判断是否 CUDA 崩溃并自动降级
                crashed_on_gpu = (
                    demucs_device != "cpu"
                    and result.returncode in _win_crash_codes
                )
                if crashed_on_gpu and attempt < max_retries:
                    logger.warning(
                        "Demucs CUDA 崩溃 (code=%d)，自动降级 CPU 重试 (attempt %d/%d)",
                        result.returncode, attempt + 1, max_retries + 1,
                    )
                    # 替换 device 参数为 cpu，重新构建命令
                    cmd = [
                        sys.executable, "-m", "demucs",
                        "--two-stems", "vocals",
                        "-o", str(demucs_out),
                        "--device", "cpu",
                        str(audio_path),
                    ]
                    demucs_device = "cpu"  # 后续使用 CPU
                    continue  # 重试

                # 非崩溃错误 或 已是最后一次重试 → 回退原始音频
                logger.warning(
                    "Demucs 失败 (code=%d, attempt %d/%d), 使用原始音频",
                    result.returncode, attempt + 1, max_retries + 1,
                )
                return None

            except FileNotFoundError:
                logger.warning("demucs 命令未找到，使用原始音频")
                return None
            except subprocess.TimeoutExpired:
                logger.warning("Demucs 超时 (%ds, attempt %d/%d), 使用原始音频",
                              timeout, attempt + 1, max_retries + 1)
                return None
            except Exception as e:
                logger.warning("Demucs 异常 (attempt %d/%d): %s",
                              attempt + 1, max_retries + 1, e)
                if attempt < max_retries:
                    import time as _time
                    _time.sleep(min(2 ** attempt, 8))  # 指数退避，上限 8s
                    continue
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

        logger.warning("Demucs 输出未找到: %s", candidates[0])
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


def _validate_srt_block(block: str) -> Tuple[bool, str]:
    """验证单个 SRT 块格式是否合法。

    返回: (是否合法, 错误原因)
    """
    lines = block.strip().split("\n")
    if len(lines) < 3:
        return False, "块行数不足（需要索引+时间戳+文本，最少3行）"

    # 第1行: 索引号
    try:
        idx = int(lines[0].strip())
        if idx <= 0:
            return False, f"索引号必须为正整数，实际: {idx}"
    except ValueError:
        return False, f"索引号格式错误: {lines[0].strip()}"

    # 第2行: 时间戳
    ts_line = lines[1].strip()
    if " --> " not in ts_line:
        return False, f"时间戳行缺少 ' --> ': {ts_line}"

    try:
        start_str, end_str = ts_line.split(" --> ")
        start = parse_srt_time(start_str.strip())
        end = parse_srt_time(end_str.strip())
        if end <= start:
            return False, f"结束时间({end:.3f})应大于开始时间({start:.3f})"
    except Exception as e:
        return False, f"时间戳解析失败: {e}"

    return True, ""


def validate_srt_content(srt_content: str) -> Tuple[bool, str, List[int]]:
    """验证 SRT 内容格式是否合法。

    返回: (是否完全合法, 错误信息, 有效块索引列表)
    """
    blocks = srt_content.strip().split("\n\n")
    valid_indices = []
    errors = []

    expected_idx = 1
    for i, block in enumerate(blocks):
        block = block.strip()
        if not block:
            continue

        lines = block.split("\n")
        # 检查是否有时间戳行
        if not any(" --> " in line for line in lines):
            errors.append(f"块{i+1}: 缺少时间戳行")
            continue

        valid, err = _validate_srt_block(block)
        if valid:
            try:
                idx = int(lines[0].strip())
                valid_indices.append(idx)
                if idx != expected_idx:
                    errors.append(f"块{i+1}: 索引号应为{expected_idx}，实际{idx}")
                expected_idx = idx + 1
            except ValueError:
                errors.append(f"块{i+1}: 索引号解析失败")
        else:
            errors.append(f"块{i+1}: {err}")

    if errors:
        return False, "; ".join(errors[:5]), valid_indices
    return True, "", valid_indices


def _parse_srt_to_segments(srt_content: str) -> List[Dict]:
    """把 SRT 内容转换为 ASR 片段格式（用于 manual 模式复用对齐算法）"""
    blocks = srt_content.strip().split("\n\n")
    segments = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n")
        if len(lines) < 2:
            continue
        ts_line = next((l for l in lines if " --> " in l), None)
        if not ts_line:
            continue
        try:
            start_str, end_str = ts_line.split(" --> ")
            start = parse_srt_time(start_str.strip())
            end = parse_srt_time(end_str.strip())
        except Exception:
            continue
        # 文本是时间戳行之后的所有行
        ts_idx = lines.index(ts_line)
        text = " ".join(l.strip() for l in lines[ts_idx + 1:] if l.strip())
        if text or (start is not None):
            segments.append({
                "text": text,
                "start": start,
                "end": end,
            })
    return segments


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

    块匹配算法：
    - lyrics.txt 是权威文本，ASR 只作为人声时间锚点。
    - 先做当前位置附近的连续歌词块匹配，必要时合并相邻 ASR 段。
    - 文本强匹配用 strong anchor；文本差但位置/时长合理时用 weak sequential anchor。
    - 缺失行最后才插值，重复/乱序段单独用更严格阈值插入。
    """

    def __init__(self, threshold_1: float = 0.42,
                 threshold_2: float = 0.35,
                 search_window: int = 10,
                 max_gap_seconds: float = 5.0,
                 weak_anchor_threshold: float = 0.18,
                 weak_anchor_max_offset: int = 1,
                 enable_weak_anchor: bool = True):
        # strong / normal thresholds：文本相似度较高时直接使用 ASR 时间锚点。
        self.threshold_1 = threshold_1
        self.threshold_2 = threshold_2
        self.search_window = search_window
        self.max_gap_seconds = max_gap_seconds

        # weak sequential anchor：用于“ASR 有人声时间戳，但识别文字差距大”的场景。
        # 只在主顺序流程中使用，不参与重复/乱序插入。
        self.enable_weak_anchor = enable_weak_anchor
        self.weak_anchor_threshold = weak_anchor_threshold
        self.weak_anchor_max_offset = max(0, int(weak_anchor_max_offset))
        self.weak_anchor_min_duration_ratio = 0.38

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

        从歌词中提取 2-4 字的去重关键词，拼成逗号分隔列表。
        Whisper 把 initial_prompt 当作"已识别的前文上下文"，解码时
        优先选用 prompt 中出现过的词汇，大幅减少同音/近音字错误。

        只放短关键词，不放完整歌词句子——完整句子会导致 Whisper
        认为"已经识别过了"而跳过歌曲开头。
        """
        if not lyrics:
            return "简体中文歌词转写。"

        # 先按标点分割，再提取 2-4 字的中文片段作为关键词
        seen: set = set()
        keywords: list = []
        for line in lyrics:
            segments = re.split(r'[，。！？、,.\s]+', line)
            for seg in segments:
                words = re.findall(r'[一-鿿]{2,4}', seg)
                for w in words:
                    if w not in seen:
                        seen.add(w)
                        keywords.append(w)

        if not keywords:
            return "简体中文歌词转写。"

        prefix = "简体中文歌词。"
        result_parts = [prefix]
        current_len = len(prefix)
        for kw in keywords:
            addition = kw + "，"
            if current_len + len(addition) > max_chars:
                break
            result_parts.append(addition)
            current_len += len(addition)

        prompt = "".join(result_parts).rstrip("，") + "。"
        return prompt

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

    @staticmethod
    def _is_probably_non_lyric_text(text: str) -> bool:
        """过滤明显不是歌词的 ASR 标签。

        规则故意保守：只过滤明确乐器/制作/字幕/版权/占位标签。
        短英文歌词如 Baby / Oh yeah / My love 不会仅因英文而被删除。
        """
        raw = str(text or "").strip()
        if not raw:
            return True

        lowered = raw.lower().strip(" .。!！?？,，:：;；-—_[]()（）")
        compact = re.sub(r"[^a-z0-9一-鿿]+", " ", lowered).strip()

        explicit_markers = (
            "instrumental", "interlude", "backing track", "karaoke",
            "music", "bgm", "sound effect", "sfx", "subtitle",
            "lyrics by", "composer", "arranger", "produced by",
            "copyright", "all rights reserved", "zither harp",
        )
        if any(marker in lowered for marker in explicit_markers):
            return True

        # 明确乐器名组成的短标签。
        instrument_words = {
            "zither", "harp", "piano", "guitar", "violin", "cello",
            "drum", "drums", "bass", "synth", "synthesizer", "flute",
            "strings", "trumpet", "sax", "saxophone", "percussion",
        }
        words = [w for w in re.split(r"\s+", compact) if w]
        has_cjk = bool(re.search(r"[一-鿿]", raw))
        if words and not has_cjk and len(words) <= 3 and all(w in instrument_words for w in words):
            return True

        production_markers = (
            "编曲", "作曲", "作词", "演唱", "原唱", "制作人",
            "出品", "发行", "字幕", "词曲", "版权所有",
        )
        if any(marker in raw for marker in production_markers):
            return True

        return False

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

        # ── manual 模式：用用户 SRT 的时间戳，对齐原始歌词 ──
        if align_mode == "manual":
            if not srt_file:
                raise ValueError("manual 模式需要提供 srt_file 参数")
            srt_path = Path(srt_file)
            if not srt_path.exists():
                raise FileNotFoundError(f"SRT 文件不存在: {srt_file}")

            srt_content = srt_path.read_text(encoding="utf-8")
            is_valid, err_msg, valid_indices = validate_srt_content(srt_content)
            if not is_valid:
                logger.warning("SRT 文件格式存在警告（非致命）: %s", err_msg)

            # 把用户 SRT 的时间戳转换为 ASR 片段格式
            user_segments = _parse_srt_to_segments(srt_content)
            if not user_segments:
                raise ValueError(f"SRT 文件无法解析出有效片段: {srt_file}")

            # 复用 auto 模式的过滤+对齐流程（跳过 Whisper 转写步骤）
            _, clean_lyrics = parse_lyrics(str(lyrics_path))
            logger.info("手动模式: 从 SRT 解析到 %d 个时间片段", len(user_segments))

            # 过滤幻觉片段
            user_segments = self._filter_misrecognized_asr(user_segments, clean_lyrics)
            logger.info("过滤幻觉后: %d 段", len(user_segments))

            # 获取音频时长
            audio_duration = 0.0
            metadata_duration = self._load_project_audio_duration(project_dir)
            if metadata_duration > 0:
                audio_duration = metadata_duration
            elif user_segments:
                audio_duration = max(seg.get("end", 0.0) for seg in user_segments)

            logger.info("对齐中: %d 行歌词 <-> %d 段 SRT...", len(clean_lyrics), len(user_segments))
            logger.info("音频时长: %.1fs", audio_duration)

            # 手动模式：直接匹配，不走 auto 模式的两遍贪心 + 时间重组算法
            # 逻辑：每个歌词行匹配最佳 SRT 片段，用该片段的原始时间戳；
            #       多个歌词行匹配同一片段时按字数比例分割时间。
            alignments = self._align_manual(clean_lyrics, user_segments)
            self._repair_alignment_timeline(alignments, audio_duration=audio_duration)

            # 生成 SRT
            srt_content = self._generate_srt(alignments, clean_lyrics)
            output_srt.write_text(srt_content, encoding="utf-8")

            matched = sum(1 for a in alignments if a["matched"])
            srt_entries = len([a for a in alignments if a["matched"]])

            logger.info("手动模式对齐完成: %d/%d 行", matched, len(clean_lyrics))
            logger.info("SRT: %d 条目", srt_entries)
            logger.info("输出: %s", output_srt)

            return {
                "srt_path": str(output_srt),
                "aligned_lines": matched,
                "total_lines": len(clean_lyrics),
                "srt_entries": srt_entries,
                "alignment": self._alignment_debug_payload(alignments),
                "status": "completed",
            }

        # ── auto 模式 ──
        start_time = time.time()

        # ① 人声分离（可选）
        cfg = ConfigManager()
        if not cfg.get_bool("align_asr_enabled", True):
            raise ImportError("ALIGN_ASR_ENABLED=false")

        demucs_enabled = cfg.get_bool("align_demucs_enabled", True)
        demucs_succeeded = False
        if demucs_enabled and DemucsVocalSeparator.is_available():
            vocal_path = DemucsVocalSeparator().separate(
                str(audio_path), str(temp_dir), timeout
            )
            audio_for_asr = vocal_path or str(audio_path)
            demucs_succeeded = bool(vocal_path)
        elif not demucs_enabled:
            audio_for_asr = str(audio_path)
            logger.info("Demucs 已通过配置关闭，使用原始音频")
        else:
            audio_for_asr = str(audio_path)
            logger.info("Demucs 未安装，使用原始音频")

        # ② Whisper 转写
        if not WhisperTranscriber.is_available():
            raise RuntimeError(
                "Whisper 未安装。请执行: pip install openai-whisper\n"
                "或在 --align-mode manual 下提供 SRT 文件跳过 ASR"
            )

        _, clean_lyrics = parse_lyrics(str(lyrics_path))

        whisper_result = WhisperTranscriber().transcribe(
            audio_for_asr, str(temp_dir),
            initial_prompt="简体中文歌曲歌词转写。",
            force_no_vad=demucs_succeeded,
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
        logger.info("过滤 ASR 幻觉段...")
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

        logger.info("对齐中: %d 行歌词 <-> %d 段 ASR...", len(clean_lyrics), len(asr_segments))
        logger.info("音频时长: %.1fs", audio_duration)

        # 统一用 _align_manual：顺序分配 + 保留原始时间戳
        # auto 和 manual 模式共用同一套算法，不再有 fallback 重组逻辑
        alignments = self._align_manual(clean_lyrics, asr_segments)
        self._repair_alignment_timeline(alignments, audio_duration=audio_duration)

        # ④ 生成 SRT
        srt_content = self._generate_srt(alignments, clean_lyrics)
        output_srt.write_text(srt_content, encoding="utf-8")

        # 统计
        matched = sum(1 for a in alignments if a["matched"])
        elapsed = time.time() - start_time
        srt_entries = len([a for a in alignments if a["matched"]])

        logger.info("对齐完成 (%.1fs)", elapsed)
        logger.info("对齐: %d/%d 行", matched, len(clean_lyrics))
        logger.info("SRT: %d 条目", srt_entries)
        logger.info("输出: %s", output_srt)

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
            "alignment": self._alignment_debug_payload(alignments),
            "status": "completed",
        }

    def _line_weight(self, text: str) -> int:
        """歌词行分配时间时的权重。"""
        return max(1, len(SimilarityScorer.normalize(text)))

    @staticmethod
    def _init_alignment_result(lyrics: List[str]) -> List[Dict[str, Any]]:
        return [
            {
                "idx": i,
                "text": lyrics[i],
                "start": 0.0,
                "end": 0.0,
                "score": 0.0,
                "matched": False,
                "interpolated": False,
                "_source": "",
                "_srt_idx": -1,
                "_srt_idx_end": -1,
                "_asr_text": "",
                "_matched_block": "",
                "low_confidence": False,
                "_match_kind": "",
            }
            for i in range(len(lyrics))
        ]

    def _min_readable_duration_for_line(self, text: str) -> float:
        """估算一行歌词的最低可唱/可读时长。

        注意：这是“完整歌词行”的最低时长，不是 SRT 技术合法时长。
        目标是避免 6~8 个中文字被压到 0.3s 这种明显不合理的时间段。
        """
        norm = SimilarityScorer.normalize(text)
        n = len(norm)
        if n <= 0:
            return 0.30
        if n <= 1:
            return 0.30
        if n <= 2:
            return 0.45
        if n <= 4:
            return 0.70
        if n <= 7:
            return 0.95
        if n <= 11:
            return 1.15
        return 1.35

    def _block_required_duration(self, lyrics: List[str], start_i: int, end_i: int) -> float:
        """连续歌词块的最低合理承载时长。"""
        if end_i <= start_i:
            return 0.0
        return sum(self._min_readable_duration_for_line(lyrics[i]) for i in range(start_i, end_i))

    def _duration_fit(self,
                      lyrics: List[str],
                      start_i: int,
                      end_i: int,
                      duration: float) -> Tuple[float, float]:
        """返回 (duration_ratio, required_duration)。"""
        required = max(0.05, self._block_required_duration(lyrics, start_i, end_i))
        ratio = max(0.0, float(duration)) / required
        return ratio, required

    def _duration_can_hold_block(self,
                                 lyrics: List[str],
                                 start_i: int,
                                 end_i: int,
                                 duration: float,
                                 min_ratio: float = 0.45) -> bool:
        """判断时间区间是否足够承载歌词块。

        min_ratio 不设为 1.0，是因为唱歌可能比朗读快，且 Whisper 边界常偏短。
        主顺序匹配可宽松一些；重复/乱序插入要更严格。
        """
        ratio, _ = self._duration_fit(lyrics, start_i, end_i, duration)
        return ratio >= min_ratio

    def _estimate_avg_line_len(self, lyrics: List[str]) -> float:
        lengths = [self._line_weight(line) for line in lyrics if SimilarityScorer.normalize(line)]
        if not lengths:
            return 6.0
        return max(1.0, sum(lengths) / len(lengths))

    def _estimate_max_block_lines(self, asr_text: str, duration: float, lyrics: List[str]) -> int:
        """根据 ASR 文本长度和时间长度动态估算最多匹配几行歌词。

        旧版固定 1~4 行，会在快歌/长段副歌里不够，也会在短 segment 上过度匹配。
        这里同时受文本长度和时长约束，最大允许 8 行。
        """
        norm_len = len(SimilarityScorer.normalize(asr_text))
        avg_len = self._estimate_avg_line_len(lyrics)
        by_text = int(round(norm_len / avg_len)) + 1
        by_time = int(max(1.0, float(duration)) / 0.70) + 1
        return max(1, min(8, max(by_text, by_time)))

    def _merge_gap_limit(self) -> float:
        """允许合并相邻 ASR segment 的最大静音间隔。"""
        return max(0.35, min(float(self.max_gap_seconds or 5.0), 1.20))

    def _build_segment_group(self,
                             srt_entries: List[Tuple[float, float, str]],
                             start_idx: int,
                             end_idx: int) -> Tuple[float, float, str]:
        """把 [start_idx, end_idx] 的 ASR/SRT 段合并成一个候选时间区间。"""
        seg_start = float(srt_entries[start_idx][0])
        seg_end = float(srt_entries[end_idx][1])
        text = " ".join(
            str(srt_entries[i][2] or "").strip()
            for i in range(start_idx, end_idx + 1)
            if str(srt_entries[i][2] or "").strip()
        )
        return seg_start, seg_end, text

    def _assign_segment_to_lyric_block(self,
                                      result: List[Dict[str, Any]],
                                      lyrics: List[str],
                                      start_i: int,
                                      end_i: int,
                                      seg_start: float,
                                      seg_end: float,
                                      score: float,
                                      seg_idx: int,
                                      seg_idx_end: Optional[int] = None,
                                      source: str = "block",
                                      asr_text: str = "",
                                      low_confidence: bool = False,
                                      match_kind: str = "strong") -> None:
        """把一个 ASR/SRT 时间区间按字符权重分配给连续歌词块。

        这个时间区间可以来自单个 ASR segment，也可以来自多个相邻 segment 的合并。
        """
        if end_i <= start_i:
            return

        seg_start = float(seg_start)
        seg_end = float(seg_end)
        duration = max(0.05, seg_end - seg_start)
        indices = list(range(start_i, end_i))
        weights = [self._line_weight(lyrics[i]) for i in indices]
        total_weight = max(1, sum(weights))
        matched_block = "".join(lyrics[start_i:end_i])
        if seg_idx_end is None:
            seg_idx_end = seg_idx

        cursor = seg_start
        for pos, i in enumerate(indices):
            if pos == len(indices) - 1:
                line_end = seg_end
            else:
                line_end = cursor + duration * weights[pos] / total_weight

            # 这里只保证切分不产生 0 长度。可读时长约束在候选区间层面判断，
            # 不在这里强行拉长，否则会撑爆原始 ASR 区间。
            min_line_duration = min(0.20, duration / max(1, len(indices)))
            line_end = max(cursor + min_line_duration, line_end)
            if pos != len(indices) - 1:
                line_end = min(line_end, seg_end)
            else:
                line_end = seg_end

            old_score = float(result[i].get("score", 0.0) or 0.0)
            old_source = str(result[i].get("_source", "") or "")
            # 只有真正的兜底插值可以被较低分 ASR 锚点覆盖。
            # 连续歌词块切分出来的行也会 interpolated=True，但它们仍然是 ASR 锚点，
            # 不能被后续低分匹配覆盖，否则会造成副歌/Bridge 错位。
            should_update = (
                not result[i].get("matched")
                or score > old_score + 0.05
                or old_source in ("interpolate", "uniform_fallback")
            )

            if should_update:
                result[i].update({
                    "start": cursor,
                    "end": max(cursor + 0.05, line_end),
                    "score": float(score),
                    "matched": True,
                    "interpolated": len(indices) > 1 or seg_idx_end != seg_idx,
                    "_source": source,
                    "_srt_idx": seg_idx,
                    "_srt_idx_end": seg_idx_end,
                    "_asr_text": asr_text,
                    "_matched_block": matched_block,
                    "low_confidence": bool(low_confidence),
                    "_match_kind": match_kind,
                })

            cursor = max(cursor + 0.05, line_end)

    def _find_best_lyric_block_for_segment(self,
                                           asr_text: str,
                                           lyrics: List[str],
                                           lyric_ptr: int,
                                           max_block_lines: int = 4,
                                           look_back: int = 2,
                                           look_ahead: Optional[int] = None,
                                           seg_duration: Optional[float] = None,
                                           min_duration_ratio: float = 0.45,
                                           allow_any_position: bool = False) -> Optional[Dict[str, Any]]:
        """为一个 ASR 时间区间寻找最佳连续歌词块。

        关键改动：评分时同时看“ASR 区间总时长是否足够承载歌词块”。
        这样短 segment 不会直接承载完整长歌词；但如果多个短 segment 合并后
        区间足够，则可以正常匹配，避免走插值导致字幕提前。
        """
        M = len(lyrics)
        if M == 0:
            return None

        if look_ahead is None:
            look_ahead = max(6, int(self.search_window))

        norm_asr = SimilarityScorer.normalize(asr_text)
        if not norm_asr:
            return None

        if allow_any_position:
            start_min = 0
            start_max = M
        else:
            start_min = max(0, lyric_ptr - look_back)
            start_max = min(M, lyric_ptr + look_ahead)

        if seg_duration is None:
            seg_duration = 0.0

        best: Optional[Dict[str, Any]] = None

        for start_i in range(start_min, start_max):
            candidate_parts: List[str] = []
            for block_size in range(1, max_block_lines + 1):
                end_i = start_i + block_size
                if end_i > M:
                    break
                candidate_parts.append(lyrics[end_i - 1])
                candidate = "".join(candidate_parts)

                duration_ratio, required_duration = self._duration_fit(
                    lyrics, start_i, end_i, float(seg_duration)
                )
                # 严重时长不足直接拒绝。这样“0.35s 承载 7 个字”不会通过。
                if float(seg_duration) > 0 and duration_ratio < min_duration_ratio:
                    continue

                raw_score = SimilarityScorer.score_pair(norm_asr, candidate)

                # 位置惩罚：顺序主流程优先匹配当前进度附近；重复插入时不使用。
                if allow_any_position:
                    position_penalty = 0.0
                else:
                    distance = abs(start_i - lyric_ptr)
                    position_penalty = min(0.25, distance * 0.025)

                # 没有明显证据时，轻微偏向少行块，避免一个区间吃太多歌词。
                block_penalty = max(0, block_size - 1) * 0.012

                # 时长惩罚：不拒绝边界略短的真实演唱，但会降分。
                duration_penalty = 0.0
                if float(seg_duration) > 0:
                    duration_penalty = max(0.0, 1.0 - min(1.0, duration_ratio)) * 0.18

                final_score = raw_score - position_penalty - block_penalty - duration_penalty

                if best is None or final_score > best["score"]:
                    best = {
                        "start_i": start_i,
                        "end_i": end_i,
                        "score": final_score,
                        "raw_score": raw_score,
                        "block_size": block_size,
                        "candidate": candidate,
                        "duration_ratio": duration_ratio,
                        "required_duration": required_duration,
                    }

        return best

    def _find_best_segment_group(self,
                                 srt_entries: List[Tuple[float, float, str]],
                                 consumed: List[bool],
                                 start_idx: int,
                                 lyrics: List[str],
                                 lyric_ptr: int,
                                 min_duration_ratio: float = 0.45,
                                 sequential_only: bool = False) -> Optional[Dict[str, Any]]:
        """从 start_idx 开始尝试单段或相邻多段合并，返回最佳候选。

        这是解决“短 ASR segment 被拒绝后插值提前”的核心：
        单个短段不够承载歌词时，先尝试与后续相邻短段合并成更大的演唱区间。
        """
        N = len(srt_entries)
        if start_idx >= N or consumed[start_idx]:
            return None

        best_group: Optional[Dict[str, Any]] = None
        max_merge_segments = 5
        max_gap = self._merge_gap_limit()

        for end_idx in range(start_idx, min(N, start_idx + max_merge_segments)):
            if consumed[end_idx]:
                break
            if end_idx > start_idx:
                prev_end = float(srt_entries[end_idx - 1][1])
                cur_start = float(srt_entries[end_idx][0])
                if cur_start - prev_end > max_gap:
                    break

            seg_start, seg_end, merged_text = self._build_segment_group(srt_entries, start_idx, end_idx)
            if not SimilarityScorer.normalize(merged_text):
                continue

            duration = seg_end - seg_start
            max_block_lines = self._estimate_max_block_lines(merged_text, duration, lyrics)
            if sequential_only:
                # weak 顺序锚点不要一次吃掉过多歌词行；长段强匹配仍可通过 broad strong 处理。
                max_block_lines = min(max_block_lines, 6)
                look_back = self.weak_anchor_max_offset
                look_ahead = self.weak_anchor_max_offset + 1
            else:
                look_back = 2
                look_ahead = max(6, int(self.search_window))

            best = self._find_best_lyric_block_for_segment(
                merged_text,
                lyrics,
                lyric_ptr=lyric_ptr,
                max_block_lines=max_block_lines,
                look_back=look_back,
                look_ahead=look_ahead,
                seg_duration=duration,
                min_duration_ratio=min_duration_ratio,
                allow_any_position=False,
            )
            if not best:
                continue

            merge_count = end_idx - start_idx + 1
            merge_penalty = max(0, merge_count - 1) * 0.018
            adjusted_score = float(best["score"]) - merge_penalty

            candidate = {
                **best,
                "score": adjusted_score,
                "base_score": float(best["score"]),
                "seg_start": seg_start,
                "seg_end": seg_end,
                "seg_idx": start_idx,
                "seg_idx_end": end_idx,
                "seg_text": merged_text,
                "merge_count": merge_count,
            }

            if best_group is None or candidate["score"] > best_group["score"]:
                best_group = candidate

        return best_group

    def _interpolate_missing_lines(self,
                                   result: List[Dict[str, Any]],
                                   audio_duration: float = 0.0,
                                   default_duration: float = 1.6) -> None:
        """只给未匹配的原始歌词行补时间，不改变已匹配锚点。"""
        M = len(result)
        if M == 0:
            return

        matched_indices = [i for i, a in enumerate(result) if a.get("matched")]
        if not matched_indices:
            total = audio_duration if audio_duration > 0 else M * default_duration
            step = total / max(1, M)
            for i, a in enumerate(result):
                a.update({
                    "start": i * step,
                    "end": max(i * step + 0.3, (i + 1) * step),
                    "matched": True,
                    "interpolated": True,
                    "_source": "uniform_fallback",
                })
            return

        for i, a in enumerate(result):
            if a.get("matched"):
                continue

            prev_i = None
            next_i = None
            for k in range(i - 1, -1, -1):
                if result[k].get("matched"):
                    prev_i = k
                    break
            for k in range(i + 1, M):
                if result[k].get("matched"):
                    next_i = k
                    break

            if prev_i is not None and next_i is not None:
                prev_end = float(result[prev_i]["end"])
                next_start = float(result[next_i]["start"])
                slots = next_i - prev_i
                gap = max(0.2, (next_start - prev_end) / max(1, slots))
                start = prev_end + gap * (i - prev_i - 1)
                end = min(next_start - 0.05, start + max(0.3, gap * 0.85))
                if end <= start:
                    end = start + 0.5
            elif prev_i is not None:
                prev_end = float(result[prev_i]["end"])
                prev_dur = max(0.6, float(result[prev_i]["end"]) - float(result[prev_i]["start"]))
                start = prev_end + 0.05
                end = start + min(2.5, prev_dur)
                if audio_duration > 0:
                    end = min(end, audio_duration)
                    if end <= start:
                        end = start + 0.5
            elif next_i is not None:
                next_start = float(result[next_i]["start"])
                missing_count = next_i + 1
                span = max(0.6 * missing_count, next_start)
                step = span / max(1, missing_count)
                start = max(0.0, i * step)
                end = min(next_start - 0.05, start + max(0.3, step * 0.85))
                if end <= start:
                    end = start + 0.5
            else:
                start = i * default_duration
                end = start + default_duration

            a.update({
                "start": float(start),
                "end": float(max(start + 0.05, end)),
                "score": 0.0,
                "matched": True,
                "interpolated": True,
                "_source": "interpolate",
            })

    def _find_best_repeat_block_for_group(self,
                                          lyrics: List[str],
                                          seg_text: str,
                                          duration: float,
                                          min_duration_ratio: float = 0.58) -> Optional[Dict[str, Any]]:
        """未消耗 ASR 组用于重复/额外段插入时，匹配任意位置的连续歌词块。"""
        max_block_lines = self._estimate_max_block_lines(seg_text, duration, lyrics)
        return self._find_best_lyric_block_for_segment(
            seg_text,
            lyrics,
            lyric_ptr=0,
            max_block_lines=max_block_lines,
            look_back=0,
            look_ahead=len(lyrics),
            seg_duration=duration,
            min_duration_ratio=min_duration_ratio,
            allow_any_position=True,
        )

    def _append_unmatched_segments_as_repeats(self,
                                             result: List[Dict[str, Any]],
                                             lyrics: List[str],
                                             srt_entries: List[Tuple[float, float, str]],
                                             consumed: List[bool],
                                             min_repeat_score: float = 0.55) -> List[Dict[str, Any]]:
        """把未消耗但可信的 ASR 段作为重复副歌/额外歌词块插入。

        与主流程一样，这里也先尝试合并相邻未消耗 ASR 段，再匹配连续歌词块。
        这样一整段副歌不会被压成最像的一行；同时重复插入使用更高阈值和
        更严格的时长比例，降低误插风险。
        """
        if not lyrics:
            return result

        output = list(result)
        start_times = [float(a.get("start", 0.0) or 0.0) for a in output]
        next_idx = max((int(a.get("idx", 0)) for a in output), default=-1) + 1
        local_consumed = list(consumed)
        max_gap = self._merge_gap_limit()
        max_merge_segments = 5
        seg_idx = 0
        N = len(srt_entries)

        while seg_idx < N:
            if local_consumed[seg_idx]:
                seg_idx += 1
                continue

            best_group: Optional[Dict[str, Any]] = None
            for end_idx in range(seg_idx, min(N, seg_idx + max_merge_segments)):
                if local_consumed[end_idx]:
                    break
                if end_idx > seg_idx:
                    prev_end = float(srt_entries[end_idx - 1][1])
                    cur_start = float(srt_entries[end_idx][0])
                    if cur_start - prev_end > max_gap:
                        break

                seg_start, seg_end, merged_text = self._build_segment_group(srt_entries, seg_idx, end_idx)
                if not SimilarityScorer.normalize(merged_text):
                    continue
                duration = seg_end - seg_start
                best = self._find_best_repeat_block_for_group(
                    lyrics, merged_text, duration, min_duration_ratio=0.58
                )
                if not best:
                    continue
                merge_count = end_idx - seg_idx + 1
                adjusted_score = float(best["score"]) - max(0, merge_count - 1) * 0.020
                candidate = {
                    **best,
                    "score": adjusted_score,
                    "seg_start": seg_start,
                    "seg_end": seg_end,
                    "seg_idx": seg_idx,
                    "seg_idx_end": end_idx,
                    "seg_text": merged_text,
                    "merge_count": merge_count,
                }
                if best_group is None or candidate["score"] > best_group["score"]:
                    best_group = candidate

            if not best_group or float(best_group["score"]) < min_repeat_score:
                seg_idx += 1
                continue

            # 插入重复歌词块。这里创建临时 result 承接切分，再按时间插入 output。
            block_start = int(best_group["start_i"])
            block_end = int(best_group["end_i"])
            temp = [
                {
                    "idx": next_idx + k,
                    "text": lyrics[i],
                    "start": 0.0,
                    "end": 0.0,
                    "score": 0.0,
                    "matched": False,
                    "interpolated": True,
                    "_source": "repeat_block",
                    "_srt_idx": int(best_group["seg_idx"]),
                    "_srt_idx_end": int(best_group["seg_idx_end"]),
                    "_asr_text": str(best_group.get("seg_text", "")),
                    "_matched_block": "".join(lyrics[block_start:block_end]),
                    "low_confidence": False,
                    "_match_kind": "repeat_strong",
                }
                for k, i in enumerate(range(block_start, block_end))
            ]
            # 复用切分逻辑需要歌词索引从 0 开始，因此传入块歌词。
            block_lyrics = lyrics[block_start:block_end]
            self._assign_segment_to_lyric_block(
                result=temp,
                lyrics=block_lyrics,
                start_i=0,
                end_i=len(block_lyrics),
                seg_start=float(best_group["seg_start"]),
                seg_end=float(best_group["seg_end"]),
                score=float(best_group["score"]),
                seg_idx=int(best_group["seg_idx"]),
                seg_idx_end=int(best_group["seg_idx_end"]),
                source="repeat_block",
                asr_text=str(best_group.get("seg_text", "")),
                low_confidence=False,
                match_kind="repeat_strong",
            )
            for entry in temp:
                entry["idx"] = next_idx
                next_idx += 1
                insert_pos = bisect.bisect_right(start_times, float(entry["start"]))
                output.insert(insert_pos, entry)
                start_times.insert(insert_pos, float(entry["start"]))

            for i in range(int(best_group["seg_idx"]), int(best_group["seg_idx_end"]) + 1):
                local_consumed[i] = True

            seg_idx = int(best_group["seg_idx_end"]) + 1

        return output

    def _can_accept_weak_anchor(self, best: Optional[Dict[str, Any]], lyric_ptr: int) -> bool:
        """判断低文本分数候选是否可作为 weak sequential anchor。

        使用前提：lyrics.txt 是权威文本，ASR 来自人声分离后的 vocals。
        因此 ASR 文本可以错，但时间段若在当前歌词进度附近且时长合理，
        就比纯插值更有价值。
        """
        if not self.enable_weak_anchor or not best:
            return False

        start_i = int(best.get("start_i", -999))
        end_i = int(best.get("end_i", -999))
        if start_i < 0 or end_i <= start_i:
            return False

        # weak anchor 只允许绑定当前歌词进度附近的连续块，不能拿来跳远匹配副歌。
        if abs(start_i - lyric_ptr) > self.weak_anchor_max_offset:
            return False

        raw_score = float(best.get("raw_score", best.get("score", 0.0)) or 0.0)
        if raw_score < float(self.weak_anchor_threshold):
            return False

        if float(best.get("duration_ratio", 0.0) or 0.0) < self.weak_anchor_min_duration_ratio:
            return False

        asr_text = str(best.get("seg_text", "") or "")
        if self._is_probably_non_lyric_text(asr_text):
            return False

        return True

    def _alignment_debug_payload(self, alignments: List[Dict]) -> List[Dict[str, Any]]:
        """返回对齐调试信息，便于定位字幕提前、缺行、重复等问题。"""
        fields = (
            "idx", "text", "start", "end", "score", "matched",
            "interpolated", "low_confidence", "_match_kind", "_source",
            "_srt_idx", "_srt_idx_end", "_asr_text", "_matched_block",
        )
        return [{k: a.get(k) for k in fields if k in a} for a in alignments]

    def _align_manual(self, lyrics: List[str],
                      srt_segments: List[dict]) -> List[Dict]:
        """歌词对齐核心算法：ASR/SRT 区间匹配连续歌词块。

        关键点：
        1. 不再只用单个 ASR segment 判断时长，先尝试合并相邻 segment。
        2. strong/normal match 依赖文本相似度；weak sequential anchor 依赖
           当前歌词进度、合理时长和 vocals ASR 时间锚点。
        3. weak 只用于主顺序流程，不用于重复/乱序插入。
        4. 实在没有 ASR 锚点时才插值。
        """
        M, N = len(lyrics), len(srt_segments)
        result = self._init_alignment_result(lyrics)

        if M == 0:
            return result
        if N == 0:
            self._interpolate_missing_lines(result, audio_duration=0.0)
            return result

        srt_entries: List[Tuple[float, float, str]] = []
        for seg in srt_segments:
            try:
                start = float(seg.get("start", 0.0) or 0.0)
                end = float(seg.get("end", 0.0) or 0.0)
                text = str(seg.get("text", "") or "").strip()
                if end > start:
                    srt_entries.append((start, end, text))
            except Exception:
                continue

        if not srt_entries:
            self._interpolate_missing_lines(result, audio_duration=0.0)
            return result

        N = len(srt_entries)
        consumed = [False] * N
        strong_threshold = float(self.threshold_1 or 0.42)
        weak_threshold = float(self.threshold_2 or 0.35)
        lyric_ptr = 0
        seg_idx = 0

        while seg_idx < N and lyric_ptr < M:
            if consumed[seg_idx]:
                seg_idx += 1
                continue

            # 主流程优先顺序：
            # 1) 当前位置附近 strong/normal match；
            # 2) 更宽搜索的 strong match（允许跳过 ASR 没覆盖的歌词，后续插值）；
            # 3) 当前位置附近 weak sequential anchor。
            #
            # 注意：weak 不能早于 broad strong。否则当某段歌词实际漏识别时，
            # 可能会把后面明确识别出的 Bridge/Refrain 时间强行绑给当前缺失歌词。
            sequential_best = self._find_best_segment_group(
                srt_entries=srt_entries,
                consumed=consumed,
                start_idx=seg_idx,
                lyrics=lyrics,
                lyric_ptr=lyric_ptr,
                min_duration_ratio=0.42,
                sequential_only=True,
            )

            best = None
            accept_kind = ""
            low_confidence = False

            if sequential_best:
                seq_threshold = weak_threshold
                if float(sequential_best["score"]) >= seq_threshold:
                    best = sequential_best
                    accept_kind = "strong" if float(sequential_best["score"]) >= strong_threshold else "normal"

            broad_best = None
            if best is None:
                broad_best = self._find_best_segment_group(
                    srt_entries=srt_entries,
                    consumed=consumed,
                    start_idx=seg_idx,
                    lyrics=lyrics,
                    lyric_ptr=lyric_ptr,
                    min_duration_ratio=0.42,
                    sequential_only=False,
                )
                if broad_best:
                    threshold = weak_threshold if int(broad_best["start_i"]) <= lyric_ptr <= int(broad_best["end_i"]) else strong_threshold
                    if float(broad_best["score"]) >= threshold:
                        best = broad_best
                        accept_kind = "strong" if float(broad_best["score"]) >= strong_threshold else "normal"

            if best is None and self._can_accept_weak_anchor(sequential_best, lyric_ptr):
                best = sequential_best
                accept_kind = "weak"
                low_confidence = True

            if not best:
                logger.debug("未找到可接受 ASR 区间 seg=%d lyric_ptr=%d", seg_idx, lyric_ptr)
                seg_idx += 1
                continue

            if accept_kind == "weak":
                logger.debug(
                    "使用 weak anchor %d-%d [%.1f-%.1f] raw=%.3f score=%.3f ratio=%.2f lyric=%d-%d asr=%s",
                    int(best["seg_idx"]), int(best["seg_idx_end"]),
                    float(best["seg_start"]), float(best["seg_end"]),
                    float(best.get("raw_score", 0.0)), float(best.get("score", 0.0)),
                    float(best.get("duration_ratio", 0.0)),
                    int(best["start_i"]), int(best["end_i"]),
                    str(best.get("seg_text", ""))[:40],
                )

            source_prefix = "weak" if accept_kind == "weak" else "block"
            is_group = int(best["seg_idx_end"]) > int(best["seg_idx"])
            source = f"{source_prefix}_group" if is_group else source_prefix

            self._assign_segment_to_lyric_block(
                result=result,
                lyrics=lyrics,
                start_i=int(best["start_i"]),
                end_i=int(best["end_i"]),
                seg_start=float(best["seg_start"]),
                seg_end=float(best["seg_end"]),
                score=float(best["score"]),
                seg_idx=int(best["seg_idx"]),
                seg_idx_end=int(best["seg_idx_end"]),
                source=source,
                asr_text=str(best.get("seg_text", "")),
                low_confidence=low_confidence,
                match_kind=accept_kind,
            )

            for i in range(int(best["seg_idx"]), int(best["seg_idx_end"]) + 1):
                consumed[i] = True

            lyric_ptr = max(lyric_ptr, int(best["end_i"]))
            seg_idx = int(best["seg_idx_end"]) + 1

        audio_duration = max((end for _, end, _ in srt_entries), default=0.0)

        # 先补齐原始歌词行，保持 result[0:M] 的索引稳定。
        self._interpolate_missing_lines(result, audio_duration=audio_duration)

        # 原始歌词稳定后，再插入可信的重复段。重复/乱序插入更严格，避免多插。
        result = self._append_unmatched_segments_as_repeats(
            result=result,
            lyrics=lyrics,
            srt_entries=srt_entries,
            consumed=consumed,
            min_repeat_score=max(0.55, strong_threshold + 0.08),
        )

        result.sort(key=lambda a: (float(a.get("start", 0.0) or 0.0), int(a.get("idx", 0))))
        return result

    @staticmethod
    def _repair_alignment_timeline(alignments: List[Dict],
                                   min_gap: float = 0.03,
                                   min_duration: float = 0.35,
                                   fallback_duration: float = 1.2,
                                   audio_duration: float = 0.0) -> None:
        """轻量修复 SRT 时间线。

        只做合法化，不承担核心对齐职责：
        - end <= start 时补一个最小时长；
        - 轻微重叠时优先缩短上一条；
        - 只有上一条不能再缩短时，才小幅移动当前条；
        - 裁剪超出音频总时长的字幕。
        """
        matched = [a for a in alignments if a.get("matched")]
        if not matched:
            return

        matched.sort(key=lambda a: (float(a.get("start", 0.0) or 0.0), int(a.get("idx", 0))))
        repaired = 0

        for a in matched:
            start = max(0.0, float(a.get("start", 0.0) or 0.0))
            end = float(a.get("end", 0.0) or 0.0)

            if end <= start:
                end = start + fallback_duration
                a["interpolated"] = True
                repaired += 1

            if audio_duration > 0:
                start = min(start, max(0.0, audio_duration - min_duration))
                end = min(end, audio_duration)
                if end <= start:
                    start = max(0.0, end - min_duration)

            a["start"] = start
            a["end"] = max(start + min_duration, end)

        for prev, cur in zip(matched, matched[1:]):
            prev_start = float(prev["start"])
            prev_end = float(prev["end"])
            cur_start = float(cur["start"])
            cur_end = float(cur["end"])

            if cur_start < prev_end + min_gap:
                target_prev_end = cur_start - min_gap

                # 优先缩短上一条，避免把当前和后续字幕整体推迟。
                if target_prev_end >= prev_start + min_duration:
                    prev["end"] = target_prev_end
                    prev["interpolated"] = True
                    repaired += 1
                else:
                    prev["end"] = prev_start + min_duration
                    needed_start = prev["end"] + min_gap
                    max_shift = 0.5
                    shift = min(max_shift, max(0.0, needed_start - cur_start))
                    if shift > 0:
                        cur["start"] = cur_start + shift
                        cur["end"] = max(cur_end + shift, cur["start"] + min_duration)
                        cur["interpolated"] = True
                        repaired += 1

            if audio_duration > 0 and cur["end"] > audio_duration:
                cur["end"] = audio_duration
                if cur["start"] >= cur["end"]:
                    cur["start"] = max(0.0, cur["end"] - min_duration)
                cur["interpolated"] = True
                repaired += 1

        if repaired:
            logger.info("轻量修复 %d 个字幕时间戳", repaired)

    @staticmethod
    def _generate_srt(alignments: List[Dict],
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

    logger.info("歌词时间轴对齐 v2 (Python), 模式: %s", args.align_mode)

    result = align_lyrics(
        project_dir=args.project_dir,
        align_mode=args.align_mode,
        srt_file=args.srt_file,
    )

    logger.info("对齐完成! SRT: %s, 对齐: %d/%d 行, SRT条目: %d",
                result['srt_path'], result['aligned_lines'], result['total_lines'], result['srt_entries'])


if __name__ == "__main__":
    main()
