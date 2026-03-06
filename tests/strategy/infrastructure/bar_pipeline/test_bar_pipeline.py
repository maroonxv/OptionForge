"""
Tests for BarPipeline — 单元测试

Feature: bar-generator-decoupling

Validates: Requirements 2.2, 2.3, 2.4, 2.5
"""

import sys
from unittest.mock import MagicMock, patch, call

import pytest

# Mock vnpy modules before importing BarPipeline
for _mod_name in [
    "vnpy",
    "vnpy.event",
    "vnpy.trader",
    "vnpy.trader.setting",
    "vnpy.trader.engine",
    "vnpy.trader.constant",
    "vnpy.trader.object",
    "vnpy.trader.database",
    "vnpy_postgresql",
    "vnpy_portfoliostrategy",
    "vnpy_portfoliostrategy.utility",
]:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()

# Provide a mock Interval enum
mock_interval = MagicMock()
mock_interval.MINUTE = "MINUTE"
mock_interval.HOUR = "HOUR"
mock_interval.DAILY = "DAILY"
sys.modules["vnpy.trader.constant"].Interval = mock_interval


class TestBarPipelineConstruction:
    """构造函数参数验证 — Validates: Requirements 2.2"""

    def test_creation_stores_bar_callback(self):
        """BarPipeline 创建时正确接收 bar_callback 参数。"""
        mock_pbg_class = MagicMock()

        with patch(
            "src.strategy.infrastructure.bar_pipeline.bar_pipeline.PortfolioBarGenerator",
            mock_pbg_class,
        ):
            from src.strategy.infrastructure.bar_pipeline.bar_pipeline import BarPipeline

            callback = MagicMock()
            pipeline = BarPipeline(
                bar_callback=callback, window=15, interval=mock_interval.MINUTE
            )

            assert pipeline._bar_callback is callback

    def test_creation_creates_pbg_instance(self):
        """BarPipeline 创建时内部 _pbg 属性为 PortfolioBarGenerator 实例。"""
        mock_pbg_instance = MagicMock()
        mock_pbg_class = MagicMock(return_value=mock_pbg_instance)

        with patch(
            "src.strategy.infrastructure.bar_pipeline.bar_pipeline.PortfolioBarGenerator",
            mock_pbg_class,
        ):
            from src.strategy.infrastructure.bar_pipeline.bar_pipeline import BarPipeline

            callback = MagicMock()
            pipeline = BarPipeline(
                bar_callback=callback, window=15, interval=mock_interval.MINUTE
            )

            assert pipeline._pbg is mock_pbg_instance

    def test_creation_passes_correct_params_to_pbg(self):
        """BarPipeline 创建时将 window、interval 和回调正确传递给 PBG。"""
        mock_pbg_class = MagicMock()

        with patch(
            "src.strategy.infrastructure.bar_pipeline.bar_pipeline.PortfolioBarGenerator",
            mock_pbg_class,
        ):
            from src.strategy.infrastructure.bar_pipeline.bar_pipeline import BarPipeline

            callback = MagicMock()
            pipeline = BarPipeline(
                bar_callback=callback, window=30, interval=mock_interval.HOUR
            )

            mock_pbg_class.assert_called_once()
            call_kwargs = mock_pbg_class.call_args[1]
            assert call_kwargs["window"] == 30
            assert call_kwargs["interval"] == mock_interval.HOUR
            assert callable(call_kwargs["on_bars"])
            assert callable(call_kwargs["on_window_bars"])


class TestHandleTickDelegation:
    """handle_tick 委托 — Validates: Requirements 2.3"""

    def test_handle_tick_delegates_to_pbg(self):
        """调用 handle_tick(tick) 时，应委托给 _pbg.update_tick(tick)。"""
        mock_pbg_instance = MagicMock()
        mock_pbg_class = MagicMock(return_value=mock_pbg_instance)

        with patch(
            "src.strategy.infrastructure.bar_pipeline.bar_pipeline.PortfolioBarGenerator",
            mock_pbg_class,
        ):
            from src.strategy.infrastructure.bar_pipeline.bar_pipeline import BarPipeline

            callback = MagicMock()
            pipeline = BarPipeline(
                bar_callback=callback, window=15, interval=mock_interval.MINUTE
            )

            tick = MagicMock()
            pipeline.handle_tick(tick)

            mock_pbg_instance.update_tick.assert_called_once_with(tick)


class TestHandleBarsDelegation:
    """handle_bars 委托 — Validates: Requirements 2.4"""

    def test_handle_bars_delegates_to_pbg(self):
        """调用 handle_bars(bars) 时，应委托给 _pbg.update_bars(bars)。"""
        mock_pbg_instance = MagicMock()
        mock_pbg_class = MagicMock(return_value=mock_pbg_instance)

        with patch(
            "src.strategy.infrastructure.bar_pipeline.bar_pipeline.PortfolioBarGenerator",
            mock_pbg_class,
        ):
            from src.strategy.infrastructure.bar_pipeline.bar_pipeline import BarPipeline

            callback = MagicMock()
            pipeline = BarPipeline(
                bar_callback=callback, window=15, interval=mock_interval.MINUTE
            )

            bars = {"AAPL.SMART": MagicMock(), "GOOG.SMART": MagicMock()}
            pipeline.handle_bars(bars)

            mock_pbg_instance.update_bars.assert_called_once_with(bars)


class TestPBGCallbackChain:
    """PBG 回调链路 — Validates: Requirements 2.5"""

    def test_on_window_bars_triggers_bar_callback(self):
        """PBG 合成完成后触发 _on_window_bars，应调用 bar_callback。"""
        captured_on_window_bars = None

        def capture_pbg_constructor(**kwargs):
            nonlocal captured_on_window_bars
            captured_on_window_bars = kwargs["on_window_bars"]
            return MagicMock()

        with patch(
            "src.strategy.infrastructure.bar_pipeline.bar_pipeline.PortfolioBarGenerator",
            side_effect=capture_pbg_constructor,
        ):
            from src.strategy.infrastructure.bar_pipeline.bar_pipeline import BarPipeline

            callback = MagicMock()
            pipeline = BarPipeline(
                bar_callback=callback, window=15, interval=mock_interval.MINUTE
            )

            # Simulate PBG completing synthesis and calling on_window_bars
            assert captured_on_window_bars is not None
            synthesized_bars = {"AAPL.SMART": MagicMock(), "GOOG.SMART": MagicMock()}
            captured_on_window_bars(synthesized_bars)

            callback.assert_called_once_with(synthesized_bars)

    def test_on_window_bars_passes_exact_bars_data(self):
        """bar_callback 接收到的 bars 数据应与 PBG 传出的完全一致。"""
        captured_on_window_bars = None

        def capture_pbg_constructor(**kwargs):
            nonlocal captured_on_window_bars
            captured_on_window_bars = kwargs["on_window_bars"]
            return MagicMock()

        with patch(
            "src.strategy.infrastructure.bar_pipeline.bar_pipeline.PortfolioBarGenerator",
            side_effect=capture_pbg_constructor,
        ):
            from src.strategy.infrastructure.bar_pipeline.bar_pipeline import BarPipeline

            received_bars = []
            callback = lambda bars: received_bars.append(bars)
            pipeline = BarPipeline(
                bar_callback=callback, window=15, interval=mock_interval.MINUTE
            )

            original_bars = {"SYM1": MagicMock(), "SYM2": MagicMock()}
            captured_on_window_bars(original_bars)

            assert len(received_bars) == 1
            assert received_bars[0] is original_bars
