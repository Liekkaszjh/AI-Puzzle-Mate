# 后端模块 · FastAPI

负责 HTTP 校验、Cookie/CSRF、用户昵称、回合状态与游戏服务编排。业务流程位于 `service.py`；路由和装配位于 `app.py`。

依赖引擎 `Engine` 协议与存储 `Repository`，不在路由内编写提示词或 SQL。前端不导入 Python 实现。新增接口同步更新 OpenAPI 快照和契约文档。

从项目根目录启动：`python code/run.py --demo`，交互接口文档：<http://127.0.0.1:8000/docs>。

完整接口与协作约定见 [架构文档](../../../docs/software/architecture.md)。
