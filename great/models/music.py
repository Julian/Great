from sqlalchemy.ext.hybrid import hybrid_property

from great.models.core import Model, Media, db


class Track(Media):
    __tablename__ = "tracks"

    number = db.Column(db.Integer)

    disc_id = db.Column(db.Integer, db.ForeignKey("discs.id"), nullable=True)

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

    tracks = db.relationship(
        "Track", backref="artists", secondary="tracks_artists", lazy="dynamic",
    )


class Album(Media):
    __tablename__ = "albums"

    discs = db.relationship("Disc", backref="album", lazy="dynamic")


class Disc(Media):
    __tablename__ = "discs"

    number = db.Column(db.Integer)

    tracks = db.relationship("Track", backref="disc")

    album_id = db.Column(db.Integer, db.ForeignKey("albums.id"))


class Composer(Model):
    __tablename__ = "composers"

    tracks = db.relationship(
        "Track",
        backref="composers",
        secondary="tracks_composers",
        lazy="dynamic",
    )


db.Table(
    "tracks_artists",
    db.metadata,
    db.Column("track_id", db.Integer, db.ForeignKey("tracks.id")),
    db.Column("artist_id", db.Integer, db.ForeignKey("artists.id")),
)

db.Table(
    "tracks_composers",
    db.metadata,
    db.Column("track_id", db.Integer, db.ForeignKey("tracks.id")),
    db.Column("composer_id", db.Integer, db.ForeignKey("composers.id")),
)
