from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Integer, Unicode, UnicodeText,
    CheckConstraint, MetaData, Table, sql,
)


METADATA = MetaData()


def table(name, *args, **kwargs):
    with_dates = kwargs.pop("with_dates", False)
    if with_dates:
        now = datetime.now
        args += (
            Column("created_at", DateTime, default=now),
            Column("modified_at", DateTime, default=now, onupdate=now),
        )
    return Table(name, METADATA, *(table_columns() + args), **kwargs)


def table_columns():
    return (
        Column("id", Integer, primary_key=True),
        Column("name", Unicode(256)),

        Column(
            "rating",
            Integer,
            CheckConstraint("rating >= 0 AND rating <= 10"),
        ),

        Column(
            "pinned",
            Boolean,
            default=False,
            nullable=False,
            server_default=sql.expression.false(),
        ),

        Column("comments", UnicodeText),
    )


def media_table(name, *args, **kwargs):
    return Table(name, METADATA, *(media_table_columns() + args), **kwargs)


def media_table_columns():
    return table_columns() + (
        Column("play_count", Integer, default=0, nullable=False),
        Column("played_at", DateTime),

        Column("skip_count", Integer, default=0, nullable=False),
        Column("skipped_at", DateTime),
    )
