# 模块3 · 汤主与游戏服务

| 文件/目录 | 职责 |
| --- | --- |
| `host.py` | 判题提示词、逐事实评分、Python 等权计算总分 |
| `api/app.py` | FastAPI 路由、请求校验、Cookie/CSRF、模块装配 |
| `api/service.py` | 游戏状态机、单人/合作回合、公开状态与队友失败恢复 |
| `storage/repository.py` | SQLite 用户、题库、会话、对话与公开队友记忆 |

判题接口：`judge(client, puzzle, text, kind="question")`；评分接口：`score_reconstruction(client, puzzle, text)`。`__init__.py` 对外导出这两个函数。

应用服务通过根目录 `Engine` 协议调用出题、队友和汤主能力；`code/engine.py` 负责组合三个模块。HTTP 层不直接拼提示词，数据库层不调用模型。SQLite 基础设施集中在本模块的 `storage/` 下供后端使用。

从根目录启动：`python code/run.py --demo`。API 文档：<http://127.0.0.1:8000/docs>。

更多说明：[API](api/README.md)、[存储](storage/README.md)、[团队接口约定](../../docs/software/architecture.md)。
