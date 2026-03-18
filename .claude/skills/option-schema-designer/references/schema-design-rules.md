# Schema 设计规则

## 总原则

- 核心交易事实优先坚持 3NF / BCNF。
- 快照、投影、缓存类对象允许受控冗余，但必须在文档中说明原因和更新来源。
- 先设计读路径，再决定存储切分：
  - 实时交易
  - 重启恢复
  - 历史回放
  - 风控监控
  - 事后分析

## 标识与主键

- 对于核心事实，优先使用稳定代理键，同时保留自然键唯一约束。
- 期权合约不要只用裸 `symbol` 做身份。
- 需要明确并统一这些标识：
  - `strategy_name`
  - `strategy_instance_id`
  - `gateway_name`
  - `account_id`
  - `exchange`
  - `underlying_symbol`
  - `option_type`
  - `strike`
  - `expiry`
  - `multiplier`
  - `trading_day`
  - `order_ref`
  - `broker_order_id`
  - `fill_id`
  - `trade_id`
  - `position_key`
  - `trace_id`
  - `config_version`
  - `schema_version`

## 外键与唯一约束

- 优先用外键显式表达核心关系，不用一堆松散字符串引用替代。
- 同一实体如果有自然业务唯一性，必须写在文档里，并建议唯一约束。
- 对事件流对象，要同时说明内部 ID 与外部 ID。

## 时间戳规范

- 如果来源提供多个时间戳，必须区分：
  - 交易所时间
  - 券商时间
  - 接收时间
  - 处理时间
- 派生分析必须携带其依赖的市场时间，避免失去上下文。

## 事实、快照、投影的边界

### 核心事实表

- 合约主数据
- 行情事实
- signal / intent
- order / order event
- fill / trade
- 核心风险事件

这些对象默认按高范式处理。

### 快照表

- `position_snapshot`
- `account_snapshot`
- `strategy_state_snapshot`
- `working_order_snapshot`

这些对象允许冗余，但要写清：

- 生成来源
- 更新时机
- 用途是恢复、监控还是查询优化

### 投影表

- 监控看板
- 统计聚合
- 可视化或报表优化

这些对象不应替代核心事实表，也不应被当作重启恢复的唯一来源。

## 执行生命周期规则

- `signal_event` 与 `execution_intent` 是否拆分，必须明确。
- `order` 与 `order_event` 不要混成一个宽表。
- 部分成交、撤单、改价、拒单都要能单独表达。
- `fill_event` 与 `trade aggregate` 的边界要明确。
- `position_lot` 与 `position_snapshot` 的边界要明确。
- `roll` / `hedge` / `unwind` 要能追到来源动作或来源持仓。

## 审计与恢复规则

- 需要回放或合规审计时，优先 append-only 事件流。
- 快照用于恢复，不应替代完整历史。
- 保留 raw payload 的前提：
  - 上游映射不稳定
  - 审计要求高
  - 后续追责需要原始回报

## 文档中必须解释的取舍

- 为什么某个对象属于核心高范式
- 为什么某个对象允许受控冗余
- 为什么使用代理键或自然键
- 为什么某些派生分析选择落库或重算
