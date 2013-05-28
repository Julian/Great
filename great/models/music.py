from sqlalchemy import Column, ForeignKey, Integer, Table
from sqlalchemy.orm import relationship

from great.models.core import Base, Model, Media


class Track(Media):
    __tablename__ = "tracks"

    number = Column(Integer)

    artists = relationship(
        "Artist", secondary="tracks_artists", lazy="dynamic",
    )

    composers = relationship(
        "Composer", secondary="tracks_composers", lazy="dynamic",
    )

    disc_id = Column(Integer, ForeignKey("discs.id"), nullable=True)


class Artist(Model):
    __tablename__ = "artists"


class Album(Media):
    __tablename__ = "albums"

    discs = relationship("Disc", backref="album", lazy="dynamic")


class Disc(Media):
    __tablename__ = "discs"

    number = Column(Integer)

    tracks = relationship("Track", backref="disc")

    album_id = Column(Integer, ForeignKey("albums.id"))


class Composer(Model):
    __tablename__ = "composers"


Table(
    "tracks_artists",
    Base.metadata,
    Column("track_id", Integer, ForeignKey("tracks.id")),
    Column("artist_id", Integer, ForeignKey("artists.id")),
)

Table(
    "tracks_composers",
    Base.metadata,
    Column("track_id", Integer, ForeignKey("tracks.id")),
    Column("composer_id", Integer, ForeignKey("composers.id")),
)
