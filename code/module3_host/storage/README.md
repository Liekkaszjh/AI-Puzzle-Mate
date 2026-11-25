# 存储模块 · SQLite

唯一实现入口为 `repository.py`。SQLite 使用外键、WAL 和事务；游戏写入通过版本号做乐观并发校验，冲突返回业务层处理。模型请求期间不占用数据库写事务。

数据库默认在根目录 `data/puzzle-mate.sqlite3`，可通过 `DATABASE_PATH` 设置。无需独立数据库服务。

表：`users`（匿名用户/昵称）、`sessions`（浏览器会话/CSRF/当前局）、`puzzles`（含秘密答案的题库）、`games`（回合/评分/版本）、`messages`（有序对话）、`teammate_memories`（单局公开问答）、`schema_version`（当前结构 v1）。

队友记忆只保留已公开的 `actor/kind/question/verdict`，与对话在同一事务提交。不是跨局画像或向量记忆。昵称是展示信息，匿名 Cookie 是会话凭证，不提供密码登录、跨设备找回或多人房间。

旧 JSON 题库可从根目录执行 `python scripts/import_puzzles.py` 导入。重复 ID 跳过，内存会话无法迁移。导入脚本不使用模型。

修改 schema 时提供可重复执行的迁移；禁止删除用户库重建。现阶段首次启动自动创建 v1 表。
