"""
log_setup.py — 统一应用日志配置

终端（stdout）由各模块的 print() 负责面向用户的进度输出；
本模块配置的 logging 写入 stderr / 可选文件，承载算法/调试细节。

═══════════════════════════════════════════════════════════
终端级别（MV_LOG_LEVEL）与文件级别（MV_LOG_FILE_LEVEL）独立控制
═══════════════════════════════════════════════════════════

终端（stderr）级别 — 三层优先级：
    ① CLI 参数   --log-level DEBUG
    ② 环境变量   MV_LOG_LEVEL=DEBUG
    ③ .env 文件  MV_LOG_LEVEL=DEBUG
    ④ 默认       INFO

文件级别（仅在配置了 MV_LOG_FILE 时生效）— 同样三层优先：
    ① CLI 参数   --log-file-level DEBUG
    ② 环境变量   MV_LOG_FILE_LEVEL=DEBUG
    ③ .env 文件  MV_LOG_FILE_LEVEL=DEBUG
    ④ 默认       DEBUG（文件默认捕获全部细节）

典型配置：
  .env:  MV_LOG_LEVEL=INFO          → 终端只看摘要
         MV_LOG_FILE=logs/mv.log    → 文件自动 DEBUG，记录完整 prompt/response
  临时调试终端：  --log-level DEBUG  → 终端也输出完整内容

写文件路径（优先级从高到低）:
    ① CLI:  --log-file <path>         显式指定完整路径，最高优先
    ② env:  MV_LOG_FILE=<path>        固定路径（每次覆盖）
    ③ env:  MV_LOG_DIR=logs           推荐：目录 + 自动命名 {run_name}.log
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
                logger.warning("读取 .env 文件失败")
            return None
        current = current.parent
    return None


def _resolve_level(cli_level: Optional[str],
                   env_key: str = "MV_LOG_LEVEL",
                   default: int = logging.INFO) -> int:
    """按优先级 CLI > env > .env > default 解析日志级别。"""
    candidates = (
        cli_level,
        os.environ.get(env_key),
        _read_env_file(env_key),
    )
    for raw in candidates:
        if not raw:
            continue
        name = str(raw).strip().upper()
        if name in _VALID_LEVELS:
            return getattr(logging, name)
    return default


def _project_root() -> Path:
    """定位项目根目录（.env 所在的那一层，向上最多 5 层）。"""
    current = Path.cwd()
    for _ in range(5):
        if (current / ".env").exists():
            return current
        current = current.parent
    return Path.cwd()


def _resolve_file(cli_file: Optional[str]) -> Optional[Path]:
    """按优先级 CLI > env > .env 解析日志文件路径，未配置则返回 None。
    相对路径相对项目根（.env 所在目录）解析。
    """
    for raw in (cli_file, os.environ.get("MV_LOG_FILE"), _read_env_file("MV_LOG_FILE")):
        if raw and str(raw).strip():
            p = Path(str(raw).strip())
            if not p.is_absolute():
                p = _project_root() / p
            return p
    return None


def _resolve_log_dir() -> Path:
    """读取 MV_LOG_DIR（env > .env），未配置默认 logs/（项目根目录下）。"""
    for raw in (os.environ.get("MV_LOG_DIR"), _read_env_file("MV_LOG_DIR")):
        if raw and str(raw).strip():
            p = Path(str(raw).strip())
            if not p.is_absolute():
                p = _project_root() / p
            return p
    return _project_root() / "logs"


def setup_logging(cli_level: Optional[str] = None,
                  cli_file: Optional[str] = None,
                  cli_file_level: Optional[str] = None,
                  run_name: Optional[str] = None) -> None:
    """配置根 logger。可重复调用：会覆盖之前的级别和 handler。

    终端与文件使用独立级别：
      - 终端（stderr）：MV_LOG_LEVEL，默认 INFO
      - 文件：MV_LOG_FILE_LEVEL，默认 DEBUG（文件总是捕获完整细节）

    日志文件路径优先级：
      1. --log-file / MV_LOG_FILE（显式指定完整路径）
      2. MV_LOG_DIR + run_name（目录 + 自动命名：{run_name}.log）
      3. 不写文件

    Args:
        cli_level:      终端级别，来自 --log-level，最高优先
        cli_file:       日志文件完整路径，来自 --log-file，最高优先
        cli_file_level: 文件级别，来自 --log-file-level，最高优先
        run_name:       运行标识（如 "秋日落叶_20260505_143022"），用于自动命名日志文件
    """
    root = logging.getLogger()

    # 重新配置时清掉旧 handler，避免日志重复输出
    for handler in list(root.handlers):
        if getattr(handler, "_mv_owned", False):
            root.removeHandler(handler)

    console_level = _resolve_level(cli_level, "MV_LOG_LEVEL", logging.INFO)
    file_level = _resolve_level(cli_file_level, "MV_LOG_FILE_LEVEL", logging.DEBUG)

    # 根 logger 取两者最低（让消息能流到各 handler，由 handler 自己过滤）
    root.setLevel(min(console_level, file_level))

    fmt_console = logging.Formatter(
        fmt="%(asctime)s %(levelname).1s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    fmt_file = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # stderr handler：按终端级别过滤
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(console_level)
    stderr_handler.setFormatter(fmt_console)
    stderr_handler._mv_owned = True
    root.addHandler(stderr_handler)

    log_file = _resolve_file(cli_file)
    if log_file is None and run_name:
        log_file = _resolve_log_dir() / f"{run_name}.log"
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
        file_handler.setLevel(file_level)
        file_handler.setFormatter(fmt_file)
        file_handler._mv_owned = True
        root.addHandler(file_handler)

    # 静音第三方库的 DEBUG 噪音（PIL EXIF 标签、urllib3 连接细节等）
    for _noisy in ("PIL", "PIL.Image", "PIL.TiffImagePlugin", "PIL.PngImagePlugin",
                   "urllib3", "urllib3.connectionpool", "httpx", "httpcore",
                   "charset_normalizer"):
        logging.getLogger(_noisy).setLevel(logging.WARNING)
