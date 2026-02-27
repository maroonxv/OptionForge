"""
LiquidityRiskMonitor 属性测试

使用 Hypothesis 进行基于属性的测试，验证持仓流动性监控服务的通用正确性属性。
"""
from hypothesis import given, strategies as st, settings, assume
from datetime import datetime, timedelta

from src.strategy.domain.domain_service.risk.liquidity_risk_monitor import LiquidityRiskMonitor
from src.strategy.domain.entity.position import Position
from src.strategy.domain.value_object.risk.risk import (
    LiquidityMonitorConfig,
    MarketData,
)


# ============================================================================
# 测试数据生成策略
# ============================================================================

def liquidity_config_strategy():
    """生成流动性监控配置的策略"""
    # 生成三个权重，确保总和为 1.0
    volume_weight = st.floats(min_value=0.1, max_value=0.8, allow_nan=False, allow_infinity=False)
    
    @st.composite
    def config_with_valid_weights(draw):
        vw = draw(volume_weight)
        # 剩余权重在 spread 和 oi 之间分配
        remaining = 1.0 - vw
        sw = draw(st.floats(min_value=0.1 * remaining, max_value=0.9 * remaining, allow_nan=False, allow_infinity=False))
        ow = remaining - sw
        
        return LiquidityMonitorConfig(
            volume_weight=vw,
            spread_weight=sw,
            open_interest_weight=ow,
            liquidity_score_threshold=draw(st.floats(min_value=0.1, max_value=0.9, allow_nan=False, allow_infinity=False)),
            lookback_days=draw(st.integers(min_value=1, max_value=30)),
        )
    
    return config_with_valid_weights()


def market_data_strategy(vt_symbol: str = "10005000C2412.SSE"):
    """生成市场数据的策略"""
    return st.builds(
        MarketData,
        vt_symbol=st.just(vt_symbol),
        timestamp=st.datetimes(min_value=datetime(2024, 1, 1), max_value=datetime(2024, 12, 31)),
        volume=st.floats(min_value=0.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        bid_price=st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False),
        ask_price=st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False),
        open_interest=st.floats(min_value=0.0, max_value=50000.0, allow_nan=False, allow_infinity=False),
    )


def position_strategy():
    """生成持仓实体的策略"""
    return st.builds(
        Position,
        vt_symbol=st.text(min_size=10, max_size=20, alphabet="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ."),
        underlying_vt_symbol=st.just("510050.SSE"),
        signal=st.just("test_signal"),
        volume=st.integers(min_value=1, max_value=100),
        direction=st.sampled_from(["long", "short"]),
        open_price=st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False),
        is_closed=st.just(False),
    )


# ============================================================================
# Feature: risk-service-enhancement, Property 9: 流动性评分范围
# **Validates: Requirements 3.1, 3.6**
# ============================================================================

@settings(max_examples=100)
@given(
    config=liquidity_config_strategy(),
    current_data=market_data_strategy(),
    historical_data=st.lists(market_data_strategy(), min_size=0, max_size=10),
)
def test_property_liquidity_score_range(config, current_data, historical_data):
    """
    Feature: risk-service-enhancement, Property 9: 流动性评分范围
    
    对于任意市场数据，计算的流动性评分应该在 [0, 1] 范围内，
    且综合评分应该是各子评分的加权平均
    
    **Validates: Requirements 3.1, 3.6**
    """
    # 确保价格有效（ask >= bid）
    if current_data.ask_price < current_data.bid_price:
        current_data = MarketData(
            vt_symbol=current_data.vt_symbol,
            timestamp=current_data.timestamp,
            volume=current_data.volume,
            bid_price=min(current_data.bid_price, current_data.ask_price),
            ask_price=max(current_data.bid_price, current_data.ask_price),
            open_interest=current_data.open_interest,
        )
    
    # 修正历史数据中的价格
    fixed_historical = []
    for data in historical_data:
        if data.ask_price < data.bid_price:
            data = MarketData(
                vt_symbol=data.vt_symbol,
                timestamp=data.timestamp,
                volume=data.volume,
                bid_price=min(data.bid_price, data.ask_price),
                ask_price=max(data.bid_price, data.ask_price),
                open_interest=data.open_interest,
            )
        fixed_historical.append(data)
    
    monitor = LiquidityRiskMonitor(config)
    
    # 计算流动性评分
    score = monitor.calculate_liquidity_score(
        current_data.vt_symbol, current_data, fixed_historical
    )
    
    # 属性验证 1: 所有评分应该在 [0, 1] 范围内
    assert 0.0 <= score.overall_score <= 1.0, \
        f"综合评分应在 [0, 1] 范围内，实际: {score.overall_score}"
    assert 0.0 <= score.volume_score <= 1.0, \
        f"成交量评分应在 [0, 1] 范围内，实际: {score.volume_score}"
    assert 0.0 <= score.spread_score <= 1.0, \
        f"价差评分应在 [0, 1] 范围内，实际: {score.spread_score}"
    assert 0.0 <= score.open_interest_score <= 1.0, \
        f"持仓量评分应在 [0, 1] 范围内，实际: {score.open_interest_score}"
    
    # 属性验证 2: 综合评分应该是各子评分的加权平均
    expected_overall = (
        score.volume_score * config.volume_weight +
        score.spread_score * config.spread_weight +
        score.open_interest_score * config.open_interest_weight
    )
    
    assert abs(score.overall_score - expected_overall) < 1e-6, \
        f"综合评分应是加权平均。期望: {expected_overall:.6f}, 实际: {score.overall_score:.6f}"
    
    # 属性验证 3: 合约代码应该匹配
    assert score.vt_symbol == current_data.vt_symbol, \
        f"评分结果应包含正确的合约代码"


# ============================================================================
# Feature: risk-service-enhancement, Property 10: 流动性趋势识别
# **Validates: Requirements 3.2, 3.3, 3.4**
# ============================================================================

@settings(max_examples=100)
@given(
    config=liquidity_config_strategy(),
    base_volume=st.floats(min_value=100.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
    base_bid=st.floats(min_value=0.1, max_value=5.0, allow_nan=False, allow_infinity=False),
    base_spread_pct=st.floats(min_value=0.01, max_value=0.05, allow_nan=False, allow_infinity=False),
    base_oi=st.floats(min_value=1000.0, max_value=20000.0, allow_nan=False, allow_infinity=False),
    volume_change=st.floats(min_value=-0.5, max_value=0.5, allow_nan=False, allow_infinity=False),
    spread_change=st.floats(min_value=-0.5, max_value=0.5, allow_nan=False, allow_infinity=False),
    oi_change=st.floats(min_value=-0.5, max_value=0.5, allow_nan=False, allow_infinity=False),
)
def test_property_liquidity_trend_identification(
    config, base_volume, base_bid, base_spread_pct, base_oi,
    volume_change, spread_change, oi_change
):
    """
    Feature: risk-service-enhancement, Property 10: 流动性趋势识别
    
    对于任意历史市场数据序列，当成交量递减、价差扩大或持仓量减少时，
    流动性趋势应该识别为"deteriorating"
    
    **Validates: Requirements 3.2, 3.3, 3.4**
    """
    monitor = LiquidityRiskMonitor(config)
    
    # 创建稳定的历史数据（5天）
    base_time = datetime(2024, 1, 1, 9, 30)
    base_ask = base_bid * (1 + base_spread_pct)
    
    historical_data = [
        MarketData(
            vt_symbol="10005000C2412.SSE",
            timestamp=base_time + timedelta(days=i),
            volume=base_volume,
            bid_price=base_bid,
            ask_price=base_ask,
            open_interest=base_oi,
        )
        for i in range(5)
    ]
    
    # 创建当前数据（应用变化）
    current_volume = base_volume * (1 + volume_change)
    current_spread_pct = base_spread_pct * (1 + spread_change)
    current_oi = base_oi * (1 + oi_change)
    current_ask = base_bid * (1 + current_spread_pct)
    
    # 确保数据有效
    assume(current_volume >= 0)
    assume(current_oi >= 0)
    assume(current_spread_pct > 0)
    assume(current_ask > base_bid)
    
    current_data = MarketData(
        vt_symbol="10005000C2412.SSE",
        timestamp=base_time + timedelta(days=5),
        volume=current_volume,
        bid_price=base_bid,
        ask_price=current_ask,
        open_interest=current_oi,
    )
    
    # 计算流动性评分
    score = monitor.calculate_liquidity_score(
        "10005000C2412.SSE", current_data, historical_data
    )
    
    # 计算恶化信号数量
    deteriorating_signals = 0
    improving_signals = 0
    
    # 成交量递减超过 10% -> 恶化
    if volume_change < -0.1:
        deteriorating_signals += 1
    elif volume_change > 0.1:
        improving_signals += 1
    
    # 价差扩大超过 10% -> 恶化
    if spread_change > 0.1:
        deteriorating_signals += 1
    elif spread_change < -0.1:
        improving_signals += 1
    
    # 持仓量减少超过 10% -> 恶化
    if oi_change < -0.1:
        deteriorating_signals += 1
    elif oi_change > 0.1:
        improving_signals += 1
    
    # 属性验证: 当有 2 个或更多恶化信号时，趋势应该是 deteriorating
    if deteriorating_signals >= 2:
        assert score.trend == "deteriorating", \
            f"当成交量递减、价差扩大或持仓量减少时（{deteriorating_signals}个恶化信号），" \
            f"趋势应为 deteriorating，实际: {score.trend}"
    
    # 当有 2 个或更多改善信号时，趋势应该是 improving
    if improving_signals >= 2:
        assert score.trend == "improving", \
            f"当成交量增加、价差缩小或持仓量增加时（{improving_signals}个改善信号），" \
            f"趋势应为 improving，实际: {score.trend}"
    
    # 其他情况应该是 stable
    if deteriorating_signals < 2 and improving_signals < 2:
        assert score.trend == "stable", \
            f"当信号混合或不明显时，趋势应为 stable，实际: {score.trend}"


# ============================================================================
# Feature: risk-service-enhancement, Property 11: 流动性警告触发
# **Validates: Requirements 3.5**
# ============================================================================

@settings(max_examples=100)
@given(
    config=liquidity_config_strategy(),
    positions=st.lists(position_strategy(), min_size=1, max_size=5),
    score_multiplier=st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False),
)
def test_property_liquidity_warning_trigger(config, positions, score_multiplier):
    """
    Feature: risk-service-enhancement, Property 11: 流动性警告触发
    
    对于任意持仓合约和流动性评分，当评分低于配置阈值时，
    监控结果应该包含该合约的流动性警告
    
    **Validates: Requirements 3.5**
    """
    monitor = LiquidityRiskMonitor(config)
    
    # 为每个持仓创建市场数据
    # 通过 score_multiplier 控制流动性评分相对于阈值的高低
    market_data = {}
    historical_data = {}
    
    for position in positions:
        # 确保持仓是活跃的
        if not position.is_active:
            continue
        
        # 创建市场数据，使流动性评分接近阈值 * score_multiplier
        # 当 score_multiplier < 1 时，评分应低于阈值，触发警告
        # 当 score_multiplier > 1 时，评分应高于阈值，不触发警告
        
        # 使用简单的市场数据（无历史数据）
        # 成交量评分 = min(volume / 1000, 1.0)
        # 价差评分 = exp(-10.5 * relative_spread)
        # 持仓量评分 = min(oi / 5000, 1.0)
        
        # 目标综合评分 = threshold * score_multiplier
        target_score = config.liquidity_score_threshold * score_multiplier
        target_score = max(0.0, min(1.0, target_score))  # 限制在 [0, 1]
        
        # 简化：让所有子评分都等于目标评分
        # volume = target_score * 1000
        # oi = target_score * 5000
        # 价差评分 = target_score => relative_spread = -ln(target_score) / 10.5
        
        import math
        volume = target_score * 1000.0
        oi = target_score * 5000.0
        
        # 计算相对价差
        if target_score > 0.01:
            relative_spread = -math.log(target_score) / 10.5
        else:
            relative_spread = 1.0  # 很大的价差
        
        bid_price = 0.5
        mid_price = bid_price / (1 - relative_spread / 2)
        ask_price = mid_price * (1 + relative_spread / 2)
        
        # 确保价格有效
        if ask_price <= bid_price:
            ask_price = bid_price * 1.01
        
        market_data[position.vt_symbol] = MarketData(
            vt_symbol=position.vt_symbol,
            timestamp=datetime.now(),
            volume=volume,
            bid_price=bid_price,
            ask_price=ask_price,
            open_interest=oi,
        )
    
    # 执行流动性监控
    warnings = monitor.monitor_positions(positions, market_data, historical_data)
    
    # 属性验证
    active_positions = [pos for pos in positions if pos.is_active and pos.vt_symbol in market_data]
    
    if score_multiplier < 1.0:
        # 评分应低于阈值，应该触发警告
        # 每个活跃持仓都应该有警告
        warning_symbols = {w.vt_symbol for w in warnings}
        active_symbols = {pos.vt_symbol for pos in active_positions}
        
        assert warning_symbols == active_symbols, \
            f"当评分低于阈值时，所有活跃持仓都应触发警告。" \
            f"期望: {active_symbols}, 实际: {warning_symbols}"
        
        # 验证每个警告的内容
        for warning in warnings:
            assert warning.current_score < config.liquidity_score_threshold, \
                f"警告的评分应低于阈值。评分: {warning.current_score}, 阈值: {config.liquidity_score_threshold}"
            assert warning.threshold == config.liquidity_score_threshold, \
                f"警告应包含正确的阈值"
            assert len(warning.message) > 0, \
                f"警告应包含消息"
            assert "流动性恶化警告" in warning.message, \
                f"警告消息应包含关键词"
    
    elif score_multiplier > 1.1:
        # 评分应高于阈值，不应该触发警告
        assert len(warnings) == 0, \
            f"当评分高于阈值时，不应触发警告。实际警告数: {len(warnings)}"


# ============================================================================
# Feature: risk-service-enhancement, Property 12: 持仓过滤正确性
# **Validates: Requirements 3.8**
# ============================================================================

@settings(max_examples=100)
@given(
    config=liquidity_config_strategy(),
    held_positions=st.lists(position_strategy(), min_size=1, max_size=5),
    extra_symbols=st.lists(
        st.text(min_size=10, max_size=20, alphabet="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ."),
        min_size=0,
        max_size=5
    ),
)
def test_property_position_filtering_correctness(config, held_positions, extra_symbols):
    """
    Feature: risk-service-enhancement, Property 12: 持仓过滤正确性
    
    对于任意持仓列表和市场数据，流动性监控结果应该只包含持仓列表中的合约，
    不包含其他合约
    
    **Validates: Requirements 3.8**
    """
    monitor = LiquidityRiskMonitor(config)
    
    # 收集持仓合约代码
    held_symbols = {pos.vt_symbol for pos in held_positions if pos.is_active}
    
    # 确保 extra_symbols 不与 held_symbols 重复
    extra_symbols = [s for s in extra_symbols if s not in held_symbols]
    
    # 创建市场数据：包含持仓合约 + 额外合约
    market_data = {}
    
    # 为持仓合约创建低流动性数据（触发警告）
    for position in held_positions:
        if not position.is_active:
            continue
        
        market_data[position.vt_symbol] = MarketData(
            vt_symbol=position.vt_symbol,
            timestamp=datetime.now(),
            volume=50.0,  # 低成交量
            bid_price=0.5,
            ask_price=0.55,  # 宽价差
            open_interest=200.0,  # 低持仓量
        )
    
    # 为额外合约创建低流动性数据
    for symbol in extra_symbols:
        market_data[symbol] = MarketData(
            vt_symbol=symbol,
            timestamp=datetime.now(),
            volume=50.0,
            bid_price=0.5,
            ask_price=0.55,
            open_interest=200.0,
        )
    
    # 执行流动性监控
    warnings = monitor.monitor_positions(held_positions, market_data, {})
    
    # 属性验证: 警告应该只包含持仓列表中的合约
    warning_symbols = {w.vt_symbol for w in warnings}
    
    # 警告合约应该是持仓合约的子集
    assert warning_symbols.issubset(held_symbols), \
        f"警告应该只包含持仓合约。持仓: {held_symbols}, 警告: {warning_symbols}"
    
    # 警告合约不应该包含额外合约
    for symbol in extra_symbols:
        assert symbol not in warning_symbols, \
            f"警告不应包含非持仓合约: {symbol}"
    
    # 验证每个警告的合约都在持仓列表中
    for warning in warnings:
        assert any(
            pos.vt_symbol == warning.vt_symbol and pos.is_active
            for pos in held_positions
        ), f"警告的合约 {warning.vt_symbol} 应该在活跃持仓列表中"
