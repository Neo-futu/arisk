"""Standalone development scripts.

- ``riskengine/`` — 开发用引擎包
  - ``config.py``  引入、参数、夹具 / DB 组合加载
  - ``objects.py`` Engine / BoundEngine / SliceSpec
  - ``main.py``    BoundEngine 示例运行
- ``run_riskengine.py`` — 仓库根启动器
- ``platform_workflow.py`` — 平台闭环，``import riskengine`` 嵌入引擎
"""
