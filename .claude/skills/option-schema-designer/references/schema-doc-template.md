# Schema 设计文档模板

将正式文档写到 `docs/design/schema/<strategy-slug>.md`，并保持中文说明。

```md
# <策略名称> Schema 设计

## 设计目标与上下文

- 策略名称：
- `strategy-slug`：
- 标的范围：
- 运行周期：
- 账户与实例范围：

## 已确认业务约束

- 约束 1
- 约束 2

## 持久化范围清单

- 核心事实：
- 快照：
- 投影：
- 可重算对象：

## 核心实体概览

| 实体 | 角色 | 说明 |
| --- | --- | --- |
| `option_contract` | 合约主数据 | ... |

## E-R 图

<!-- option-schema-designer:er-diagram:start -->
![<策略名称> 主 E-R 图](../../plantuml/charts/<strategy-slug>-er.svg)
<!-- option-schema-designer:er-diagram:end -->

## 实体字典

### `option_contract`

- 角色：
- 主键：
- 自然唯一键：
- 关键字段：
- 是否为核心高范式对象：

## 关系与基数说明

- `underlying` 1:N `option_contract`
- `execution_intent` 1:N `order`

## 范式设计说明

- 哪些对象坚持 3NF / BCNF：
- 哪些对象允许受控冗余：
- 允许冗余的原因：

## 一致性与约束设计

- 主键策略：
- 外键策略：
- 唯一约束：
- 幂等键 / 去重键：
- 时间戳规范：

## 待确认项与 Peewee 映射准备

- 待确认项 1
- 待确认项 2
- Peewee Model 需要保留的索引 / 约束说明
```
