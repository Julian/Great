"""
Add some Spotify URIs.

Revision ID: 24927d9fc648
Revises: 13747a4fb942
Create Date: 2018-01-15 17:03:01.677371

"""

from alembic import op
import sqlalchemy


revision = "24927d9fc648"
down_revision = "13747a4fb942"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        u"albums",
        sqlalchemy.Column(
            "spotify_uri",
            sqlalchemy.Boolean(),
            server_default=sqlalchemy.text(u"0"),
            nullable=False,
        ),
    )
    op.add_column(
        u"artists",
        sqlalchemy.Column(
            "spotify_uri",
            sqlalchemy.Boolean(),
            server_default=sqlalchemy.text(u"0"),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column(u"artists", "spotify_uri")
    op.drop_column(u"albums", "spotify_uri")
