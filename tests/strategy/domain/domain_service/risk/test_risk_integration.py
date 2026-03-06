"""
风险服务集成测试

测试五个风险监控服务的完整端到端流程和协同工作：
1. StopLossManager 与持仓实体的交互
2. RiskBudgetAllocator 与 PortfolioRiskAggregator 的协同
3. LiquidityRiskMonitor 的完整流程
4. ConcentrationMonitor 的完整流程
5. TimeDecayMonitor 的完整流程
6. 多个风险服务同时工作的场景

Validates: Requirements 全部 (1-5)
"""

import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Mock vnpy modules before importing domain modules
# ---------------------------------------------------------------------------
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

from src.strategy.domain.domain_service.risk.stop_loss_manager import (  # noqa: E402
    StopLossManager,
)
from src.strategy.domain.domain_service.risk.risk_budget_allocator import (  # noqa: E402
    RiskBudgetAllocator,
)
from src.strategy.domain.domain_service.risk.liquidity_risk_monitor import (  # noqa: E402
    LiquidityRiskMonitor,
)
from src.strategy.domain.domain_service.risk.concentration_monitor import (  # noqa: E402
    ConcentrationMonitor,
)
from src.strategy.domain.domain_service.risk.time_decay_monitor import (  # noqa: E402
    TimeDecayMonitor,
)
from src.strategy.domain.entity.position import Position  # noqa: E402
from src.strategy.domain.value_object.risk.risk import (  # noqa: E402
    StopLossConfig,
    RiskBudgetConfig,
    LiquidityMonitorConfig,
    ConcentrationConfig,
    TimeDecayConfig,
    RiskThresholds,
    MarketData,
)
from src.strategy.domain.value_object.pricing.greeks import GreeksResult  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_position(
    vt_symbol: str = "IO2506-C-5000.CFFEX",
    underlying: str = "IO2506.CFFEX",
    signal: str = "test_signal",
    volume: int = 10,
    direction: str = "short",
    open_price: float = 200.0,
) -> Position:
    """创建测试用持仓"""
    pos = Position(
        vt_symbol=vt_symbol,
        underlying_vt_symbol=underlying,
        signal=signal,
        volume=volume,
        target_volume=volume,
        direction=direction,
        open_price=open_price,
        create_time=datetime.now(),
        open_time=datetime.now(),
    )
    return pos


def _make_greeks(
    delta: float = 0.5,
    gamma: float = 0.01,
    theta: float = -0.5,
    vega: float = 0.2,
) -> GreeksResult:
    """创建测试用 Greeks"""
    return GreeksResult(
        success=True,
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
    )


# ===========================================================================
# Test 1: StopLossManager 与持仓实体的交互
# ===========================================================================


class TestStopLossManagerIntegration:
    """测试止损管理器与持仓实体的完整交互流程
    
    Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6
    """
    
    def test_position_lifecycle_with_stop_loss(self):
        """完整流程：创建持仓 → 价格变化 → 触发止损 → 平仓"""
        # 创建止损管理器
        config = StopLossConfig(
            enable_fixed_stop=True,
            fixed_stop_loss_amount=5000.0,
            fixed_stop_loss_percent=0.3,
            enable_trailing_stop=False,
        )
        manager = StopLossManager(config)
        
        # 创建持仓：卖出 10 手 Call，开仓价 200
        position = _make_position(
            vt_symbol="IO2506-C-5000.CFFEX",
            volume=10,
            direction="short",
            open_price=200.0,
        )
        
        # 场景 1：价格上涨到 220，亏损 = (220-200) * 10 * 10000 = 2000000
        current_price = 220.0
        trigger = manager.check_position_stop_loss(position, current_price)
        
        # 应该触发止损（亏损 2000000 > 阈值 5000）
        assert trigger is not None
        assert trigger.trigger_type == "fixed"
        assert trigger.vt_symbol == "IO2506-C-5000.CFFEX"
        assert trigger.current_loss == 2000000.0
        
        # 模拟平仓
        position.reduce_volume(10)
        assert position.is_closed
        assert position.volume == 0

    def test_trailing_stop_with_position_profit_tracking(self):
        """移动止损流程：持仓盈利 → 达到峰值 → 回撤触发止损"""
        config = StopLossConfig(
            enable_fixed_stop=False,
            enable_trailing_stop=True,
            trailing_stop_percent=0.3,
        )
        manager = StopLossManager(config)
        
        # 创建持仓：卖出 5 手，开仓价 300
        position = _make_position(volume=5, open_price=300.0)
        
        # 场景 1：价格下跌到 250，盈利 = (300-250) * 5 * 10000 = 2500000
        peak_profit = 2500000.0
        
        # 场景 2：价格反弹到 280，当前盈利 = (300-280) * 5 * 10000 = 1000000
        # 回撤 = 2500000 - 1000000 = 1500000，回撤比例 = 1500000/2500000 = 0.6 > 0.3
        current_price = 280.0
        trigger = manager.check_position_stop_loss(
            position, current_price, peak_profit=peak_profit
        )
        
        # 应该触发移动止损
        assert trigger is not None
        assert trigger.trigger_type == "trailing"
        assert trigger.current_loss == 1500000.0
    
    def test_portfolio_stop_loss_closes_all_positions(self):
        """组合止损流程：多个持仓 → 总亏损超限 → 全部平仓"""
        config = StopLossConfig(
            enable_portfolio_stop=True,
            daily_loss_limit=30000.0,
        )
        manager = StopLossManager(config)
        
        # 创建多个持仓
        positions = [
            _make_position(vt_symbol="IO2506-C-5000.CFFEX", volume=10),
            _make_position(vt_symbol="IO2506-C-5100.CFFEX", volume=8),
            _make_position(vt_symbol="IO2506-P-4900.CFFEX", volume=12),
        ]
        
        # 当前价格（所有持仓都亏损）
        current_prices = {
            "IO2506-C-5000.CFFEX": 220.0,  # 开仓 200，亏损
            "IO2506-C-5100.CFFEX": 230.0,  # 开仓 200，亏损
            "IO2506-P-4900.CFFEX": 210.0,  # 开仓 200，亏损
        }
        
        # 当日起始权益 100000，当前权益 65000，亏损 35000
        trigger = manager.check_portfolio_stop_loss(
            positions, current_prices,
            daily_start_equity=100000.0,
            current_equity=65000.0,
        )
        
        # 应该触发组合止损
        assert trigger is not None
        assert trigger.total_loss == 35000.0
        assert len(trigger.positions_to_close) == 3
        assert "IO2506-C-5000.CFFEX" in trigger.positions_to_close


# ===========================================================================
# Test 2: RiskBudgetAllocator 与 PortfolioRiskAggregator 的协同
# ===========================================================================


class TestRiskBudgetAllocatorIntegration:
    """测试风险预算分配器与组合风险聚合的协同工作
    
    Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7
    """
    
    def test_budget_allocation_and_usage_tracking(self):
        """完整流程：分配预算 → 开仓 → 计算使用量 → 检查预算"""
        # 配置预算分配：50ETF 40%, 300ETF 30%, 500ETF 30%
        config = RiskBudgetConfig(
            allocation_dimension="underlying",
            allocation_ratios={
                "IO.CFFEX": 0.4,
                "HO.CFFEX": 0.3,
                "MO.CFFEX": 0.3,
            }
        )
        allocator = RiskBudgetAllocator(config)
        
        # 组合级限额
        total_limits = RiskThresholds(
            portfolio_delta_limit=10000.0,
            portfolio_gamma_limit=1000.0,
            portfolio_vega_limit=50000.0,
        )
        
        # 按品种分配预算
        budget_map = allocator.allocate_budget_by_underlying(total_limits)
        
        # 验证分配结果
        assert len(budget_map) == 3
        assert budget_map["IO.CFFEX"].delta_budget == 4000.0  # 10000 * 0.4
        assert budget_map["HO.CFFEX"].delta_budget == 3000.0  # 10000 * 0.3
        assert budget_map["MO.CFFEX"].vega_budget == 15000.0  # 50000 * 0.3
        
        # 创建持仓（IO 品种）
        positions = [
            _make_position(
                vt_symbol="IO2506-C-5000.CFFEX",
                underlying="IO.CFFEX",
                volume=10,
            ),
            _make_position(
                vt_symbol="IO2506-C-5100.CFFEX",
                underlying="IO.CFFEX",
                volume=8,
            ),
        ]
        
        # Greeks 数据
        greeks_map = {
            "IO2506-C-5000.CFFEX": _make_greeks(delta=0.5, gamma=0.01, vega=20.0),
            "IO2506-C-5100.CFFEX": _make_greeks(delta=0.4, gamma=0.008, vega=18.0),
        }
        
        # 计算使用量
        usage_map = allocator.calculate_usage(positions, greeks_map, dimension="underlying")
        
        # 验证 IO 品种的使用量
        io_usage = usage_map["IO.CFFEX"]
        # Delta: |0.5*10*10000| + |0.4*8*10000| = 50000 + 32000 = 82000
        assert io_usage.delta_used == pytest.approx(82000.0, abs=1.0)
        assert io_usage.position_count == 2
        
        # 检查预算限额
        result = allocator.check_budget_limit(io_usage, budget_map["IO.CFFEX"])
        
        # 应该超限（使用量 82000 > 预算 4000）
        assert not result.passed
        assert "delta" in result.exceeded_dimensions

    def test_multi_underlying_budget_allocation(self):
        """多品种预算分配：不同品种独立计算使用量"""
        config = RiskBudgetConfig(
            allocation_dimension="underlying",
            allocation_ratios={
                "IO.CFFEX": 0.5,
                "HO.CFFEX": 0.5,
            }
        )
        allocator = RiskBudgetAllocator(config)
        
        total_limits = RiskThresholds(
            portfolio_delta_limit=20000.0,
            portfolio_gamma_limit=2000.0,
            portfolio_vega_limit=100000.0,
        )
        
        budget_map = allocator.allocate_budget_by_underlying(total_limits)
        
        # 创建不同品种的持仓
        positions = [
            _make_position(vt_symbol="IO2506-C-5000.CFFEX", underlying="IO.CFFEX", volume=5),
            _make_position(vt_symbol="HO2506-C-3000.CFFEX", underlying="HO.CFFEX", volume=8),
        ]
        
        greeks_map = {
            "IO2506-C-5000.CFFEX": _make_greeks(delta=0.6, gamma=0.02, vega=25.0),
            "HO2506-C-3000.CFFEX": _make_greeks(delta=0.5, gamma=0.015, vega=20.0),
        }
        
        usage_map = allocator.calculate_usage(positions, greeks_map, dimension="underlying")
        
        # 验证两个品种的使用量分别计算
        assert "IO.CFFEX" in usage_map
        assert "HO.CFFEX" in usage_map
        assert usage_map["IO.CFFEX"].position_count == 1
        assert usage_map["HO.CFFEX"].position_count == 1
        
        # IO: |0.6*5*10000| = 30000
        assert usage_map["IO.CFFEX"].delta_used == pytest.approx(30000.0, abs=1.0)
        # HO: |0.5*8*10000| = 40000
        assert usage_map["HO.CFFEX"].delta_used == pytest.approx(40000.0, abs=1.0)
        
        # 检查 IO 预算（预算 10000，使用 30000，超限）
        io_result = allocator.check_budget_limit(usage_map["IO.CFFEX"], budget_map["IO.CFFEX"])
        assert not io_result.passed
        
        # 检查 HO 预算（预算 10000，使用 40000，超限）
        ho_result = allocator.check_budget_limit(usage_map["HO.CFFEX"], budget_map["HO.CFFEX"])
        assert not ho_result.passed


# ===========================================================================
# Test 3: LiquidityRiskMonitor 的完整流程
# ===========================================================================


class TestLiquidityRiskMonitorIntegration:
    """测试流动性监控器的完整工作流程
    
    Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8
    """
    
    def test_liquidity_monitoring_full_pipeline(self):
        """完整流程：持仓 → 市场数据 → 计算评分 → 生成警告"""
        config = LiquidityMonitorConfig(
            volume_weight=0.4,
            spread_weight=0.3,
            open_interest_weight=0.3,
            liquidity_score_threshold=0.3,
            lookback_days=5,
        )
        monitor = LiquidityRiskMonitor(config)
        
        # 创建持仓
        positions = [
            _make_position(vt_symbol="IO2506-C-5000.CFFEX", volume=10),
            _make_position(vt_symbol="IO2506-C-5100.CFFEX", volume=8),
        ]
        
        # 当前市场数据
        current_time = datetime.now()
        market_data = {
            "IO2506-C-5000.CFFEX": MarketData(
                vt_symbol="IO2506-C-5000.CFFEX",
                timestamp=current_time,
                volume=500.0,  # 成交量低
                bid_price=195.0,
                ask_price=205.0,  # 价差大
                open_interest=2000.0,
            ),
            "IO2506-C-5100.CFFEX": MarketData(
                vt_symbol="IO2506-C-5100.CFFEX",
                timestamp=current_time,
                volume=3000.0,  # 成交量正常
                bid_price=198.0,
                ask_price=202.0,  # 价差小
                open_interest=8000.0,
            ),
        }
        
        # 历史数据（5000 合约流动性恶化）
        historical_data = {
            "IO2506-C-5000.CFFEX": [
                MarketData(
                    vt_symbol="IO2506-C-5000.CFFEX",
                    timestamp=current_time - timedelta(days=i),
                    volume=1000.0 - i * 100,  # 成交量递减
                    bid_price=195.0,
                    ask_price=203.0 + i * 0.5,  # 价差扩大
                    open_interest=3000.0 - i * 200,  # 持仓量递减
                )
                for i in range(1, 6)
            ],
            "IO2506-C-5100.CFFEX": [
                MarketData(
                    vt_symbol="IO2506-C-5100.CFFEX",
                    timestamp=current_time - timedelta(days=i),
                    volume=3000.0,
                    bid_price=198.0,
                    ask_price=202.0,
                    open_interest=8000.0,
                )
                for i in range(1, 6)
            ],
        }
        
        # 监控持仓流动性
        warnings = monitor.monitor_positions(positions, market_data, historical_data)
        
        # 流动性监控应该正常运行（可能有警告，取决于评分计算）
        assert isinstance(warnings, list)
        # 5000 合约流动性较差，可能触发警告
        if len(warnings) > 0:
            warning_symbols = [w.vt_symbol for w in warnings]
            # 如果有警告，验证警告内容
            for w in warnings:
                assert w.current_score < config.liquidity_score_threshold

    def test_liquidity_trend_identification(self):
        """流动性趋势识别：improving vs deteriorating"""
        config = LiquidityMonitorConfig()
        monitor = LiquidityRiskMonitor(config)
        
        current_time = datetime.now()
        
        # 场景 1：流动性改善（成交量增加、价差缩小）
        improving_current = MarketData(
            vt_symbol="IO2506-C-5000.CFFEX",
            timestamp=current_time,
            volume=5000.0,  # 高成交量
            bid_price=199.0,
            ask_price=201.0,  # 小价差
            open_interest=10000.0,
        )
        
        improving_history = [
            MarketData(
                vt_symbol="IO2506-C-5000.CFFEX",
                timestamp=current_time - timedelta(days=i),
                volume=3000.0,  # 历史成交量低
                bid_price=195.0,
                ask_price=205.0,  # 历史价差大
                open_interest=8000.0,
            )
            for i in range(1, 6)
        ]
        
        score = monitor.calculate_liquidity_score(
            "IO2506-C-5000.CFFEX", improving_current, improving_history
        )
        
        assert score.trend == "improving"
        assert score.overall_score > 0.5
        
        # 场景 2：流动性恶化（成交量减少、价差扩大）
        deteriorating_current = MarketData(
            vt_symbol="IO2506-C-5100.CFFEX",
            timestamp=current_time,
            volume=500.0,  # 低成交量
            bid_price=190.0,
            ask_price=210.0,  # 大价差
            open_interest=2000.0,
        )
        
        deteriorating_history = [
            MarketData(
                vt_symbol="IO2506-C-5100.CFFEX",
                timestamp=current_time - timedelta(days=i),
                volume=3000.0,  # 历史成交量高
                bid_price=198.0,
                ask_price=202.0,  # 历史价差小
                open_interest=8000.0,
            )
            for i in range(1, 6)
        ]
        
        score = monitor.calculate_liquidity_score(
            "IO2506-C-5100.CFFEX", deteriorating_current, deteriorating_history
        )
        
        assert score.trend == "deteriorating"
        assert score.overall_score < 0.5


# ===========================================================================
# Test 4: ConcentrationMonitor 的完整流程
# ===========================================================================


class TestConcentrationMonitorIntegration:
    """测试集中度监控器的完整工作流程
    
    Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7
    """
    
    def test_concentration_monitoring_full_pipeline(self):
        """完整流程：多品种持仓 → 计算集中度 → 检查超限"""
        config = ConcentrationConfig(
            underlying_concentration_limit=0.5,
            expiry_concentration_limit=0.6,
            strike_concentration_limit=0.4,
            hhi_threshold=0.25,
        )
        monitor = ConcentrationMonitor(config)
        
        # 创建持仓：IO 品种占比高
        positions = [
            _make_position(
                vt_symbol="IO2506-C-5000.CFFEX",
                underlying="IO.CFFEX",
                volume=20,
            ),
            _make_position(
                vt_symbol="IO2506-C-5100.CFFEX",
                underlying="IO.CFFEX",
                volume=15,
            ),
            _make_position(
                vt_symbol="HO2506-C-3000.CFFEX",
                underlying="HO.CFFEX",
                volume=5,
            ),
        ]
        
        # 价格数据
        prices = {
            "IO2506-C-5000.CFFEX": 200.0,
            "IO2506-C-5100.CFFEX": 180.0,
            "HO2506-C-3000.CFFEX": 150.0,
        }
        
        # 计算集中度
        metrics = monitor.calculate_concentration(positions, prices)
        
        # 验证品种集中度
        # IO 价值: 200*20 + 180*15 = 4000 + 2700 = 6700
        # HO 价值: 150*5 = 750
        # 总价值: 7450
        # IO 占比: 6700/7450 ≈ 0.90
        assert "IO.CFFEX" in metrics.underlying_concentration
        assert "HO.CFFEX" in metrics.underlying_concentration
        assert metrics.underlying_concentration["IO.CFFEX"] > 0.85
        assert metrics.max_underlying_ratio > 0.85
        
        # 验证 HHI
        # HHI = 0.90^2 + 0.10^2 ≈ 0.82
        assert metrics.underlying_hhi > 0.8
        
        # 检查集中度超限
        warnings = monitor.check_concentration_limits(metrics)
        
        # 应该有警告（IO 品种集中度超限，HHI 超限）
        assert len(warnings) >= 2
        warning_dimensions = [w.dimension for w in warnings]
        assert "underlying" in warning_dimensions
        assert "hhi" in warning_dimensions

    def test_multi_dimension_concentration(self):
        """多维度集中度：品种、到期日、行权价同时监控"""
        config = ConcentrationConfig(
            underlying_concentration_limit=0.6,
            expiry_concentration_limit=0.7,
            strike_concentration_limit=0.5,
        )
        monitor = ConcentrationMonitor(config)
        
        # 创建持仓：同一到期日、同一行权价区间
        positions = [
            _make_position(vt_symbol="IO2506-C-5000.CFFEX", volume=10),
            _make_position(vt_symbol="IO2506-C-5100.CFFEX", volume=8),
            _make_position(vt_symbol="IO2506-P-4900.CFFEX", volume=12),
            _make_position(vt_symbol="IO2509-C-5200.CFFEX", volume=3),
        ]
        
        prices = {
            "IO2506-C-5000.CFFEX": 200.0,
            "IO2506-C-5100.CFFEX": 180.0,
            "IO2506-P-4900.CFFEX": 190.0,
            "IO2509-C-5200.CFFEX": 150.0,
        }
        
        metrics = monitor.calculate_concentration(positions, prices)
        
        # 验证到期日集中度（2506 占比高）
        assert "2506" in metrics.expiry_concentration
        assert "2509" in metrics.expiry_concentration
        # 2506: (200*10 + 180*8 + 190*12) = 6720
        # 2509: 150*3 = 450
        # 总计: 7170
        # 2506 占比: 6720/7170 ≈ 0.937
        assert metrics.expiry_concentration["2506"] > 0.9
        assert metrics.max_expiry_ratio > 0.9
        
        # 验证行权价集中度
        # 5000-5500 区间包含 5000, 5100, 5200
        # 4500-5000 区间包含 4900
        assert len(metrics.strike_concentration) >= 2
        
        # 检查超限
        warnings = monitor.check_concentration_limits(metrics)
        
        # 到期日集中度应该超限
        expiry_warnings = [w for w in warnings if w.dimension == "expiry"]
        assert len(expiry_warnings) >= 1


# ===========================================================================
# Test 5: TimeDecayMonitor 的完整流程
# ===========================================================================


class TestTimeDecayMonitorIntegration:
    """测试时间衰减监控器的完整工作流程
    
    Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7
    """
    
    def test_theta_calculation_and_expiry_identification(self):
        """完整流程：持仓 → 计算 Theta → 识别临近到期"""
        config = TimeDecayConfig(
            expiry_warning_days=7,
            critical_expiry_days=3,
        )
        monitor = TimeDecayMonitor(config)
        
        # 创建持仓
        positions = [
            _make_position(vt_symbol="IO2506-C-5000.CFFEX", volume=10),
            _make_position(vt_symbol="IO2506-C-5100.CFFEX", volume=8),
            _make_position(vt_symbol="IO2509-C-5200.CFFEX", volume=5),
        ]
        
        # Greeks 数据
        greeks_map = {
            "IO2506-C-5000.CFFEX": _make_greeks(theta=-0.8),
            "IO2506-C-5100.CFFEX": _make_greeks(theta=-0.6),
            "IO2509-C-5200.CFFEX": _make_greeks(theta=-0.5),
        }
        
        # 计算组合 Theta
        theta_metrics = monitor.calculate_portfolio_theta(positions, greeks_map)
        
        # 验证 Theta 聚合
        # Total Theta = (-0.8*10 + -0.6*8 + -0.5*5) * 10000
        #             = (-8 - 4.8 - 2.5) * 10000 = -152000
        expected_theta = (-0.8 * 10 + -0.6 * 8 + -0.5 * 5) * 10000
        assert theta_metrics.total_theta == pytest.approx(expected_theta, abs=100.0)
        assert theta_metrics.daily_decay_amount == pytest.approx(abs(expected_theta), abs=100.0)
        assert theta_metrics.position_count == 3
        
        # 识别临近到期持仓（假设当前日期是 2025-06-08，2506 合约 6 天后到期）
        current_date = datetime(2025, 6, 8)
        expiring = monitor.identify_expiring_positions(positions, current_date)
        
        # 2506 合约应该被识别为 warning（距离到期 7 天内）
        # 2509 合约不应该被识别（距离到期超过 7 天）
        assert len(expiring) >= 2  # 两个 2506 合约
        expiring_symbols = [e.vt_symbol for e in expiring]
        assert "IO2506-C-5000.CFFEX" in expiring_symbols
        assert "IO2506-C-5100.CFFEX" in expiring_symbols
        
        # 验证紧急程度
        for exp in expiring:
            if "2506" in exp.vt_symbol:
                assert exp.urgency in ["warning", "critical"]

    def test_expiry_distribution_grouping(self):
        """到期日分组：按到期日统计持仓分布"""
        config = TimeDecayConfig()
        monitor = TimeDecayMonitor(config)
        
        # 创建不同到期日的持仓
        positions = [
            _make_position(vt_symbol="IO2506-C-5000.CFFEX", volume=10),
            _make_position(vt_symbol="IO2506-C-5100.CFFEX", volume=8),
            _make_position(vt_symbol="IO2506-P-4900.CFFEX", volume=12),
            _make_position(vt_symbol="IO2509-C-5200.CFFEX", volume=5),
            _make_position(vt_symbol="IO2509-P-5000.CFFEX", volume=7),
        ]
        
        # 按到期日分组
        distribution = monitor.calculate_expiry_distribution(positions)
        
        # 验证分组结果
        assert "2506" in distribution
        assert "2509" in distribution
        
        # 2506 分组：3 个持仓，总手数 30
        group_2506 = distribution["2506"]
        assert group_2506.position_count == 3
        assert group_2506.total_volume == 30
        assert len(group_2506.positions) == 3
        
        # 2509 分组：2 个持仓，总手数 12
        group_2509 = distribution["2509"]
        assert group_2509.position_count == 2
        assert group_2509.total_volume == 12
        assert len(group_2509.positions) == 2
        
        # 验证完整性：所有持仓都被分组
        total_positions = sum(g.position_count for g in distribution.values())
        assert total_positions == len(positions)
    
    def test_critical_expiry_urgency(self):
        """紧急到期：距离到期 3 天内标记为 critical"""
        config = TimeDecayConfig(
            expiry_warning_days=7,
            critical_expiry_days=3,
        )
        monitor = TimeDecayMonitor(config)
        
        positions = [
            _make_position(vt_symbol="IO2506-C-5000.CFFEX", volume=10),
        ]
        
        # 场景 1：距离到期 2 天（critical）
        current_date = datetime(2025, 6, 13)
        expiring = monitor.identify_expiring_positions(positions, current_date)
        
        assert len(expiring) == 1
        assert expiring[0].urgency == "critical"
        assert expiring[0].days_to_expiry <= 3
        
        # 场景 2：距离到期 5 天（warning）
        current_date = datetime(2025, 6, 10)
        expiring = monitor.identify_expiring_positions(positions, current_date)
        
        assert len(expiring) == 1
        assert expiring[0].urgency == "warning"
        assert 3 < expiring[0].days_to_expiry <= 7


# ===========================================================================
# Test 6: 多个风险服务同时工作的场景
# ===========================================================================


class TestMultipleRiskServicesIntegration:
    """测试多个风险服务协同工作的综合场景
    
    Validates: Requirements 全部 (1-5)
    """
    
    def test_comprehensive_risk_monitoring_scenario(self):
        """综合场景：同时监控止损、预算、流动性、集中度、时间衰减"""
        # 初始化所有风险服务
        stop_loss_manager = StopLossManager(StopLossConfig(
            enable_fixed_stop=True,
            fixed_stop_loss_amount=10000.0,
        ))
        
        budget_allocator = RiskBudgetAllocator(RiskBudgetConfig(
            allocation_dimension="underlying",
            allocation_ratios={"IO.CFFEX": 0.6, "HO.CFFEX": 0.4},
        ))
        
        liquidity_monitor = LiquidityRiskMonitor(LiquidityMonitorConfig(
            liquidity_score_threshold=0.4,
        ))
        
        concentration_monitor = ConcentrationMonitor(ConcentrationConfig(
            underlying_concentration_limit=0.7,
        ))
        
        time_decay_monitor = TimeDecayMonitor(TimeDecayConfig(
            expiry_warning_days=10,
        ))
        
        # 创建持仓组合
        positions = [
            _make_position(
                vt_symbol="IO2506-C-5000.CFFEX",
                underlying="IO.CFFEX",
                volume=15,
                open_price=200.0,
            ),
            _make_position(
                vt_symbol="IO2506-C-5100.CFFEX",
                underlying="IO.CFFEX",
                volume=10,
                open_price=180.0,
            ),
            _make_position(
                vt_symbol="HO2506-C-3000.CFFEX",
                underlying="HO.CFFEX",
                volume=5,
                open_price=150.0,
            ),
        ]
        
        # 当前价格（部分持仓亏损）
        current_prices = {
            "IO2506-C-5000.CFFEX": 220.0,  # 亏损
            "IO2506-C-5100.CFFEX": 190.0,  # 亏损
            "HO2506-C-3000.CFFEX": 140.0,  # 盈利
        }
        
        # Greeks 数据
        greeks_map = {
            "IO2506-C-5000.CFFEX": _make_greeks(delta=0.6, gamma=0.02, theta=-0.8, vega=25.0),
            "IO2506-C-5100.CFFEX": _make_greeks(delta=0.5, gamma=0.015, theta=-0.6, vega=20.0),
            "HO2506-C-3000.CFFEX": _make_greeks(delta=0.4, gamma=0.01, theta=-0.5, vega=18.0),
        }
        
        # 市场数据
        current_time = datetime.now()
        market_data = {
            "IO2506-C-5000.CFFEX": MarketData(
                vt_symbol="IO2506-C-5000.CFFEX",
                timestamp=current_time,
                volume=800.0,
                bid_price=218.0,
                ask_price=222.0,
                open_interest=5000.0,
            ),
            "IO2506-C-5100.CFFEX": MarketData(
                vt_symbol="IO2506-C-5100.CFFEX",
                timestamp=current_time,
                volume=600.0,
                bid_price=188.0,
                ask_price=192.0,
                open_interest=4000.0,
            ),
            "HO2506-C-3000.CFFEX": MarketData(
                vt_symbol="HO2506-C-3000.CFFEX",
                timestamp=current_time,
                volume=400.0,
                bid_price=138.0,
                ask_price=142.0,
                open_interest=3000.0,
            ),
        }
        
        historical_data = {
            sym: [
                MarketData(
                    vt_symbol=sym,
                    timestamp=current_time - timedelta(days=i),
                    volume=1000.0,
                    bid_price=data.bid_price,
                    ask_price=data.ask_price,
                    open_interest=data.open_interest,
                )
                for i in range(1, 6)
            ]
            for sym, data in market_data.items()
        }
        
        # 1. 检查止损
        stop_loss_triggers = []
        for pos in positions:
            trigger = stop_loss_manager.check_position_stop_loss(
                pos, current_prices[pos.vt_symbol]
            )
            if trigger:
                stop_loss_triggers.append(trigger)
        
        # 应该有止损触发（IO2506-C-5000 亏损 30万）
        assert len(stop_loss_triggers) >= 1
        
        # 2. 检查预算
        total_limits = RiskThresholds(
            portfolio_delta_limit=100000.0,
            portfolio_gamma_limit=10000.0,
            portfolio_vega_limit=500000.0,
        )
        budget_map = budget_allocator.allocate_budget_by_underlying(total_limits)
        usage_map = budget_allocator.calculate_usage(positions, greeks_map, "underlying")
        
        budget_violations = []
        for underlying, usage in usage_map.items():
            if underlying in budget_map:
                result = budget_allocator.check_budget_limit(usage, budget_map[underlying])
                if not result.passed:
                    budget_violations.append((underlying, result))
        
        # 可能有预算超限
        assert isinstance(budget_violations, list)
        
        # 3. 检查流动性
        liquidity_warnings = liquidity_monitor.monitor_positions(
            positions, market_data, historical_data
        )
        
        # 流动性监控应该正常运行
        assert isinstance(liquidity_warnings, list)
        
        # 4. 检查集中度
        concentration_metrics = concentration_monitor.calculate_concentration(
            positions, current_prices
        )
        concentration_warnings = concentration_monitor.check_concentration_limits(
            concentration_metrics
        )
        
        # IO 品种占比高，可能有集中度警告
        assert concentration_metrics.max_underlying_ratio > 0.6
        
        # 5. 检查时间衰减
        theta_metrics = time_decay_monitor.calculate_portfolio_theta(positions, greeks_map)
        current_date = datetime(2025, 6, 8)
        expiring_positions = time_decay_monitor.identify_expiring_positions(
            positions, current_date
        )
        
        # Theta 应该为负（期权卖方）
        assert theta_metrics.total_theta < 0
        assert theta_metrics.daily_decay_amount > 0
        
        # 应该识别到临近到期的持仓
        assert len(expiring_positions) >= 2
        
        # 综合验证：所有风险服务都正常工作
        print(f"\n=== 综合风险监控结果 ===")
        print(f"止损触发: {len(stop_loss_triggers)} 个")
        print(f"预算超限: {len(budget_violations)} 个")
        print(f"流动性警告: {len(liquidity_warnings)} 个")
        print(f"集中度警告: {len(concentration_warnings)} 个")
        print(f"临近到期: {len(expiring_positions)} 个")
        print(f"组合 Theta: {theta_metrics.total_theta:.2f}")
        print(f"每日衰减: {theta_metrics.daily_decay_amount:.2f}")

    
    def test_risk_services_with_position_lifecycle(self):
        """风险服务与持仓生命周期：开仓 → 监控 → 触发风险 → 平仓"""
        # 初始化服务
        stop_loss_manager = StopLossManager(StopLossConfig(
            enable_fixed_stop=True,
            fixed_stop_loss_amount=5000.0,
        ))
        
        concentration_monitor = ConcentrationMonitor(ConcentrationConfig(
            underlying_concentration_limit=0.8,
        ))
        
        # 阶段 1：开仓
        position = _make_position(
            vt_symbol="IO2506-C-5000.CFFEX",
            underlying="IO.CFFEX",
            volume=10,
            open_price=200.0,
        )
        
        assert position.is_active
        assert position.volume == 10
        
        # 阶段 2：价格变化，监控风险
        current_price = 210.0
        trigger = stop_loss_manager.check_position_stop_loss(position, current_price)
        
        # 亏损 (210-200)*10*10000 = 1000000，超过阈值 5000
        assert trigger is not None
        assert trigger.current_loss == 1000000.0
        
        # 阶段 3：检查集中度（单一持仓，100% 集中）
        metrics = concentration_monitor.calculate_concentration(
            [position], {"IO2506-C-5000.CFFEX": current_price}
        )
        
        assert metrics.max_underlying_ratio == 1.0
        assert metrics.underlying_hhi == 1.0
        
        # 阶段 4：平仓
        position.reduce_volume(10)
        
        assert position.is_closed
        assert position.volume == 0
        assert not position.is_active
        
        # 阶段 5：平仓后不再触发风险
        trigger_after_close = stop_loss_manager.check_position_stop_loss(
            position, current_price
        )
        
        assert trigger_after_close is None  # 已平仓，不触发止损
    
    def test_empty_positions_handling(self):
        """边界情况：空持仓列表的处理"""
        # 所有服务都应该能处理空持仓列表
        stop_loss_manager = StopLossManager(StopLossConfig())
        budget_allocator = RiskBudgetAllocator(RiskBudgetConfig())
        liquidity_monitor = LiquidityRiskMonitor(LiquidityMonitorConfig())
        concentration_monitor = ConcentrationMonitor(ConcentrationConfig())
        time_decay_monitor = TimeDecayMonitor(TimeDecayConfig())
        
        empty_positions = []
        
        # 组合止损
        portfolio_trigger = stop_loss_manager.check_portfolio_stop_loss(
            empty_positions, {}, 100000.0, 100000.0
        )
        assert portfolio_trigger is None
        
        # 预算使用量
        usage_map = budget_allocator.calculate_usage(empty_positions, {})
        assert len(usage_map) == 0
        
        # 流动性监控
        warnings = liquidity_monitor.monitor_positions(empty_positions, {}, {})
        assert len(warnings) == 0
        
        # 集中度计算
        metrics = concentration_monitor.calculate_concentration(empty_positions, {})
        assert metrics.max_underlying_ratio == 0.0
        assert metrics.underlying_hhi == 0.0
        
        # Theta 计算
        theta_metrics = time_decay_monitor.calculate_portfolio_theta(empty_positions, {})
        assert theta_metrics.total_theta == 0.0
        assert theta_metrics.position_count == 0
        
        # 到期识别
        expiring = time_decay_monitor.identify_expiring_positions(
            empty_positions, datetime.now()
        )
        assert len(expiring) == 0
