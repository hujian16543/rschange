"""后端测试套件。

本文件的存在使 pytest 推导出的模块名为 `rschange.tests.test_*` 而非裸
`test_*`，从而避免与仓库根 `tests/`（Phase 5 的契约测试）下的同名文件冲突。
`backend/src` 在 `sys.path` 上由根 `pyproject.toml` 的
`[tool.pytest.ini_options].pythonpath` 保证。

共享 fixture 见 `conftest.py`；基线锚点断言标 `@pytest.mark.baseline`。
"""
