# Peewee 映射规则

只有在用户已经批准 Schema 设计文档，并明确要求继续建模时才读取本文件。

## 目标

- 将逻辑模型映射为 Peewee Model。
- 保留文档中的主键、外键、唯一约束和索引建议。
- 不生成 DDL，不承担部署职责。

## Peewee Model 设计原则

- 一个核心实体对应一个 `Peewee Model`。
- 代理键、自然唯一键、复合唯一键都要在模型层表达清楚。
- 核心事实表与快照表不要混在一个 Model 中。
- 事件流对象优先建成 append-only 事实模型。

## 字段映射建议

- 标识字段统一英文命名，尽量和文档一致。
- 时间戳字段命名保持显式：
  - `exchange_time`
  - `broker_time`
  - `ingest_time`
  - `processed_at`
- 原始 payload 可用文本字段或 JSON 字段承载，具体取决于项目既有习惯。

## 关系映射建议

- 核心关系优先用 `ForeignKeyField`。
- 复合业务唯一性不能只靠注释，需体现在 Meta 索引或唯一约束建议中。
- 多腿组合可拆为组合头实体与腿明细实体，不要只靠嵌套 JSON 表达。

## 执行生命周期映射

- `signal_event`、`execution_intent`、`order`、`order_event`、`fill_event`、`trade`、`position_lot`、`position_snapshot` 按职责拆模。
- `roll` / `hedge` / `unwind` 可以统一成动作事件模型，也可以拆专用模型，但必须保持来源可追溯。

## 输出时要带上的说明

- 每个 Model 对应哪个文档实体
- 主键与唯一键如何映射
- 哪些索引是为查询优化，哪些是为幂等或约束服务
- 哪些对象是快照，哪些对象是事实

## 禁止项

- 不生成 DDL
- 不讨论迁移脚本
- 不把部署细节混入 Peewee Model 设计说明
