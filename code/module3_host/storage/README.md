# 存储模块 · SQLite

唯一实现入口为 `repository.py`。SQLite 使用外键、WAL 和事务；游戏写入通过版本号做乐观并发校验，冲突返回业务层处理。模型请求期间不占用数据库写事务。

数据库默认在根目录 `data/puzzle-mate.sqlite3`，可通过 `DATABASE_PATH` 设置。无需独立数据库服务。

表：`users`（昵称、邮箱、密码哈希、角色、启用状态和最近登录时间）、`sessions`（浏览器会话/CSRF/当前局）、`puzzles`（含秘密答案的题库）、`games`（回合/评分/版本）、`messages`（有序对话）、`teammate_memories`（单局公开问答）、`schema_version`（当前结构 v3）。

队友记忆只保留已公开的 `actor/kind/question/verdict`，与对话在同一事务提交。不是跨局画像或向量记忆。未登录 Cookie 只用于注册/登录与 CSRF，不能开始游戏。注册、登录和退出会轮换会话标识。密码使用带随机盐的 PBKDF2-SHA256 哈希，不保存明文。管理员只能通过本地脚本创建；禁用玩家会使其会话过期。

旧 JSON 题库可从根目录执行 `python scripts/import_puzzles.py` 导入。重复 ID 跳过，内存会话无法迁移。导入脚本不使用模型。

旧数据库启动时自动增加账号与角色相关列并建立邮箱唯一索引；迁移可重复执行，不删除已有数据。
