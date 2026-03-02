"""
ConcentrationMonitor - 集中度风险监控服务

监控持仓在品种、到期日、行权价三个维度的集中度风险，计算 HHI 指数。

职责变更说明:
- 合约解析职责已移至 ContractHelper (基础设施层)
- 本服务专注于纯业务逻辑：集中度计算、HHI 计算、风险识别
"""
import logging
from collections import defaultdict
from typing import Dict, List

from src.strategy.domain.entity.position import Position
from src.strategy.domain.value_object.risk.risk import (
    ConcentrationConfig,
    ConcentrationMetrics,
    ConcentrationWarning,
)
from src.strategy.infrastructure.parsing.contract_helper import ContractHelper

logger = logging.getLogger(__name__)


class ConcentrationMonitor:
    """
    集中度风险监控服务
    
    职责:
    1. 计算品种、到期日、行权价三个维度的集中度
    2. 计算 HHI（赫芬达尔指数）作为集中度综合指标
    3. 检测集中度超限并生成警告
    
    注意:
    - 合约解析使用 ContractHelper (infrastructure/parsing)
    - 到期日提取和行权价分组已移至基础设施层
    
    Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7
    """
    
    def __init__(self, config: ConcentrationConfig) -> None:
        """
        初始化集中度监控器
        
        Args:
            config: 集中度监控配置
        """
        self.config = config
        logger.info(
            f"ConcentrationMonitor initialized with config: "
            f"underlying_limit={config.underlying_concentration_limit}, "
            f"expiry_limit={config.expiry_concentration_limit}, "
            f"strike_limit={config.strike_concentration_limit}, "
            f"hhi_threshold={config.hhi_threshold}, "
            f"basis={config.concentration_basis}"
        )
    
    def calculate_concentration(
        self,
        positions: List[Position],
        prices: Dict[str, float]
    ) -> ConcentrationMetrics:
        """
        计算集中度指标
        
        Args:
            positions: 活跃持仓列表
            prices: 当前价格字典 {vt_symbol: price}
            
        Returns:
            ConcentrationMetrics（包含各维度集中度和 HHI）
            
        Requirements: 4.1, 4.2, 4.3, 4.6, 4.7
        """
        if not positions:
            logger.warning("Empty positions list, returning zero concentration metrics")
            return ConcentrationMetrics(
                underlying_concentration={},
                max_underlying_ratio=0.0,
                expiry_concentration={},
                max_expiry_ratio=0.0,
                strike_concentration={},
                max_strike_ratio=0.0,
                underlying_hhi=0.0,
                expiry_hhi=0.0,
                strike_hhi=0.0,
            )
        
        # 计算总价值
        total_value = self._calculate_total_value(positions, prices)
        
        if total_value <= 0:
            logger.warning("Total value is zero or negative, returning zero concentration metrics")
            return ConcentrationMetrics(
                underlying_concentration={},
                max_underlying_ratio=0.0,
                expiry_concentration={},
                max_expiry_ratio=0.0,
                strike_concentration={},
                max_strike_ratio=0.0,
                underlying_hhi=0.0,
                expiry_hhi=0.0,
                strike_hhi=0.0,
            )
        
        # 计算品种维度集中度
        underlying_concentration = self._calculate_dimension_concentration(
            positions, prices, total_value, dimension="underlying"
        )
        underlying_hhi = self._calculate_hhi(underlying_concentration)
        max_underlying_ratio = max(underlying_concentration.values()) if underlying_concentration else 0.0
        
        # 计算到期日维度集中度
        expiry_concentration = self._calculate_dimension_concentration(
            positions, prices, total_value, dimension="expiry"
        )
        expiry_hhi = self._calculate_hhi(expiry_concentration)
        max_expiry_ratio = max(expiry_concentration.values()) if expiry_concentration else 0.0
        
        # 计算行权价维度集中度
        strike_concentration = self._calculate_dimension_concentration(
            positions, prices, total_value, dimension="strike"
        )
        strike_hhi = self._calculate_hhi(strike_concentration)
        max_strike_ratio = max(strike_concentration.values()) if strike_concentration else 0.0
        
        logger.debug(
            f"Concentration calculated: underlying_hhi={underlying_hhi:.4f}, "
            f"expiry_hhi={expiry_hhi:.4f}, strike_hhi={strike_hhi:.4f}"
        )
        
        return ConcentrationMetrics(
            underlying_concentration=underlying_concentration,
            max_underlying_ratio=max_underlying_ratio,
            expiry_concentration=expiry_concentration,
            max_expiry_ratio=max_expiry_ratio,
            strike_concentration=strike_concentration,
            max_strike_ratio=max_strike_ratio,
            underlying_hhi=underlying_hhi,
            expiry_hhi=expiry_hhi,
            strike_hhi=strike_hhi,
        )
    
    def check_concentration_limits(
        self,
        metrics: ConcentrationMetrics
    ) -> List[ConcentrationWarning]:
        """
        检查集中度是否超限
        
        Args:
            metrics: 集中度指标
            
        Returns:
            集中度警告列表
            
        Requirements: 4.4, 4.5
        """
        warnings = []
        
        # 检查品种集中度
        if metrics.max_underlying_ratio > self.config.underlying_concentration_limit:
            # 找出超限的品种
            for underlying, ratio in metrics.underlying_concentration.items():
                if ratio > self.config.underlying_concentration_limit:
                    warnings.append(ConcentrationWarning(
                        dimension="underlying",
                        key=underlying,
                        concentration=ratio,
                        limit=self.config.underlying_concentration_limit,
                        message=f"品种 {underlying} 集中度 {ratio:.2%} 超过限额 {self.config.underlying_concentration_limit:.2%}"
                    ))
        
        # 检查到期日集中度
        if metrics.max_expiry_ratio > self.config.expiry_concentration_limit:
            for expiry, ratio in metrics.expiry_concentration.items():
                if ratio > self.config.expiry_concentration_limit:
                    warnings.append(ConcentrationWarning(
                        dimension="expiry",
                        key=expiry,
                        concentration=ratio,
                        limit=self.config.expiry_concentration_limit,
                        message=f"到期日 {expiry} 集中度 {ratio:.2%} 超过限额 {self.config.expiry_concentration_limit:.2%}"
                    ))
        
        # 检查行权价集中度
        if metrics.max_strike_ratio > self.config.strike_concentration_limit:
            for strike_range, ratio in metrics.strike_concentration.items():
                if ratio > self.config.strike_concentration_limit:
                    warnings.append(ConcentrationWarning(
                        dimension="strike",
                        key=strike_range,
                        concentration=ratio,
                        limit=self.config.strike_concentration_limit,
                        message=f"行权价区间 {strike_range} 集中度 {ratio:.2%} 超过限额 {self.config.strike_concentration_limit:.2%}"
                    ))
        
        # 检查 HHI
        if metrics.underlying_hhi > self.config.hhi_threshold:
            warnings.append(ConcentrationWarning(
                dimension="hhi",
                key="underlying",
                concentration=metrics.underlying_hhi,
                limit=self.config.hhi_threshold,
                message=f"品种 HHI {metrics.underlying_hhi:.4f} 超过阈值 {self.config.hhi_threshold:.4f}"
            ))
        
        if metrics.expiry_hhi > self.config.hhi_threshold:
            warnings.append(ConcentrationWarning(
                dimension="hhi",
                key="expiry",
                concentration=metrics.expiry_hhi,
                limit=self.config.hhi_threshold,
                message=f"到期日 HHI {metrics.expiry_hhi:.4f} 超过阈值 {self.config.hhi_threshold:.4f}"
            ))
        
        if metrics.strike_hhi > self.config.hhi_threshold:
            warnings.append(ConcentrationWarning(
                dimension="hhi",
                key="strike",
                concentration=metrics.strike_hhi,
                limit=self.config.hhi_threshold,
                message=f"行权价 HHI {metrics.strike_hhi:.4f} 超过阈值 {self.config.hhi_threshold:.4f}"
            ))
        
        if warnings:
            logger.warning(f"Concentration limits exceeded: {len(warnings)} warnings generated")
        
        return warnings
    
    def _calculate_total_value(
        self,
        positions: List[Position],
        prices: Dict[str, float]
    ) -> float:
        """
        计算持仓总价值
        
        Args:
            positions: 持仓列表
            prices: 价格字典
            
        Returns:
            总价值（基于配置的计算基准）
        """
        total = 0.0
        for pos in positions:
            if not pos.is_active:
                continue
            
            price = prices.get(pos.vt_symbol)
            if price is None:
                logger.warning(f"Price not found for {pos.vt_symbol}, skipping")
                continue
            
            # 简化实现：使用名义价值（notional value）
            # 名义价值 = 价格 × 手数
            # 注意：实际应用中可能需要考虑合约乘数
            value = abs(price * pos.volume)
            total += value
        
        return total
    
    def _calculate_dimension_concentration(
        self,
        positions: List[Position],
        prices: Dict[str, float],
        total_value: float,
        dimension: str
    ) -> Dict[str, float]:
        """
        计算指定维度的集中度
        
        Args:
            positions: 持仓列表
            prices: 价格字典
            total_value: 总价值
            dimension: 维度类型 ("underlying" | "expiry" | "strike")
            
        Returns:
            维度键 -> 占比的字典
        """
        dimension_values: Dict[str, float] = defaultdict(float)
        
        for pos in positions:
            if not pos.is_active:
                continue
            
            price = prices.get(pos.vt_symbol)
            if price is None:
                continue
            
            value = abs(price * pos.volume)
            
            # 根据维度提取键
            if dimension == "underlying":
                key = pos.underlying_vt_symbol
            elif dimension == "expiry":
                key = ContractHelper.extract_expiry_from_symbol(pos.vt_symbol)
            elif dimension == "strike":
                key = ContractHelper.group_by_strike_range(pos.vt_symbol)
            else:
                logger.warning(f"Unknown dimension: {dimension}")
                continue
            
            if key:
                dimension_values[key] += value
        
        # 计算占比
        concentration = {}
        for key, value in dimension_values.items():
            concentration[key] = value / total_value if total_value > 0 else 0.0
        
        return concentration
    
    def _calculate_hhi(self, concentration: Dict[str, float]) -> float:
        """
        计算 HHI（赫芬达尔指数）
        
        HHI = Σ(占比^2)
        
        Args:
            concentration: 维度键 -> 占比的字典
            
        Returns:
            HHI 值 [0, 1]
            
        Requirements: 4.6
        """
        if not concentration:
            return 0.0
        
        hhi = sum(ratio ** 2 for ratio in concentration.values())
        return hhi
    
    
