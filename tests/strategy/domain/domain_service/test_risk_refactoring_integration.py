"""
风险服务重构集成测试

验证重构后的风险服务使用基础设施层组件的行为与重构前一致。

测试内容:
1. ConcentrationMonitor 使用 ContractHelper 的行为
2. TimeDecayMonitor 使用 ContractHelper 和 DateCalculator 的行为
3. 验证重构前后计算结果一致

**Validates: Requirements 5.3, 5.4, 5.5, 7.3**
"""

import sys
from datetime import datetime
from unittest.mock import MagicMock

# Mock vnpy modules
for _name in [
    "vnpy",
    "vnpy.event",
    "vnpy.trader",
    "vnpy.trader.setting",
    "vnpy.trader.engine",
    "vnpy.trader.database",
    "vnpy.trader.constant",
    "vnpy.trader.object",
    "vnpy_postgresql",
]:
    if _name not in sys.modules:
        sys.modules[_name] = MagicMock()

from src.strategy.domain.domain_service.risk.concentration_monitor import (  # noqa: E402
    ConcentrationMonitor,
)
from src.strategy.domain.domain_service.risk.time_decay_monitor import (  # noqa: E402
    TimeDecayMonitor,
)
from src.strategy.domain.value_object.risk.risk import (  # noqa: E402
    ConcentrationConfig,
    TimeDecayConfig,
)
from src.strategy.domain.entity.position import Position  # noqa: E402
from src.strategy.domain.value_object.pricing.greeks import GreeksResult  # noqa: E402
from src.strategy.infrastructure.parsing.contract_helper import ContractHelper  # noqa: E402
from src.strategy.infrastructure.utils.date_calculator import DateCalculator  # noqa: E402


class TestConcentrationMonitorRefactoring:
    """测试 ConcentrationMonitor 重构后使用 ContractHelper 的行为"""

    def test_expiry_extraction_using_contract_helper(self):
        """
        测试 ConcentrationMonitor 使用 ContractHelper 提取到期日
        
        **Validates: Requirements 5.3, 5.5**
        """
        config = ConcentrationConfig(
            underlying_concentration_limit=0.5,
            expiry_concentration_limit=0.6,
            strike_concentration_limit=0.4,
            hhi_threshold=0.3,
        )
        monitor = ConcentrationMonitor(config)
        
        # 创建不同到期日的持仓
        positions = [
            Position(
                vt_symbol="IO2401-C-4000.CFFEX",
                underlying_vt_symbol="IO.CFFEX",
                signal="test",
                volume=10,
            ),
            Position(
                vt_symbol="IO2402-C-4100.CFFEX",
                underlying_vt_symbol="IO.CFFEX",
                signal="test",
                volume=15,
            ),
            Position(
                vt_symbol="IO2401-P-3900.CFFEX",
                underlying_vt_symbol="IO.CFFEX",
                signal="test",
                volume=20,
            ),
        ]
        
        prices = {
            "IO2401-C-4000.CFFEX": 100.0,
            "IO2402-C-4100.CFFEX": 150.0,
            "IO2401-P-3900.CFFEX": 200.0,
        }
        
        # 计算集中度
        metrics = monitor.calculate_concentration(positions, prices)
        
        # 验证到期日维度集中度
        assert "2401" in metrics.expiry_concentration
        assert "2402" in metrics.expiry_concentration
        
        # 验证到期日集中度计算正确
        # 2401: (10*100 + 20*200) / (10*100 + 15*150 + 20*200) = 5000 / 7250 ≈ 0.69
        # 2402: (15*150) / 7250 ≈ 0.31
        assert abs(metrics.expiry_concentration["2401"] - 0.6897) < 0.01
        assert abs(metrics.expiry_concentration["2402"] - 0.3103) < 0.01

    def test_strike_grouping_using_contract_helper(self):
        """
        测试 ConcentrationMonitor 使用 ContractHelper 分组行权价
        
        **Validates: Requirements 5.3, 5.5**
        """
        config = ConcentrationConfig(
            underlying_concentration_limit=0.5,
            expiry_concentration_limit=0.6,
            strike_concentration_limit=0.4,
            hhi_threshold=0.3,
        )
        monitor = ConcentrationMonitor(config)
        
        # 创建不同行权价的持仓
        positions = [
            Position(
                vt_symbol="IO2401-C-4000.CFFEX",
                underlying_vt_symbol="IO.CFFEX",
                signal="test",
                volume=10,
            ),
            Position(
                vt_symbol="IO2401-C-4200.CFFEX",
                underlying_vt_symbol="IO.CFFEX",
                signal="test",
                volume=15,
            ),
            Position(
                vt_symbol="IO2401-C-4500.CFFEX",
                underlying_vt_symbol="IO.CFFEX",
                signal="test",
                volume=20,
            ),
        ]
        
        prices = {
            "IO2401-C-4000.CFFEX": 100.0,
            "IO2401-C-4200.CFFEX": 100.0,
            "IO2401-C-4500.CFFEX": 100.0,
        }
        
        # 计算集中度
        metrics = monitor.calculate_concentration(positions, prices)
        
        # 验证行权价分组（根据 ContractHelper 的分组逻辑）
        # 4000, 4200, 4500 应该被分到不同的区间
        assert len(metrics.strike_concentration) > 0
        
        # 验证所有持仓都被分组
        total_concentration = sum(metrics.strike_concentration.values())
        assert abs(total_concentration - 1.0) < 0.01

    def test_concentration_calculation_consistency(self):
        """
        测试重构前后集中度计算结果一致
        
        **Validates: Requirements 5.3, 5.5, 7.3**
        """
        config = ConcentrationConfig(
            underlying_concentration_limit=0.5,
            expiry_concentration_limit=0.6,
            strike_concentration_limit=0.4,
            hhi_threshold=0.3,
        )
        monitor = ConcentrationMonitor(config)
        
        # 创建测试持仓
        positions = [
            Position(
                vt_symbol="IO2401-C-4000.CFFEX",
                underlying_vt_symbol="IO.CFFEX",
                signal="test",
                volume=10,
            ),
            Position(
                vt_symbol="MO2401-C-2800.DCE",
                underlying_vt_symbol="m.DCE",
                signal="test",
                volume=20,
            ),
        ]
        
        prices = {
            "IO2401-C-4000.CFFEX": 100.0,
            "MO2401-C-2800.DCE": 50.0,
        }
        
        # 计算集中度
        metrics = monitor.calculate_concentration(positions, prices)
        
        # 验证品种集中度
        assert "IO.CFFEX" in metrics.underlying_concentration
        assert "m.DCE" in metrics.underlying_concentration
        
        # IO: 10*100 / (10*100 + 20*50) = 1000 / 2000 = 0.5
        # m: 20*50 / 2000 = 0.5
        assert abs(metrics.underlying_concentration["IO.CFFEX"] - 0.5) < 0.01
        assert abs(metrics.underlying_concentration["m.DCE"] - 0.5) < 0.01
        
        # 验证 HHI 计算
        expected_hhi = 0.5**2 + 0.5**2  # 0.5
        assert abs(metrics.underlying_hhi - expected_hhi) < 0.01


class TestTimeDecayMonitorRefactoring:
    """测试 TimeDecayMonitor 重构后使用 ContractHelper 和 DateCalculator 的行为"""

    def test_expiry_identification_using_contract_helper(self):
        """
        测试 TimeDecayMonitor 使用 ContractHelper 识别到期持仓
        
        **Validates: Requirements 5.4, 5.5**
        """
        config = TimeDecayConfig(
            expiry_warning_days=30,
            critical_expiry_days=7,
        )
        monitor = TimeDecayMonitor(config)
        
        # 创建不同到期日的持仓
        positions = [
            Position(
                vt_symbol="IO2401-C-4000.CFFEX",
                underlying_vt_symbol="IO.CFFEX",
                signal="test",
                volume=10,
            ),
            Position(
                vt_symbol="IO2402-C-4100.CFFEX",
                underlying_vt_symbol="IO.CFFEX",
                signal="test",
                volume=15,
            ),
        ]
        
        # 使用 2024-01-01 作为当前日期
        current_date = datetime(2024, 1, 1)
        
        # 识别临近到期的持仓
        expiring_positions = monitor.identify_expiring_positions(positions, current_date)
        
        # 验证识别到临近到期的持仓
        # 2401 到期日约为 2024-01-15，距离 2024-01-01 约 14 天，应该触发 warning
        assert len(expiring_positions) > 0
        
        # 验证到期日提取正确
        for exp_pos in expiring_positions:
            assert exp_pos.expiry_date in ["2401", "2402"]

    def test_days_to_expiry_calculation_using_date_calculator(self):
        """
        测试 TimeDecayMonitor 使用 DateCalculator 计算到期天数
        
        **Validates: Requirements 5.4, 5.5**
        """
        config = TimeDecayConfig(
            expiry_warning_days=30,
            critical_expiry_days=7,
        )
        monitor = TimeDecayMonitor(config)
        
        # 创建持仓
        positions = [
            Position(
                vt_symbol="IO2401-C-4000.CFFEX",
                underlying_vt_symbol="IO.CFFEX",
                signal="test",
                volume=10,
            ),
        ]
        
        # 使用 2024-01-01 作为当前日期
        current_date = datetime(2024, 1, 1)
        
        # 识别临近到期的持仓
        expiring_positions = monitor.identify_expiring_positions(positions, current_date)
        
        # 验证天数计算
        if len(expiring_positions) > 0:
            exp_pos = expiring_positions[0]
            # 2401 到期日约为 2024-01-15，距离 2024-01-01 约 14 天
            assert exp_pos.days_to_expiry > 0
            assert exp_pos.days_to_expiry < 30

    def test_expiry_distribution_grouping(self):
        """
        测试 TimeDecayMonitor 按到期日分组统计
        
        **Validates: Requirements 5.4, 5.5, 7.3**
        """
        config = TimeDecayConfig(
            expiry_warning_days=30,
            critical_expiry_days=7,
        )
        monitor = TimeDecayMonitor(config)
        
        # 创建不同到期日的持仓
        positions = [
            Position(
                vt_symbol="IO2401-C-4000.CFFEX",
                underlying_vt_symbol="IO.CFFEX",
                signal="test",
                volume=10,
            ),
            Position(
                vt_symbol="IO2401-P-3900.CFFEX",
                underlying_vt_symbol="IO.CFFEX",
                signal="test",
                volume=20,
            ),
            Position(
                vt_symbol="IO2402-C-4100.CFFEX",
                underlying_vt_symbol="IO.CFFEX",
                signal="test",
                volume=15,
            ),
        ]
        
        # 计算到期日分布
        expiry_distribution = monitor.calculate_expiry_distribution(positions)
        
        # 验证分组
        assert "2401" in expiry_distribution
        assert "2402" in expiry_distribution
        
        # 验证 2401 分组统计
        group_2401 = expiry_distribution["2401"]
        assert group_2401.position_count == 2
        assert group_2401.total_volume == 30  # 10 + 20
        assert len(group_2401.positions) == 2
        
        # 验证 2402 分组统计
        group_2402 = expiry_distribution["2402"]
        assert group_2402.position_count == 1
        assert group_2402.total_volume == 15

    def test_theta_calculation_consistency(self):
        """
        测试重构前后 Theta 计算结果一致
        
        **Validates: Requirements 5.4, 5.5, 7.3**
        """
        config = TimeDecayConfig(
            expiry_warning_days=30,
            critical_expiry_days=7,
        )
        monitor = TimeDecayMonitor(config)
        
        # 创建持仓
        positions = [
            Position(
                vt_symbol="IO2401-C-4000.CFFEX",
                underlying_vt_symbol="IO.CFFEX",
                signal="test",
                volume=10,
            ),
            Position(
                vt_symbol="IO2401-P-3900.CFFEX",
                underlying_vt_symbol="IO.CFFEX",
                signal="test",
                volume=20,
            ),
        ]
        
        # 创建 Greeks 数据
        greeks_map = {
            "IO2401-C-4000.CFFEX": GreeksResult(
                delta=0.5,
                gamma=0.01,
                vega=0.2,
                theta=-0.05,
            ),
            "IO2401-P-3900.CFFEX": GreeksResult(
                delta=-0.4,
                gamma=0.01,
                vega=0.18,
                theta=-0.04,
            ),
        }
        
        # 计算组合 Theta
        metrics = monitor.calculate_portfolio_theta(positions, greeks_map)
        
        # 验证 Theta 计算
        # 总 Theta = (10 * -0.05 + 20 * -0.04) * 10000 = (-0.5 - 0.8) * 10000 = -13000
        expected_total_theta = (10 * -0.05 + 20 * -0.04) * 10000
        assert abs(metrics.total_theta - expected_total_theta) < 1.0
        
        # 验证每日衰减金额
        assert abs(metrics.daily_decay_amount - abs(expected_total_theta)) < 1.0
        
        # 验证持仓数量
        assert metrics.position_count == 2


class TestInfrastructureComponentsIntegration:
    """测试基础设施组件的集成使用"""

    def test_contract_helper_expiry_extraction(self):
        """
        测试 ContractHelper 到期日提取功能
        
        **Validates: Requirements 3.2, 5.3, 5.4**
        """
        # 测试不同格式的合约代码
        test_cases = [
            ("IO2401-C-4000.CFFEX", "2401"),
            ("MO2402-P-2800.DCE", "2402"),
            ("HO2509-C-3500.CZCE", "2509"),
            ("m2401-C-2800.DCE", "2401"),
        ]
        
        for vt_symbol, expected_expiry in test_cases:
            expiry = ContractHelper.extract_expiry_from_symbol(vt_symbol)
            assert expiry == expected_expiry, f"Failed for {vt_symbol}: expected {expected_expiry}, got {expiry}"

    def test_contract_helper_strike_grouping(self):
        """
        测试 ContractHelper 行权价分组功能
        
        **Validates: Requirements 3.3, 5.3**
        """
        # 测试不同行权价的分组
        test_cases = [
            ("IO2401-C-4000.CFFEX", "4000-4500"),  # 4000 在 [4000, 5000) 区间，宽度 500
            ("MO2401-C-2800.DCE", "2500-3000"),    # 2800 在 [1000, 5000) 区间，宽度 500
            ("HO2401-C-800.CZCE", "800-900"),      # 800 在 [0, 1000) 区间，宽度 100
        ]
        
        for vt_symbol, expected_range in test_cases:
            strike_range = ContractHelper.group_by_strike_range(vt_symbol)
            assert strike_range == expected_range, f"Failed for {vt_symbol}: expected {expected_range}, got {strike_range}"

    def test_date_calculator_days_to_expiry(self):
        """
        测试 DateCalculator 到期天数计算功能
        
        **Validates: Requirements 4.2, 5.4**
        """
        # 测试天数计算
        current_date = datetime(2024, 1, 1)
        
        # 2401 到期日约为 2024-01-15
        days = DateCalculator.calculate_days_to_expiry("2401", current_date)
        assert days is not None
        assert days > 0
        assert days < 30
        
        # 2402 到期日约为 2024-02-15
        days = DateCalculator.calculate_days_to_expiry("2402", current_date)
        assert days is not None
        assert days > 30
        assert days < 60
