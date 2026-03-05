"""兼容导出：strategy_state 的 PO 已迁移至 persistence.model 子目录。"""

from src.strategy.infrastructure.persistence.model.strategy_state_po import (
    StrategyStatePO as StrategyStateModel,
)

__all__ = ["StrategyStateModel"]
