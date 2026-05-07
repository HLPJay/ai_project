"""
align.py — 歌词时间轴对齐模块（纯 Python，替代原版 align_lyrics.sh）

工作流程：
  ① 人声分离（Demucs，可选）→ ② Whisper ASR 转写 → ③ 两遍匹配对齐
  → ④ 后处理修正 → ⑤ 生成 SRT

核心算法：ASR/SRT 片段匹配连续歌词块 + 低分不消耗 + 缺失行插值

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


def _kill_process_tree(proc: subprocess.Popen):
    """杀掉进程及其所有子进程（Windows 上 subprocess.kill 只杀直接进程）"""
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True, timeout=10,
            )
        else:
            import signal
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _run_subprocess_with_live_output(cmd: list, cwd: str = None,
                                     env: dict = None,
                                     timeout: int = 600,
                                     label: str = "") -> subprocess.CompletedProcess:
    """启动子进程，stderr 实时透传到终端，超时后杀整棵进程树。

    使用线程读取 stdout/stderr，兼容 Windows（Windows 的 select/selectors
    不支持 pipe 句柄，只支持 socket）。
    """
    import threading

    kwargs = dict(
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="backslashreplace",
    )
    if cwd:
        kwargs["cwd"] = cwd
    if env:
        kwargs["env"] = env
    if sys.platform != "win32":
        kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd, **kwargs)
    stdout_lines = []
    stderr_lines = []

    def _read_stdout():
        for line in proc.stdout:
            stdout_lines.append(line)

    def _read_stderr():
        for line in proc.stderr:
            stderr_lines.append(line)
            stripped = line.rstrip()
            if not stripped:
                continue
            # 过滤 tqdm 进度条（含 \r 回车、百分号+竖线、大量非 ASCII）
            if '\r' in line or '|' in stripped and '%' in stripped:
                continue
            # 过滤高比例非 ASCII 乱码行（GBK 全角字符等）
            non_ascii = sum(1 for c in stripped if ord(c) > 127)
            if len(stripped) > 10 and non_ascii / len(stripped) > 0.3:
                continue
            print(f"    [{label}] {stripped}", flush=True)

    t_out = threading.Thread(target=_read_stdout, daemon=True)
    t_err = threading.Thread(target=_read_stderr, daemon=True)
    t_out.start()
    t_err.start()

    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"  [!!] {label} 子进程超时 ({timeout}s)，强制终止...", flush=True)
        _kill_process_tree(proc)
        raise

    # 等待读取线程结束（进程已退出，pipe 会关闭，线程会自然结束）
    t_out.join(timeout=10)
    t_err.join(timeout=10)

    return subprocess.CompletedProcess(
        cmd, proc.returncode,
        stdout="".join(stdout_lines),
        stderr="".join(stderr_lines),
    )


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

    result = _run_subprocess_with_live_output(
        cmd,
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
        timeout=timeout,
        label="whisper",
    )

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
        f"{(result.stderr or '')[-1000:]}"
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
        logger.debug("检查 Whisper 是否可用...")
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
                    logger.debug("Whisper 缓存命中，跳过转写")
                    return cached
            except (json.JSONDecodeError, KeyError):
                pass

        fp16 = device.startswith("cuda")

        logger.debug("Whisper 转写中（模型链: %s, device=%s）...", f" -> ".join(model_sizes), device)
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

                logger.debug("Whisper %s (%s): %d 段, %s...",
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
        logger.debug("检查 Demucs 是否可用...")
        return importlib.util.find_spec("demucs") is not None

    def separate(self, audio_path: str, temp_dir: str,
                 timeout: int = 600) -> Optional[str]:
        """执行人声分离

        返回:
            人声 WAV 路径，或 None 表示失败（自动回退原始音频）
        """
        cfg = ConfigManager()
        demucs_device = _resolve_torch_device(str(cfg.get("align_demucs_device", "auto")))
        logger.debug("Demucs 人声分离中（device=%s）...", demucs_device)

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
                result = _run_subprocess_with_live_output(
                    cmd, timeout=timeout, label="demucs",
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
                    demucs_device = "cpu"
                    continue

                logger.warning(
                    "Demucs 失败 (code=%d, attempt %d/%d), 使用原始音频",
                    result.returncode, attempt + 1, max_retries + 1,
                )
                return None

            except FileNotFoundError:
                logger.warning("demucs 命令未找到，使用原始音频")
                return None
            except subprocess.TimeoutExpired:
                print(f"  [!!] Demucs 超时 ({timeout}s)，跳过人声分离", flush=True)
                logger.warning("Demucs 超时 (%ds, attempt %d/%d), 使用原始音频",
                              timeout, attempt + 1, max_retries + 1)
                return None
            except Exception as e:
                logger.warning("Demucs 异常 (attempt %d/%d): %s",
                              attempt + 1, max_retries + 1, e)
                if attempt < max_retries:
                    import time as _time
                    _time.sleep(min(2 ** attempt, 8))
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
                logger.debug("人声分离完成: %s", candidate)
                return str(candidate)

        found = list(demucs_out.rglob("vocals.wav"))
        if found:
            logger.debug("人声分离完成: %s", found[0])
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

    设计目标：
    - lyrics.txt 是权威歌词文本，最终字幕文本始终来自 lyrics.txt。
    - Whisper/faster-whisper 的 ASR 文本只作为时间锚点辅助，文本可以有错。
    - 支持连续歌词块匹配、相邻 ASR 段合并、weak sequential anchor、时长合理性约束。
    - 重复/乱序段只使用高置信 strong match，避免 weak match 乱插副歌。
    """

    def __init__(self, threshold_1: float = 0.42,
                 threshold_2: float = 0.35,
                 search_window: int = 10,
                 max_gap_seconds: float = 5.0,
                 weak_anchor_threshold: float = 0.18,
                 weak_anchor_max_offset: int = 1,
                 enable_weak_anchor: bool = True,
                 max_merge_segments: int = 4,
                 max_block_lines: int = 8):
        self.threshold_1 = float(threshold_1)
        self.threshold_2 = float(threshold_2)
        self.search_window = int(search_window)
        self.max_gap_seconds = float(max_gap_seconds)
        self.weak_anchor_threshold = float(weak_anchor_threshold)
        self.weak_anchor_max_offset = int(weak_anchor_max_offset)
        self.enable_weak_anchor = bool(enable_weak_anchor)
        self.max_merge_segments = int(max(1, max_merge_segments))
        self.max_block_lines = int(max(1, max_block_lines))

        # 可通过 ConfigManager 覆盖；没有配置时使用保守默认。
        try:
            cfg = ConfigManager()
            self.align_debug_decisions = bool(cfg.get_bool("align_debug_decisions", False))
            self.merge_max_gap_sec = float(cfg.get("align_merge_max_gap_sec", 1.5) or 1.5)
            self.repeat_min_score = float(cfg.get("align_repeat_min_score", max(0.55, self.threshold_1 + 0.08)) or max(0.55, self.threshold_1 + 0.08))
            self.weak_anchor_threshold = float(cfg.get("align_weak_anchor_threshold", self.weak_anchor_threshold) or self.weak_anchor_threshold)
            self.weak_anchor_max_offset = int(cfg.get_int("align_weak_anchor_max_offset", self.weak_anchor_max_offset))
            self.enable_weak_anchor = bool(cfg.get_bool("align_weak_anchor_enabled", self.enable_weak_anchor))
            self.max_merge_segments = int(cfg.get_int("align_max_merge_segments", self.max_merge_segments))
            self.max_block_lines = int(cfg.get_int("align_max_block_lines", self.max_block_lines))
        except Exception:
            self.align_debug_decisions = False
            self.merge_max_gap_sec = 1.5
            self.repeat_min_score = max(0.55, self.threshold_1 + 0.08)

    # ───────────────────────────────────────────────────────
    # 基础工具
    # ───────────────────────────────────────────────────────

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
        """保留兼容旧调用。当前 auto 模式默认不用真实歌词构造 prompt。"""
        return "简体中文歌曲歌词转写。"

    def _decision_debug(self, message: str, *args) -> None:
        """匹配决策级日志。配置 align_debug_decisions=true 时输出。"""
        if self.align_debug_decisions:
            logger.debug(message, *args)

    def _log_alignment_parameters(self, mode: str) -> None:
        logger.debug(
            "对齐参数: mode=%s threshold_1=%.2f threshold_2=%.2f search_window=%d "
            "max_gap=%.1fs weak_anchor=%s weak_threshold=%.2f weak_offset=%d",
            mode,
            self.threshold_1,
            self.threshold_2,
            self.search_window,
            self.max_gap_seconds,
            self.enable_weak_anchor,
            self.weak_anchor_threshold,
            self.weak_anchor_max_offset,
        )
        logger.debug(
            "高级对齐策略: block_matching=true merge_adjacent_asr=true max_merge_segments=%d "
            "merge_max_gap=%.1fs max_block_lines=%d duration_check=true repeat_min_score=%.2f debug_decisions=%s",
            self.max_merge_segments,
            self.merge_max_gap_sec,
            self.max_block_lines,
            self.repeat_min_score,
            self.align_debug_decisions,
        )

    @staticmethod
    def _alignment_debug_payload(alignments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        keys = (
            "idx", "text", "start", "end", "score", "matched", "interpolated",
            "low_confidence", "_source", "_match_kind", "_srt_idx", "_srt_idx_end",
            "_asr_text", "_matched_block", "_duration_fit", "_required_duration",
        )
        return [{k: a.get(k) for k in keys if k in a} for a in alignments]

    @staticmethod
    def _log_alignment_summary(alignments: List[Dict[str, Any]]) -> None:
        try:
            from collections import Counter
            matched = [a for a in alignments if a.get("matched")]
            sources = Counter(str(a.get("_source") or "unknown") for a in matched)
            kinds = Counter(str(a.get("_match_kind") or "unknown") for a in matched)
            low_conf = sum(1 for a in matched if a.get("low_confidence"))
            interpolated = sum(1 for a in matched if str(a.get("_source")) in ("interpolate", "uniform_fallback"))
            logger.debug(
                "对齐来源统计: sources=%s kinds=%s low_confidence=%d interpolated=%d matched=%d",
                dict(sources), dict(kinds), low_conf, interpolated, len(matched)
            )
        except Exception as exc:
            logger.debug("对齐来源统计失败: %s", exc)

    # ───────────────────────────────────────────────────────
    # ASR 过滤与原生 SRT 输出
    # ───────────────────────────────────────────────────────

    def _filter_misrecognized_asr(self, asr_segments: List[dict],
                                   lyrics: List[str],
                                   min_global_coverage: float = 0.35) -> List[dict]:
        """温和过滤明显 ASR 幻觉段，尽量保留人声时间戳。

        注意：因为 lyrics.txt 是权威文本，ASR 文本即使差距大也可能是可用时间锚点。
        所以这里不能激进过滤，只删除明显制作信息、字幕信息、乐器标签、极端静音幻觉。
        """
        if not asr_segments or not lyrics:
            return asr_segments

        all_lyrics_text = "".join(lyrics)
        filtered = []
        removed = []
        for seg in asr_segments:
            text = str(seg.get("text", "") or "").strip()
            no_speech = float(seg.get("no_speech_prob", 0.0) or 0.0)
            if self._is_obvious_non_lyric_segment(text, lyrics, all_lyrics_text=all_lyrics_text, no_speech_prob=no_speech):
                removed.append(seg)
            else:
                filtered.append(seg)

        if removed:
            logger.debug("过滤 %d 个明显非歌词/幻觉 ASR 段", len(removed))
            for seg in removed:
                self._decision_debug(
                    "过滤ASR: %.2f-%.2f text=%s",
                    float(seg.get("start", 0.0) or 0.0),
                    float(seg.get("end", 0.0) or 0.0),
                    str(seg.get("text", "") or "")[:80],
                )
        return filtered if filtered else asr_segments

    @staticmethod
    def _write_asr_raw_srt(asr_segments: List[dict], output_path: Path) -> None:
        """Write raw ASR subtitles before lyric-text synchronization."""
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
                logger.debug("ASR 原生字幕: %s", output_path)
        except Exception as exc:
            logger.warning("ASR 原生字幕写入失败: %s", exc)

    @staticmethod
    def _is_obvious_asr_hallucination(text: str,
                                      coverage: float,
                                      no_speech_prob: float) -> bool:
        chars = re.findall(r'[\u4e00-\u9fff]', text or "")
        if len(chars) < 3:
            return False
        unique_ratio = len(set(chars)) / max(1, len(chars))
        repeated_noise = len(chars) >= 5 and unique_ratio <= 0.35
        near_unrelated = coverage < 0.20
        mostly_silence = no_speech_prob >= 0.60
        production_credit = any(
            marker in text
            for marker in (
                "编曲", "作曲", "作词", "演唱", "原唱", "制作人",
                "出品", "发行", "字幕", "词曲", "Composer", "Lyrics",
            )
        ) and coverage < 0.50
        return production_credit or (mostly_silence and (near_unrelated or repeated_noise))

    def _is_obvious_non_lyric_segment(self, text: str, lyrics: List[str],
                                      all_lyrics_text: str = "",
                                      no_speech_prob: float = 0.0) -> bool:
        """通用非歌词判断。尽量保守，避免误删 Baby/Oh yeah 等真实歌词。"""
        raw = str(text or "").strip()
        if not raw:
            return True
        norm = SimilarityScorer.normalize(raw)
        if not norm:
            return True

        # 如果能匹配到任意歌词行/块，就不要提前过滤。
        quick_best = 0.0
        for lyric in lyrics[:200]:
            quick_best = max(quick_best, SimilarityScorer.score_pair(raw, lyric))
            if quick_best >= 0.30:
                return False

        low = raw.lower().strip()
        production_markers = (
            "composer", "lyrics", "lyricist", "arranger", "producer", "subtitle",
            "caption", "copyright", "provided by", "all rights", "作曲", "作词",
            "编曲", "制作", "出品", "发行", "字幕", "翻译",
        )
        if any(m in low for m in production_markers):
            return True

        non_lyric_markers = (
            "instrumental", "interlude", "zither", "harp", "guitar", "piano", "drums",
            "bass", "synth", "violin", "cello", "flute", "solo", "music", "backing track",
            "orchestra", "strings", "choir", "beat", "edm", "sound effect", "sfx",
        )
        ascii_letters = re.findall(r"[a-zA-Z]", raw)
        cjk = re.findall(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", raw)
        is_short_english = len(ascii_letters) >= 3 and not cjk and len(norm) <= 24
        if is_short_english and any(m in low for m in non_lyric_markers):
            return True

        # 纯短英文且和 lyrics 无相似度，通常是乐器/模型标签；但保留常见拟声歌词。
        safe_vocals = {"oh", "yeah", "baby", "hey", "la", "lala", "wow", "woo", "ah", "love", "you"}
        tokens = re.findall(r"[a-zA-Z]+", low)
        if is_short_english and quick_best < 0.18 and not any(t in safe_vocals for t in tokens):
            return True

        # 高 no_speech 且文本和歌词几乎无关，才作为幻觉删除。
        if no_speech_prob >= 0.75 and quick_best < 0.16:
            return True
        return False

    # ───────────────────────────────────────────────────────
    # 主流程
    # ───────────────────────────────────────────────────────

    def run(self, project_dir: str, align_mode: str = "auto",
            srt_file: str = "", timeout: int = 600) -> Dict[str, Any]:
        """执行完整对齐流程。"""
        project_dir = Path(project_dir)
        audio_path = project_dir / "audio" / "song.mp3"
        lyrics_path = project_dir / "audio" / "lyrics.txt"
        output_srt = project_dir / "audio" / "song.srt"
        temp_dir = project_dir / "temp"

        if not audio_path.exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")
        if not lyrics_path.exists():
            raise FileNotFoundError(f"歌词文件不存在: {lyrics_path}")
        temp_dir.mkdir(parents=True, exist_ok=True)

        self._log_alignment_parameters(align_mode)

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

            user_segments = _parse_srt_to_segments(srt_content)
            if not user_segments:
                raise ValueError(f"SRT 文件无法解析出有效片段: {srt_file}")

            _, clean_lyrics = parse_lyrics(str(lyrics_path))
            logger.debug("手动模式: 从 SRT 解析到 %d 个时间片段", len(user_segments))
            user_segments = self._filter_misrecognized_asr(user_segments, clean_lyrics)
            logger.debug("过滤后: %d 段", len(user_segments))

            metadata_duration = self._load_project_audio_duration(project_dir)
            audio_duration = metadata_duration if metadata_duration > 0 else max((seg.get("end", 0.0) for seg in user_segments), default=0.0)

            logger.debug("对齐中: %d 行歌词 <-> %d 段 SRT, 音频时长: %.1fs", len(clean_lyrics), len(user_segments), audio_duration)
            alignments = self._align_manual(clean_lyrics, user_segments)
            self._repair_alignment_timeline(alignments, audio_duration=audio_duration)
            self._log_alignment_summary(alignments)

            srt_content = self._generate_srt(alignments, clean_lyrics)
            output_srt.write_text(srt_content, encoding="utf-8")
            matched = sum(1 for a in alignments if a.get("matched"))
            srt_entries = len([a for a in alignments if a.get("matched")])

            logger.debug("手动模式对齐完成: %d/%d 行, SRT %d 条目, 输出: %s", matched, len(clean_lyrics), srt_entries, output_srt)
            return {
                "srt_path": str(output_srt),
                "aligned_lines": matched,
                "total_lines": len(clean_lyrics),
                "srt_entries": srt_entries,
                "alignment": self._alignment_debug_payload(alignments),
                "status": "completed",
            }

        # auto 模式
        start_time = time.time()
        cfg = ConfigManager()
        if not cfg.get_bool("align_asr_enabled", True):
            raise ImportError("ALIGN_ASR_ENABLED=false")

        demucs_enabled = cfg.get_bool("align_demucs_enabled", True)
        demucs_succeeded = False
        if demucs_enabled and DemucsVocalSeparator.is_available():
            print("  [..] Demucs 人声分离中（CPU 上约需 3-8 分钟）...", flush=True)
            vocal_path = DemucsVocalSeparator().separate(str(audio_path), str(temp_dir), timeout)
            audio_for_asr = vocal_path or str(audio_path)
            demucs_succeeded = bool(vocal_path)
            print(f"  [OK] Demucs 完成: {'成功分离人声' if demucs_succeeded else '回退使用原始音频'}", flush=True)
        elif not demucs_enabled:
            audio_for_asr = str(audio_path)
            logger.info("Demucs 已通过配置关闭，使用原始音频")
        else:
            audio_for_asr = str(audio_path)
            logger.info("Demucs 未安装，使用原始音频")

        if not WhisperTranscriber.is_available():
            raise RuntimeError(
                "Whisper 未安装。请执行: pip install openai-whisper\n"
                "或在 --align-mode manual 下提供 SRT 文件跳过 ASR"
            )

        _, clean_lyrics = parse_lyrics(str(lyrics_path))
        print("  [..] Whisper ASR 转写中（CPU 上约需 5-15 分钟）...", flush=True)
        whisper_result = WhisperTranscriber().transcribe(
            audio_for_asr,
            str(temp_dir),
            initial_prompt="简体中文歌曲歌词转写。",
            force_no_vad=demucs_succeeded,
        )
        print(f"  [OK] Whisper 转写完成: {len(whisper_result.get('segments', []))} 段", flush=True)

        asr_segments = whisper_result.get("segments", [])
        logger.debug("ASR segments: %d 段", len(asr_segments))
        if asr_segments:
            logger.debug("第一段 keys: %s", list(asr_segments[0].keys()))
            logger.debug("第一段 text: %s", str(asr_segments[0].get("text", ""))[:50])
            logger.debug("第一段 start/end: %s -> %s", asr_segments[0].get("start"), asr_segments[0].get("end"))
        logger.debug("clean_lyrics: %d 行", len(clean_lyrics))

        asr_segments = self._filter_misrecognized_asr(asr_segments, clean_lyrics)
        logger.debug("过滤后: %d 段", len(asr_segments))
        raw_srt_path = project_dir / "audio" / "asr_raw.srt"
        self._write_asr_raw_srt(asr_segments, raw_srt_path)

        metadata_duration = self._load_project_audio_duration(project_dir)
        audio_duration = metadata_duration if metadata_duration > 0 else max((seg.get("end", 0.0) for seg in asr_segments), default=0.0)

        logger.debug("对齐中: %d 行歌词 <-> %d 段 ASR, 音频时长: %.1fs", len(clean_lyrics), len(asr_segments), audio_duration)
        alignments = self._align_manual(clean_lyrics, asr_segments)
        self._repair_alignment_timeline(alignments, audio_duration=audio_duration)
        self._log_alignment_summary(alignments)

        srt_content = self._generate_srt(alignments, clean_lyrics)
        output_srt.write_text(srt_content, encoding="utf-8")

        matched = sum(1 for a in alignments if a.get("matched"))
        elapsed = time.time() - start_time
        srt_entries = len([a for a in alignments if a.get("matched")])

        logger.debug("对齐详情: %.1fs, %d/%d 行, SRT %d 条目, 输出: %s", elapsed, matched, len(clean_lyrics), srt_entries, output_srt)

        for a in alignments:
            if a.get("_source") in ("interpolate", "uniform_fallback"):
                logger.debug("插值/兜底行 %d: %.2fs-%.2fs \"%s...\"",
                             int(a.get("idx", 0)) + 1,
                             float(a.get("start", 0.0) or 0.0),
                             float(a.get("end", 0.0) or 0.0),
                             str(a.get("text", ""))[:20])

        return {
            "srt_path": str(output_srt),
            "aligned_lines": matched,
            "total_lines": len(clean_lyrics),
            "srt_entries": srt_entries,
            "asr_raw_srt_path": str(raw_srt_path),
            "alignment": self._alignment_debug_payload(alignments),
            "status": "completed",
        }

    # ───────────────────────────────────────────────────────
    # 对齐核心辅助方法
    # ───────────────────────────────────────────────────────

    def _line_weight(self, text: str) -> int:
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
                "low_confidence": False,
                "_source": "",
                "_match_kind": "",
                "_srt_idx": -1,
                "_srt_idx_end": -1,
                "_asr_text": "",
                "_matched_block": "",
            }
            for i in range(len(lyrics))
        ]

    def _min_readable_duration_for_line(self, text: str) -> float:
        n = len(SimilarityScorer.normalize(text))
        if n <= 1:
            return 0.30
        if n <= 2:
            return 0.45
        if n <= 4:
            return 0.70
        if n <= 7:
            return 0.95
        if n <= 12:
            return 1.15
        return 1.35

    def _duration_fit_for_block(self, lyrics: List[str], start_i: int, end_i: int,
                                duration: float, strict_ratio: float = 0.55) -> Tuple[bool, float, float]:
        required = sum(self._min_readable_duration_for_line(lyrics[i]) for i in range(start_i, end_i))
        required = max(0.30, required)
        fit = float(duration) / required
        return fit >= strict_ratio, fit, required

    def _max_block_lines_for_segment(self, asr_text: str, lyrics: List[str], duration: float, cap: Optional[int] = None) -> int:
        cap = int(cap or self.max_block_lines)
        norm_len = len(SimilarityScorer.normalize(asr_text))
        lyric_lens = [len(SimilarityScorer.normalize(x)) for x in lyrics if SimilarityScorer.normalize(x)]
        avg_len = sum(lyric_lens) / max(1, len(lyric_lens))
        by_text = max(1, int(round(norm_len / max(1.0, avg_len))) + 1)
        by_time = max(1, int(float(duration) // 1.7) + 1)
        return max(1, min(cap, max(by_text, by_time)))

    def _make_segment_group(self, entries: List[Tuple[float, float, str]], start_idx: int, end_idx: int) -> Tuple[float, float, str]:
        start = float(entries[start_idx][0])
        end = float(entries[end_idx][1])
        text = " ".join(str(entries[i][2] or "").strip() for i in range(start_idx, end_idx + 1)).strip()
        return start, end, text

    def _valid_group_end_indices(self, entries: List[Tuple[float, float, str]], start_idx: int, consumed: List[bool]) -> List[int]:
        ends = []
        last_end = float(entries[start_idx][1])
        for end_idx in range(start_idx, min(len(entries), start_idx + self.max_merge_segments)):
            if consumed[end_idx]:
                break
            if end_idx > start_idx:
                gap = float(entries[end_idx][0]) - last_end
                if gap > self.merge_max_gap_sec:
                    break
            ends.append(end_idx)
            last_end = float(entries[end_idx][1])
        return ends

    def _find_best_lyric_block_for_segment(self,
                                           asr_text: str,
                                           lyrics: List[str],
                                           lyric_ptr: int,
                                           max_block_lines: int = 4,
                                           look_back: int = 2,
                                           look_ahead: Optional[int] = None,
                                           seg_duration: Optional[float] = None) -> Optional[Dict[str, Any]]:
        M = len(lyrics)
        if M == 0:
            return None
        if look_ahead is None:
            look_ahead = max(6, int(self.search_window))
        norm_asr = SimilarityScorer.normalize(asr_text)
        if not norm_asr:
            return None

        start_min = max(0, lyric_ptr - look_back)
        start_max = min(M, lyric_ptr + look_ahead)
        best: Optional[Dict[str, Any]] = None

        for start_i in range(start_min, start_max):
            parts: List[str] = []
            for block_size in range(1, max_block_lines + 1):
                end_i = start_i + block_size
                if end_i > M:
                    break
                parts.append(lyrics[end_i - 1])
                candidate = "".join(parts)
                raw_score = SimilarityScorer.score_pair(norm_asr, candidate)

                distance = abs(start_i - lyric_ptr)
                position_penalty = min(0.30, distance * 0.030)
                block_penalty = max(0, block_size - 1) * 0.015
                duration_fit = 1.0
                required_duration = 0.0
                duration_penalty = 0.0
                duration_ok = True
                if seg_duration is not None:
                    duration_ok, duration_fit, required_duration = self._duration_fit_for_block(
                        lyrics, start_i, end_i, float(seg_duration), strict_ratio=0.45
                    )
                    duration_penalty = max(0.0, 1.0 - min(1.0, duration_fit)) * 0.35

                final_score = raw_score - position_penalty - block_penalty - duration_penalty
                if best is None or final_score > best["score"]:
                    best = {
                        "start_i": start_i,
                        "end_i": end_i,
                        "score": final_score,
                        "raw_score": raw_score,
                        "block_size": block_size,
                        "candidate": candidate,
                        "duration_fit": duration_fit,
                        "required_duration": required_duration,
                        "duration_ok": duration_ok,
                    }
        return best

    def _choose_best_group_match(self,
                                 entries: List[Tuple[float, float, str]],
                                 consumed: List[bool],
                                 seg_idx: int,
                                 lyrics: List[str],
                                 lyric_ptr: int) -> Optional[Dict[str, Any]]:
        """为当前 ASR 段选择最佳 group ↔ lyric block 候选。

        优先级：
        1. 当前位置附近 strong/normal match；
        2. 更宽范围 broad strong match；
        3. weak sequential anchor（仅当前位置附近）。
        """
        candidates: List[Dict[str, Any]] = []
        for end_idx in self._valid_group_end_indices(entries, seg_idx, consumed):
            group_start, group_end, group_text = self._make_segment_group(entries, seg_idx, end_idx)
            if not SimilarityScorer.normalize(group_text):
                continue
            group_duration = group_end - group_start
            max_lines = self._max_block_lines_for_segment(group_text, lyrics, group_duration, cap=self.max_block_lines)

            near_best = self._find_best_lyric_block_for_segment(
                group_text, lyrics, lyric_ptr,
                max_block_lines=max_lines,
                look_back=1,
                look_ahead=max(6, int(self.search_window)),
                seg_duration=group_duration,
            )
            if near_best:
                candidates.append({**near_best, "seg_idx": seg_idx, "seg_idx_end": end_idx,
                                   "seg_start": group_start, "seg_end": group_end, "seg_text": group_text,
                                   "scope": "near"})

            broad_best = self._find_best_lyric_block_for_segment(
                group_text, lyrics, lyric_ptr,
                max_block_lines=max_lines,
                look_back=0,
                look_ahead=max(10, int(self.search_window) * 2),
                seg_duration=group_duration,
            )
            if broad_best:
                candidates.append({**broad_best, "seg_idx": seg_idx, "seg_idx_end": end_idx,
                                   "seg_start": group_start, "seg_end": group_end, "seg_text": group_text,
                                   "scope": "broad"})

        if not candidates:
            return None

        strong_threshold = float(self.threshold_1)
        normal_threshold = float(self.threshold_2)

        def classify(c: Dict[str, Any]) -> Tuple[bool, str, float]:
            start_i = int(c["start_i"])
            end_i = int(c["end_i"])
            score = float(c["score"])
            raw = float(c.get("raw_score", score))
            duration_ok = bool(c.get("duration_ok", True))
            group_len = int(c["seg_idx_end"]) - int(c["seg_idx"]) + 1
            start_near = abs(start_i - lyric_ptr) <= self.weak_anchor_max_offset
            ptr_inside = start_i <= lyric_ptr <= end_i

            if not duration_ok:
                return False, "duration_reject", -999.0

            threshold = normal_threshold if ptr_inside or start_near else strong_threshold
            if score >= threshold:
                return True, "strong" if score >= strong_threshold else "normal", score + (0.03 if c.get("scope") == "near" else 0.0) - group_len * 0.01

            # Broad strong：如果 ASR 明确强匹配后面歌词，优先跳过当前缺失段而不是 weak 错绑。
            if c.get("scope") == "broad" and score >= strong_threshold + 0.08:
                return True, "broad_strong", score - 0.02 - group_len * 0.01

            # Weak sequential anchor：只允许当前位置附近，只用于主顺序流程。
            if (self.enable_weak_anchor and c.get("scope") == "near" and start_near
                    and raw >= self.weak_anchor_threshold and score >= self.weak_anchor_threshold - 0.08):
                return True, "weak", score - 0.10 - group_len * 0.015

            return False, "low_score", score

        accepted = []
        rejected_preview = []
        for c in candidates:
            ok, kind, rank = classify(c)
            c["match_kind"] = kind
            c["rank"] = rank
            if ok:
                accepted.append(c)
            else:
                rejected_preview.append(c)

        if not accepted:
            # 只打少量 debug，避免日志爆炸。
            best_rej = max(rejected_preview, key=lambda x: float(x.get("score", -999)), default=None)
            if best_rej:
                self._decision_debug(
                    "跳过ASR[%d] %.2f-%.2f best=%s score=%.3f raw=%.3f fit=%.2f lyric[%d:%d] text=%s",
                    seg_idx,
                    float(entries[seg_idx][0]),
                    float(entries[seg_idx][1]),
                    best_rej.get("match_kind"),
                    float(best_rej.get("score", 0.0)),
                    float(best_rej.get("raw_score", 0.0)),
                    float(best_rej.get("duration_fit", 0.0)),
                    int(best_rej.get("start_i", -1)),
                    int(best_rej.get("end_i", -1)),
                    str(best_rej.get("seg_text", ""))[:80],
                )
            return None

        best = max(accepted, key=lambda x: float(x.get("rank", x.get("score", 0.0))))
        return best

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
                                       match_kind: str = "strong",
                                       low_confidence: bool = False,
                                       asr_text: str = "",
                                       matched_block: str = "",
                                       duration_fit: float = 1.0,
                                       required_duration: float = 0.0) -> None:
        if end_i <= start_i:
            return

        seg_idx_end = seg_idx if seg_idx_end is None else seg_idx_end
        seg_start = float(seg_start)
        seg_end = float(seg_end)
        duration = max(0.05, seg_end - seg_start)
        indices = list(range(start_i, end_i))
        weights = [self._line_weight(lyrics[i]) for i in indices]
        total_weight = max(1, sum(weights))

        cursor = seg_start
        for pos, i in enumerate(indices):
            if pos == len(indices) - 1:
                line_end = seg_end
            else:
                line_end = cursor + duration * weights[pos] / total_weight

            min_line_duration = min(0.35, duration / max(1, len(indices)))
            line_end = max(cursor + min_line_duration, line_end)
            if pos != len(indices) - 1:
                line_end = min(line_end, seg_end)
            else:
                line_end = seg_end

            old_score = float(result[i].get("score", 0.0) or 0.0)
            old_source = str(result[i].get("_source") or "")
            is_fallback = old_source in ("", "interpolate", "uniform_fallback")
            should_update = (not result[i].get("matched")) or is_fallback or score > old_score + 0.05

            if should_update:
                result[i].update({
                    "start": cursor,
                    "end": max(cursor + 0.05, line_end),
                    "score": float(score),
                    "matched": True,
                    "interpolated": len(indices) > 1,
                    "low_confidence": bool(low_confidence),
                    "_source": source,
                    "_match_kind": match_kind,
                    "_srt_idx": seg_idx,
                    "_srt_idx_end": seg_idx_end,
                    "_asr_text": asr_text[:300],
                    "_matched_block": matched_block[:300],
                    "_duration_fit": float(duration_fit),
                    "_required_duration": float(required_duration),
                })
            cursor = max(cursor + 0.05, line_end)

        self._decision_debug(
            "%s匹配: ASR[%d-%d] %.2f-%.2f score=%.3f fit=%.2f lyric[%d:%d] \"%s\" <- \"%s\"",
            "弱锚点" if low_confidence else "强/普通",
            seg_idx,
            seg_idx_end,
            seg_start,
            seg_end,
            float(score),
            float(duration_fit),
            start_i,
            end_i,
            (matched_block or "".join(lyrics[start_i:end_i]))[:80],
            asr_text[:100],
        )

    def _interpolate_missing_lines(self,
                                   result: List[Dict[str, Any]],
                                   audio_duration: float = 0.0,
                                   default_duration: float = 1.6) -> None:
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
                    "low_confidence": True,
                    "_source": "uniform_fallback",
                    "_match_kind": "fallback",
                })
            logger.warning("没有可靠 ASR 锚点，使用均匀兜底分配 %d 行歌词", M)
            return

        for i, a in enumerate(result):
            if a.get("matched"):
                continue

            prev_i = next((k for k in range(i - 1, -1, -1) if result[k].get("matched")), None)
            next_i = next((k for k in range(i + 1, M) if result[k].get("matched")), None)

            reason = ""
            if prev_i is not None and next_i is not None:
                prev_end = float(result[prev_i]["end"])
                next_start = float(result[next_i]["start"])
                slots = next_i - prev_i
                gap = max(0.2, (next_start - prev_end) / max(1, slots))
                start = prev_end + gap * (i - prev_i - 1)
                end = min(next_start - 0.05, start + max(0.3, gap * 0.85))
                if end <= start:
                    end = start + 0.5
                reason = f"between {prev_i}->{next_i}"
            elif prev_i is not None:
                prev_end = float(result[prev_i]["end"])
                prev_dur = max(0.6, float(result[prev_i]["end"]) - float(result[prev_i]["start"]))
                start = prev_end + 0.05
                end = start + min(2.5, prev_dur)
                if audio_duration > 0:
                    end = min(end, audio_duration)
                reason = f"after {prev_i}"
            elif next_i is not None:
                next_start = float(result[next_i]["start"])
                missing_count = next_i + 1
                span = max(0.6 * missing_count, next_start)
                step = span / max(1, missing_count)
                start = max(0.0, i * step)
                end = min(next_start - 0.05, start + max(0.3, step * 0.85))
                if end <= start:
                    end = start + 0.5
                reason = f"before {next_i}"
            else:
                start = i * default_duration
                end = start + default_duration
                reason = "no_anchor"

            a.update({
                "start": float(start),
                "end": float(max(start + 0.05, end)),
                "score": 0.0,
                "matched": True,
                "interpolated": True,
                "low_confidence": True,
                "_source": "interpolate",
                "_match_kind": "interpolate",
            })
            self._decision_debug("插值补齐: lyric[%d] %.2f-%.2f reason=%s text=%s", i, start, end, reason, str(a.get("text", ""))[:80])

    def _find_best_repeat_lyric_block(self,
                                      asr_text: str,
                                      lyrics: List[str],
                                      seg_duration: float,
                                      min_repeat_score: float) -> Optional[Dict[str, Any]]:
        M = len(lyrics)
        if M == 0 or not SimilarityScorer.normalize(asr_text):
            return None
        max_lines = self._max_block_lines_for_segment(asr_text, lyrics, seg_duration, cap=self.max_block_lines)
        best = None
        for start_i in range(M):
            parts = []
            for block_size in range(1, max_lines + 1):
                end_i = start_i + block_size
                if end_i > M:
                    break
                parts.append(lyrics[end_i - 1])
                candidate = "".join(parts)
                score = SimilarityScorer.score_pair(asr_text, candidate)
                duration_ok, fit, required = self._duration_fit_for_block(lyrics, start_i, end_i, seg_duration, strict_ratio=0.60)
                if not duration_ok:
                    score -= 0.30
                score -= max(0, block_size - 1) * 0.01
                if best is None or score > best["score"]:
                    best = {
                        "start_i": start_i,
                        "end_i": end_i,
                        "score": score,
                        "candidate": candidate,
                        "duration_fit": fit,
                        "required_duration": required,
                        "duration_ok": duration_ok,
                    }
        if best and best["score"] >= min_repeat_score and best.get("duration_ok", True):
            return best
        return None

    def _append_unmatched_segments_as_repeats(self,
                                             result: List[Dict[str, Any]],
                                             lyrics: List[str],
                                             srt_entries: List[Tuple[float, float, str]],
                                             consumed: List[bool],
                                             min_repeat_score: Optional[float] = None) -> List[Dict[str, Any]]:
        """把未消耗但可信的 ASR 段作为重复副歌/额外段插入。仅 strong，高阈值。"""
        min_repeat_score = float(min_repeat_score if min_repeat_score is not None else self.repeat_min_score)
        output = list(result)
        start_times = [float(a.get("start", 0.0) or 0.0) for a in output]
        next_idx = max((int(a.get("idx", 0)) for a in output), default=-1) + 1

        j = 0
        while j < len(srt_entries):
            if consumed[j]:
                j += 1
                continue

            best_group = None
            for end_idx in self._valid_group_end_indices(srt_entries, j, consumed):
                start, end, text = self._make_segment_group(srt_entries, j, end_idx)
                if not SimilarityScorer.normalize(text):
                    continue
                if self._is_obvious_non_lyric_segment(text, lyrics):
                    continue
                cand = self._find_best_repeat_lyric_block(text, lyrics, end - start, min_repeat_score=min_repeat_score)
                if cand:
                    cand.update({"seg_idx": j, "seg_idx_end": end_idx, "seg_start": start, "seg_end": end, "seg_text": text})
                    if best_group is None or cand["score"] > best_group["score"]:
                        best_group = cand

            if best_group:
                start_i = int(best_group["start_i"])
                end_i = int(best_group["end_i"])
                start = float(best_group["seg_start"])
                end = float(best_group["seg_end"])
                duration = max(0.05, end - start)
                weights = [self._line_weight(lyrics[i]) for i in range(start_i, end_i)]
                total = max(1, sum(weights))
                cursor = start
                inserted = []
                for pos, i in enumerate(range(start_i, end_i)):
                    if pos == end_i - start_i - 1:
                        line_end = end
                    else:
                        line_end = cursor + duration * weights[pos] / total
                    entry = {
                        "idx": next_idx,
                        "text": lyrics[i],
                        "start": cursor,
                        "end": max(cursor + 0.05, line_end),
                        "score": float(best_group["score"]),
                        "matched": True,
                        "interpolated": True,
                        "low_confidence": False,
                        "_source": "repeat_block",
                        "_match_kind": "repeat_strong",
                        "_srt_idx": int(best_group["seg_idx"]),
                        "_srt_idx_end": int(best_group["seg_idx_end"]),
                        "_asr_text": str(best_group.get("seg_text", ""))[:300],
                        "_matched_block": str(best_group.get("candidate", ""))[:300],
                        "_duration_fit": float(best_group.get("duration_fit", 1.0)),
                        "_required_duration": float(best_group.get("required_duration", 0.0)),
                    }
                    next_idx += 1
                    inserted.append(entry)
                    cursor = max(cursor + 0.05, line_end)

                for entry in inserted:
                    pos = bisect.bisect_right(start_times, float(entry["start"]))
                    output.insert(pos, entry)
                    start_times.insert(pos, float(entry["start"]))

                for k in range(int(best_group["seg_idx"]), int(best_group["seg_idx_end"]) + 1):
                    consumed[k] = True

                self._decision_debug(
                    "重复段插入: ASR[%d-%d] %.2f-%.2f score=%.3f lyric[%d:%d] %s",
                    int(best_group["seg_idx"]), int(best_group["seg_idx_end"]), start, end,
                    float(best_group["score"]), start_i, end_i, str(best_group.get("candidate", ""))[:80]
                )
                j = int(best_group["seg_idx_end"]) + 1
            else:
                j += 1
        return output

    def _align_manual(self, lyrics: List[str], srt_segments: List[dict]) -> List[Dict]:
        """核心对齐：相邻 ASR 区间 ↔ 连续歌词块 + weak sequential anchor。"""
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

        consumed = [False] * len(srt_entries)
        lyric_ptr = 0
        seg_idx = 0

        while seg_idx < len(srt_entries) and lyric_ptr < M:
            if consumed[seg_idx]:
                seg_idx += 1
                continue
            seg_text = str(srt_entries[seg_idx][2] or "").strip()
            if not SimilarityScorer.normalize(seg_text):
                seg_idx += 1
                continue
            if self._is_obvious_non_lyric_segment(seg_text, lyrics):
                self._decision_debug("跳过明显非歌词 ASR[%d] %.2f-%.2f text=%s", seg_idx, srt_entries[seg_idx][0], srt_entries[seg_idx][1], seg_text[:80])
                consumed[seg_idx] = True
                seg_idx += 1
                continue

            best = self._choose_best_group_match(srt_entries, consumed, seg_idx, lyrics, lyric_ptr)
            if not best:
                seg_idx += 1
                continue

            match_kind = str(best.get("match_kind", "strong"))
            low_conf = match_kind == "weak"
            source = "weak_group" if low_conf and int(best["seg_idx_end"]) > int(best["seg_idx"]) else "weak" if low_conf else "block_group" if int(best["seg_idx_end"]) > int(best["seg_idx"]) else "block"

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
                match_kind=match_kind,
                low_confidence=low_conf,
                asr_text=str(best.get("seg_text", "")),
                matched_block=str(best.get("candidate", "")),
                duration_fit=float(best.get("duration_fit", 1.0)),
                required_duration=float(best.get("required_duration", 0.0)),
            )
            for k in range(int(best["seg_idx"]), int(best["seg_idx_end"]) + 1):
                consumed[k] = True
            lyric_ptr = max(lyric_ptr, int(best["end_i"]))
            seg_idx = int(best["seg_idx_end"]) + 1

        audio_duration = max((end for _, end, _ in srt_entries), default=0.0)
        self._interpolate_missing_lines(result, audio_duration=audio_duration)
        result = self._append_unmatched_segments_as_repeats(
            result=result,
            lyrics=lyrics,
            srt_entries=srt_entries,
            consumed=consumed,
            min_repeat_score=self.repeat_min_score,
        )
        result.sort(key=lambda a: (float(a.get("start", 0.0) or 0.0), int(a.get("idx", 0))))
        return result

    @staticmethod
    def _repair_alignment_timeline(alignments: List[Dict],
                                   min_gap: float = 0.03,
                                   min_duration: float = 0.35,
                                   fallback_duration: float = 1.2,
                                   audio_duration: float = 0.0) -> None:
        """轻量修复 SRT 时间线。只做合法化，不承担核心对齐职责。"""
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
            logger.debug("轻量修复 %d 个字幕时间戳", repaired)

    @staticmethod
    def _generate_srt(alignments: List[Dict], lyrics: List[str]) -> str:
        srt_parts = []
        for a in alignments:
            if not a.get("matched"):
                continue
            srt_parts.append(
                f"{len(srt_parts) + 1}\n"
                f"{format_srt_time(float(a['start']))} --> {format_srt_time(float(a['end']))}\n"
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
