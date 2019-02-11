from sqlalchemy import (
    Boolean, Column, DateTime, Integer, Unicode, UnicodeText,
    CheckConstraint, MetaData, Table, func, delete, sql, select,
)
import attr


METADATA = MetaData()


class NotFound(Exception):
    pass


@attr.s
class ModelManager(object):

    db = attr.ib()
    table = attr.ib()
    _detail_columns = attr.ib()

    def __attrs_post_init__(self):
        self._basic_fields = [self.table.c.id, self.table.c.name]
        self._detail_query = select(
            self._basic_fields + list(self._detail_columns),
        )

    def query(self, query, db):
        return db.execute(query)

    def create(self, **kwargs):
        result = self.query(
            query=self.table.insert().values(**kwargs),
            db=self.db,
        )
        id, = result.inserted_primary_key
        return self.detail(id=id)

    def delete(self, id):
        self.query(delete(self.table).where(self.table.c.id == id), db=self.db)

    def list(self, fields=()):
        fields = self._basic_fields + [
            getattr(self.table.c, field) for field in fields
        ]
        return [dict(row) for row in self.query(select(fields), db=self.db)]

    def detail(self, id):
        query = self._detail_query.where(self.table.c.id == id)
        model = self.query(query, db=self.db).first()
        if model is None:
            raise NotFound(id)
        return dict(model)


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
        Column("name", Unicode(256), nullable=False),

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
