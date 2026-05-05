"""
log_setup.py — 统一应用日志配置

终端（stdout）由各模块的 print() 负责面向用户的进度输出；
本模块配置的 logging 写入 stderr / 文件，承载算法/调试细节。

用法（在 main.py 顶部调用一次即可）:
    from src.log_setup import setup_logging
    setup_logging()

各算法模块直接使用标准 logging:
    import logging
    logger = logging.getLogger(__name__)
    logger.debug("内部参数: ...")
    logger.info("一般流程信息")
    logger.warning("非致命降级")
    logger.error("出错: ...")

环境变量:
    MV_LOG_LEVEL  日志级别（DEBUG/INFO/WARNING/ERROR），默认 INFO
    MV_LOG_FILE   写入文件路径（同时仍输出到 stderr），默认不写文件
"""

import logging
import os
import sys


def setup_logging() -> None:
    """配置根 logger。重复调用幂等。"""
    root = logging.getLogger()
    if getattr(root, "_mv_configured", False):
        return

    level_name = os.environ.get("MV_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root.setLevel(level)

    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname).1s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # stderr 流（不污染 CLI 用户的 stdout 进度输出）
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(fmt)
    root.addHandler(stderr_handler)

    log_file = os.environ.get("MV_LOG_FILE")
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
        ))
        root.addHandler(file_handler)

    root._mv_configured = True
