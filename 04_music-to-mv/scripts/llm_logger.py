#!/usr/bin/env python3
"""
llm_logger.py — 统一 LLM 调用日志记录器
所有 LLM/API 调用统一通过这里记录，实现无遗漏的日志追踪

用法:
    from llm_logger import log_llm

    # 记录成功调用
    log_llm(project_dir, "scene_desc", "MiniMax-M2.7", prompt, response)

    # 记录失败调用
    log_llm(project_dir, "scene_desc", "MiniMax-M2.7", prompt, None, error="timeout")

输出: {project_dir}/metadata/llm_calls/{step}_{ts}.jsonl
每行为一个 JSON 条目，方便追溯。
"""

import json
import os
import time
from pathlib import Path
from datetime import datetime

LOG_DIR_NAME = "llm_calls"

def log_llm(project_dir, step, model, prompt, response=None, error=None, extra=None):
    """
    记录一次 LLM / API 调用

    参数:
        project_dir: 项目根目录
        step: 步骤标识，如 "lyrics", "music", "scene_desc", "variant_desc", "base_char", "scene_img"
        model: 模型/接口名称
        prompt: 发送的完整 prompt
        response: 原始响应内容（dict 或 str），失败时传 None
        error: 错误信息，失败时填写
        extra: 额外信息 dict
    """
    if response is not None and isinstance(response, (dict, list)):
        # 深拷贝避免引用问题
        resp_copy = json.loads(json.dumps(response))
    else:
        resp_copy = response

    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3],
        "step": step,
        "model": model,
        "prompt": prompt,
        "response": resp_copy,
        "error": error,
        "extra": extra or {},
    }

    # 写入 JSONL 文件（每行一个 JSON）
    proj = Path(project_dir)
    log_dir = proj / "metadata" / LOG_DIR_NAME
    log_dir.mkdir(parents=True, exist_ok=True)

    # 文件名: {step}_{unix_ts}.jsonl
    ts_ms = int(time.time() * 1000)
    log_file = log_dir / f"{step}_{ts_ms}.jsonl"

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return log_file


def log_llm_batch(project_dir, step, model, prompt, responses, errors=None):
    """
    记录一次批量 LLM 调用（一次 API 返回多个结果）
    responses: list of {"id": ..., "desc": ...}
    """
    entries = []
    for i, resp in enumerate(responses):
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3],
            "step": f"{step}_{i}",
            "model": model,
            "prompt": prompt if i == 0 else None,  # prompt 只在第一行重复
            "response": resp,
            "error": errors[i] if errors and i < len(errors) else None,
            "extra": {"batch": True, "batch_index": i, "batch_size": len(responses)},
        }
        entries.append(entry)

    proj = Path(project_dir)
    log_dir = proj / "metadata" / LOG_DIR_NAME
    log_dir.mkdir(parents=True, exist_ok=True)

    ts_ms = int(time.time() * 1000)
    log_file = log_dir / f"{step}_{ts_ms}.jsonl"

    with open(log_file, "a", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return log_file
