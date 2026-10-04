"""配置装载与结构化日志。"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from rschange.config import Settings
from rschange.logging import (
    ConsoleFormatter,
    JsonFormatter,
    configure_logging,
    get_logger,
)
from rschange.tests.support import make_settings


def _record(level: int = logging.INFO, message: str = "变化检测完成") -> logging.LogRecord:
    return logging.LogRecord("probe", level, __file__, 1, message, None, None)


class TestPrecedence:
    """优先级：显式参数 > 环境变量 > local.toml > default.toml。"""

    def test_explicit_argument_beats_toml(self) -> None:
        assert make_settings(runtime={"port": 1234}).runtime.port == 1234

    def test_env_beats_toml(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RSCHANGE_POSTPROCESS__MIN_SIZE", "77")
        assert Settings().postprocess.min_size == 77

    def test_env_removed_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("RSCHANGE_POSTPROCESS__MIN_SIZE", raising=False)
        assert Settings().postprocess.min_size == 30

    def test_relative_path_resolves_against_repo_root(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """相对路径一律相对仓库根解析。

        断言**禁止**写死预设名。`build_dir` 的最终取值由优先级最高的来源决定：
        `RSCHANGE_ENGINE__BUILD_DIR` > `local.toml` > `default.toml`。CI 的两个
        平台分别注入 `dev-linux` 与 `dev-win`，此前把 `dev-win` 写进断言，于是
        Linux 侧必红——而 Linux 只是忠实反映了注入值，产品行为并没有错。
        这里显式注入一个相对值，判据收敛到规则本身：相对 -> 锚定 repo_root。
        """
        monkeypatch.setenv("RSCHANGE_ENGINE__BUILD_DIR", "./engine/build/some-preset")
        settings = Settings()
        assert settings.build_dir == settings.repo_root / "engine" / "build" / "some-preset"

    def test_effective_build_dir_is_anchored_at_repo_root(self) -> None:
        """不多问取值来源，只问「实际生效的路径是否落在仓库根之下」。

        这一条与上一条互补：上一条钉住规则的形状，这一条保证无论环境变量、
        local.toml 还是 default.toml 胜出，结果都不会跑到仓库外。
        """
        settings = Settings()
        assert settings.build_dir.is_relative_to(settings.repo_root)
        assert settings.uploads_dir.is_relative_to(settings.repo_root)
        assert settings.outputs_dir.is_relative_to(settings.repo_root)

    def test_data_dirs_are_derived_from_data_dir(self, settings: Settings) -> None:
        assert settings.uploads_dir == settings.data_dir / "uploads"
        assert settings.outputs_dir == settings.data_dir / "outputs"

    def test_empty_string_resolves_to_repo_root(self) -> None:
        settings = make_settings(engine={"runtime_dll_dir": ""})
        assert settings.runtime_dll_dir == Settings().repo_root


class TestStrictness:
    """`extra="forbid"` 必须向嵌套模型传播。"""

    def test_unknown_top_level_key_rejected(self) -> None:
        with pytest.raises(ValidationError, match="typo_key"):
            Settings(typo_key=1)  # type: ignore[call-arg]

    @pytest.mark.parametrize("section", ["runtime", "engine", "logging", "postprocess", "baseline"])
    def test_unknown_nested_key_rejected(self, section: str) -> None:
        """每个嵌套模型都要单独拦住。

        `Settings.model_config` 的 `extra` **不会**传播到嵌套模型；缺了
        `_StrictModel` 时 `{"engine": {"typo_key": 1}}` 会被静默忽略，表现为
        「我改了配置但没生效」——最难定位的一类配置问题。
        """
        with pytest.raises(ValidationError, match="typo_key"):
            make_settings(**{section: {"typo_key": 1}})

    def test_wildcard_origin_rejected(self) -> None:
        """D1 的前置拦截：`"*"` 与凭据并存时白名单失效。"""
        with pytest.raises(ValidationError, match="禁止包含"):
            make_settings(runtime={"allowed_origins": ["*"]})

    @pytest.mark.parametrize("key", ["legacy_build_dir", "legacy_fixtures_dir"])
    def test_legacy_baseline_paths_rejected(self, key: str) -> None:
        """`legacy_*` 非空即说明有人在回退旧仓库路径，必须启动期失败。"""
        with pytest.raises(ValidationError, match="必须为空"):
            make_settings(baseline={key: "../legacy"})

    @pytest.mark.parametrize(
        ("field", "value"),
        [("port", 0), ("port", 70000), ("max_upload_mb", 0)],
    )
    def test_out_of_range_values_rejected(self, field: str, value: int) -> None:
        with pytest.raises(ValidationError):
            make_settings(runtime={field: value})

    def test_max_upload_bytes_is_derived(self) -> None:
        settings = make_settings(runtime={"max_upload_mb": 2})
        assert settings.runtime.max_upload_bytes == 2 * 1024 * 1024


class TestFormatters:
    def test_json_formatter_emits_single_line_object(self) -> None:
        record = _record()
        record.pixels = 7209  # 模拟 logger.info(..., pixels=7209) 产生的 extra
        payload = json.loads(JsonFormatter().format(record))
        assert payload["msg"] == "变化检测完成"
        assert payload["logger"] == "probe"
        assert payload["level"] == "INFO"
        assert payload["pixels"] == 7209
        assert "\n" not in JsonFormatter().format(record)

    def test_json_formatter_keeps_chinese_unescaped(self) -> None:
        assert "变化检测完成" in JsonFormatter().format(_record())

    def test_json_formatter_survives_non_serializable_extra(self) -> None:
        """`default=str` 兜底：日志本身不能成为新的崩溃点。"""
        record = _record()
        record.where = Path("C:/tmp/x.tif")
        assert "x.tif" in JsonFormatter().format(record)

    def test_console_formatter_renders_fields(self) -> None:
        record = _record()
        record.pixels = 7209
        text = ConsoleFormatter().format(record)
        assert "变化检测完成" in text
        assert "pixels=7209" in text


class TestStructuredLogger:
    def test_fields_are_attached_to_record(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="rschange.tests.probe"):
            get_logger("rschange.tests.probe").info("变化检测完成", pixels=7209, detector="cva")
        assert caplog.records, "未捕获到日志"
        record = caplog.records[-1]
        # 字段由 StructuredLogger 经 `extra=` 注入；stdlib `LogRecord` 没有这些
        # 属性声明，静态检查不可见，故逐处放行（而非整文件关掉 attr-defined）。
        assert record.pixels == 7209  # type: ignore[attr-defined]
        assert record.detector == "cva"  # type: ignore[attr-defined]

    def test_reserved_field_names_are_suffixed(self, caplog: pytest.LogCaptureFixture) -> None:
        """与 `LogRecord` 内置属性同名的字段加下划线后缀。

        不加的话 stdlib 会抛 `KeyError`，让「打一条日志」本身成为崩溃点。
        """
        with caplog.at_level(logging.INFO, logger="rschange.tests.probe"):
            get_logger("rschange.tests.probe").info("借用了保留名", name="a", module="b")
        record = caplog.records[-1]
        assert record.__dict__.get("name_") == "a"
        assert record.__dict__.get("module_") == "b"

    def test_all_levels_accept_structured_fields(self, caplog: pytest.LogCaptureFixture) -> None:
        """直接调 `logger.info("m", pixels=7209)` 在「裸 extra」设计下会 TypeError。"""
        with caplog.at_level(logging.DEBUG, logger="rschange.tests.probe"):
            logger = get_logger("rschange.tests.probe")
            logger.debug("a", n=1)
            logger.warning("b", n=2)
            logger.error("c", n=3)
            logger.critical("d", n=4)
        assert [r.getMessage() for r in caplog.records] == ["a", "b", "c", "d"]
        # 同上：`n` 由 `extra=` 注入。
        assert [r.n for r in caplog.records] == [1, 2, 3, 4]  # type: ignore[attr-defined]


class TestConfigureLogging:
    def test_idempotent_and_goes_to_stderr(self) -> None:
        root = logging.getLogger()
        saved_handlers = list(root.handlers)
        saved_level = root.level
        try:
            configure_logging(level="DEBUG", format="json")
            configure_logging(level="DEBUG", format="json")
            assert len(root.handlers) == 1
            handler = root.handlers[0]
            assert isinstance(handler, logging.StreamHandler)
            assert isinstance(handler.formatter, JsonFormatter)
            assert handler.stream is sys.stderr
            assert root.level == logging.DEBUG
        finally:
            for handler in list(root.handlers):
                root.removeHandler(handler)
            for handler in saved_handlers:
                root.addHandler(handler)
            root.setLevel(saved_level)

    def test_console_format_selected_by_name(self) -> None:
        root = logging.getLogger()
        saved_handlers = list(root.handlers)
        saved_level = root.level
        try:
            configure_logging(level="INFO", format="console")
            assert isinstance(root.handlers[0].formatter, ConsoleFormatter)
        finally:
            for handler in list(root.handlers):
                root.removeHandler(handler)
            for handler in saved_handlers:
                root.addHandler(handler)
            root.setLevel(saved_level)
