# 数据持久化需求访谈清单

按下面顺序逐组追问。一次只推进一个领域，不要把所有问题一次抛给用户。

每一组结束后，都输出一个简短小结：

- 新增实体候选
- 新增关系候选
- 建议主键/唯一键
- 是否为核心高范式对象
- 是否允许快照型冗余
- 仍缺失的信息

## 1. 策略上下文与范围

- 策略名称、`strategy-slug`、交易标的范围是什么？
- 是单账户还是多账户？是单策略实例还是多实例并行？
- 哪些数据一旦丢失会影响恢复、回放、风控或审计？
- 哪些数据可以通过重算获得，不必作为核心事实长期保存？

## 2. 合约与标的主数据

- 是否需要持久化 underlying、期权合约、交易所、合约生命周期？
- 合约身份是否由 `exchange + underlying + expiry + strike + option_type + multiplier` 唯一确定？
- 是否需要保存合约原始 payload、上市/退市时间、交易状态？

## 3. 行情与时间序列

- 要不要保存 quote、tick、bar、open interest、chain snapshot？
- 需要区分哪些时间戳：交易所时间、券商时间、接收时间、处理时间？
- 这些行情对象是 append-only 事实，还是允许保留按时点聚合的快照？

## 4. 定价、Greeks 与波动率

- 是否需要持久化 theoretical price、IV、Greeks、vol surface、pricing snapshot？
- 哪些派生分析必须保留以便审计或回放？哪些可以重算？
- 选链评分、定价输入、模型版本是否需要一并保存？

## 5. 执行与生命周期

这是重点领域，必须问细。

### 候选与建仓意图

- 是否区分 candidate universe、selected structure、signal event、execution intent？
- 建仓意图与最终下单是否拆开保存？
- 多腿结构是否需要组合级实体和腿级明细同时存在？

### 订单生命周期

- 是否需要持久化 parent order、child order、order basket？
- 是否保存 submit、ack、partial fill、replace、cancel、reject、expire 的完整事件流？
- 是否需要幂等去重键来处理券商重复回报？

### 成交与持仓生命周期

- 成交要只保留 broker fill，还是还要内部 `trade aggregate`？
- 持仓是按 `position_lot` 管，还是只保存 `position_snapshot`？
- 是否需要保留平均成本、已实现/未实现盈亏、分腿暴露？

### 策略动作生命周期

- 是否需要显式建模 open、scale-in、scale-out、hedge、roll、unwind？
- `roll` / `hedge` / `unwind` 是否需要可追溯回原始建仓意图？
- 到期、行权、指派是否纳入同一生命周期设计？

### 恢复与审计

- 重启恢复依赖哪些可信快照？
- 哪些状态必须通过事件回放还原？
- 是否要保存外部 raw payload、trace id、schema version、config version？

## 6. 账户与风控

- 是否需要保存账户快照、保证金、组合暴露、风控限制、风险事件？
- 风控对象是策略级、账户级还是组合级？
- 风险计算结果属于核心事实，还是只保留触发事件和快照？

## 7. 策略状态与恢复

- 需要哪些 `strategy_state`、`working_order_snapshot`、`position_snapshot`？
- 启动时靠快照恢复，还是靠事件回放恢复，还是两者混合？
- 是否需要记录恢复游标、最后处理时间、配置版本？

## 8. 审计与可追溯性

- 哪些对象必须携带 `trace_id`？
- 是否需要保留用户输入、设计版本、策略配置、原始券商回报？
- 是否需要显式区分业务事实、监控投影和恢复快照？

## 收束时必须确认

- 核心高范式对象有哪些？
- 哪些对象允许为查询或恢复做受控冗余？
- 哪些关系必须体现在主 E-R 图中？
- 文档中还存在哪些待确认项？
