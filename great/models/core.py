import datetime

from sqlalchemy import Column, DateTime, Integer, Unicode, UnicodeText
from sqlalchemy.orm import sessionmaker, validates
from sqlalchemy.ext.declarative import AbstractConcreteBase, declarative_base


Base = declarative_base()
Session = sessionmaker()


class ModelMixin(object):
    id = Column(Integer, primary_key=True)

    name = Column(Unicode(256))
    comments = Column(UnicodeText)
    rating = Column(Integer)

    created_at = Column(DateTime, default=datetime.datetime.now)
    modified_at = Column(DateTime, onupdate=datetime.datetime.now)

    @validates("rating")
    def validate_rating(self, name, rating):
        if rating is not None and not 0 <= rating <= 10:
            raise ValueError("%r is not between 0 and 10." % (rating,))
        return rating

    @classmethod
    def get_or_create(cls, session, **kwargs):
        model = session.query(cls).filter_by(**kwargs).first()
        if model is not None:
            return model
        return cls(**kwargs)

    def __repr__(self):
        return "<{0.__class__.__name__} id={0.id} name={0.name!r}>".format(self)


class Model(ModelMixin, AbstractConcreteBase, Base):
    pass


class Media(ModelMixin, AbstractConcreteBase, Base):
    genre = Column(Unicode(64))
    year = Column(Integer)

    play_count = Column(Integer, default=0, nullable=False)
    played_at = Column(DateTime)

    skip_count = Column(Integer, default=0, nullable=False)
    skipped_at = Column(DateTime)
