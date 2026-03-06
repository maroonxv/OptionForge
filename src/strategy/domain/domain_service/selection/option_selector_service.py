"""
OptionSelectorService - 期权选择领域服务

负责从全市场合约中筛选出符合策略要求的虚值期权合约。
"""
from datetime import datetime
import math
from typing import Optional, List, Callable, Any, Dict

import pandas as pd

from ...value_object.market.option_contract import OptionContract, OptionType
from ...value_object.combination import CombinationType
from ...value_object.selection.selection import CombinationSelectionResult, SelectionScore
from ...value_object.combination.combination_rules import VALIDATION_RULES, LegStructure
from ...value_object.pricing.greeks import GreeksResult
from ...value_object.selection.option_selector_config import OptionSelectorConfig


class OptionSelectorService:
    """
    期权选择服务
    
    职责:
    - 过滤不符合流动性要求的合约
    - 按虚值程度排序选择目标档位
    - 过滤到期日不合适的合约
    """
    
    def __init__(self, config: Optional[OptionSelectorConfig] = None):
        """
        初始化期权选择服务

        参数:
            config: 配置对象，未提供时使用默认配置
        """
        self.config = config or OptionSelectorConfig()
    
    def check_liquidity(
        self,
        tick: Any,
        contract: Any,
        min_volume: Optional[int] = None,
        min_bid_volume: Optional[int] = None,
        max_spread_ticks: Optional[int] = None,
        log_func: Optional[Callable] = None,
        required_volume: Optional[int] = None,
        side: str = "sell",
    ) -> bool:
        """
        检查开仓前流动性
        
        参数:
            tick: TickData
            contract: ContractData
            min_volume: 当日最小成交量 (默认使用 config)
            min_bid_volume: 最小买一量 (默认使用 config)
            max_spread_ticks: 最大买卖价差 (默认使用 config)
            log_func: 日志记录函数
            required_volume: 期望成交手数 (默认使用 min_bid_volume)
            side: 交易方向侧 ("sell" 或 "buy")
            
        返回:
            如果检查通过则返回 True
        """
        if not tick or not contract:
            return False

        min_volume = min_volume if min_volume is not None else self.config.liquidity_min_volume
        min_bid_volume = min_bid_volume if min_bid_volume is not None else self.config.liquidity_min_bid_volume
        max_spread_ticks = max_spread_ticks if max_spread_ticks is not None else self.config.liquidity_max_spread_ticks
        required_volume = max(int(required_volume if required_volume is not None else min_bid_volume), 1)

        side_norm = self._normalize_side(side)
        if side_norm is None:
            if log_func:
                log_func(f"[流动性] 过滤: 无效方向 side={side}")
            return False
            
        vt_symbol = getattr(tick, "vt_symbol", "")
        bid_price = float(getattr(tick, "bid_price_1", 0) or 0)
        ask_price = float(getattr(tick, "ask_price_1", 0) or 0)
        
        current_volume = float(getattr(tick, "volume", 0) or 0)

        # 1. 宏观活跃度：成交量
        if current_volume < min_volume:
            if log_func:
                log_func(f"[流动性] 过滤 {vt_symbol}: 活跃度低 (成交量 {current_volume} < {min_volume})")
            return False

        # 2. 盘口有效性
        if self.config.liquidity_require_valid_quotes:
            if (
                not self._is_finite_positive(bid_price)
                or not self._is_finite_positive(ask_price)
                or ask_price <= bid_price
            ):
                if log_func:
                    log_func(
                        f"[流动性] 过滤 {vt_symbol}: 无效盘口 "
                        f"(bid={bid_price}, ask={ask_price})"
                    )
                return False
        else:
            if not math.isfinite(bid_price) or not math.isfinite(ask_price) or ask_price < bid_price:
                if log_func:
                    log_func(
                        f"[流动性] 过滤 {vt_symbol}: 盘口异常 "
                        f"(bid={bid_price}, ask={ask_price})"
                    )
                return False

        # 3. 买卖价差过滤
        pricetick = getattr(contract, "pricetick", 0)
        if pricetick <= 0:
            if log_func: log_func(f"[流动性] 过滤 {vt_symbol}: 无效的最小变动价位 {pricetick}")
            return False
            
        spread = ask_price - bid_price
        if spread < 0:
            if log_func:
                log_func(
                    f"[流动性] 过滤 {vt_symbol}: 价差异常 "
                    f"(bid={bid_price}, ask={ask_price})"
                )
            return False
        spread_ticks = spread / pricetick
        
        if max_spread_ticks > 0 and spread_ticks >= max_spread_ticks:
            if log_func:
                log_func(
                    f"[流动性] 过滤 {vt_symbol}: 价差过大 "
                    f"买一 {bid_price} 卖一 {ask_price} "
                    f"({spread_ticks:.1f} 跳 >= {max_spread_ticks})"
                )
            return False

        max_relative_spread = self.config.liquidity_max_relative_spread
        if max_relative_spread > 0:
            mid_price = (bid_price + ask_price) / 2.0
            relative_spread = spread / mid_price if mid_price > 0 else float("inf")
            if relative_spread > max_relative_spread:
                if log_func:
                    log_func(
                        f"[流动性] 过滤 {vt_symbol}: 相对价差过大 "
                        f"({relative_spread:.4f} > {max_relative_spread:.4f})"
                    )
                return False

        max_staleness = self.config.liquidity_max_tick_staleness_seconds
        if max_staleness > 0:
            tick_dt = getattr(tick, "datetime", None)
            if not isinstance(tick_dt, datetime):
                if log_func:
                    log_func(f"[流动性] 过滤 {vt_symbol}: Tick 时间戳缺失或无效")
                return False
            now = datetime.now(tick_dt.tzinfo) if tick_dt.tzinfo else datetime.now()
            age_seconds = max(0.0, (now - tick_dt).total_seconds())
            if age_seconds > max_staleness:
                if log_func:
                    log_func(
                        f"[流动性] 过滤 {vt_symbol}: Tick 过期 "
                        f"({age_seconds:.1f}s > {max_staleness:.1f}s)"
                    )
                return False

        depth_levels = max(1, min(5, int(self.config.liquidity_depth_levels)))
        if side_norm == "sell":
            top_volume = float(getattr(tick, "bid_volume_1", 0) or 0)
            total_depth_volume = self._sum_depth_volume(tick, "bid", depth_levels)
            depth_desc = "买盘深度"
        else:
            top_volume = float(getattr(tick, "ask_volume_1", 0) or 0)
            total_depth_volume = self._sum_depth_volume(tick, "ask", depth_levels)
            depth_desc = "卖盘深度"

        # 保留向后兼容: 顶层盘口量也要满足最小阈值
        if top_volume < min_bid_volume:
            if log_func:
                log_func(
                    f"[流动性] 过滤 {vt_symbol}: 顶档深度不足 "
                    f"({top_volume} < {min_bid_volume})"
                )
            return False

        if total_depth_volume < required_volume:
            if log_func:
                log_func(
                    f"[流动性] 过滤 {vt_symbol}: {depth_desc}不足 "
                    f"({total_depth_volume:.1f} < {required_volume}, depth_levels={depth_levels})"
                )
            return False

        return True

    @staticmethod
    def _normalize_side(side: Optional[str]) -> Optional[str]:
        if side is None:
            return "sell"

        text = str(side).strip().lower()
        mapping = {
            "sell": "sell",
            "short": "sell",
            "bid": "sell",
            "buy": "buy",
            "long": "buy",
            "ask": "buy",
        }
        return mapping.get(text)

    @staticmethod
    def _sum_depth_volume(tick: Any, side_prefix: str, depth_levels: int) -> float:
        total = 0.0
        for level in range(1, depth_levels + 1):
            raw = getattr(tick, f"{side_prefix}_volume_{level}", 0)
            try:
                value = float(raw)
            except (TypeError, ValueError):
                value = 0.0

            if not math.isfinite(value) or value < 0:
                value = 0.0

            total += value
        return total

    @staticmethod
    def _is_finite_positive(value: float) -> bool:
        return math.isfinite(value) and value > 0

    def select_option(
        self,
        contracts: pd.DataFrame,
        option_type: str,  # "CALL" | "PUT" (case-insensitive)
        underlying_price: float,
        strike_level: Optional[int] = None,
        log_func: Optional[Callable] = None
    ) -> Optional[OptionContract]:
        """
        选择目标期权合约
        
        参数:
            contracts: 合约 DataFrame (需包含必要列)
            option_type: 期权类型，支持 "CALL" 或 "PUT" (大小写不敏感)
            underlying_price: 标的当前价格
            strike_level: 虚值档位 (可选，默认使用初始化值)
            log_func: 日志回调函数
            
        返回:
            选中的期权合约，如果没有符合条件的则返回 None
        """
        if contracts.empty:
            if log_func: log_func("[DEBUG-OPT] 筛选失败: 传入合约列表为空")
            return None
        
        # 归一化 option_type
        option_type = option_type.lower()
        if option_type not in ["call", "put"]:
             if log_func: log_func(f"[DEBUG-OPT] 错误: 无效的 option_type {option_type}")
             return None

        level = strike_level if strike_level is not None else self.config.strike_level
        df = contracts.copy()
        
        if log_func:
            log_func(f"[DEBUG-OPT] 标的价: {underlying_price} | 开始筛选 {option_type} 期权 (初始数量: {len(df)})")
            # 打印数据摘要
            log_func(f"[DEBUG-OPT] 传入列名: {list(df.columns)}")
            sample_cols = ["vt_symbol", "strike_price", "days_to_expiry", "bid_price", "option_type"]
            available_cols = [c for c in sample_cols if c in df.columns]
            if available_cols:
                log_func(f"[DEBUG-OPT] 数据摘要(前5行):\n{df[available_cols].head(5).to_string()}")
        
        # 1. 按期权类型筛选
        if "option_type" in df.columns:
            df = df[df["option_type"] == option_type]
        
        if df.empty:
            if log_func: log_func("[DEBUG-OPT] 筛选失败: 无该类型期权")
            return None
        
        # 2. 过滤流动性
        df = self._filter_liquidity(df, log_func)
        
        if df.empty:
            if log_func: log_func(f"[DEBUG-OPT] 筛选失败: 流动性过滤后为空 (最小买价: {self.config.min_bid_price}, 最小买量: {self.config.min_bid_volume})")
            return None
        
        # 3. 过滤到期日
        if log_func and "days_to_expiry" in df.columns:
            days = df["days_to_expiry"]
            if not days.empty:
                log_func(f"[DEBUG-OPT] 过滤前天数分布: min={days.min()}, max={days.max()}, mean={days.mean():.1f}")
            else:
                log_func("[DEBUG-OPT] 警告: days_to_expiry 列为空")

        df = self._filter_trading_days(df, log_func)
        
        if df.empty:
            if log_func: log_func(f"[DEBUG-OPT] 筛选失败: 到期日过滤后为空 (最小天数: {self.config.min_trading_days}, 最大天数: {self.config.max_trading_days})")
            return None
        
        # 4. 计算虚值程度并排序
        df = self._calculate_otm_ranking(df, option_type, underlying_price)
        
        if log_func and not df.empty:
            log_func(f"[DEBUG-OPT] 虚值计算后剩余: {len(df)}")
            cols = ["vt_symbol", "strike_price", "diff1"]
            available_cols = [c for c in cols if c in df.columns]
            log_func(f"[DEBUG-OPT] 虚值前5:\n{df[available_cols].head(5).to_string()}")

        if df.empty:
            if log_func: log_func(f"[DEBUG-OPT] 筛选失败: 无虚值期权 (标的价: {underlying_price})")
            return None
        
        if log_func:
            log_func(f"[DEBUG-OPT] 候选数量: {len(df)}")
            # 打印前5个虚值合约
            for i in range(min(5, len(df))):
                row = df.iloc[i]
                log_func(f"  {i+1}. {row.get('vt_symbol')} | 虚值度: {row.get('diff1'):.2%} | 买价: {row.get('bid_price')}")

        # 5. 选择虚值第 N 档
        target = self._select_by_level(df, option_type, level)
        
        if target is None:
            return None
        
        result = self._to_option_contract(target, option_type)
        if log_func:
            log_func(f"[DEBUG-OPT] 最终选中: {result.vt_symbol} (虚值第{level}档)")
            
        return result
    
    def _filter_liquidity(self, df: pd.DataFrame, log_func: Optional[Callable] = None) -> pd.DataFrame:
        """过滤流动性不足的合约"""
        result = df.copy()
        if result.empty:
            return result

        def _apply_filter(mask: pd.Series, message: str) -> None:
            nonlocal result
            start_len = len(result)
            result = result[mask]
            if log_func and len(result) < start_len:
                log_func(f"[DEBUG-OPT] {message}: {start_len} -> {len(result)}")

        if self.config.filter_require_valid_quotes and "bid_price" in result.columns:
            bid = pd.to_numeric(result["bid_price"], errors="coerce")
            valid_mask = bid > 0
            if "ask_price" in result.columns:
                ask = pd.to_numeric(result["ask_price"], errors="coerce")
                valid_mask = valid_mask & (ask > 0) & (ask > bid)
            _apply_filter(valid_mask, "盘口有效性过滤")

        if "bid_price" in result.columns:
            bid = pd.to_numeric(result["bid_price"], errors="coerce")
            _apply_filter(
                bid >= self.config.min_bid_price,
                f"买价过滤(min_bid_price={self.config.min_bid_price})"
            )

        if "bid_volume" in result.columns:
            bid_volume = pd.to_numeric(result["bid_volume"], errors="coerce")
            _apply_filter(
                bid_volume >= self.config.min_bid_volume,
                f"买量过滤(min_bid_volume={self.config.min_bid_volume})"
            )

        if self.config.filter_min_ask_volume > 0 and "ask_volume" in result.columns:
            ask_volume = pd.to_numeric(result["ask_volume"], errors="coerce")
            _apply_filter(
                ask_volume >= self.config.filter_min_ask_volume,
                f"卖量过滤(min_ask_volume={self.config.filter_min_ask_volume})"
            )

        if self.config.filter_min_total_volume > 0 and "volume" in result.columns:
            volume = pd.to_numeric(result["volume"], errors="coerce")
            _apply_filter(
                volume >= self.config.filter_min_total_volume,
                f"成交量过滤(min_total_volume={self.config.filter_min_total_volume})"
            )

        if self.config.filter_min_open_interest > 0 and "open_interest" in result.columns:
            open_interest = pd.to_numeric(result["open_interest"], errors="coerce")
            _apply_filter(
                open_interest >= self.config.filter_min_open_interest,
                f"持仓量过滤(min_open_interest={self.config.filter_min_open_interest})"
            )

        if (
            self.config.filter_max_relative_spread > 0
            and "bid_price" in result.columns
            and "ask_price" in result.columns
        ):
            bid = pd.to_numeric(result["bid_price"], errors="coerce")
            ask = pd.to_numeric(result["ask_price"], errors="coerce")
            spread = ask - bid
            mid = (ask + bid) / 2.0
            rel_spread = spread / mid
            _apply_filter(
                (mid > 0)
                & (spread >= 0)
                & rel_spread.notna()
                & (rel_spread <= self.config.filter_max_relative_spread),
                f"相对价差过滤(max_relative_spread={self.config.filter_max_relative_spread})"
            )

        if (
            self.config.filter_max_spread_ticks > 0
            and "bid_price" in result.columns
            and "ask_price" in result.columns
            and "pricetick" in result.columns
        ):
            bid = pd.to_numeric(result["bid_price"], errors="coerce")
            ask = pd.to_numeric(result["ask_price"], errors="coerce")
            pricetick = pd.to_numeric(result["pricetick"], errors="coerce")
            spread_ticks = (ask - bid) / pricetick
            _apply_filter(
                (pricetick > 0)
                & spread_ticks.notna()
                & (spread_ticks >= 0)
                & (spread_ticks <= self.config.filter_max_spread_ticks),
                f"价差跳数过滤(max_spread_ticks={self.config.filter_max_spread_ticks})"
            )

        return result
    
    def _filter_trading_days(self, df: pd.DataFrame, log_func: Optional[Callable] = None) -> pd.DataFrame:
        """过滤到期日不合适的合约"""
        if "days_to_expiry" not in df.columns:
            return df
        
        result = df.copy()
        start_len = len(result)
        
        result = result[result["days_to_expiry"] >= self.config.min_trading_days]
        result = result[result["days_to_expiry"] <= self.config.max_trading_days]
        
        if log_func and len(result) < start_len:
            log_func(f"[DEBUG-OPT] 到期日过滤: {start_len} -> {len(result)} (days={self.config.min_trading_days}-{self.config.max_trading_days})")
        
        return result
    
    def _calculate_otm_ranking(
        self,
        df: pd.DataFrame,
        option_type: OptionType,
        underlying_price: float
    ) -> pd.DataFrame:
        """
        计算虚值程度排名
        
        虚值程度 (diff1):
        - Call: (strike_price - underlying_price) / underlying_price
        - Put: (underlying_price - strike_price) / underlying_price
        
        虚值期权的 diff1 > 0
        """
        if "strike_price" not in df.columns or underlying_price <= 0:
            return df
        
        result = df.copy()
        
        if option_type == "call":
            # Call 虚值: 行权价 > 标的价格
            result["diff1"] = (result["strike_price"] - underlying_price) / underlying_price
            result = result[result["diff1"] > 0]  # 只保留虚值
            result = result.sort_values("diff1", ascending=True)  # 虚值程度从小到大
        else:
            # Put 虚值: 行权价 < 标的价格
            result["diff1"] = (underlying_price - result["strike_price"]) / underlying_price
            result = result[result["diff1"] > 0]  # 只保留虚值
            result = result.sort_values("diff1", ascending=True)  # 虚值程度从小到大
        
        return result
    
    def _select_by_level(
        self,
        df: pd.DataFrame,
        option_type: OptionType,
        level: int
    ) -> Optional[pd.Series]:
        """
        选择虚值第 N 档
        
        参数:
            df: 已按虚值程度排序的 DataFrame
            option_type: 期权类型
            level: 虚值档位
            
        返回:
            选中的行，或 None
        """
        if len(df) < level:
            # 如果合约数量不足，选择最后一个 (最虚值)
            if len(df) > 0:
                return df.iloc[-1]
            return None
        
        # 选择第 level 档 (索引从 0 开始，所以是 level - 1)
        return df.iloc[level - 1]
    
    def _to_option_contract(
        self,
        row: pd.Series,
        option_type: OptionType
    ) -> OptionContract:
        """将 DataFrame 行转换为 OptionContract 对象"""
        return OptionContract(
            vt_symbol=str(row.get("vt_symbol", "")),
            underlying_symbol=str(row.get("underlying_symbol", "")),
            option_type=option_type,
            strike_price=float(row.get("strike_price", 0)),
            expiry_date=str(row.get("expiry_date", "")),
            diff1=float(row.get("diff1", 0)),
            bid_price=float(row.get("bid_price", 0)),
            bid_volume=int(row.get("bid_volume", 0)),
            ask_price=float(row.get("ask_price", 0)),
            ask_volume=int(row.get("ask_volume", 0)),
            days_to_expiry=int(row.get("days_to_expiry", 0))
        )
    
    def get_all_otm_options(
        self,
        contracts: pd.DataFrame,
        option_type: str,  # "CALL" | "PUT" (case-insensitive)
        underlying_price: float
    ) -> List[OptionContract]:
        """
        获取所有虚值期权列表 (按虚值程度排序)
        
        参数:
            contracts: 合约 DataFrame
            option_type: 期权类型，支持 "CALL" 或 "PUT" (大小写不敏感)
            underlying_price: 标的当前价格
            
        返回:
            虚值期权列表 (从最接近平值到最虚值)
        """
        if contracts.empty:
            return []
        
        # 归一化 option_type
        option_type = option_type.lower()
        if option_type not in ["call", "put"]:
             return []

        df = contracts.copy()
        
        # 按期权类型筛选
        if "option_type" in df.columns:
            df = df[df["option_type"] == option_type]
        
        # 过滤流动性
        df = self._filter_liquidity(df)
        
        # 过滤到期日
        df = self._filter_trading_days(df)
        
        # 计算虚值排名
        df = self._calculate_otm_ranking(df, option_type, underlying_price)
        
        # 转换为对象列表
        return [self._to_option_contract(row, option_type) for _, row in df.iterrows()]

    def select_combination(
        self,
        contracts: pd.DataFrame,
        combination_type: CombinationType,
        underlying_price: float,
        strike_level: Optional[int] = None,
        spread_width: Optional[int] = None,
        option_type_for_spread: Optional[str] = None,
        log_func: Optional[Callable] = None
    ) -> Optional[CombinationSelectionResult]:
        """
        根据组合类型联合选择多个期权腿。

        参数:
            contracts: 合约 DataFrame
            combination_type: 组合策略类型
            underlying_price: 标的当前价格
            strike_level: 虚值档位 (STRANGLE 使用)
            spread_width: 行权价间距档位数 (VERTICAL_SPREAD 使用)
            option_type_for_spread: 期权类型 (VERTICAL_SPREAD 使用, "call" 或 "put")
            log_func: 日志回调函数

        返回:
            CombinationSelectionResult 或 None (underlying_price 无效时)
        """
        if underlying_price <= 0:
            if log_func:
                log_func(f"[COMBO] 错误: underlying_price={underlying_price} 无效")
            return None

        if contracts.empty:
            return CombinationSelectionResult(
                combination_type=combination_type,
                legs=[],
                success=False,
                failure_reason="合约列表为空"
            )

        dispatch = {
            CombinationType.STRADDLE: self._select_straddle,
            CombinationType.STRANGLE: self._select_strangle,
            CombinationType.VERTICAL_SPREAD: self._select_vertical_spread,
        }

        handler = dispatch.get(combination_type)
        if handler is None:
            return CombinationSelectionResult(
                combination_type=combination_type,
                legs=[],
                success=False,
                failure_reason=f"不支持的组合类型: {combination_type.value}"
            )

        result = handler(
            contracts=contracts,
            underlying_price=underlying_price,
            strike_level=strike_level,
            spread_width=spread_width,
            option_type_for_spread=option_type_for_spread,
            log_func=log_func,
        )

        # 成功时进行结构验证
        if result.success:
            validation_error = self._validate_combination(result)
            if validation_error is not None:
                return CombinationSelectionResult(
                    combination_type=combination_type,
                    legs=result.legs,
                    success=False,
                    failure_reason=f"结构验证失败: {validation_error}"
                )

        return result

    def select_by_delta(
        self,
        contracts: pd.DataFrame,
        option_type: str,
        underlying_price: float,
        target_delta: float,
        greeks_data: Dict[str, GreeksResult],
        delta_tolerance: Optional[float] = None,
        log_func: Optional[Callable] = None
    ) -> Optional[OptionContract]:
        """
        基于目标 Delta 选择最优期权。
        若无 Greeks 数据则回退到虚值档位选择。

        参数:
            contracts: 合约 DataFrame
            option_type: 期权类型 ("CALL" | "PUT", 大小写不敏感)
            underlying_price: 标的当前价格
            target_delta: 目标 Delta 值
            greeks_data: Greeks 数据字典 (key 为 vt_symbol)
            delta_tolerance: Delta 容差范围 (默认使用 config)
            log_func: 日志回调函数

        返回:
            选中的期权合约，如果没有符合条件的则返回 None
        """
        delta_tolerance = delta_tolerance if delta_tolerance is not None else self.config.delta_tolerance
        if contracts.empty:
            if log_func:
                log_func("[DELTA] 筛选失败: 传入合约列表为空")
            return None

        if underlying_price <= 0:
            if log_func:
                log_func(f"[DELTA] 错误: underlying_price={underlying_price} 无效")
            return None

        # 归一化 option_type
        option_type = option_type.lower()
        if option_type not in ("call", "put"):
            if log_func:
                log_func(f"[DELTA] 错误: 无效的 option_type {option_type}")
            return None

        df = contracts.copy()

        # 1. 按期权类型筛选
        if "option_type" in df.columns:
            df = df[df["option_type"] == option_type]

        if df.empty:
            if log_func:
                log_func("[DELTA] 筛选失败: 无该类型期权")
            return None

        # 2. 过滤流动性
        df = self._filter_liquidity(df, log_func)
        if df.empty:
            if log_func:
                log_func("[DELTA] 筛选失败: 流动性过滤后为空")
            return None

        # 3. 过滤到期日
        df = self._filter_trading_days(df, log_func)
        if df.empty:
            if log_func:
                log_func("[DELTA] 筛选失败: 到期日过滤后为空")
            return None

        # 4. 查找候选合约的 Greeks 数据
        candidates = []
        for _, row in df.iterrows():
            vt_symbol = str(row.get("vt_symbol", ""))
            greeks = greeks_data.get(vt_symbol)
            if greeks is not None and greeks.success:
                candidates.append((row, greeks.delta))

        # 5. 无 Greeks 数据时回退到虚值档位选择
        if not candidates:
            if log_func:
                log_func("[DELTA] 无可用 Greeks 数据，回退到虚值档位选择")
            return self.select_option(
                contracts, option_type, underlying_price, log_func=log_func
            )

        # 6. 按 delta_tolerance 范围过滤
        filtered = [
            (row, delta)
            for row, delta in candidates
            if abs(delta - target_delta) <= delta_tolerance
        ]

        if not filtered:
            if log_func:
                log_func(
                    f"[DELTA] 无候选合约在 Delta 容差范围内 "
                    f"(target={target_delta}, tolerance={delta_tolerance})"
                )
            return None

        # 7. 选择 Delta 最接近目标值的合约
        best_row, best_delta = min(filtered, key=lambda x: abs(x[1] - target_delta))

        result = self._to_option_contract(best_row, option_type)
        if log_func:
            log_func(
                f"[DELTA] 选中: {result.vt_symbol} "
                f"(delta={best_delta:.4f}, target={target_delta}, diff={abs(best_delta - target_delta):.4f})"
            )

        return result


    def _validate_combination(self, result: CombinationSelectionResult) -> Optional[str]:
        """对选择结果调用 VALIDATION_RULES 验证结构合规"""
        validator = VALIDATION_RULES.get(result.combination_type)
        if validator is None:
            return None
        leg_structures = [
            LegStructure(
                option_type=leg.option_type,
                strike_price=leg.strike_price,
                expiry_date=leg.expiry_date,
            )
            for leg in result.legs
        ]
        return validator(leg_structures)

    def _select_straddle(
        self,
        contracts: pd.DataFrame,
        underlying_price: float,
        log_func: Optional[Callable] = None,
        **kwargs,
    ) -> CombinationSelectionResult:
        """
        STRADDLE: 选择同一到期日、同一行权价的一个 Call 和一个 Put，
        行权价最接近标的当前价格。
        """
        combo_type = CombinationType.STRADDLE
        df = contracts.copy()

        # 过滤流动性和到期日
        df = self._filter_liquidity(df, log_func)
        df = self._filter_trading_days(df, log_func)

        if df.empty:
            return CombinationSelectionResult(
                combination_type=combo_type, legs=[], success=False,
                failure_reason="流动性或到期日过滤后无可用合约"
            )

        for expiry_group in self._sorted_expiry_groups(df):
            # 分离 Call 和 Put
            calls = expiry_group[expiry_group["option_type"] == "call"] if "option_type" in expiry_group.columns else pd.DataFrame()
            puts = expiry_group[expiry_group["option_type"] == "put"] if "option_type" in expiry_group.columns else pd.DataFrame()

            if calls.empty or puts.empty:
                continue

            call_strikes = set(calls["strike_price"].unique())
            put_strikes = set(puts["strike_price"].unique())
            common_strikes = call_strikes & put_strikes
            if not common_strikes:
                continue

            # 选择最接近标的价格的行权价
            atm_strike = min(common_strikes, key=lambda s: abs(s - underlying_price))
            call_rows = calls[calls["strike_price"] == atm_strike]
            put_rows = puts[puts["strike_price"] == atm_strike]
            if call_rows.empty or put_rows.empty:
                continue

            if "bid_volume" in call_rows.columns:
                call_rows = call_rows.sort_values("bid_volume", ascending=False)
            if "bid_volume" in put_rows.columns:
                put_rows = put_rows.sort_values("bid_volume", ascending=False)

            call_row = call_rows.iloc[0]
            put_row = put_rows.iloc[0]

            call_leg = self._to_option_contract(call_row, "call")
            put_leg = self._to_option_contract(put_row, "put")

            if log_func:
                log_func(
                    f"[COMBO] STRADDLE 选中: expiry={call_leg.expiry_date}, "
                    f"行权价={atm_strike}, Call={call_leg.vt_symbol}, Put={put_leg.vt_symbol}"
                )

            return CombinationSelectionResult(
                combination_type=combo_type,
                legs=[call_leg, put_leg],
                success=True,
            )

        return CombinationSelectionResult(
            combination_type=combo_type, legs=[], success=False,
            failure_reason="流动性不足: 无同到期日的可用 Call/Put 组合"
        )

    def _select_strangle(
        self,
        contracts: pd.DataFrame,
        underlying_price: float,
        strike_level: Optional[int] = None,
        log_func: Optional[Callable] = None,
        **kwargs,
    ) -> CombinationSelectionResult:
        """
        STRANGLE: 选择同一到期日的一个虚值 Call 和一个虚值 Put，
        虚值档位由 strike_level 决定。
        """
        combo_type = CombinationType.STRANGLE
        level = strike_level if strike_level is not None else self.config.strike_level
        df = contracts.copy()

        # 过滤流动性和到期日
        df = self._filter_liquidity(df, log_func)
        df = self._filter_trading_days(df, log_func)

        if df.empty:
            return CombinationSelectionResult(
                combination_type=combo_type, legs=[], success=False,
                failure_reason="流动性或到期日过滤后无可用合约"
            )

        for expiry_group in self._sorted_expiry_groups(df):
            # 分别计算 Call 和 Put 的虚值排名
            calls = expiry_group[expiry_group["option_type"] == "call"].copy() if "option_type" in expiry_group.columns else pd.DataFrame()
            puts = expiry_group[expiry_group["option_type"] == "put"].copy() if "option_type" in expiry_group.columns else pd.DataFrame()

            if calls.empty or puts.empty:
                continue

            calls_ranked = self._calculate_otm_ranking(calls, "call", underlying_price)
            puts_ranked = self._calculate_otm_ranking(puts, "put", underlying_price)
            if calls_ranked.empty or puts_ranked.empty:
                continue

            call_target = self._select_by_level(calls_ranked, "call", level)
            put_target = self._select_by_level(puts_ranked, "put", level)
            if call_target is None or put_target is None:
                continue

            call_leg = self._to_option_contract(call_target, "call")
            put_leg = self._to_option_contract(put_target, "put")

            if log_func:
                log_func(
                    f"[COMBO] STRANGLE 选中: expiry={call_leg.expiry_date}, 档位={level}, "
                    f"Call={call_leg.vt_symbol}(K={call_leg.strike_price}), "
                    f"Put={put_leg.vt_symbol}(K={put_leg.strike_price})"
                )

            return CombinationSelectionResult(
                combination_type=combo_type,
                legs=[call_leg, put_leg],
                success=True,
            )

        return CombinationSelectionResult(
            combination_type=combo_type, legs=[], success=False,
            failure_reason="流动性不足: 无同到期日的可用虚值 Call/Put 组合"
        )

    def _select_vertical_spread(
        self,
        contracts: pd.DataFrame,
        underlying_price: float,
        spread_width: Optional[int] = None,
        option_type_for_spread: Optional[str] = None,
        log_func: Optional[Callable] = None,
        **kwargs,
    ) -> CombinationSelectionResult:
        """
        VERTICAL_SPREAD: 选择同一到期日、同一期权类型、不同行权价的两个期权，
        行权价间距由 spread_width 档位数决定。
        """
        combo_type = CombinationType.VERTICAL_SPREAD
        width = spread_width if spread_width is not None else self.config.default_spread_width
        opt_type = (option_type_for_spread or "call").lower()

        if opt_type not in ("call", "put"):
            return CombinationSelectionResult(
                combination_type=combo_type, legs=[], success=False,
                failure_reason=f"无效的期权类型: {opt_type}"
            )

        df = contracts.copy()

        # 过滤流动性和到期日
        df = self._filter_liquidity(df, log_func)
        df = self._filter_trading_days(df, log_func)

        if df.empty:
            return CombinationSelectionResult(
                combination_type=combo_type, legs=[], success=False,
                failure_reason="流动性或到期日过滤后无可用合约"
            )

        for expiry_group in self._sorted_expiry_groups(df):
            local_df = expiry_group

            # 按期权类型筛选
            if "option_type" in local_df.columns:
                local_df = local_df[local_df["option_type"] == opt_type]

            if local_df.empty:
                continue

            # 计算虚值排名
            ranked = self._calculate_otm_ranking(local_df, opt_type, underlying_price)
            if ranked.empty:
                continue

            # 选择近腿 (第1档虚值) 和远腿 (第1+width档虚值)
            near_target = self._select_by_level(ranked, opt_type, 1)
            far_target = self._select_by_level(ranked, opt_type, 1 + width)
            if near_target is None or far_target is None:
                continue

            near_strike = float(near_target.get("strike_price", 0))
            far_strike = float(far_target.get("strike_price", 0))
            if near_strike == far_strike:
                continue

            near_leg = self._to_option_contract(near_target, opt_type)
            far_leg = self._to_option_contract(far_target, opt_type)

            if log_func:
                log_func(
                    f"[COMBO] VERTICAL_SPREAD 选中: expiry={near_leg.expiry_date}, 类型={opt_type}, "
                    f"近腿={near_leg.vt_symbol}(K={near_leg.strike_price}), "
                    f"远腿={far_leg.vt_symbol}(K={far_leg.strike_price})"
                )

            return CombinationSelectionResult(
                combination_type=combo_type,
                legs=[near_leg, far_leg],
                success=True,
            )

        return CombinationSelectionResult(
            combination_type=combo_type, legs=[], success=False,
            failure_reason=f"流动性不足: 无同到期日且可构造的 {opt_type} 垂直价差"
        )

    def _sorted_expiry_groups(self, df: pd.DataFrame) -> List[pd.DataFrame]:
        """
        按到期日分组并排序：
        - 优先选择 days_to_expiry 更接近配置区间中点的组
        - 再按 expiry_date 字符串排序，确保结果稳定
        """
        if "expiry_date" not in df.columns:
            return [df]

        midpoint = (self.config.min_trading_days + self.config.max_trading_days) / 2.0
        grouped: List[tuple[float, str, pd.DataFrame]] = []

        for expiry, group in df.groupby("expiry_date"):
            score = float("inf")
            if "days_to_expiry" in group.columns:
                days = pd.to_numeric(group["days_to_expiry"], errors="coerce").dropna()
                if not days.empty:
                    score = abs(float(days.median()) - midpoint)
            grouped.append((score, str(expiry), group.copy()))

        grouped.sort(key=lambda x: (x[0], x[1]))
        return [group for _, _, group in grouped]

    # ------------------------------------------------------------------
    # 评分排名
    # ------------------------------------------------------------------

    def score_candidates(
        self,
        contracts: pd.DataFrame,
        option_type: str,
        underlying_price: float,
        liquidity_weight: Optional[float] = None,
        otm_weight: Optional[float] = None,
        expiry_weight: Optional[float] = None,
        log_func: Optional[Callable] = None,
    ) -> List[SelectionScore]:
        """
        对候选合约进行多维度评分排名。

        参数:
            contracts: 合约 DataFrame
            option_type: 期权类型 ("CALL" | "PUT", 大小写不敏感)
            underlying_price: 标的当前价格
            liquidity_weight: 流动性得分权重 (默认使用 config)
            otm_weight: 虚值程度得分权重 (默认使用 config)
            expiry_weight: 到期日得分权重 (默认使用 config)
            log_func: 日志回调函数

        返回:
            List[SelectionScore] 按 total_score 降序排列
        """
        liquidity_weight = liquidity_weight if liquidity_weight is not None else self.config.score_liquidity_weight
        otm_weight = otm_weight if otm_weight is not None else self.config.score_otm_weight
        expiry_weight = expiry_weight if expiry_weight is not None else self.config.score_expiry_weight
        # 空合约列表 → 空结果
        if contracts.empty:
            if log_func:
                log_func("[SCORE] 合约列表为空，返回空评分列表")
            return []

        # underlying_price 无效
        if underlying_price <= 0:
            if log_func:
                log_func(f"[SCORE] 错误: underlying_price={underlying_price} 无效")
            return []

        # 归一化 option_type
        option_type = option_type.lower()
        if option_type not in ("call", "put"):
            if log_func:
                log_func(f"[SCORE] 错误: 无效的 option_type {option_type}")
            return []

        # 校验权重：任一为负或总和为零 → 使用默认值
        if (
            liquidity_weight < 0
            or otm_weight < 0
            or expiry_weight < 0
            or (liquidity_weight + otm_weight + expiry_weight) == 0
        ):
            if log_func:
                log_func(
                    f"[SCORE] 警告: 权重参数非法 "
                    f"(liq={liquidity_weight}, otm={otm_weight}, exp={expiry_weight})，"
                    "使用默认权重"
                )
            liquidity_weight = self.config.score_liquidity_weight
            otm_weight = self.config.score_otm_weight
            expiry_weight = self.config.score_expiry_weight

        df = contracts.copy()

        # 按期权类型筛选
        if "option_type" in df.columns:
            df = df[df["option_type"] == option_type]

        if df.empty:
            if log_func:
                log_func("[SCORE] 筛选后无该类型期权")
            return []

        # 先应用基础流动性和到期日过滤，再进行评分
        df = self._filter_liquidity(df, log_func)
        if df.empty:
            if log_func:
                log_func("[SCORE] 流动性过滤后无候选")
            return []

        df = self._filter_trading_days(df, log_func)
        if df.empty:
            if log_func:
                log_func("[SCORE] 到期日过滤后无候选")
            return []

        # 计算虚值排名 (需要 diff1 列)
        df = self._calculate_otm_ranking(df, option_type, underlying_price)

        if df.empty:
            if log_func:
                log_func("[SCORE] 无虚值期权可评分")
            return []

        # 为每个候选合约计算评分
        scores: List[SelectionScore] = []
        for _, row in df.iterrows():
            oc = self._to_option_contract(row, option_type)

            liq = self._calc_liquidity_score(row)
            otm = self._calc_otm_score(row)
            exp = self._calc_expiry_score(row)

            total = (
                liq * liquidity_weight
                + otm * otm_weight
                + exp * expiry_weight
            )

            scores.append(
                SelectionScore(
                    option_contract=oc,
                    liquidity_score=liq,
                    otm_score=otm,
                    expiry_score=exp,
                    total_score=total,
                )
            )

        # 按 total_score 降序排列
        scores.sort(key=lambda s: s.total_score, reverse=True)

        if log_func:
            log_func(f"[SCORE] 评分完成: {len(scores)} 个候选合约")
            for i, s in enumerate(scores[:5]):
                log_func(
                    f"  {i + 1}. {s.option_contract.vt_symbol} "
                    f"total={s.total_score:.4f} "
                    f"(liq={s.liquidity_score:.4f}, otm={s.otm_score:.4f}, exp={s.expiry_score:.4f})"
                )

        return scores

    # ------------------------------------------------------------------
    # 内部评分函数
    # ------------------------------------------------------------------

    def _calc_liquidity_score(self, row: pd.Series) -> float:
        """
        流动性得分 [0, 1]。

        基于买卖价差跳数和买一量：
        - spread_component = 1 / (1 + spread)   价差越小得分越高
        - volume_component = 1 - 1 / (1 + bid_volume)  买一量越大得分越高
        - liquidity_score = liq_spread_weight × spread_component + liq_volume_weight × volume_component
        """
        bid_price = float(row.get("bid_price", 0))
        ask_price = float(row.get("ask_price", 0))
        bid_volume = int(row.get("bid_volume", 0))

        # 计算价差 (用绝对价差)
        spread = max(0.0, ask_price - bid_price)
        # 归一化：使用 1/(1+spread) 使得价差越小得分越高
        spread_component = 1.0 / (1.0 + spread)

        # 买一量归一化：使用 1 - 1/(1+volume) 使得量越大得分越高
        volume_component = 1.0 - 1.0 / (1.0 + max(0, bid_volume))

        return self.config.liq_spread_weight * spread_component + self.config.liq_volume_weight * volume_component

    @staticmethod
    def _calc_otm_score(row: pd.Series) -> float:
        """
        虚值程度得分 [0, 1]。

        基于实际虚值档位与目标档位的偏差：
        - 使用 diff1 (虚值程度百分比) 作为偏差度量
        - otm_score = 1 / (1 + diff1)  偏差越小得分越高
        """
        diff1 = float(row.get("diff1", 0))
        # diff1 已经是虚值程度 (>0)，越小表示越接近平值
        return 1.0 / (1.0 + abs(diff1))

    def _calc_expiry_score(self, row: pd.Series) -> float:
        """
        到期日得分 [0, 1]。

        基于剩余交易日与目标范围中点的偏差：
        - midpoint = (min_trading_days + max_trading_days) / 2
        - deviation = |days_to_expiry - midpoint|
        - half_range = (max_trading_days - min_trading_days) / 2
        - expiry_score = max(0, 1 - deviation / half_range)
        """
        days = int(row.get("days_to_expiry", 0))
        midpoint = (self.config.min_trading_days + self.config.max_trading_days) / 2.0
        half_range = (self.config.max_trading_days - self.config.min_trading_days) / 2.0

        if half_range <= 0:
            # min == max 的退化情况
            return 1.0 if days == self.config.min_trading_days else 0.0

        deviation = abs(days - midpoint)
        return max(0.0, 1.0 - deviation / half_range)


