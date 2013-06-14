import logging.config

from alembic import context
from sqlalchemy import create_engine, pool

from great.app import create_config
from great.models.core import db


GREAT_CONFIG = create_config()
TARGET_METADATA = db.metadata

ALEMBIC_CONFIG = context.config
logging.config.fileConfig(ALEMBIC_CONFIG.config_file_name)


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """

    url = GREAT_CONFIG["SQLALCHEMY_DATABASE_URI"]
    context.configure(url=url)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    url = GREAT_CONFIG["SQLALCHEMY_DATABASE_URI"]
    engine = create_engine(url, poolclass=pool.NullPool)

    connection = engine.connect()
    context.configure(connection=connection, target_metadata=TARGET_METADATA)

    try:
        with context.begin_transaction():
            context.run_migrations()
    finally:
        connection.close()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
