"""strategy_state 表的 Peewee PO。"""

from peewee import AutoField, CharField, DateTimeField, IntegerField, Model, TextField


class StrategyStatePO(Model):
    """策略状态持久化对象。"""

    id = AutoField(primary_key=True)
    strategy_name = CharField(max_length=128, index=True)
    snapshot_json = TextField()
    schema_version = IntegerField(default=1)
    saved_at = DateTimeField(index=True)

    class Meta:
        table_name = "strategy_state"
        indexes = ((("strategy_name", "saved_at"), False),)

