"""
Initial revision

Revision ID: 44359856d0a6
Revises:
Create Date: 2018-02-19 19:44:21.111145

"""

from alembic import op
import sqlalchemy

import great.models._guid


revision = "44359856d0a6"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "albums",
        sqlalchemy.Column(
            "id",
            sqlalchemy.Integer(),
            nullable=False,
        ),
        sqlalchemy.Column(
            "name",
            sqlalchemy.Unicode(length=256),
            nullable=False,
        ),
        sqlalchemy.Column(
            "rating",
            sqlalchemy.Integer(),
            nullable=True,
        ),
        sqlalchemy.Column(
            "pinned",
            sqlalchemy.Boolean(),
            server_default=sqlalchemy.text(u"0"),
            nullable=False,
        ),
        sqlalchemy.Column(
            "comments",
            sqlalchemy.UnicodeText(),
            nullable=True,
        ),
        sqlalchemy.Column(
            "release_date",
            sqlalchemy.Date(),
            nullable=True,
        ),
        sqlalchemy.Column(
            "type",
            sqlalchemy.Enum(u"lp", u"broadcast", u"ep", u"single"),
            nullable=False,
        ),
        sqlalchemy.Column(
            "compilation",
            sqlalchemy.Boolean(),
            server_default=sqlalchemy.text(u"0"),
            nullable=False,
        ),
        sqlalchemy.Column(
            "live",
            sqlalchemy.Boolean(),
            server_default=sqlalchemy.text(u"0"),
            nullable=False,
        ),
        sqlalchemy.Column("mbid", great.models._guid.GUID(), nullable=True),
        sqlalchemy.Column("spotify_uri", sqlalchemy.Unicode(), nullable=True),
        sqlalchemy.PrimaryKeyConstraint("id"),
        sqlalchemy.UniqueConstraint("mbid"),
        sqlalchemy.UniqueConstraint("spotify_uri")
    )
    op.create_table(
        "artists",
        sqlalchemy.Column("id", sqlalchemy.Integer(), nullable=False),
        sqlalchemy.Column(
            "name",
            sqlalchemy.Unicode(length=256),
            nullable=False,
        ),
        sqlalchemy.Column("rating", sqlalchemy.Integer(), nullable=True),
        sqlalchemy.Column(
            "pinned",
            sqlalchemy.Boolean(),
            server_default=sqlalchemy.text(u"0"),
            nullable=False,
        ),
        sqlalchemy.Column("comments", sqlalchemy.UnicodeText(), nullable=True),
        sqlalchemy.Column(
            "tracked",
            sqlalchemy.Boolean(),
            server_default=sqlalchemy.text(u"0"),
            nullable=False,
        ),
        sqlalchemy.Column("mbid", great.models._guid.GUID(), nullable=True),
        sqlalchemy.Column("spotify_uri", sqlalchemy.Unicode(), nullable=True),
        sqlalchemy.Column("created_at", sqlalchemy.DateTime(), nullable=True),
        sqlalchemy.Column("modified_at", sqlalchemy.DateTime(), nullable=True),
        sqlalchemy.PrimaryKeyConstraint("id"),
        sqlalchemy.UniqueConstraint("mbid"),
        sqlalchemy.UniqueConstraint("spotify_uri")
    )
    op.create_table(
        "album_artists",
        sqlalchemy.Column("album_id", sqlalchemy.Integer(), nullable=False),
        sqlalchemy.Column("artist_id", sqlalchemy.Integer(), nullable=False),
        sqlalchemy.Column(
            "join_phrase",
            sqlalchemy.Unicode(length=16),
            nullable=True,
        ),
        sqlalchemy.ForeignKeyConstraint(["album_id"], ["albums.id"]),
        sqlalchemy.ForeignKeyConstraint(["artist_id"], ["artists.id"]),
        sqlalchemy.PrimaryKeyConstraint("album_id", "artist_id")
    )


def downgrade():
    op.drop_table("album_artists")
    op.drop_table("artists")
    op.drop_table("albums")
