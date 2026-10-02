"""根级 `tests/` 的夹具。

为什么有这一层
--------------
conftest 的作用域是**目录树**：`backend/src/rschange/tests/conftest.py` 里的夹具
对根级 `tests/` 不可见。而 `pyproject.toml` 的 `testpaths` 同时收录了两处，根级
`tests/contract/` 的端到端用例需要 `before_path` / `after_path` / `engine_ready`
这批夹具。

在此**重复定义**同一批夹具看似直接，代价是两处会随时间漂移——尤其是 `REPO_ROOT`
的推导层级与 `settings` 的覆盖项，漂移后表现为「同一份夹具在两个目录下行为不同」。

故此处只做**转发**：从包内 conftest 导入夹具对象本身。pytest 把被导入的
`@pytest.fixture` 函数当作本 conftest 定义的夹具，作用域（`session` / `function`）
由被导入对象自带，不因导入而改变。
"""

from __future__ import annotations

from rschange.tests.conftest import (  # noqa: F401
    after_path,
    before_path,
    client,
    context,
    engine_ready,
    fixtures_dir,
    repo_root,
    settings,
)
