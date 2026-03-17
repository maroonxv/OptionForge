# Service Activation Runtime Composition Design

**Date:** 2026-03-17

## Goal

将 `config/strategy_config.toml` 中的 `[service_activation]` 从“运行时布尔开关”升级为唯一的能力装配入口，让仓库可以保留完整能力模块，但运行时和应用层只导入、初始化、暴露已启用能力。

## Context

当前脚手架已经具备能力开关，但运行时仍然由中心化代码直接依赖并实例化大量具体领域服务和基础设施对象：

- `src/strategy/strategy_entry.py` 静态导入了大量可选能力类，并在宿主对象上暴露大量可选服务属性。
- `src/strategy/application/lifecycle_workflow.py` 直接根据配置拼装具体服务和基础设施。
- `src/strategy/application/market_workflow.py` 通过 `entry.xxx_service` 判断能力是否存在，并消费这些具体对象。
- 仓库的真实使用方式经常是 template repo 直接生成新项目，而不是依赖 CLI 裁剪式创建，因此“运行时真正按需装配”比“物理删除未使用代码”更重要。

结果是：

- 未启用能力虽然可能不会实例化，但仍被静态导入，应用层仍然知道所有能力的存在。
- 领域服务和应用层之间形成了反向耦合，能力越多，`StrategyEntry` 和 `LifecycleWorkflow` 越膨胀。
- `service_activation` 只是开关，不是 composition root。

## Problem Statement

仓库需要从“中心化装配所有能力，再通过开关局部禁用”迁移到“基于能力清单的懒导入、按需装配、按角色暴露”模型。

新的模型必须满足：

1. 仓库保留完整能力模块，便于 template repo 直接使用。
2. 未启用能力在启动时不会被 import、不会初始化、不会出现在运行时暴露面上。
3. 应用层只依赖稳定的运行时角色，不再静态依赖全部具体领域服务。
4. `service_activation` 成为唯一事实来源，不再由其他地方隐式决定能力启用状态。

## Non-Goals

本次设计不包含以下内容：

- 不做 CLI 生成物理裁剪，也不要求 `create` 命令只复制被启用能力的文件。
- 不重做现有指标服务和信号服务契约。`strategy_contracts.indicator_service` 与 `strategy_contracts.signal_service` 仍然是策略内核必需项。
- 不将所有基础设施都抽象成插件系统。网关、聚合根、订阅工作流等核心宿主能力继续保留为固定内核。
- 不顺带重构具体的定价、风控、执行、对冲算法实现。
- 不引入 facade、coordinator 一类的额外上层封装。上层工作流直接调用显式运行时角色。

## Design Principles

- `service_activation` 是唯一能力清单。
- 先校验能力清单，再导入 provider 模块。
- workflow 只依赖稳定角色，不依赖具体能力类。
- provider 只负责自己的配置、构建和管线贡献。
- 禁用能力等于不存在，而不是存在但返回 `None`。
- 能力依赖和互斥规则只有一份真相。
- 这次重构优先解决装配和边界问题，不扩大为全面领域模型重写。

## Scope Boundary

### 固定内核

以下对象继续作为固定内核存在，不由 `service_activation` 控制：

- `StrategyEntry` 宿主对象
- `EventBridge`
- `LifecycleWorkflow`
- `MarketWorkflow`
- `StateWorkflow`
- `SubscriptionWorkflow`
- `InstrumentManager`
- `PositionAggregate`
- `CombinationAggregate`
- 历史数据读取能力
- 必需网关适配器
- `strategy_contracts` 指定的指标/信号服务

### 可选能力

以下能力由 `service_activation` 唯一控制：

- `future_selection`
- `option_chain`
- `option_selector`
- `position_sizing`
- `pricing_engine`
- `greeks_calculator`
- `portfolio_risk`
- `smart_order_executor`
- `advanced_order_scheduler`
- `delta_hedging`
- `vega_hedging`
- `monitoring`
- `decision_observability`

## Proposed Architecture

### 1. 新增 `src/strategy/runtime/`

新增运行时装配子包，专门负责能力注册、校验与装配。

建议包含以下文件：

- `src/strategy/runtime/models.py`
  - 定义运行时模型和 contribution 模型。
- `src/strategy/runtime/registry.py`
  - 定义能力注册表，保存 provider import path 和元数据。
- `src/strategy/runtime/builder.py`
  - 根据 `service_activation` 校验并构建运行时。
- `src/strategy/runtime/providers/`
  - 每个能力一个 provider 模块。

### 2. `StrategyEntry` 退回为宿主对象

`src/strategy/strategy_entry.py` 只保留：

- 核心宿主状态
- 固定 workflow 实例
- 固定内核对象
- `runtime`

它不再静态导入以下可选类：

- `FutureSelectionService`
- `OptionSelectorService`
- `PricingEngine`
- `GreeksCalculator`
- `PortfolioRiskAggregator`
- `PositionSizingService`
- `SmartOrderExecutor`
- `StrategyMonitor`
- 其他由 `service_activation` 控制的可选能力实现

### 3. `LifecycleWorkflow` 退回为装配入口调用者

`src/strategy/application/lifecycle_workflow.py` 从“直接 new 各种服务”变为：

1. 读取完整配置。
2. 准备固定内核对象。
3. 调用 `StrategyRuntimeBuilder.build(entry, full_config)`。
4. 将构建结果挂到 `entry.runtime`。
5. 执行 runtime 中注册的生命周期 hook。

`LifecycleWorkflow` 不再直接知道可选能力类的构造细节。

### 4. workflow 只消费角色

`src/strategy/application/market_workflow.py` 和 `src/strategy/application/state_workflow.py` 不再通过 `entry.pricing_engine`、`entry.option_selector_service`、`entry.monitor` 等属性工作，而是通过 `entry.runtime` 中的显式角色消费能力。

这不是 service locator。workflow 看到的是固定命名、固定职责的角色位，而不是随意的字符串查找。

## Runtime Model

### `StrategyRuntime`

`StrategyRuntime` 是运行时聚合对象，负责承载“已启用能力对固定工作流角色的贡献”。

建议结构如下：

- `enabled_capabilities`
  - 已启用能力集合，用于诊断和测试。
- `lifecycle`
  - `init_hooks`
  - `start_hooks`
  - `stop_hooks`
- `universe`
  - `initializer`
  - `rollover_checker`
- `open_pipeline`
  - `option_chain_loader`
  - `contract_selector`
  - `greeks_enricher`
  - `pricing_enricher`
  - `risk_evaluator`
  - `sizing_evaluator`
  - `execution_planner`
  - `execution_scheduler`
- `close_pipeline`
  - `close_volume_planner`
  - `risk_evaluator`
  - `execution_planner`
  - `execution_scheduler`
- `portfolio`
  - `rebalance_planner`
- `state`
  - `snapshot_sinks`
- `observability`
  - `trace_sinks`

### `RuntimeKernel`

builder 在装配时会构建一个固定内核对象，供 provider 使用。它只包含固定宿主依赖，例如：

- `entry`
- `logger`
- 固定聚合根
- 固定网关适配器
- 基础配置
- 历史数据访问能力

provider 只在构建期拿到 `RuntimeKernel`，之后通过返回的闭包向 workflow 贡献能力。

## Provider Contract

每个 provider 模块负责一个能力，不负责别的能力。

每个 provider 至少需要声明：

- `key`
- `requires`
- `conflicts`
- `provides_roles`
- `build(entry, full_config, kernel) -> CapabilityContribution`

其中 `CapabilityContribution` 只描述该能力对固定角色位的贡献，例如：

- 某个单例角色的实现
- 某个多例 sink 的追加项
- 某个生命周期 hook

provider 必须满足以下约束：

- provider 模块只在对应能力被启用时才被 import。
- provider 只能读取并构建自己的能力配置。
- provider 不得修改其他 provider 的贡献。
- provider 返回的角色实现可以捕获具体服务实例，但 workflow 看不到这些具体实例。

## Capability Registry

`src/strategy/runtime/registry.py` 保存能力注册元数据，作为唯一真相。

每个注册项至少包含：

- `key`
- `provider_import_path`
- `requires`
- `conflicts`
- `single_roles`
- `multi_roles`

设计要求：

- registry 只保存元数据和 import path，不直接 import provider。
- builder 在完成 manifest 校验前不得导入 provider。
- 未来 CLI 或 scaffold catalog 如果需要能力信息，应消费 registry，而不是维护第二套依赖/互斥规则。

## Pipeline Contribution Model

### 单例角色

单例角色一次只能由一个 provider 占用，例如：

- `universe.initializer`
- `universe.rollover_checker`
- `open_pipeline.option_chain_loader`
- `open_pipeline.contract_selector`
- `open_pipeline.greeks_enricher`
- `open_pipeline.pricing_enricher`
- `open_pipeline.risk_evaluator`
- `open_pipeline.sizing_evaluator`
- `open_pipeline.execution_planner`
- `open_pipeline.execution_scheduler`
- `close_pipeline.close_volume_planner`
- `close_pipeline.risk_evaluator`
- `close_pipeline.execution_planner`
- `close_pipeline.execution_scheduler`
- `portfolio.rebalance_planner`

如果多个 provider 尝试占用同一个单例角色，builder 直接失败。

### 多例角色

多例角色允许多个 provider 追加贡献，例如：

- `lifecycle.init_hooks`
- `lifecycle.start_hooks`
- `lifecycle.stop_hooks`
- `state.snapshot_sinks`
- `observability.trace_sinks`

builder 对多例角色做追加合并，调用顺序采用构建顺序。

### 初始能力与角色映射

首批 provider 的建议映射如下：

- `future_selection`
  - `universe.initializer`
  - `universe.rollover_checker`
- `option_chain`
  - `open_pipeline.option_chain_loader`
- `option_selector`
  - `open_pipeline.contract_selector`
- `greeks_calculator`
  - `open_pipeline.greeks_enricher`
- `pricing_engine`
  - `open_pipeline.pricing_enricher`
- `portfolio_risk`
  - `open_pipeline.risk_evaluator`
  - `close_pipeline.risk_evaluator`
- `position_sizing`
  - `open_pipeline.sizing_evaluator`
  - `close_pipeline.close_volume_planner`
- `smart_order_executor`
  - `open_pipeline.execution_planner`
  - `close_pipeline.execution_planner`
- `advanced_order_scheduler`
  - `open_pipeline.execution_scheduler`
  - `close_pipeline.execution_scheduler`
- `delta_hedging`
  - `portfolio.rebalance_planner`
- `vega_hedging`
  - `portfolio.rebalance_planner`
- `monitoring`
  - `state.snapshot_sinks`
  - `observability.trace_sinks`
  - `lifecycle.stop_hooks`
- `decision_observability`
  - `observability.trace_sinks`

## Workflow Changes

### `MarketWorkflow`

`MarketWorkflow` 保留固定骨架，但阶段实现改为读取 `entry.runtime`。

开仓主链按以下顺序执行：

1. 运行指标阶段。
2. 运行信号阶段。
3. 如果存在 `option_chain_loader`，加载期权链。
4. 如果存在 `contract_selector`，执行选约。
5. 如果存在 `greeks_enricher`，补充 Greeks 信息。
6. 如果存在 `pricing_enricher`，补充理论价格信息。
7. 如果存在 `risk_evaluator`，执行开仓前风险校验。
8. 如果存在 `sizing_evaluator`，评估开仓尺寸。
9. 如果存在 `execution_planner`，生成基础执行计划。
10. 如果存在 `execution_scheduler`，对基础执行计划做调度增强。
11. 将 trace 发送到 `trace_sinks`。

平仓主链按以下顺序执行：

1. 运行平仓信号阶段。
2. 如果存在 `close_volume_planner`，生成平仓数量与方向建议。
3. 如果存在 `risk_evaluator`，执行平仓前风险校验。
4. 如果存在 `execution_planner`，生成基础平仓执行计划。
5. 如果存在 `execution_scheduler`，对平仓执行计划做调度增强。
6. 将平仓 trace 发送到 `trace_sinks`。

批量 bar 处理结束后，如果存在 `portfolio.rebalance_planner`，则按组合级触发点执行一次再平衡评估，并将对冲决策作为独立 trace 发送到 `trace_sinks`。

`delta_hedging` 与 `vega_hedging` 由于在 registry 中互斥，因此都可以安全占用 `portfolio.rebalance_planner` 这个单例角色。

`portfolio_risk` 作为显式风险阶段存在，负责生成风险校验结果并供后续 sizing 或执行阶段消费；它不再只是被动实例化却不参与工作流。

`MarketWorkflow` 不再读取 `service_activation`，也不再读取 `entry.xxx_service` 判断能力是否存在。是否存在某一阶段，由 runtime 角色是否已装配决定。

### `StateWorkflow`

`StateWorkflow` 不再直接依赖 `entry.monitor`。它只遍历 `entry.runtime.state.snapshot_sinks`，将快照发送给所有已启用 sink。

### `LifecycleWorkflow`

`LifecycleWorkflow` 在 `on_start` 和 `on_stop` 中执行 runtime 生命周期 hook，不直接操作监控、可观测性等可选能力对象。

## Configuration Semantics

### `service_activation` 成为完整 manifest

`[service_activation]` 升级为显式、完整的能力清单。

要求如下：

- 所有 registry 中声明的能力键都必须在配置中出现。
- 每个值必须是布尔值。
- 出现未知键时启动失败。
- 缺少已知键时启动失败。

这是一项有意的 breaking change。由于项目尚未部署，本次设计不保留旧的隐式默认行为。

### `strategy_contracts` 仍然保留

以下内容继续从 `strategy_contracts` 读取，不受 `service_activation` 管理：

- `indicator_service`
- `signal_service`
- 对应的 kwargs

理由是这些属于“策略内核实现”，不是共享能力开关。

## Validation Rules

builder 在导入任何 provider 之前必须完成以下校验：

1. manifest 类型校验
   - `service_activation` 必须存在且为字典。
   - 每个值必须为布尔值。
2. 键集合校验
   - manifest 中不能有未知能力。
   - registry 中的已知能力不能缺失。
3. 依赖校验
   - 如果启用某能力，则其 `requires` 必须全部启用。
4. 互斥校验
   - 如果两个互斥能力同时启用，则启动失败。
5. 角色占用校验
   - 两个 provider 不能同时占用同一个单例角色。
6. provider 输出校验
   - provider 不能返回未声明角色。

错误信息必须带出：

- 能力 key
- 冲突或缺失的依赖 key
- 角色名
- 配置路径 `[service_activation]`

## Initial Dependency and Conflict Rules

首批规则沿用当前仓库已有语义：

- `option_selector` requires `option_chain`
- `portfolio_risk` requires `greeks_calculator`
- `advanced_order_scheduler` requires `smart_order_executor`
- `delta_hedging` requires `greeks_calculator`
- `vega_hedging` requires `greeks_calculator`

首批互斥规则如下：

- `delta_hedging` conflicts `vega_hedging`
- `advanced_order_scheduler` conflicts `delta_hedging`
- `advanced_order_scheduler` conflicts `vega_hedging`

这些规则迁移到 runtime registry 后，`src/main/scaffold/catalog.py` 不应再维护独立真相。

## Builder Algorithm

`StrategyRuntimeBuilder.build(entry, full_config)` 的推荐流程：

1. 构建固定内核对象。
2. 读取并校验 `service_activation` manifest。
3. 从 registry 取出激活能力集合。
4. 根据 `requires` 做拓扑排序。
5. 按顺序懒导入 provider。
6. 调用 provider `build(...)` 获取 contribution。
7. 合并 contribution，并检测角色冲突。
8. 生成 `StrategyRuntime`。
9. 将 `entry.runtime` 指向该对象。

只有在第 5 步之后，具体 provider 模块才会被导入。

## Expected File Impact

### 新增

- `src/strategy/runtime/__init__.py`
- `src/strategy/runtime/models.py`
- `src/strategy/runtime/registry.py`
- `src/strategy/runtime/builder.py`
- `src/strategy/runtime/providers/__init__.py`
- 首批 provider 模块

### 修改

- `src/main/config/config_loader.py`
- `src/strategy/strategy_entry.py`
- `src/strategy/application/lifecycle_workflow.py`
- `src/strategy/application/market_workflow.py`
- `src/strategy/application/state_workflow.py`
- `src/main/scaffold/catalog.py`
- 相关测试文件

## Migration Plan

### Phase 1: 建立 runtime 骨架

目标：

- 引入 runtime 目录、registry、builder、models。
- 在不改变现有行为的前提下，让 `LifecycleWorkflow` 先能构建 `entry.runtime`。

要求：

- 这一阶段 workflow 仍可暂时兼容旧属性，但新增测试必须覆盖 runtime 构建路径。

### Phase 2: 迁移低风险能力

优先迁移：

- `monitoring`
- `decision_observability`
- `future_selection`
- `option_chain`

目标：

- 将这些能力从 `entry.xxx` 属性迁移到 runtime 角色。
- `StateWorkflow` 与 universe 初始化逻辑开始消费 runtime。

### Phase 3: 迁移决策主链能力

依次迁移：

- `option_selector`
- `pricing_engine`
- `greeks_calculator`
- `position_sizing`
- `smart_order_executor`
- `advanced_order_scheduler`

目标：

- `MarketWorkflow` 的 open/close pipeline 全部改为消费 runtime 角色。
- 可选能力不再通过宿主属性暴露。

### Phase 4: 删除旧装配路径

目标：

- 删除 `StrategyEntry` 中针对可选能力的兼容属性。
- 删除 `LifecycleWorkflow` 中对可选能力具体类的直接导入和实例化。
- 删除 workflow 中分散的 `service_activation` 判断。

完成标志：

- `service_activation` 成为唯一可选能力装配入口。
- `StrategyEntry` 和 `LifecycleWorkflow` 不再静态依赖全部可选能力类。

## Testing Strategy

### Builder Tests

必须覆盖：

- 未知能力键
- 缺失能力键
- 非布尔值
- 依赖缺失
- 互斥冲突
- 单例角色冲突
- provider 返回未声明角色

### Provider Tests

每个 provider 至少覆盖：

- 启用时构建 contribution 成功
- 未启用时不被导入
- 读取并应用自己的配置
- 不污染其他角色

### Workflow Integration Tests

至少覆盖以下组合：

- `selection-only`
- `selection + pricing + risk`
- `monitoring off`
- `decision_observability off`

### Structural Regression Tests

需要增加结构性测试，确保：

- `StrategyEntry` 不再静态导入可选能力类
- `LifecycleWorkflow` 不再静态导入可选能力类
- 启动仅导入启用 provider

## Risks and Mitigations

### 风险 1: runtime 退化为 service locator

缓解：

- runtime 只暴露固定角色树，不暴露任意字符串查找接口。
- workflow 只能消费预定义角色。

### 风险 2: provider 之间出现隐藏耦合

缓解：

- 所有依赖和互斥必须显式声明在 registry。
- provider 不允许读取其他 provider 的内部对象。

### 风险 3: 一个角色被多个 provider 争用

缓解：

- builder 对单例角色做强校验，冲突时直接失败。

### 风险 4: 配置迁移时出现隐式默认值残留

缓解：

- 将 `service_activation` 升级为完整 manifest。
- 删除旧的隐式默认解析逻辑。

## Acceptance Criteria

当以下条件全部满足时，本设计视为完成：

1. `service_activation` 成为唯一可选能力装配入口。
2. 未启用能力在启动路径中不会被 import。
3. 未启用能力不会被实例化，也不会通过宿主对象暴露。
4. `MarketWorkflow`、`StateWorkflow`、`LifecycleWorkflow` 只消费 runtime 角色。
5. registry 成为依赖和互斥规则唯一真相。
6. 典型能力组合的回归测试通过。

## Summary

本设计将脚手架从“集中化装配所有能力，再局部禁用”转为“以 `service_activation` 为唯一清单的懒导入按需装配”。

这样可以在保留完整 template repo 的前提下，让运行时真正做到：

- 已启用能力才导入
- 已启用能力才初始化
- workflow 只看到稳定角色
- 应用层不再与全部领域服务实现绑死
