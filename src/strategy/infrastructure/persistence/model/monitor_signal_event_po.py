"""monitor_signal_event 表的 Peewee PO。"""

from peewee import BigAutoField, CharField, DateTimeField, Model, TextField


class MonitorSignalEventPO(Model):
    """监控事件持久化对象。"""

    id = BigAutoField(primary_key=True)
    variant = CharField(max_length=64, index=True)
    instance_id = CharField(max_length=64)
    vt_symbol = CharField(max_length=64, index=True)
    bar_dt = DateTimeField(null=True, index=True)
    event_type = CharField(max_length=32, index=True)
    event_key = CharField(max_length=192, unique=True)
    created_at = DateTimeField(index=True)
    payload_json = TextField()

    class Meta:
        table_name = "monitor_signal_event"
        indexes = (
            (("variant", "created_at"), False),
            (("vt_symbol", "bar_dt"), False),
            (("event_type", "created_at"), False),
        )

