from sqlalchemy import (
    Boolean, Column, DateTime, Integer, Unicode, UnicodeText,
    CheckConstraint, MetaData, Table, func, delete, sql, select,
)


METADATA = MetaData()


class ModelManager(object):
    def __init__(self, db, table, detail_columns):
        self.db = db
        self.table = table

        basic_entity_info = [table.c.id, table.c.name]
        self._detail_query = select(basic_entity_info + detail_columns)
        self._list_query = select(basic_entity_info)

    def create(self, **kwargs):
        result = self.db.execute(self.table.insert().values(**kwargs))
        id, = result.inserted_primary_key
        return self.detail(id=id)

    def delete(self, id):
        self.db.execute(delete(self.table).where(self.table.c.id == id))

    def list(self):
        return [dict(row) for row in self.db.execute(self._list_query)]

    def detail(self, id):
        query = self._detail_query.where(self.table.c.id == id)
        return dict(self.db.execute(query).fetchone())


def table(name, *args, **kwargs):
    with_dates = kwargs.pop("with_dates", False)
    if with_dates:
        now = func.now()
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
