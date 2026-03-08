"""
config_loader.py - 配置加载器

支持:
1. TOML 配置文件 (策略配置)
2. 环境变量 (网关配置)
3. 配置验证
"""
import os
import sys
import copy
import importlib
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Python 3.11+ 内置 tomllib，之前版本使用 tomli
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


class ConfigLoader:
    """
    配置加载器
    
    - 策略配置: 从 YAML 文件加载
    - 网关配置: 从环境变量加载 (.env)
    """
    
    @staticmethod
    def load_toml(path: str) -> Dict[str, Any]:
        """加载 TOML 配置文件"""
        with open(path, "rb") as f:
            return tomllib.load(f)
    
    @staticmethod
    def load_yaml(path: str) -> Dict[str, Any]:
        """加载 YAML 配置文件（已弃用，保留用于向后兼容）"""
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    @staticmethod
    def import_from_string(path: str) -> Any:
        """从 ``module:attr`` 或 ``module.attr`` 字符串动态导入对象。"""
        raw = str(path or "").strip()
        if not raw:
            raise ValueError("导入路径不能为空")

        module_path = ""
        attr_name = ""
        if ":" in raw:
            module_path, attr_name = raw.split(":", 1)
        else:
            module_path, _, attr_name = raw.rpartition(".")

        if not module_path or not attr_name:
            raise ValueError(f"无效导入路径: {raw}")

        module = importlib.import_module(module_path)
        return getattr(module, attr_name)

    @staticmethod
    def _deep_merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """递归合并字典，优先使用 override。"""
        result = copy.deepcopy(base)
        for key, value in (override or {}).items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = ConfigLoader._deep_merge_dict(result[key], value)
            else:
                result[key] = copy.deepcopy(value)
        return result

    @staticmethod
    def load_strategy_config(
        path: str,
        override_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """加载并合并 TOML 策略配置。"""
        config = ConfigLoader.load_toml(path)
        if override_path and Path(override_path).exists():
            override_config = ConfigLoader.load_toml(override_path)
            return ConfigLoader.merge_strategy_config(config, override_config)
        return config

    @staticmethod
    def extract_shared_strategy_settings(config: Dict[str, Any]) -> Dict[str, Any]:
        """提取需要注入到 strategy setting 的共享配置。"""
        result: Dict[str, Any] = {}
        for key in ("strategy_contracts", "service_activation", "observability"):
            value = config.get(key)
            if isinstance(value, dict):
                result[key] = copy.deepcopy(value)
        return result

    @staticmethod
    def resolve_service_activation(config: Dict[str, Any]) -> Dict[str, bool]:
        """解析领域服务按需装配开关。"""
        defaults = {
            "future_selection": True,
            "option_chain": True,
            "option_selector": True,
            "position_sizing": False,
            "pricing_engine": False,
            "greeks_calculator": False,
            "portfolio_risk": False,
            "smart_order_executor": False,
            "advanced_order_scheduler": False,
            "delta_hedging": False,
            "vega_hedging": False,
            "monitoring": True,
            "decision_observability": True,
        }
        raw = config.get("service_activation")
        if not isinstance(raw, dict):
            return defaults

        resolved = dict(defaults)
        for key, value in raw.items():
            resolved[str(key)] = bool(value)
        return resolved
    
    @staticmethod
    def load_gateway_config() -> Dict[str, Any]:
        """
        从环境变量加载网关配置
        
        需要:
            包含 CTP 配置的 .env 文件
        """
        # 显式定位项目根目录下的 .env
        # 从 src/main/config/config_loader.py 到项目根目录需要 4 级 parent
        env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=env_path)
        else:
            # 回退到默认搜索
            load_dotenv()
        
        def get_env_any(*keys, default=""):
            for key in keys:
                val = os.getenv(key)
                if val:
                    return val
            return default

        # 加载并标准化地址
        td_addr = get_env_any("CTP_TD_ADDRESS", "CTP_TD_SERVER", "CTP_TD_URI")
        md_addr = get_env_any("CTP_MD_ADDRESS", "CTP_MD_SERVER", "CTP_MD_URI")
        
        if td_addr and not td_addr.startswith("tcp://"):
            td_addr = "tcp://" + td_addr
        if md_addr and not md_addr.startswith("tcp://"):
            md_addr = "tcp://" + md_addr

        config = {
            "ctp": {
                "用户名": get_env_any("CTP_USERID", "CTP_USERNAME"),
                "密码": get_env_any("CTP_PASSWORD"),
                "经纪商代码": get_env_any("CTP_BROKERID", "CTP_BROKER_ID"),
                "交易服务器": td_addr,
                "行情服务器": md_addr,
                "产品名称": get_env_any("CTP_PRODUCT_NAME", "CTP_APP_ID", "CTP_PRODUCT_INFO", default="simnow_client_test"),
                "授权编码": get_env_any("CTP_AUTH_CODE", default="0000000000000000"),
                "柜台环境": get_env_any("CTP_ENV", default="实盘")
            }
        }
        
        # 立即验证关键字段
        if not config["ctp"]["交易服务器"]:
            raise ValueError(f"CTP_TD_ADDRESS (or CTP_TD_SERVER) 未配置或为空! (.env path: {env_path})")
        if not config["ctp"]["行情服务器"]:
            # 如果行情服务器为空，尝试使用交易服务器（有些环境可能是同一个，或者用户忘了配）
            # 但通常不建议这样做，这里还是报错提示用户
            raise ValueError(f"CTP_MD_ADDRESS (or CTP_MD_SERVER) 未配置或为空! (.env path: {env_path})")
            
        return config
    
    @staticmethod
    def validate_gateway_config(config: Dict[str, Any]) -> bool:
        """
        验证网关配置
        
        Args:
            config: 网关配置字典
            
        Returns:
            True 如果配置有效
        """
        required_fields = [
            "用户名", "密码", "经纪商代码",
            "交易服务器", "行情服务器"
        ]
        
        for gateway_name, gateway_config in config.items():
            for field in required_fields:
                if field not in gateway_config:
                    raise ValueError(
                        f"网关 {gateway_name} 缺少必填字段: {field}"
                    )
        
        return True

    @staticmethod
    def validate_strategy_config(config: Dict[str, Any]) -> bool:
        """
        验证策略配置
        
        Args:
            config: 策略配置字典
            
        Returns:
            True 如果配置有效
        """
        strategies = config.get("strategies", [])
        
        if not strategies:
            raise ValueError("策略配置为空")
        
        for strategy in strategies:
            if "class_name" not in strategy:
                raise ValueError("策略缺少 class_name")
        return True

    @staticmethod
    def _normalize_timeframe_name(raw: Any) -> str:
        """Normalize timeframe name from override config."""
        if raw is None:
            return ""

        name = str(raw).strip()
        if not name:
            return ""

        return name.replace(" ", "_")

    @staticmethod
    def _append_timeframe_suffix(strategy_name: str, timeframe_name: str) -> str:
        """Append timeframe suffix only when needed."""
        base_name = str(strategy_name or "default_strategy").strip() or "default_strategy"
        if not timeframe_name:
            return base_name

        suffix = f"_{timeframe_name}"
        if base_name.endswith(suffix):
            return base_name
        return f"{base_name}{suffix}"

    @staticmethod
    def extract_timeframe_name(override_config: Dict[str, Any], fallback: str = "") -> str:
        """Extract timeframe name from override config."""
        if not isinstance(override_config, dict):
            return fallback

        timeframe_cfg = override_config.get("timeframe")
        if isinstance(timeframe_cfg, dict):
            timeframe_name = ConfigLoader._normalize_timeframe_name(timeframe_cfg.get("name"))
            if timeframe_name:
                return timeframe_name

        return fallback

    @staticmethod
    def merge_strategy_config(base_config: Dict[str, Any], override_config: Dict[str, Any]) -> Dict[str, Any]:
        """Merge override config into strategy config.

        New format (recommended):
            [timeframe]
            name = "15m"
            bar_window = 15
            bar_interval = "MINUTE"

        Legacy format is still accepted:
            [[strategies]]
            strategy_name = "..."
            [strategies.setting]
            ...
        """
        if not isinstance(base_config, dict):
            return {}

        if not override_config:
            return base_config

        if not isinstance(override_config, dict):
            return base_config

        merged: Dict[str, Any] = ConfigLoader._deep_merge_dict(
            {
                **base_config,
                "strategies": [
                    {
                        **(strategy or {}),
                        "setting": dict((strategy or {}).get("setting") or {}),
                    }
                    for strategy in (base_config.get("strategies") or [])
                    if isinstance(strategy, dict)
                ],
            },
            {
                key: value
                for key, value in override_config.items()
                if key not in {"strategies", "timeframe"}
            },
        )

        timeframe_cfg = override_config.get("timeframe")
        if isinstance(timeframe_cfg, dict):
            timeframe_name = ConfigLoader._normalize_timeframe_name(
                timeframe_cfg.get("name")
            )
            bar_window = timeframe_cfg.get("bar_window")
            bar_interval = timeframe_cfg.get("bar_interval")

            strategies = merged.get("strategies") or []
            for strategy in strategies:
                if not isinstance(strategy, dict):
                    continue

                setting = strategy.setdefault("setting", {})
                if not isinstance(setting, dict):
                    setting = {}
                    strategy["setting"] = setting

                if bar_window is not None:
                    setting["bar_window"] = bar_window
                if bar_interval is not None:
                    setting["bar_interval"] = (
                        str(bar_interval).strip().upper() if isinstance(bar_interval, str) else bar_interval
                    )

                if timeframe_name:
                    strategy["strategy_name"] = ConfigLoader._append_timeframe_suffix(
                        strategy.get("strategy_name", "default_strategy"),
                        timeframe_name,
                    )
                    setting["timeframe"] = timeframe_name

            return merged

        # Legacy override format: merge first strategy.
        override_strategies = override_config.get("strategies") or []
        if not override_strategies:
            return merged

        if "strategies" not in merged or not merged.get("strategies"):
            merged["strategies"] = [
                {
                    **(strategy or {}),
                    "setting": dict((strategy or {}).get("setting") or {}),
                }
                for strategy in override_strategies
                if isinstance(strategy, dict)
            ]
            return merged

        base_strategy = merged["strategies"][0]
        override_strategy = next(
            (item for item in override_strategies if isinstance(item, dict)),
            None,
        )
        if not override_strategy:
            return merged

        if "strategy_name" in override_strategy:
            base_strategy["strategy_name"] = override_strategy["strategy_name"]

        override_setting = override_strategy.get("setting")
        if isinstance(override_setting, dict):
            base_setting = base_strategy.setdefault("setting", {})
            if not isinstance(base_setting, dict):
                base_setting = {}
                base_strategy["setting"] = base_setting
            base_setting.update(override_setting)

        return merged

    @staticmethod
    def load_target_products(path: str = "config/general/trading_target.toml") -> list[str]:
        """
        加载交易目标品种列表
        
        Args:
            path: 配置文件路径
            
        Returns:
            品种代码列表 (e.g. ['rb', 'm'])
        """
        if not os.path.isabs(path):
            # 从 src/main/config/config_loader.py 到项目根目录需要 4 级 parent
            project_root = Path(__file__).resolve().parent.parent.parent.parent
            path = str(project_root / path)
            
        if not os.path.exists(path):
            return []
        
        # 尝试 TOML 格式
        if path.endswith('.toml'):
            with open(path, "rb") as f:
                data = tomllib.load(f)
                return data.get("targets", [])
        
        # 向后兼容：尝试 YAML 格式
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    @staticmethod
    def load_hedging_config(config: dict) -> dict:
        """
        从策略配置中加载对冲配置

        Args:
            config: 完整策略配置字典

        Returns:
            包含 delta_hedging 和 gamma_scalping 配置的字典，缺失字段使用默认值
        """
        hedging = config.get("hedging", {})

        delta_defaults = {
            "target_delta": 0.0,
            "hedging_band": 0.5,
            "hedge_instrument_vt_symbol": "",
            "hedge_instrument_delta": 1.0,
            "hedge_instrument_multiplier": 10.0,
        }
        gamma_defaults = {
            "rebalance_threshold": 0.3,
            "hedge_instrument_vt_symbol": "",
            "hedge_instrument_delta": 1.0,
            "hedge_instrument_multiplier": 10.0,
        }

        delta_cfg = hedging.get("delta_hedging", {})
        gamma_cfg = hedging.get("gamma_scalping", {})

        return {
            "delta_hedging": {k: delta_cfg.get(k, v) for k, v in delta_defaults.items()},
            "gamma_scalping": {k: gamma_cfg.get(k, v) for k, v in gamma_defaults.items()},
        }

    @staticmethod
    def load_advanced_orders_config(config: dict) -> dict:
        """
        从策略配置中加载高级订单配置

        Args:
            config: 完整策略配置字典

        Returns:
            高级订单配置字典，缺失字段使用默认值
        """
        defaults = {
            "default_iceberg_batch_size": 5,
            "default_twap_slices": 10,
            "default_time_window_seconds": 300,
        }
        ao_cfg = config.get("advanced_orders", {})
        return {k: ao_cfg.get(k, v) for k, v in defaults.items()}

    @staticmethod
    def load_combination_risk_config(config: dict) -> "CombinationRiskConfig":
        """
        从策略配置中加载组合策略风控配置

        Args:
            config: 完整策略配置字典

        Returns:
            CombinationRiskConfig 实例，缺失字段使用默认值
            默认值: delta_limit=2.0, gamma_limit=0.5, vega_limit=200.0
        """
        from src.strategy.domain.value_object.combination.combination import CombinationRiskConfig

        combination_risk = config.get("combination_risk", {})

        return CombinationRiskConfig(
            delta_limit=combination_risk.get("delta_limit", 2.0),
            gamma_limit=combination_risk.get("gamma_limit", 0.5),
            vega_limit=combination_risk.get("vega_limit", 200.0),
        )

@staticmethod
def load_combination_risk_config(config: dict) -> "CombinationRiskConfig":
    """
    从策略配置中加载组合策略风控配置

    Args:
        config: 完整策略配置字典

    Returns:
        CombinationRiskConfig 实例，缺失字段使用默认值
        默认值: delta_limit=2.0, gamma_limit=0.5, vega_limit=200.0
    """
    from src.strategy.domain.value_object.combination.combination import CombinationRiskConfig

    combination_risk = config.get("combination_risk", {})

    return CombinationRiskConfig(
        delta_limit=combination_risk.get("delta_limit", 2.0),
        gamma_limit=combination_risk.get("gamma_limit", 0.5),
        vega_limit=combination_risk.get("vega_limit", 200.0),
    )

