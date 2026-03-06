"""StrategyStateReader 单元测试

测试覆盖:
- 数据库连接失败返回空列表/None (Requirements 1.2, 1.3)
- malformed JSON 返回 None (Requirements 2.5)
- 正常快照的完整转换流程 (Requirements 2.4)
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from src.web.reader import StrategyStateReader


# ---------------------------------------------------------------------------
# 1. Connection failure tests (no mock needed - just use invalid config)
# ---------------------------------------------------------------------------

class TestConnectionFailure:
    """数据库连接失败时应返回安全默认值"""

    def test_list_strategies_with_invalid_config(self):
        """空/无效 db_config 时 list_available_strategies 返回空列表"""
        reader = StrategyStateReader({})
        assert reader.list_available_strategies() == []

    def test_get_strategy_data_with_invalid_config(self):
        """空/无效 db_config 时 get_strategy_data 返回 None"""
        reader = StrategyStateReader({})
        assert reader.get_strategy_data("test") is None

    def test_get_strategy_data_empty_name(self):
        """空策略名称时 get_strategy_data 返回 None"""
        reader = StrategyStateReader({"host": "localhost", "user": "root", "database": "test"})
        assert reader.get_strategy_data("") is None


# ---------------------------------------------------------------------------
# 2. Malformed JSON tests (mock postgres connection)
# ---------------------------------------------------------------------------

def _make_mock_conn(fetchone_return=None, fetchall_return=None):
    """构造 mock connection + cursor"""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchone.return_value = fetchone_return
    mock_cursor.fetchall.return_value = fetchall_return
    return mock_conn, mock_cursor


class TestMalformedJson:
    """malformed / 异常 JSON 场景"""

    def test_get_strategy_data_malformed_json(self):
        """snapshot_json 为无效 JSON 字符串时返回 None"""
        reader = StrategyStateReader({"host": "localhost", "user": "root", "database": "test"})
        mock_conn, _ = _make_mock_conn(
            fetchone_return={"snapshot_json": "{not valid json!!!"}
        )
        with patch.object(reader, "_connect", return_value=mock_conn):
            result = reader.get_strategy_data("test")
        assert result is None

    def test_get_strategy_data_none_snapshot(self):
        """snapshot_json 为 None 时返回 None"""
        reader = StrategyStateReader({"host": "localhost", "user": "root", "database": "test"})
        mock_conn, _ = _make_mock_conn(
            fetchone_return={"snapshot_json": None}
        )
        with patch.object(reader, "_connect", return_value=mock_conn):
            result = reader.get_strategy_data("test")
        assert result is None

    def test_get_strategy_data_non_dict_snapshot(self):
        """snapshot_json 解析后不是 dict（如 JSON array）时返回 None"""
        reader = StrategyStateReader({"host": "localhost", "user": "root", "database": "test"})
        mock_conn, _ = _make_mock_conn(
            fetchone_return={"snapshot_json": "[1, 2, 3]"}
        )
        with patch.object(reader, "_connect", return_value=mock_conn):
            result = reader.get_strategy_data("test")
        assert result is None


# ---------------------------------------------------------------------------
# 3. Normal flow tests (mock postgres connection)
# ---------------------------------------------------------------------------

class TestNormalFlow:
    """正常数据流转换"""

    def test_get_strategy_data_normal_snapshot(self):
        """正常 snapshot_json 应完整转换为前端格式"""
        snapshot = {
            "current_dt": {"__datetime__": "2025-01-15T14:30:00+08:00"},
            "target_aggregate": {
                "instruments": {
                    "rb2501.SHFE": {
                        "bars": {
                            "__dataframe__": True,
                            "records": [
                                {
                                    "datetime": "2025-01-15 14:29:00",
                                    "open": 3500.0,
                                    "close": 3505.0,
                                    "low": 3498.0,
                                    "high": 3510.0,
                                    "volume": 1200,
                                }
                            ],
                        },
                        "indicators": {"hv_20": 0.25},
                    }
                }
            },
            "position_aggregate": {
                "positions": {
                    "rb2501.SHFE.LONG": {
                        "vt_symbol": "rb2501.SHFE",
                        "direction": {"__enum__": "Direction.LONG"},
                        "volume": 1,
                        "open_price": 3500.0,
                        "pnl": 100.0,
                    }
                },
                "pending_orders": {
                    "order_001": {
                        "vt_orderid": "CTP.001",
                        "vt_symbol": "rb2501.SHFE",
                        "direction": {"__enum__": "Direction.LONG"},
                        "offset": {"__enum__": "Offset.OPEN"},
                        "volume": 1,
                        "price": 3500.0,
                        "status": {"__enum__": "Status.SUBMITTING"},
                    }
                },
            },
        }
        reader = StrategyStateReader({"host": "localhost", "user": "root", "database": "test"})
        mock_conn, _ = _make_mock_conn(
            fetchone_return={"snapshot_json": json.dumps(snapshot)}
        )
        with patch.object(reader, "_connect", return_value=mock_conn):
            result = reader.get_strategy_data("15m")

        assert result is not None
        assert result["timestamp"] == "2025-01-15 14:30:00"
        assert result["variant"] == "15m"
        assert "rb2501.SHFE" in result["instruments"]
        assert len(result["positions"]) == 1
        assert len(result["orders"]) == 1
        assert set(result.keys()) == {"timestamp", "variant", "instruments", "positions", "orders"}

    def test_list_strategies_normal(self):
        """正常查询策略列表"""
        from datetime import datetime

        reader = StrategyStateReader({"host": "localhost", "user": "root", "database": "test"})
        mock_conn, _ = _make_mock_conn(
            fetchall_return=[
                {"strategy_name": "15m", "last_update": datetime(2025, 1, 15, 14, 30, 0)},
                {"strategy_name": "30m", "last_update": datetime(2025, 1, 15, 14, 25, 0)},
            ]
        )
        with patch.object(reader, "_connect", return_value=mock_conn):
            result = reader.list_available_strategies()

        assert len(result) == 2
        assert result[0]["variant"] == "15m"
        assert result[0]["last_update"] == "2025-01-15 14:30:00"
        assert result[0]["file_size"] is None
        assert result[1]["variant"] == "30m"
        assert result[1]["last_update"] == "2025-01-15 14:25:00"

    def test_get_strategy_data_no_rows(self):
        """查询无结果时返回 None"""
        reader = StrategyStateReader({"host": "localhost", "user": "root", "database": "test"})
        mock_conn, _ = _make_mock_conn(fetchone_return=None)
        with patch.object(reader, "_connect", return_value=mock_conn):
            result = reader.get_strategy_data("nonexistent")
        assert result is None
