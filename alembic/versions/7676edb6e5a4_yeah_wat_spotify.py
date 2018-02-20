"""
yeah wat spotify

Revision ID: 7676edb6e5a4
Revises: 24927d9fc648
Create Date: 2018-02-19 19:32:11.220236

"""

from alembic import op
import sqlalchemy


revision = "7676edb6e5a4"
down_revision = "24927d9fc648"
branch_labels = None
depends_on = None


def upgrade():
    for table in u"albums", u"artists":
        with op.batch_alter_table(table) as batch:
            batch.drop_column("spotify_uri")
            batch.add_column(
                sqlalchemy.Column(
                    "spotify_uri",
                    sqlalchemy.Unicode(),
                    nullable=True,
                ),
            )


def downgrade():
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
