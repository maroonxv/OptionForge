# 实施计划：领域服务基础设施职责分离

## 概述

本实施计划将领域服务层中的基础设施职责（序列化、合约解析、日期计算）提取到基础设施层，保持领域层的纯净性。重构采用渐进式方法，先创建基础设施组件并测试，再重构领域服务，最后运行回归测试确保功能不变。

## 任务列表

- [x] 1. 创建 SmartOrderExecutor 序列化器
  - [x] 1.1 实现 SmartOrderExecutorSerializer 类
    - 创建 `src/strategy/infrastructure/persistence/smart_order_executor_serializer.py`
    - 实现 `to_dict` 静态方法，序列化配置和订单状态
    - 实现 `from_dict` 静态方法，从字典恢复实例
    - 处理 ManagedOrder 对象的序列化和反序列化
    - 处理缺失字段，使用默认值
    - _需求: 1.1, 1.2, 1.3, 1.4_

  - [x] 1.2 编写 SmartOrderExecutorSerializer 单元测试
    - 创建 `tests/strategy/infrastructure/persistence/test_smart_order_executor_serializer.py`
    - 测试基本序列化和反序列化
    - 测试包含订单的序列化
    - 测试缺失字段的默认值处理
    - 测试错误处理（None 输入、无效数据）
    - _需求: 7.1, 7.5_

  - [x] 1.3 编写 SmartOrderExecutorSerializer 属性测试
    - 创建 `tests/strategy/infrastructure/persistence/test_smart_order_executor_serializer_properties.py`
    - **属性 1: SmartOrderExecutor 序列化往返保持等价性**
    - **验证需求: 1.5**
    - 使用 Hypothesis 生成随机 SmartOrderExecutor 实例
    - 验证序列化后反序列化的对象与原对象等价
    - 配置至少 100 次迭代
    - _需求: 1.5_

- [x] 2. 创建 AdvancedOrderScheduler 序列化器
  - [x] 2.1 实现 AdvancedOrderSchedulerSerializer 类
    - 创建 `src/strategy/infrastructure/persistence/advanced_order_scheduler_serializer.py`
    - 实现 `to_dict` 静态方法，序列化配置和订单状态
    - 实现 `from_dict` 静态方法，从字典恢复实例
    - 处理 AdvancedOrder、ChildOrder、SliceEntry 的序列化
    - 正确处理 datetime 对象的序列化和反序列化
    - _需求: 2.1, 2.2, 2.3, 2.4_

  - [x] 2.2 编写 AdvancedOrderSchedulerSerializer 单元测试
    - 创建 `tests/strategy/infrastructure/persistence/test_advanced_order_scheduler_serializer.py`
    - 测试基本序列化和反序列化
    - 测试包含复杂订单结构的序列化
    - 测试 datetime 对象的处理
    - 测试错误处理
    - _需求: 7.1, 7.5_

  - [x] 2.3 编写 AdvancedOrderSchedulerSerializer 属性测试
    - 创建 `tests/strategy/infrastructure/persistence/test_advanced_order_scheduler_serializer_properties.py`
    - **属性 2: AdvancedOrderScheduler 序列化往返保持等价性**
    - **验证需求: 2.5**
    - 使用 Hypothesis 生成随机 AdvancedOrderScheduler 实例
    - 验证序列化后反序列化的对象与原对象等价
    - 配置至少 100 次迭代
    - _需求: 2.5_

- [-] 3. 扩展 ContractHelper 合约解析功能
  - [x] 3.1 实现 ContractHelper 新增方法
    - 修改 `src/strategy/infrastructure/parsing/contract_helper.py`
    - 实现 `extract_expiry_from_symbol` 静态方法
    - 使用正则表达式提取 YYMM 格式的到期日
    - 实现 `group_by_strike_range` 静态方法
    - 根据行权价大小动态确定区间宽度（<1000: 100, 1000-5000: 500, >=5000: 1000）
    - 处理异常情况，返回 "unknown"
    - _需求: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 3.2 编写 ContractHelper 扩展功能单元测试
    - 创建 `tests/strategy/infrastructure/parsing/test_contract_helper_extension.py`
    - 测试各种合约格式的到期日提取（IO、MO、HO、m、c 等）
    - 测试不同行权价的区间分组
    - 测试边界条件（行权价 1000、5000）
    - 测试异常情况（无效格式、缺失信息）
    - _需求: 7.1, 7.5_

  - [x] 3.3 编写 ContractHelper 属性测试
    - 创建 `tests/strategy/infrastructure/parsing/test_contract_helper_properties.py`
    - **属性 3: 合约代码到期日提取正确性**
    - **验证需求: 3.2, 4.3**
    - **属性 4: 合约代码行权价分组正确性**
    - **验证需求: 3.3**
    - **属性 5: 合约解析幂等性**
    - **验证需求: 3.6**
    - 使用 Hypothesis 生成随机合约代码
    - 验证提取的到期日格式正确
    - 验证行权价落在返回的区间内
    - 验证多次调用返回相同结果
    - 配置至少 100 次迭代
    - _需求: 3.2, 3.3, 3.6_

- [ ] 4. 创建 DateCalculator 日期计算工具
  - [x] 4.1 实现 DateCalculator 类
    - 创建 `src/strategy/infrastructure/utils/date_calculator.py`
    - 实现 `parse_expiry_date` 静态方法，解析 YYMM 格式到期日
    - 假设到期日为该月 15 日（简化实现）
    - 实现 `calculate_days_to_expiry` 静态方法，计算距离到期天数
    - 处理异常情况，返回 None
    - _需求: 4.1, 4.2, 4.3, 4.4_

  - [x] 4.2 编写 DateCalculator 单元测试
    - 创建 `tests/strategy/infrastructure/utils/test_date_calculator.py`
    - 测试有效 YYMM 格式的解析
    - 测试天数计算的准确性
    - 测试边界条件（当月、跨年）
    - 测试异常情况（无效格式、无效月份）
    - _需求: 7.1, 7.5_

  - [x] 4.3 编写 DateCalculator 属性测试
    - 创建 `tests/strategy/infrastructure/utils/test_date_calculator_properties.py`
    - **属性 6: 日期计算正确性**
    - **验证需求: 4.2, 4.5**
    - 使用 Hypothesis 生成随机到期日字符串和当前日期
    - 验证计算的天数与手动计算一致
    - 配置至少 100 次迭代
    - _需求: 4.2, 4.5_

- [x] 5. 检查点 - 确保基础设施组件测试通过
  - 运行所有新增的单元测试和属性测试
  - 确保所有测试通过，如有问题请询问用户

- [ ] 6. 扩展 DomainServiceConfigLoader 配置加载功能
  - [x] 6.1 实现配置加载器新增方法
    - 修改 `src/main/config/domain_service_config_loader.py`
    - 实现 `create_smart_order_executor` 静态方法
    - 从配置字典提取参数，创建 OrderExecutionConfig
    - 处理缺失配置项，使用默认值
    - 实现 `create_advanced_order_scheduler` 静态方法
    - 从配置字典提取参数，创建 AdvancedSchedulerConfig
    - _需求: 6.1, 6.2, 6.3, 6.4_

  - [x] 6.2 编写 DomainServiceConfigLoader 单元测试
    - 创建 `tests/main/config/test_domain_service_config_loader.py`
    - 测试完整配置的加载
    - 测试部分配置的加载（使用默认值）
    - 测试空配置的加载（全部使用默认值）
    - 测试无效配置的处理
    - _需求: 7.1, 7.5_

  - [x] 6.3 编写 DomainServiceConfigLoader 属性测试
    - 创建 `tests/main/config/test_domain_service_config_loader_properties.py`
    - **属性 7: 配置加载正确性**
    - **验证需求: 6.2, 6.3, 6.4, 6.5**
    - 使用 Hypothesis 生成随机配置字典（可能缺失某些字段）
    - 验证加载的实例配置参数正确
    - 验证缺失字段使用默认值
    - 配置至少 100 次迭代
    - _需求: 6.2, 6.3, 6.4, 6.5_

- [ ] 7. 重构 SmartOrderExecutor 领域服务
  - [x] 7.1 移除 SmartOrderExecutor 的序列化方法
    - 修改 `src/strategy/domain/domain_service/execution/smart_order_executor.py`
    - 移除 `to_dict` 方法
    - 移除 `from_dict` 类方法
    - 移除 `from_yaml_config` 类方法
    - 更新类文档字符串，说明职责变化
    - _需求: 1.4, 5.1, 8.4_

- [ ] 8. 重构 AdvancedOrderScheduler 领域服务
  - [x] 8.1 移除 AdvancedOrderScheduler 的序列化方法
    - 修改 `src/strategy/domain/domain_service/execution/advanced_order_scheduler.py`
    - 移除 `to_dict` 方法
    - 移除 `from_dict` 类方法
    - 移除 `from_yaml_config` 类方法
    - 更新类文档字符串，说明职责变化
    - _需求: 2.4, 5.2, 8.4_

- [ ] 9. 重构 ConcentrationMonitor 领域服务
  - [x] 9.1 使用 ContractHelper 替代内部解析方法
    - 修改 `src/strategy/domain/domain_service/risk/concentration_monitor.py`
    - 导入 ContractHelper
    - 将 `_extract_expiry_from_symbol` 调用替换为 `ContractHelper.extract_expiry_from_symbol`
    - 将 `_group_by_strike_range` 调用替换为 `ContractHelper.group_by_strike_range`
    - 移除 `_extract_expiry_from_symbol` 方法
    - 移除 `_group_by_strike_range` 方法
    - 更新类文档字符串
    - _需求: 3.4, 5.3, 8.4_

- [ ] 10. 重构 TimeDecayMonitor 领域服务
  - [x] 10.1 使用 ContractHelper 和 DateCalculator 替代内部方法
    - 修改 `src/strategy/domain/domain_service/risk/time_decay_monitor.py`
    - 导入 ContractHelper 和 DateCalculator
    - 将 `_extract_expiry_from_symbol` 调用替换为 `ContractHelper.extract_expiry_from_symbol`
    - 将 `_calculate_days_to_expiry` 调用替换为 `DateCalculator.calculate_days_to_expiry`
    - 移除 `_extract_expiry_from_symbol` 方法
    - 移除 `_calculate_days_to_expiry` 方法
    - 更新类文档字符串
    - _需求: 3.5, 4.4, 5.4, 8.4_

- [x] 11. 检查点 - 确保领域服务重构完成
  - 检查所有领域服务的修改是否正确
  - 确保没有遗留的基础设施职责
  - 如有问题请询问用户

- [-] 12. 运行回归测试
  - [x] 12.1 运行执行服务相关测试
    - 运行 `tests/strategy/domain/domain_service/test_execution_integration.py`
    - 运行 `tests/strategy/domain/domain_service/test_execution_coordinator_properties.py`
    - 运行 `tests/strategy/domain/domain_service/test_execution_serialization_properties.py`
    - 运行 `tests/strategy/domain/domain_service/test_execution_config_properties.py`
    - 确保所有测试通过
    - _需求: 5.5, 7.1, 7.2_

  - [x] 12.2 运行风险服务相关测试
    - 运行 `tests/strategy/domain/domain_service/risk/test_risk_integration.py`
    - 运行 `tests/strategy/domain/domain_service/risk/test_concentration_properties.py`
    - 运行 `tests/strategy/domain/domain_service/risk/test_concentration_monitor.py`
    - 运行 `tests/strategy/domain/domain_service/risk/test_time_decay_properties.py`
    - 运行 `tests/strategy/domain/domain_service/risk/test_time_decay_monitor.py`
    - 确保所有测试通过
    - _需求: 5.5, 7.1, 7.2_

  - [-] 12.3 编写执行服务重构集成测试
    - 创建 `tests/strategy/domain/domain_service/test_execution_refactoring_integration.py`
    - 测试使用序列化器保存和恢复 SmartOrderExecutor 状态
    - 测试使用序列化器保存和恢复 AdvancedOrderScheduler 状态
    - 测试使用配置加载器从 YAML 创建执行服务实例
    - 验证重构前后行为一致
    - _需求: 5.1, 5.2, 5.5, 7.3_

  - [ ] 12.4 编写风险服务重构集成测试
    - 创建 `tests/strategy/domain/domain_service/test_risk_refactoring_integration.py`
    - 测试 ConcentrationMonitor 使用 ContractHelper 的行为
    - 测试 TimeDecayMonitor 使用 ContractHelper 和 DateCalculator 的行为
    - 验证重构前后计算结果一致
    - _需求: 5.3, 5.4, 5.5, 7.3_

- [ ] 13. 检查点 - 确保所有测试通过
  - 运行完整的测试套件
  - 检查测试覆盖率是否满足要求
  - 如有测试失败，修复问题后重新运行
  - 如有问题请询问用户

- [ ] 14. 更新文档
  - [ ] 14.1 更新基础设施组件文档
    - 检查 SmartOrderExecutorSerializer 的文档字符串
    - 检查 AdvancedOrderSchedulerSerializer 的文档字符串
    - 检查 ContractHelper 新增方法的文档字符串
    - 检查 DateCalculator 的文档字符串
    - 添加使用示例和参数说明
    - _需求: 8.1, 8.2, 8.3_

  - [ ] 14.2 更新领域服务文档
    - 更新 SmartOrderExecutor 的文档字符串
    - 更新 AdvancedOrderScheduler 的文档字符串
    - 更新 ConcentrationMonitor 的文档字符串
    - 更新 TimeDecayMonitor 的文档字符串
    - 说明职责变化和迁移指南
    - _需求: 8.4_

  - [ ] 14.3 添加代码注释
    - 在关键设计决策处添加注释
    - 解释为什么使用基础设施组件
    - 说明简化实现的理由（如日期计算）
    - _需求: 8.5_

- [ ] 15. 最终检查点
  - 确保所有任务完成
  - 确保所有测试通过
  - 确保文档更新完整
  - 询问用户是否有其他需求

## 注意事项

- 标记 `*` 的任务为可选任务，可以跳过以加快 MVP 交付
- 每个任务都引用了具体的需求编号，便于追溯
- 检查点任务确保渐进式验证
- 属性测试验证通用正确性属性
- 单元测试验证具体示例和边界情况
- 集成测试验证重构前后行为一致性
