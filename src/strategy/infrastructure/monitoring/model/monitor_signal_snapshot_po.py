"""monitor_signal_snapshot 表的 Peewee PO。"""

from peewee import BigAutoField, CharField, DateTimeField, IntegerField, Model, TextField


class MonitorSignalSnapshotPO(Model):
    """监控快照持久化对象。"""

    id = BigAutoField(primary_key=True)
    variant = CharField(max_length=64, index=True)
    instance_id = CharField(max_length=64)
    updated_at = DateTimeField(index=True)
    bar_dt = DateTimeField(null=True, index=True)
    bar_interval = CharField(max_length=16, null=True)
    bar_window = IntegerField(null=True)
    payload_json = TextField()

    class Meta:
        table_name = "monitor_signal_snapshot"
        indexes = (
            (("variant", "instance_id"), True),
        )

