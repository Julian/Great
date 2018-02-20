from sqlalchemy import (
    Boolean, Column, Date, Enum, ForeignKey, Integer, Table, Unicode, sql,
)

from great.models.core import METADATA, table
from great.models._guid import GUID


def music_table(*args, **kwargs):
    args += (
        Column("mbid", GUID, nullable=True, unique=True),
        Column("spotify_uri", Unicode(), nullable=True, unique=True),
    )
    return table(*args, **kwargs)


artists = music_table(
    "artists",
    Column(
        "tracked",
        Boolean,
        default=False,
        nullable=False,
        server_default=sql.expression.false(),
    ),
    with_dates=True,
)
albums = music_table(
    "albums",
    Column("release_date", Date),
    Column(
        "type",
        Enum(u"lp", u"broadcast", u"ep", u"single"),
        default=u"lp",
        nullable=False,
    ),
    Column(
        "compilation",
        Boolean,
        default=False,
        nullable=False,
        server_default=sql.expression.false(),
    ),
    Column(
        "live",
        Boolean,
        default=False,
        nullable=False,
        server_default=sql.expression.false(),
    ),
)
album_artists = Table(
    "album_artists",
    METADATA,
    Column("album_id", Integer, ForeignKey("albums.id"), primary_key=True),
    Column("artist_id", Integer, ForeignKey("artists.id"), primary_key=True),
    Column("join_phrase", Unicode(16)),
)
