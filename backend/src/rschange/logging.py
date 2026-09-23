"""结构化日志。

不引入 `structlog`：本模块所需的全部能力是「把 `extra` 键值对稳定地渲染
出来」，标准库 `logging` 加一个自定义 `Formatter` 即可覆盖，多一个依赖不划算。

两种格式
--------
* `console` —— 人类可读，供本地开发：

      2026-09-23 21:40:02 INFO  rschange.pipeline  变化检测完成  pixels=7209 rate=0.11

* `json` —— 每行一个 JSON 对象，供容器与日志聚合：

      {"ts":"2026-09-23T13:40:02.145+00:00","level":"INFO","logger":"rschange.pipeline","msg":"变化检测完成","pixels":7209,"rate":0.11}

用法：先在进程边界调用一次 `configure_logging`，其余模块只 `get_logger`。

    configure_logging(level=settings.logging.level, format=settings.logging.format)

本模块**不**导入 `rschange.config`：日志是比配置更底层的设施，配置装载自身
也要能打日志，反向依赖会形成循环。
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any, Final, Literal

__all__ = [
    "ConsoleFormatter",
    "JsonFormatter",
    "StructuredLogger",
    "configure_logging",
    "get_logger",
]

#: `LogRecord` 自带的属性名。渲染 `extra` 时要排除它们，否则每条日志都会带上
#: `pathname`、`thread`、`created` 等十余个与业务无关的字段。
_RESERVED: Final[frozenset[str]] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)

#: 日志格式名。`Literal` 使 `config.LoggingSettings.format` 能复用同一组取值。
FormatName = Literal["console", "json"]


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    """取出调用方通过 `extra=` 传入的自定义字段。"""
    return {
        key: value
        for key, value in record.__dict__.items()
        if key not in _RESERVED and not key.startswith("_")
    }


def _sanitize(fields: dict[str, Any]) -> dict[str, Any]:
    """避开与 `LogRecord` 内置属性同名的键。

    stdlib 见到 `extra` 含保留键时抛 `KeyError`，这会让「打一条日志」本身成为
    崩溃点。调用方传了 `name`、`module` 这类词只是措辞疏忽，不该升级为运行时
    故障；加下划线后缀保留信息即可。
    """
    return {(f"{key}_" if key in _RESERVED else key): value for key, value in fields.items()}


class ConsoleFormatter(logging.Formatter):
    """人类可读格式：时间 级别 记录器 消息 键=值…"""

    default_time_format = "%Y-%m-%d %H:%M:%S"
    default_msec_format = "%s.%03d"

    def format(self, record: logging.LogRecord) -> str:
        head = (
            f"{self.formatTime(record, self.default_time_format)} "
            f"{record.levelname:<5} "
            f"{record.name}  "
            f"{record.getMessage()}"
        )
        extras = _extras(record)
        if extras:
            head += "  " + " ".join(f"{key}={value}" for key, value in extras.items())
        if record.exc_info:
            head += "\n" + self.formatException(record.exc_info)
        return head


class JsonFormatter(logging.Formatter):
    """每行一个 JSON 对象。`ensure_ascii=False` 保留中文原文，便于直接阅读。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update(_extras(record))
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # default=str 兜底不可序列化的 extra 值（如 Path、ndarray），
        # 使日志本身永远不会成为新的崩溃点。
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(
    *,
    level: str = "INFO",
    # 参数名与 config.LoggingSettings 的字段名一致，故用 `format` 而非 `fmt`。
    format: str = "console",
) -> None:
    """装配根记录器。

    幂等：重复调用会先清空既有处理器。若不幂等，「先导入模块触发一次配置、
    再由启动流程配置一次」会导致同一条日志打印两遍。

    输出到 `stderr` 而非 `stdout`：`stdout` 保留给进程的正式输出
    （引擎的 `print_gdal_version` 也走它），混杂日志会让重定向与管道消费变脏。
    """
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter() if format == "json" else ConsoleFormatter())

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level.upper())


class StructuredLogger:
    """把关键字参数当作结构化字段的记录器。

    stdlib 的 `Logger.info` 只接受 `msg` 与 `*args`，结构化字段必须写成

        logger.info("变化检测完成", extra={"pixels": 7209, "rate": 0.11})

    字段名藏在裸字典里：拼错了不报错，只是字段静默消失；`extra` 本身也是个
    容易漏传的位置参数。本包装把字段提到签名上：

        logger.info("变化检测完成", pixels=7209, rate=0.11)

    底层仍是 stdlib logger，因此 `caplog`、`logging.config` 以及 uvicorn 的
    日志配置照常生效——本类不做任何输出侧的接管。
    """

    _logger: logging.Logger
    __slots__ = ("_logger",)

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    @property
    def name(self) -> str:
        return self._logger.name

    def debug(self, message: str, **fields: Any) -> None:
        self._logger.debug(message, extra=_sanitize(fields))

    def info(self, message: str, **fields: Any) -> None:
        self._logger.info(message, extra=_sanitize(fields))

    def warning(self, message: str, **fields: Any) -> None:
        self._logger.warning(message, extra=_sanitize(fields))

    def error(self, message: str, **fields: Any) -> None:
        self._logger.error(message, extra=_sanitize(fields))

    def critical(self, message: str, **fields: Any) -> None:
        self._logger.critical(message, extra=_sanitize(fields))

    def exception(self, message: str, **fields: Any) -> None:
        """记录异常，自动附带 traceback。

        必须在 `except` 块内调用（stdlib 的行为），故它替代的是
        `logger.error(..., exc_info=True)` 这一更易漏写的形式。
        """
        self._logger.exception(message, extra=_sanitize(fields))


def get_logger(name: str) -> StructuredLogger:
    """取记录器。参数应传 `__name__`。"""
    return StructuredLogger(logging.getLogger(name))
