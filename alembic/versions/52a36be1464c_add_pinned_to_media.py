"""Add pinned to Media

Revision ID: 52a36be1464c
Revises: None
Create Date: 2013-06-14 16:42:57.364781

"""

# revision identifiers, used by Alembic.
revision = '52a36be1464c'
down_revision = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column(
        u'albums',
        sa.Column(
            'pinned',
            sa.Boolean(),
            default=False,
            nullable=False,
            server_default=sa.sql.expression.false()
        )
    )

    op.add_column(
        u'discs',
        sa.Column(
            'pinned',
            sa.Boolean(),
            default=False,
            nullable=False,
            server_default=sa.sql.expression.false()
        )
    )

    op.add_column(
        u'tracks',
        sa.Column(
            'pinned',
            sa.Boolean(),
            default=False,
            nullable=False,
            server_default=sa.sql.expression.false()
        )
    )



def downgrade():
    op.drop_column(u'tracks', 'pinned')
    op.drop_column(u'discs', 'pinned')
    op.drop_column(u'albums', 'pinned')
