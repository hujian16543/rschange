#!/usr/bin/env python
"""容器化资产静态门禁。

背景与边界
----------
阶段出口门 G6.2 / G6.3 依赖真实容器运行（`docker-compose up` 后 `POST /api/detect`
返回基线数字、上传 >1 MB GeoTIFF 不返回 413）。本轮容器**未实际构建**，故这两条
门禁改由本脚本承担其中**可在静态层面判定**的部分：

* nginx 的请求体上限是否真的抬高到后端上限之上（A5 缺陷的判据）
* 反向代理目标与路径改写语义是否与后端 `API_PREFIX` 一致
* 镜像定义的 Python / Node 版本是否与项目声明及 CI 一致
* 运行镜像是否避开了编译期依赖
* 编排是否具备健康检查、命名卷与启动顺序约束
* 构建上下文是否排除了虚拟环境、构建产物与本机配置

本脚本**不能**替代的（验收报告中标注为未验证）：
镜像能否构建成功、容器能否启动、端到端请求能否得到基线数字。

用法
----
    uv run python scripts/verify_containers.py

逐项打印 PASS / FAIL；任一项 FAIL 即以非零码退出（供 CI 使用）。
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path
from typing import Any, Final

import yaml

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def _strip_comments(text: str) -> str:
    """去掉以 `#` 起始的整行注释（nginx 与 Dockerfile 共用此约定）。"""
    return re.sub(r"(?m)^[ \t]*#.*$", "", text)


# ---------------------------------------------------------------------------
# nginx
# ---------------------------------------------------------------------------
def _nginx_directive(text: str, name: str) -> list[str]:
    """返回指令 `name` 的全部取值（不含分号）。"""
    body = _strip_comments(text)
    return [m.group(1).strip() for m in re.finditer(rf"\b{name}\s+([^;{{}}]+);", body)]


def _parse_size_to_bytes(raw: str) -> int | None:
    """把 nginx 的尺寸写法（500m / 1g / 1024k）换算为字节。"""
    match = re.fullmatch(r"(\d+)\s*([kKmMgG]?)", raw.strip())
    if not match:
        return None
    scale = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3}[match.group(2).lower()]
    return int(match.group(1)) * scale


# ---------------------------------------------------------------------------
# Dockerfile
# ---------------------------------------------------------------------------
def _docker_stages(text: str) -> dict[str, str]:
    """按 FROM 指令切分 Dockerfile，返回 `{阶段名: 阶段体}`。

    阶段名取 `AS <alias>` 的别名；无名阶段以镜像引用本身为键。
    """
    stages: dict[str, str] = {}
    current: str | None = None
    buffer: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^\s*FROM\s+(\S+)(?:\s+AS\s+(\S+))?\s*$", line, re.IGNORECASE)
        if match:
            if current is not None:
                stages[current] = "\n".join(buffer)
            current = (match.group(2) or match.group(1)).lower()
            buffer = []
        else:
            buffer.append(line)
    if current is not None:
        stages[current] = "\n".join(buffer)
    return stages


def _base_image(text: str, alias: str) -> str | None:
    """取 `AS <alias>` 阶段的 `FROM` 镜像引用。"""
    match = re.search(
        rf"(?im)^\s*FROM\s+(\S+)(?:\s+AS\s+{re.escape(alias)})\s*$",
        text,
    )
    return match.group(1) if match else None


def _image_version(image: str | None, product: str) -> str | None:
    """从镜像引用中取 `<product>:<version>` 的版本段。

    版本允许只写主版本（`node:22-alpine`），也允许写到次版本
    （`python:3.14-slim-bookworm`）。要求必须写次版本会把一批合法写法误判为
    解析失败。
    """
    if not image:
        return None
    match = re.match(rf"^(?:.*/)?{re.escape(product)}:(\d+(?:\.\d+)?)", image)
    return match.group(1) if match else None


def _expand_defaults(raw: str) -> str:
    """把 compose 的 `${VAR:-默认值}` 写法展开为默认值。

    编排文件用该写法把机器相关取值外置；静态门禁关心的是「默认值是否与项目
    声明一致」，故先展开再比对。不展开会因取值里含冒号与花括号而使下游正则
    全部失配。
    """
    return re.sub(r"\$\{[A-Za-z_][A-Za-z0-9_]*:-([^}]*)\}", r"\1", raw)


# ---------------------------------------------------------------------------
# 判据
# ---------------------------------------------------------------------------
class Report:
    """门禁结果收集器。"""

    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def check(self, ok: bool, name: str, detail: str) -> bool:
        self.rows.append(("PASS" if ok else "FAIL", name, detail))
        return ok

    def emit(self) -> int:
        width = max(len(name) for _, name, _ in self.rows)
        failed = 0
        for status, name, detail in self.rows:
            print(f"[{status}] {name.ljust(width)}  {detail}")
            failed += status == "FAIL"
        print()
        total = len(self.rows)
        if failed:
            print(f"{total - failed}/{total} 项通过，{failed} 项未通过")
            return 1
        print(f"{total}/{total} 项全部通过")
        return 0


def main() -> int:
    report = Report()  # type: ignore[no-untyped-call]

    nginx = _read("docker/nginx.conf")
    backend_dockerfile = _read("docker/Dockerfile.backend")
    frontend_dockerfile = _read("docker/Dockerfile.frontend")
    compose = yaml.safe_load(_read("docker-compose.yml"))
    dockerignore = _read(".dockerignore")
    default_toml = tomllib.loads(_read("config/default.toml"))
    backend_pyproject = tomllib.loads(_read("backend/pyproject.toml"))
    frontend_package = _read("frontend/package.json")
    ci_workflow = (
        _read(".github/workflows/ci.yml")
        if (REPO_ROOT / ".github/workflows/ci.yml").is_file()
        else ""
    )

    services: dict[str, Any] = compose.get("services", {})
    backend_service: dict[str, Any] = services.get("backend", {})
    frontend_service: dict[str, Any] = services.get("frontend", {})
    backend_env: dict[str, Any] = backend_service.get("environment", {}) or {}

    backend_limit_mb: int = default_toml["runtime"]["max_upload_mb"]

    # --- A5：nginx 请求体上限 ------------------------------------------------
    sizes = _nginx_directive(nginx, "client_max_body_size")
    report.check(
        bool(sizes),
        "nginx 设置 client_max_body_size",
        "已设置" if sizes else "缺失：默认上限 1 MB 会让所有 >1 MB 上传在 nginx 层 413",
    )
    nginx_limit_bytes = _parse_size_to_bytes(sizes[0]) if sizes else None
    report.check(
        nginx_limit_bytes is not None and nginx_limit_bytes >= backend_limit_mb * 1024 * 1024,
        "nginx 上限 >= 后端 max_upload_mb",
        f"nginx={sizes[0] if sizes else 'N/A'} 后端={backend_limit_mb}MB",
    )

    # --- 反代语义 ------------------------------------------------------------
    proxy_targets = _nginx_directive(nginx, "proxy_pass")
    # 端口写成 "宿主:容器"；宿主段可能是 `${VAR:-8000}`（自带冒号），故取最后一段。
    container_port = next(
        (str(raw).split(":")[-1] for raw in backend_service.get("ports", [])),
        None,
    )
    expected_target = f"http://backend:{container_port}"
    report.check(
        bool(proxy_targets) and proxy_targets[0].rstrip("/") == expected_target,
        "nginx 代理目标与 compose 一致",
        f"proxy_pass={proxy_targets[0] if proxy_targets else 'N/A'} 期望={expected_target}",
    )
    report.check(
        bool(proxy_targets) and not proxy_targets[0].endswith("/"),
        "nginx proxy_pass 不带尾斜杠",
        "带尾斜杠会剥掉 /api 前缀，与后端 API_PREFIX 冲突"
        if proxy_targets and proxy_targets[0].endswith("/")
        else "保留完整 URI",
    )

    # --- 镜像版本与项目声明 --------------------------------------------------
    builder_python = _image_version(_base_image(backend_dockerfile, "builder"), "python")
    runtime_python = _image_version(_base_image(backend_dockerfile, "runtime"), "python")
    report.check(
        builder_python is not None and builder_python == runtime_python,
        "后端两阶段 Python 版本一致",
        f"builder={builder_python} runtime={runtime_python}",
    )
    requires_python: str = backend_pyproject["project"]["requires-python"]
    lower = re.match(r">=\s*(\d+\.\d+)", requires_python)
    report.check(
        builder_python is not None and lower is not None and builder_python == lower.group(1),
        "后端镜像 Python 版本满足 requires-python 下界",
        f"镜像={builder_python} requires-python={requires_python}",
    )

    # 先剥注释：runtime 阶段的注释里提到 libgdal-dev 是为了说明「禁止退回」，
    # 那不是安装指令。不剥会让判据与提示文本得出相反结论。
    runtime_stage = _strip_comments(_docker_stages(backend_dockerfile).get("runtime", ""))
    no_dev_in_runtime = "-dev" not in runtime_stage
    report.check(
        no_dev_in_runtime,
        "后端 runtime 阶段不装编译期依赖",
        "未发现 -dev 包"
        if no_dev_in_runtime
        else "runtime 阶段出现 -dev 包：会把头文件与 pkg-config 拖进运行镜像",
    )

    node_version = _image_version(_base_image(frontend_dockerfile, "builder"), "node")
    package_node = re.search(r'"@types/node":\s*"\^?([0-9]+)', frontend_package)
    report.check(
        node_version is not None
        and package_node is not None
        and node_version.split(".")[0] == package_node.group(1),
        "前端镜像 Node 主版本与 @types/node 一致",
        f"镜像={node_version} @types/node={package_node.group(1) if package_node else 'N/A'}",
    )

    # --- CI 与镜像的一致性 ---------------------------------------------------
    ci_python = re.search(r'python-version:\s*"?([0-9]+\.[0-9]+\.[0-9]+)"?', ci_workflow)
    pinned = _read(".python-version").strip()
    report.check(
        ci_python is not None and ci_python.group(1) == pinned,
        "CI 的 Python 版本与 .python-version 一致",
        f"CI={ci_python.group(1) if ci_python else '未声明'} .python-version={pinned}",
    )
    ci_node = re.search(r'node-version:\s*"?([0-9]+)', ci_workflow)
    report.check(
        ci_node is not None
        and node_version is not None
        and ci_node.group(1) == node_version.split(".")[0],
        "CI 的 Node 主版本与前端镜像一致",
        f"CI={ci_node.group(1) if ci_node else '未声明'} 镜像={node_version}",
    )

    # --- 编排 ----------------------------------------------------------------
    for name, service in (("backend", backend_service), ("frontend", frontend_service)):
        report.check(
            bool(service.get("healthcheck", {}).get("test")),
            f"compose {name} 定义健康检查",
            "已定义" if service.get("healthcheck", {}).get("test") else "缺失",
        )
    report.check(
        backend_service.get("depends_on") is None
        and frontend_service.get("depends_on", {}).get("backend", {}).get("condition")
        == "service_healthy",
        "compose 用 service_healthy 约束启动顺序",
        "前端等待后端健康"
        if frontend_service.get("depends_on", {}).get("backend", {}).get("condition")
        == "service_healthy"
        else "未使用 service_healthy：后端冷启动期间会向后端用户暴露 502",
    )
    data_volumes = [v for v in backend_service.get("volumes", []) if str(v).endswith("/app/data")]
    report.check(
        bool(data_volumes)
        and all(":" in str(v) and not str(v).startswith((".", "/")) for v in data_volumes),
        "compose 的 /app/data 使用命名卷",
        f"{data_volumes}" if data_volumes else "未挂载 /app/data",
    )
    report.check(
        "rschange-data" in (compose.get("volumes") or {}),
        "compose 声明命名卷",
        "rschange-data"
        if "rschange-data" in (compose.get("volumes") or {})
        else "未在顶层 volumes 声明",
    )

    # --- 配置一致性 ----------------------------------------------------------
    compose_limit_raw = _expand_defaults(
        str(backend_env.get("RSCHANGE_RUNTIME__MAX_UPLOAD_MB", ""))
    )
    compose_limit = re.fullmatch(r"(\d+)", compose_limit_raw.strip())
    report.check(
        compose_limit is not None and int(compose_limit.group(1)) == backend_limit_mb,
        "compose 上传上限默认值与 default.toml 一致",
        f"compose={compose_limit.group(1) if compose_limit else 'N/A'} default.toml={backend_limit_mb}",
    )
    origins_raw = _expand_defaults(str(backend_env.get("RSCHANGE_RUNTIME__ALLOWED_ORIGINS", "")))
    frontend_port_raw = _expand_defaults(
        next((str(p) for p in frontend_service.get("ports", [])), "")
    )
    origin_port = re.search(r"localhost:(\d+)", origins_raw)
    frontend_port = re.match(r"(\d+)", frontend_port_raw)
    report.check(
        origin_port is not None
        and frontend_port is not None
        and origin_port.group(1) == frontend_port.group(1),
        "compose 前端端口与 CORS 白名单一致",
        f"端口={frontend_port.group(1) if frontend_port else 'N/A'} "
        f"CORS={origin_port.group(1) if origin_port else 'N/A'}",
    )

    # --- 构建上下文 ----------------------------------------------------------
    lines = {line.strip() for line in _strip_comments(dockerignore).splitlines() if line.strip()}
    required = [".venv/", "engine/build/", "node_modules/", "config/local.toml"]
    missing = [item for item in required if item not in lines]
    report.check(
        not missing,
        ".dockerignore 排除必要条目",
        "缺失：" + "、".join(missing) if missing else "四项齐备",
    )

    # --- 机器相关路径 --------------------------------------------------------
    crafted = {
        "docker/Dockerfile.backend": backend_dockerfile,
        "docker/Dockerfile.frontend": frontend_dockerfile,
        "docker/nginx.conf": nginx,
        "docker-compose.yml": _read("docker-compose.yml"),
    }
    machine_pattern = re.compile(r"[A-Za-z]:[\\/]Users|/c/Users|msys64|HUJIAN", re.IGNORECASE)
    offenders = [name for name, text in crafted.items() if machine_pattern.search(text)]
    report.check(
        not offenders,
        "容器化资产不含机器相关绝对路径",
        "命中：" + "、".join(offenders) if offenders else "均无命中",
    )

    return report.emit()


if __name__ == "__main__":
    sys.exit(main())
