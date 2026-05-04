"""Isolated faster-whisper worker.

Runs CTranslate2/faster-whisper in a child process so native CUDA crashes do not
take down the main MV pipeline process.
"""

import argparse
import json
import os
from pathlib import Path


def setup_cuda_dll_paths() -> None:
    base = Path(os.environ.get("VIRTUAL_ENV", Path(__file__).resolve().parents[1] / ".venv"))
    candidates = [
        base / "Lib" / "site-packages" / "nvidia" / "cublas" / "bin",
        base / "Lib" / "site-packages" / "nvidia" / "cudnn" / "bin",
    ]
    extra_paths = [str(p) for p in candidates if p.exists()]
    if extra_paths:
        os.environ["PATH"] = os.pathsep.join(extra_paths + [os.environ.get("PATH", "")])
        add_dll_directory = getattr(os, "add_dll_directory", None)
        if add_dll_directory:
            for path in extra_paths:
                add_dll_directory(path)


def json_safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    try:
        return value.item()
    except Exception:
        return str(value)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--models", required=True)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--compute-type", default="default")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--vad-filter", action="store_true")
    parser.add_argument("--word-timestamps", action="store_true")
    parser.add_argument("--initial-prompt", default="")
    return parser.parse_args()


def main() -> None:
    setup_cuda_dll_paths()

    from faster_whisper import WhisperModel

    args = parse_args()
    audio_path = str(Path(args.audio).expanduser().resolve())
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    device = args.device
    if device == "auto":
        device = "cuda"
    if str(device).startswith("cuda"):
        device = "cuda"

    compute_type = args.compute_type or "default"
    if device == "cpu" and compute_type in ("float16", "int8_float16"):
        compute_type = "int8"

    last_error = None
    for model_name in [m.strip() for m in args.models.split(",") if m.strip()]:
        try:
            print(
                f"      faster-whisper {model_name} ({device}, "
                f"compute_type={compute_type}, beam={args.beam_size}, vad={args.vad_filter})...",
                flush=True,
            )
            kwargs = {"device": device}
            if compute_type != "default":
                kwargs["compute_type"] = compute_type
            model = WhisperModel(model_name, **kwargs)
            segments_iter, info = model.transcribe(
                audio_path,
                language=args.language or None,
                task="transcribe",
                beam_size=args.beam_size,
                word_timestamps=args.word_timestamps,
                vad_filter=args.vad_filter,
                initial_prompt=args.initial_prompt or None,
            )

            segments = []
            text_parts = []
            for segment in segments_iter:
                text = str(segment.text or "")
                text_parts.append(text)
                data = {
                    "id": json_safe(getattr(segment, "id", None)),
                    "seek": json_safe(getattr(segment, "seek", None)),
                    "start": float(segment.start),
                    "end": float(segment.end),
                    "text": text,
                    "tokens": json_safe(getattr(segment, "tokens", None)),
                    "avg_logprob": json_safe(getattr(segment, "avg_logprob", None)),
                    "compression_ratio": json_safe(getattr(segment, "compression_ratio", None)),
                    "no_speech_prob": json_safe(getattr(segment, "no_speech_prob", None)),
                }
                if args.word_timestamps:
                    data["words"] = [
                        {
                            "start": None if word.start is None else float(word.start),
                            "end": None if word.end is None else float(word.end),
                            "word": str(word.word or ""),
                            "probability": json_safe(getattr(word, "probability", None)),
                        }
                        for word in (getattr(segment, "words", []) or [])
                    ]
                segments.append(data)

            if not segments:
                print(f"      faster-whisper {model_name} returned no segments", flush=True)
                continue

            payload = {
                "text": "".join(text_parts),
                "segments": segments,
                "language": str(getattr(info, "language", args.language) or args.language),
                "language_probability": json_safe(getattr(info, "language_probability", None)),
                "duration": json_safe(getattr(info, "duration", None)),
                "duration_after_vad": json_safe(getattr(info, "duration_after_vad", None)),
                "_worker_model": model_name,
                "_worker_device": device,
                "_worker_compute_type": compute_type,
            }
            output_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            print(
                f"      [OK] faster-whisper {model_name} ({device}): "
                f"{len(segments)} 段, {payload.get('text', '')[:50]}...",
                flush=True,
            )
            return
        except Exception as exc:
            last_error = exc
            print(f"      faster-whisper {model_name} failed: {exc}", flush=True)

    raise RuntimeError(f"faster-whisper failed for all models: {last_error}")


if __name__ == "__main__":
    main()
