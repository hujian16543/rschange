"""变化检测算法层（可插拔）。

新增一种检测算法只需两步：

1. 实现 `detectors/base.py` 中 `ChangeDetector` 协议规定的接口；
2. 在 `detectors/registry.py` 注册。

**禁止**为此修改 `pipeline/change_detection.py`。该约束由「可插拔验证」用例
守护（阶段出口门 G3.4）：新增算法后，编排层文件的哈希必须不变。
"""
