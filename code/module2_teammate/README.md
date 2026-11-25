# 模块2 · AI 队友

核心实现在 `__init__.py`，负责队友小夏的提示词、公开对话推理、重复问题检查和演示线索。

接口：`propose_question(client, surface, history) -> str`。只能接收公开汤面与问答记录，不接收汤底、评分事实、数据库连接或整个游戏对象。共用模型客户端来自 `code/llm.py`。

线索耗尽抛出 `DemoCluesExhausted`；模型错误抛出 `ModelError`。回合控制、失败重试与记忆持久化由模块3负责。本模块不操作浏览器、HTTP 或数据库。

协作时主要修改本目录；接口变更需同步根目录 `contracts.py`、`engine.py` 及相关测试。
