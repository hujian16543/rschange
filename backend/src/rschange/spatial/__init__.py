"""对 C++ 扩展 `_spatial` 的唯一访问点（附录 D-5）。

全项目**只有** `spatial/loader.py` 解析 DLL 路径并执行 `import _spatial`。
其余模块一律 `from rschange.spatial import read_raster`，永不接触路径。

旧实现把同一段 DLL 路径逻辑复制了四份（`main.py`、`services/detection.py`、
`tests/test_cva.py`、`tests/test_bindings.py`），且各自硬编码 MSYS2 绝对路径。

判定依据：`grep -rn "msys64" backend/` 结果为空（阶段出口门 G3.5）。
"""
