import datetime

from flask.ext.sqlalchemy import SQLAlchemy
from sqlalchemy import sql
from sqlalchemy.orm import deferred, validates
from sqlalchemy.ext.declarative import AbstractConcreteBase, declared_attr


db = SQLAlchemy()


class ModelMixin(object):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.Unicode(256))
    rating = db.Column(db.Integer)

    created_at = db.Column(db.DateTime, default=datetime.datetime.now)
    modified_at = db.Column(db.DateTime, onupdate=datetime.datetime.now)

    @declared_attr
    def comments(cls):
        return deferred(db.Column(db.UnicodeText))

    @validates("rating")
    def validate_rating(self, name, rating):
        if rating is not None and not 0 <= rating <= 10:
            raise ValueError("%r is not between 0 and 10." % (rating,))
        return rating

    def __repr__(self):
        return "<{0.__class__.__name__} id={0.id} name={0.name!r}>".format(self)

    @classmethod
    def get_or_create(cls, session, **kwargs):
        model = session.query(cls).filter_by(**kwargs).first()
        if model is not None:
            return model
        return cls(**kwargs)


class Model(ModelMixin, AbstractConcreteBase, db.Model):
    pass


class Media(ModelMixin, AbstractConcreteBase, db.Model):
    genre = db.Column(db.Unicode(64))
    year = db.Column(db.Integer)

    pinned = db.Column(
        db.Boolean,
        default=False,
        nullable=False,
        server_default=sql.expression.false(),
    )

    play_count = db.Column(db.Integer, default=0, nullable=False)
    played_at = db.Column(db.DateTime)

    skip_count = db.Column(db.Integer, default=0, nullable=False)
    skipped_at = db.Column(db.DateTime)
