# 模块1 · 出题与审核

- `workflow.py`：LangGraph `PuzzleWorkflow`，作者 → 审核 → 修改；默认最多两次修改，仅通过审核才返回。
- `prompts.py`：作者提示词与创作规则。
- `puzzles.py`：内置演示题与 `validate_generated()` 结构校验。
- `generated_puzzles.json`：保留的 JSON 题库，供根目录导入脚本迁入 SQLite；运行时新题统一由模块3入库。

接口：`PuzzleWorkflow(model, max_revisions=2).generate(theme) -> puzzle`，模型实现共用 `contracts.JsonModel` 协议。输出包含 `id/title/surface/bottom/key_points/generation`，不操作 HTTP 或数据库。

一次通过审核调用模型两次；每次修改再增加两次，默认最多六次。结构或协议错误立即失败，无自动网络重试。图执行中断后需重新生成。

根目录 `engine.AgentEngine` 将此流程与模块2、模块3组合。公共 DeepSeek 客户端位于 `code/llm.py`。协作开发主要修改本目录，模型/引擎协议变化同步 `contracts.py` 和测试。
