from sqlalchemy import Column, ForeignKey, Integer, Table
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship

from great.models.core import Base, Model, Media


class Track(Media):
    __tablename__ = "tracks"

    number = Column(Integer)

    disc_id = Column(Integer, ForeignKey("discs.id"), nullable=True)

    @hybrid_property
    def artist(self):
        if self.artists:
            return self.artists[0].name

    @artist.setter
    def artist(self, artist):
        if self.artists:
            raise ValueError("{0!r} already has artists set.".format(self))
        self.artists = [artist]

    @hybrid_property
    def album(self):
        if self.disc:
            return self.disc.album

    @album.setter
    def album(self, album):
        if self.disc is not None:
            raise ValueError("{0!r} already has its disc set.".format(self))
        if album.discs.count():
            raise ValueError("{0!r} already has discs set.".format(album))
        self.disc = Disc(number=1, album=album)


class Artist(Model):
    __tablename__ = "artists"

    tracks = relationship(
        "Track", backref="artists", secondary="tracks_artists", lazy="dynamic",
    )

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

    tracks = relationship(
        "Track",
        backref="composers",
        secondary="tracks_composers",
        lazy="dynamic",
    )


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
