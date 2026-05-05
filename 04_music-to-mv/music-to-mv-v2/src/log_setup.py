"""
log_setup.py — 统一应用日志配置

终端（stdout）由各模块的 print() 负责面向用户的进度输出；
本模块配置的 logging 写入 stderr / 可选文件，承载算法/调试细节。

═══════════════════════════════════════════════════════════
日志级别配置 — 三层优先级（从高到低）
═══════════════════════════════════════════════════════════
    ① CLI 参数         python -m src.main --log-level DEBUG ...
    ② 环境变量         MV_LOG_LEVEL=DEBUG python -m src.main ...
    ③ .env 文件        在项目根 .env 写: MV_LOG_LEVEL=DEBUG
    ④ 默认             INFO

后者只在前者未设置时生效。这样：
  - 平时跑：默认 INFO，输出干净
  - 一次性调试：加 --log-level DEBUG
  - CI / 容器：用 MV_LOG_LEVEL 环境变量覆盖
  - 长期 DEBUG：写到 .env 里持久化

写文件配置（同样三层优先）:
    ① CLI:  python -m src.main --log-file mv.log ...
    ② env:  MV_LOG_FILE=mv.log python ...
    ③ .env: MV_LOG_FILE=mv.log
    ④ 默认: 不写文件

═══════════════════════════════════════════════════════════
模块用法
═══════════════════════════════════════════════════════════

main.py 入口（在 argparse 后调用一次）:

    from src.log_setup import setup_logging
    args = parser.parse_args()
    setup_logging(cli_level=args.log_level, cli_file=args.log_file)

各算法模块直接使用标准 logging:

    import logging
    logger = logging.getLogger(__name__)
    logger.debug("内部参数: ...")
    logger.info("一般流程信息")
    logger.warning("非致命降级")
    logger.error("出错: ...")
"""

import logging
import os
import sys
from pathlib import Path
from typing import Optional


_VALID_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def _read_env_file(key: str) -> Optional[str]:
    """从项目根的 .env 简单读取一个键。不依赖 ConfigManager，避免初始化顺序耦合。

    向上最多搜索 5 层目录寻找 .env。返回 None 表示找不到。
    """
    current = Path.cwd()
    for _ in range(5):
        env_path = current / ".env"
        if env_path.exists():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    if k.strip() == key:
                        return v.strip().strip("\"'") or None
            except Exception:
                pass
            return None
        current = current.parent
    return None


def _resolve_level(cli_level: Optional[str]) -> int:
    """按优先级 CLI > env > .env > 默认 INFO 解析日志级别。"""
    candidates = (
        cli_level,
        os.environ.get("MV_LOG_LEVEL"),
        _read_env_file("MV_LOG_LEVEL"),
    )
    for raw in candidates:
        if not raw:
            continue
        name = str(raw).strip().upper()
        if name in _VALID_LEVELS:
            return getattr(logging, name)
    return logging.INFO


def _resolve_file(cli_file: Optional[str]) -> Optional[str]:
    """按优先级 CLI > env > .env 解析日志文件路径，未配置则返回 None。"""
    for raw in (cli_file, os.environ.get("MV_LOG_FILE"), _read_env_file("MV_LOG_FILE")):
        if raw and str(raw).strip():
            return str(raw).strip()
    return None


def setup_logging(cli_level: Optional[str] = None,
                  cli_file: Optional[str] = None) -> None:
    """配置根 logger。可重复调用：会覆盖之前的级别和 handler。

    Args:
        cli_level: 来自命令行的级别（DEBUG/INFO/WARNING/ERROR），最高优先
        cli_file:  来自命令行的日志文件路径，最高优先
    """
    root = logging.getLogger()

    # 重新配置时清掉旧 handler，避免日志重复输出
    for handler in list(root.handlers):
        if getattr(handler, "_mv_owned", False):
            root.removeHandler(handler)

    level = _resolve_level(cli_level)
    root.setLevel(level)

    fmt_console = logging.Formatter(
        fmt="%(asctime)s %(levelname).1s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    fmt_file = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # stderr 流（不污染 CLI 用户的 stdout 进度输出）
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(fmt_console)
    stderr_handler._mv_owned = True
    root.addHandler(stderr_handler)

    log_file = _resolve_file(cli_file)
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(fmt_file)
        file_handler._mv_owned = True
        root.addHandler(file_handler)
