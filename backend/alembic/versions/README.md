"""Alembic 迁移脚本目录。

每个文件代表一次数据库结构变更，由 `alembic revision --autogenerate` 生成后**必须人工复核**：
autogenerate 只会比较 ORM 定义与数据库现状，它无法判断字段重命名与「删除+新增」的区别，
也不会自动补上数据迁移逻辑。
"""
