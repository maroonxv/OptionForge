# 示例触发语句

## 普通模式

- 为这个跨式策略设计数据库 schema，并把 E-R 图写到文档里。
- 帮我设计一个用于持久化期权多腿策略执行链路的范式化数据库。
- 先出 `docs/design/schema/iron-condor.md`，要带 Chen notation 的 E-R 图。

## 先规划再落盘

- 先一步步梳理这个期权策略要持久化哪些数据，先不要写文件。
- 用引导式对话帮我做 schema 设计，等我确认后再落盘文档和图。
- 先给我 decision-complete 的数据库设计摘要，再决定要不要生成 Peewee Model。

## 进入 Peewee 阶段

- 我已经确认 schema 文档了，现在继续映射成 Peewee Model。
- 文档不用再改了，继续给我 Peewee 模型设计，不要生成 DDL。

## 典型场景

- 仅设计文档：用户只要 Schema 设计文档和 E-R 图。
- 设计后进入 Peewee：用户批准文档后继续模型化。
- 多腿组合与执行生命周期：用户重点关注组合结构、订单事件、成交和持仓。
- 恢复与审计要求：用户重点关注快照、回放、raw payload、trace id。
