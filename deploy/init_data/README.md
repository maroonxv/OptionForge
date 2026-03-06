# 数据库初始化指南

请将您的本地数据库架构和数据导出为 `init.sql` 文件，并放置在此目录下。
Docker Postgres 容器在首次启动时，会自动执行此目录下所有的 `.sql` 文件。

## 如何导出数据

如果您本地已安装 PostgreSQL，可以使用以下命令：

```bash
pg_dumpall -U postgres > init.sql
```

请确保文件名为 `init.sql`（或任何以 `.sql` 结尾的文件名）。

> **注意**：出于安全和体积考虑，`init.sql` 已被添加到 `.gitignore` 中。请联系开发人员获取最新的基础数据备份。
