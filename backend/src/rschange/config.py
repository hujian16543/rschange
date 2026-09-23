"""分层配置。

优先级（高到低）
----------------
    RSCHANGE_<SECTION>__<KEY>   >   config/local.toml   >   config/default.toml

`RSCHANGE_<SECTION>__<KEY>` 的双下划线是嵌套分隔符，例如
`RSCHANGE_RUNTIME__PORT=9000` 覆盖 `runtime.port`，`RSCHANGE_ENGINE__BUILD_DIR`
覆盖 `engine.build_dir`。非布尔的纯数字值会按整数解析（见 `scripts/engine_env.py`
的同名约定）。

与 `scripts/engine_env.py` 的关系
--------------------------------
两者读同一组文件、遵循同一优先级链，但**互不导入**：`scripts/` 是仓库工具
（backend 未安装时也要能跑），`backend/` 是产品代码。配置格式与优先级的
权威声明在 `config/default.toml` 头部，两侧实现都由它推导。

配置文件的定位
--------------
默认按「本文件上溯三层」得到仓库根，即 `backend/src/rschange/config.py`
→ 仓库根。editable 安装下 `__file__` 指向源码树，该推导成立；真实 wheel
安装下不成立，此时必须由 `RSCHANGE_REPO_ROOT` 显式给出仓库根。
"""

from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

__all__ = [
    "BaselineSettings",
    "EngineSettings",
    "LoggingSettings",
    "PostprocessSettings",
    "RuntimeSettings",
    "Settings",
    "get_settings",
]

ENV_PREFIX: Final[str] = "RSCHANGE_"

#: 仓库根（默认推导值）。上溯层级：config.py → rschange → src → backend → 仓库根。
DEFAULT_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]


def _repo_root_override() -> Path | None:
    """读 `RSCHANGE_REPO_ROOT`。配置文件定位必须先于 pydantic 求值，故直接读环境。"""
    raw = os.environ.get(f"{ENV_PREFIX}REPO_ROOT")
    return Path(raw).resolve() if raw else None


def _default_repo_root() -> Path:
    return _repo_root_override() or DEFAULT_REPO_ROOT


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """递归合并，`override` 覆盖 `base`。与 `scripts/engine_env.py` 的同名实现一致。"""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class _TomlPairSource(PydanticBaseSettingsSource):
    """把 `config/default.toml` 与 `config/local.toml` 合并为一个配置来源。

    pydantic-settings 内置的 `TomlConfigSettingsSource` 只接受单个文件，而本
    项目需要「入库默认值 + 本机覆盖值」两层，故在此自行合并。`local.toml`
    不存在是正常情形（新克隆的仓库、CI 环境），静默跳过。
    """

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        root = _repo_root_override() or DEFAULT_REPO_ROOT
        self._paths: tuple[Path, ...] = (
            root / "config" / "default.toml",
            root / "config" / "local.toml",
        )

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        # 本来源一次性给出整份字典，不按字段取值。
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for path in self._paths:
            if not path.is_file():
                continue
            with path.open("rb") as handle:
                merged = _deep_merge(merged, tomllib.load(handle))
        return merged


class _StrictModel(BaseModel):
    """配置模型的共同基类：拒绝未声明的字段。

    每个嵌套模型都必须单独声明这一条：`Settings.model_config` 里的 `extra`
    **不会**向嵌套模型传播。缺了它，`{"engine": {"typo_key": 1}}` 会被静默
    忽略——表现为「改了配置但没生效」，是最难定位的一类配置问题。
    """

    model_config = ConfigDict(extra="forbid")


class RuntimeSettings(_StrictModel):
    """HTTP 运行时参数。"""

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    #: 上传与输出根目录，相对仓库根解析。
    data_dir: str = "./data"
    max_upload_mb: int = Field(default=500, gt=0)
    allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    @field_validator("allowed_origins")
    @classmethod
    def _reject_wildcard(cls, value: list[str]) -> list[str]:
        """拒绝 `"*"`。

        浏览器规范禁止 `Access-Control-Allow-Origin: *` 与凭据同时出现。旧实现
        写的 `allow_origins=["*"] + allow_credentials=True` 因此是**无效配置**：
        白名单实际失效，任何来源都可通过（D1）。

        在这里前置拦截，让错误在启动期暴露，而不是在生产环境静默退化为
        「允许任何来源」，更不是等浏览器端出现难以定位的 CORS 报错。
        """
        if "*" in value:
            raise ValueError(
                'allowed_origins 禁止包含 "*"：与凭据并存时白名单失效。'
                "应逐条列出前端来源，例如 http://localhost:5173"
            )
        return value

    @property
    def max_upload_bytes(self) -> int:
        """上传大小上限（字节）。配置以 MB 声明，接口以字节比较。"""
        return self.max_upload_mb * 1024 * 1024


class EngineSettings(_StrictModel):
    """空间引擎定位。"""

    #: 原生依赖（GDAL 与 MinGW 运行时）所在目录。Windows 必填；Linux 留空。
    runtime_dll_dir: str = ""
    #: `_spatial` 扩展所在目录，相对仓库根解析。必须与 CMake 预设的输出一致。
    build_dir: str = "./engine/build/dev-win"


class LoggingSettings(_StrictModel):
    """日志。"""

    level: str = "INFO"
    format: Literal["console", "json"] = "console"


class PostprocessSettings(_StrictModel):
    """掩膜后处理参数。

    旧实现把这两项写死在算法模块里（`min_size` 甚至是函数默认值），使「调一下
    最小连通面积试试效果」必须改代码。提为配置后，改 `local.toml` 或设
    `RSCHANGE_POSTPROCESS__MIN_SIZE=50` 即可。
    """

    min_size: int = Field(default=30, ge=0)
    """连通块最小像素数。判定是「严格大于」，即**不超过**该值的块被剔除。"""

    structure_size: int = Field(default=3, ge=1)
    """闭运算结构元边长（像素）。"""


class BaselineSettings(_StrictModel):
    """黄金基线夹具定位。"""

    fixtures_dir: str = "./engine/tests/fixtures"
    #: 仅 Phase 1 使用，指向旧仓库。Phase 2 起必须为空。
    legacy_build_dir: str = ""
    legacy_fixtures_dir: str = ""

    @model_validator(mode="after")
    def _reject_legacy(self) -> BaselineSettings:
        """`legacy_*` 一旦非空即报错。

        字段保留是为了让 Phase 1 写下的配置文件仍能解析。被填值说明有人在
        回退到旧仓库路径——那是配置错误，必须在启动期失败，而不是静默生效
        后让「引擎到底用的是哪份产物」变得无法判断。
        """
        for name in ("legacy_build_dir", "legacy_fixtures_dir"):
            if getattr(self, name):
                raise ValueError(f"baseline.{name} 必须为空：Phase 2 起引擎定位由 engine.* 提供")
        return self


class Settings(BaseSettings):
    """应用配置聚合根。

    `repo_root` 不在 toml 中，由 `RSCHANGE_REPO_ROOT` 或路径推导给出；其余分组
    分别对应 `config/default.toml` 的各个 TOML 表。

    `extra="forbid"`：TOML 里出现模型未声明的键即报错。配置项少且明确，拼写
    错误在启动期失败远比被静默忽略好——后者表现为「我改了配置但没生效」。
    """

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_nested_delimiter="__",
        extra="forbid",
        case_sensitive=False,
    )

    repo_root: Path = Field(default_factory=_default_repo_root)
    runtime: RuntimeSettings = Field(default_factory=RuntimeSettings)
    engine: EngineSettings = Field(default_factory=EngineSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    postprocess: PostprocessSettings = Field(default_factory=PostprocessSettings)
    baseline: BaselineSettings = Field(default_factory=BaselineSettings)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """来源优先级：显式构造参数 > 环境变量 > TOML 文件。

        `env_settings` 必须排在 TOML 之前，否则 `RSCHANGE_*` 无法覆盖文件值。
        `dotenv_settings` 与 `file_secret_settings` 有意不启用：本项目的本机
        覆盖走 `config/local.toml`，两套机制并存只会让「值从哪来」难以追踪。
        """
        del dotenv_settings, file_secret_settings
        return (init_settings, env_settings, _TomlPairSource(settings_cls))

    def resolve(self, raw: str) -> Path:
        """相对路径按仓库根解析；空字符串返回仓库根自身。

        与 `scripts/engine_env.py:resolve_path` 语义一致。
        """
        if not raw:
            return self.repo_root
        path = Path(raw)
        return path if path.is_absolute() else (self.repo_root / path).resolve()

    @property
    def data_dir(self) -> Path:
        return self.resolve(self.runtime.data_dir)

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def outputs_dir(self) -> Path:
        return self.data_dir / "outputs"

    @property
    def build_dir(self) -> Path:
        return self.resolve(self.engine.build_dir)

    @property
    def runtime_dll_dir(self) -> Path:
        return self.resolve(self.engine.runtime_dll_dir)

    @property
    def fixtures_dir(self) -> Path:
        return self.resolve(self.baseline.fixtures_dir)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """进程级配置单例。

    装载要读磁盘、解析 TOML、跑校验，每个请求各做一次是浪费。缓存也使
    「配置在进程生命周期内不变」这一前提显式化。

    测试需要替换配置时调用 `get_settings.cache_clear()`，或直接构造
    `Settings(...)` 显式传入——后者优先，因为它不影响其它用例。
    """
    return Settings()
