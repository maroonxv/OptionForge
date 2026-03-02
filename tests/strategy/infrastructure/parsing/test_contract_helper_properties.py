"""
ContractHelper 属性测试

使用 Hypothesis 进行基于属性的测试，验证合约解析的正确性和一致性。
"""
import re
from hypothesis import given, settings, strategies as st

from src.strategy.infrastructure.parsing.contract_helper import ContractHelper


# ============================================================================
# Hypothesis 策略定义
# ============================================================================

@st.composite
def option_contract_symbol_strategy(draw):
    """
    生成符合格式的期权合约代码
    
    格式: <产品代码><YYMM>-<期权类型>-<行权价>.<交易所>
    或紧凑格式: <产品代码><YYMM><期权类型><行权价>.<交易所>
    """
    # 产品代码
    product = draw(st.sampled_from([
        "IO", "MO", "HO",  # 股指期权
        "m", "c", "SR", "CF", "cu", "au"  # 商品期权
    ]))
    
    # 年月 (YYMM 格式)
    year = draw(st.integers(min_value=24, max_value=29))
    month = draw(st.integers(min_value=1, max_value=12))
    yymm = f"{year:02d}{month:02d}"
    
    # 期权类型
    option_type = draw(st.sampled_from(["C", "P"]))
    
    # 行权价（根据产品类型选择合理范围）
    if product in ["IO", "MO", "HO"]:
        # 股指期权：1000-10000
        strike = draw(st.integers(min_value=1000, max_value=10000))
    elif product in ["SR", "CF"]:
        # 农产品期权：5000-20000
        strike = draw(st.integers(min_value=5000, max_value=20000))
    elif product in ["cu", "au"]:
        # 金属期权：30000-100000
        strike = draw(st.integers(min_value=30000, max_value=100000))
    else:
        # 其他商品期权：500-5000
        strike = draw(st.integers(min_value=500, max_value=5000))
    
    # 交易所
    exchange = draw(st.sampled_from(["CFFEX", "DCE", "CZCE", "SHFE"]))
    
    # 格式选择
    use_compact = draw(st.booleans())
    include_exchange = draw(st.booleans())
    
    if use_compact:
        # 紧凑格式: IO2401C4000.CFFEX
        symbol = f"{product}{yymm}{option_type}{strike}"
    else:
        # 标准格式: IO2401-C-4000.CFFEX
        symbol = f"{product}{yymm}-{option_type}-{strike}"
    
    if include_exchange:
        symbol = f"{symbol}.{exchange}"
    
    return symbol, yymm, strike


@st.composite
def yymm_format_strategy(draw):
    """
    生成 YYMM 格式的到期日字符串
    """
    year = draw(st.integers(min_value=24, max_value=29))
    month = draw(st.integers(min_value=1, max_value=12))
    return f"{year:02d}{month:02d}"


# ============================================================================
# 属性 3: 合约代码到期日提取正确性
# ============================================================================

class TestContractHelperExpiryExtractionProperties:
    """
    **属性 3: 合约代码到期日提取正确性**
    
    对于任何符合期权合约格式的 vt_symbol（包含 YYMM 格式的年月信息），
    ContractHelper.extract_expiry_from_symbol 应该正确提取出 YYMM 格式的到期日字符串。
    
    **验证需求: 3.2, 4.3**
    """
    
    @given(option_contract_symbol_strategy())
    @settings(max_examples=100)
    def test_extract_expiry_returns_correct_yymm(self, symbol_data):
        """
        Feature: domain-service-infrastructure-refactoring, Property 3: 合约代码到期日提取正确性
        
        **Validates: Requirements 3.2, 4.3**
        
        验证从合约代码中提取的到期日与生成时的 YYMM 一致
        """
        symbol, expected_yymm, _ = symbol_data
        
        result = ContractHelper.extract_expiry_from_symbol(symbol)
        
        # 验证提取的到期日与预期一致
        assert result == expected_yymm, (
            f"提取的到期日 '{result}' 与预期 '{expected_yymm}' 不一致，"
            f"合约代码: {symbol}"
        )
    
    @given(option_contract_symbol_strategy())
    @settings(max_examples=100)
    def test_extract_expiry_returns_valid_yymm_format(self, symbol_data):
        """
        Feature: domain-service-infrastructure-refactoring, Property 3: 合约代码到期日提取正确性
        
        **Validates: Requirements 3.2**
        
        验证提取的到期日符合 YYMM 格式（4位数字）
        """
        symbol, _, _ = symbol_data
        
        result = ContractHelper.extract_expiry_from_symbol(symbol)
        
        # 验证格式：应该是 4 位数字或 "unknown"
        if result != "unknown":
            assert len(result) == 4, f"到期日长度应为 4，实际: {len(result)}"
            assert result.isdigit(), f"到期日应为数字，实际: {result}"
            
            # 验证年份和月份的合理性
            year = int(result[:2])
            month = int(result[2:])
            assert 24 <= year <= 99, f"年份应在 24-99 之间，实际: {year}"
            assert 1 <= month <= 12, f"月份应在 1-12 之间，实际: {month}"


# ============================================================================
# 属性 4: 合约代码行权价分组正确性
# ============================================================================

class TestContractHelperStrikeGroupingProperties:
    """
    **属性 4: 合约代码行权价分组正确性**
    
    对于任何符合期权合约格式的 vt_symbol（包含行权价信息），
    ContractHelper.group_by_strike_range 应该将行权价分组到正确的区间，
    且行权价应该落在返回的区间范围内。
    
    **验证需求: 3.3**
    """
    
    @given(option_contract_symbol_strategy())
    @settings(max_examples=100)
    def test_strike_falls_within_returned_range(self, symbol_data):
        """
        Feature: domain-service-infrastructure-refactoring, Property 4: 合约代码行权价分组正确性
        
        **Validates: Requirements 3.3**
        
        验证行权价落在返回的区间范围内
        """
        symbol, _, expected_strike = symbol_data
        
        result = ContractHelper.group_by_strike_range(symbol)
        
        # 如果返回 "unknown"，跳过验证
        if result == "unknown":
            return
        
        # 解析区间
        match = re.match(r"(\d+)-(\d+)", result)
        assert match is not None, f"区间格式无效: {result}"
        
        lower = int(match.group(1))
        upper = int(match.group(2))
        
        # 验证行权价在区间内
        assert lower <= expected_strike < upper, (
            f"行权价 {expected_strike} 不在区间 [{lower}, {upper}) 内，"
            f"合约代码: {symbol}"
        )
    
    @given(option_contract_symbol_strategy())
    @settings(max_examples=100)
    def test_strike_range_uses_correct_interval(self, symbol_data):
        """
        Feature: domain-service-infrastructure-refactoring, Property 4: 合约代码行权价分组正确性
        
        **Validates: Requirements 3.3**
        
        验证区间宽度根据行权价大小正确确定：
        - 行权价 < 1000: 区间宽度 100
        - 1000 <= 行权价 < 5000: 区间宽度 500
        - 行权价 >= 5000: 区间宽度 1000
        """
        symbol, _, expected_strike = symbol_data
        
        result = ContractHelper.group_by_strike_range(symbol)
        
        # 如果返回 "unknown"，跳过验证
        if result == "unknown":
            return
        
        # 解析区间
        match = re.match(r"(\d+)-(\d+)", result)
        assert match is not None, f"区间格式无效: {result}"
        
        lower = int(match.group(1))
        upper = int(match.group(2))
        interval = upper - lower
        
        # 验证区间宽度
        if expected_strike < 1000:
            expected_interval = 100
        elif expected_strike < 5000:
            expected_interval = 500
        else:
            expected_interval = 1000
        
        assert interval == expected_interval, (
            f"行权价 {expected_strike} 的区间宽度应为 {expected_interval}，"
            f"实际为 {interval}，合约代码: {symbol}"
        )
    
    @given(option_contract_symbol_strategy())
    @settings(max_examples=100)
    def test_strike_range_lower_bound_is_multiple_of_interval(self, symbol_data):
        """
        Feature: domain-service-infrastructure-refactoring, Property 4: 合约代码行权价分组正确性
        
        **Validates: Requirements 3.3**
        
        验证区间下界是区间宽度的整数倍
        """
        symbol, _, expected_strike = symbol_data
        
        result = ContractHelper.group_by_strike_range(symbol)
        
        # 如果返回 "unknown"，跳过验证
        if result == "unknown":
            return
        
        # 解析区间
        match = re.match(r"(\d+)-(\d+)", result)
        assert match is not None, f"区间格式无效: {result}"
        
        lower = int(match.group(1))
        upper = int(match.group(2))
        interval = upper - lower
        
        # 验证下界是区间宽度的整数倍
        assert lower % interval == 0, (
            f"区间下界 {lower} 不是区间宽度 {interval} 的整数倍，"
            f"合约代码: {symbol}"
        )


# ============================================================================
# 属性 5: 合约解析幂等性
# ============================================================================

class TestContractHelperIdempotencyProperties:
    """
    **属性 5: 合约解析幂等性**
    
    对于任何有效的合约代码，多次调用 ContractHelper 的解析方法
    （extract_expiry_from_symbol 或 group_by_strike_range）应该返回相同的结果。
    
    **验证需求: 3.6**
    """
    
    @given(option_contract_symbol_strategy())
    @settings(max_examples=100)
    def test_extract_expiry_is_idempotent(self, symbol_data):
        """
        Feature: domain-service-infrastructure-refactoring, Property 5: 合约解析幂等性
        
        **Validates: Requirements 3.6**
        
        验证多次调用 extract_expiry_from_symbol 返回相同结果
        """
        symbol, _, _ = symbol_data
        
        # 调用多次
        result1 = ContractHelper.extract_expiry_from_symbol(symbol)
        result2 = ContractHelper.extract_expiry_from_symbol(symbol)
        result3 = ContractHelper.extract_expiry_from_symbol(symbol)
        
        # 验证结果一致
        assert result1 == result2 == result3, (
            f"多次调用返回不同结果: {result1}, {result2}, {result3}，"
            f"合约代码: {symbol}"
        )
    
    @given(option_contract_symbol_strategy())
    @settings(max_examples=100)
    def test_group_by_strike_range_is_idempotent(self, symbol_data):
        """
        Feature: domain-service-infrastructure-refactoring, Property 5: 合约解析幂等性
        
        **Validates: Requirements 3.6**
        
        验证多次调用 group_by_strike_range 返回相同结果
        """
        symbol, _, _ = symbol_data
        
        # 调用多次
        result1 = ContractHelper.group_by_strike_range(symbol)
        result2 = ContractHelper.group_by_strike_range(symbol)
        result3 = ContractHelper.group_by_strike_range(symbol)
        
        # 验证结果一致
        assert result1 == result2 == result3, (
            f"多次调用返回不同结果: {result1}, {result2}, {result3}，"
            f"合约代码: {symbol}"
        )
    
    @given(option_contract_symbol_strategy(), st.integers(min_value=5, max_value=10))
    @settings(max_examples=50)
    def test_both_methods_are_idempotent_with_multiple_calls(self, symbol_data, num_calls):
        """
        Feature: domain-service-infrastructure-refactoring, Property 5: 合约解析幂等性
        
        **Validates: Requirements 3.6**
        
        验证多次调用两个方法都返回相同结果
        """
        symbol, _, _ = symbol_data
        
        # 多次调用 extract_expiry_from_symbol
        expiry_results = [
            ContractHelper.extract_expiry_from_symbol(symbol)
            for _ in range(num_calls)
        ]
        
        # 多次调用 group_by_strike_range
        strike_results = [
            ContractHelper.group_by_strike_range(symbol)
            for _ in range(num_calls)
        ]
        
        # 验证所有结果一致
        assert len(set(expiry_results)) == 1, (
            f"extract_expiry_from_symbol 返回不同结果: {set(expiry_results)}，"
            f"合约代码: {symbol}"
        )
        assert len(set(strike_results)) == 1, (
            f"group_by_strike_range 返回不同结果: {set(strike_results)}，"
            f"合约代码: {symbol}"
        )
