from contextlib import closing
import logging.config

from alembic import context
from sqlalchemy import pool

from great.models.core import METADATA
from great.web import engine_from_config, load_config


CONFIG = load_config()
logging.config.fileConfig(context.config.config_file_name)


def run_migrations_offline(config):
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine,
    though an Engine is acceptable here as well. By skipping the Engine
    creation we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the script
    output.

    """

    context.configure(url=config["db"]["url"], target_metadata=METADATA)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online(config):
    """
    Run migrations in 'online' mode.

    In this scenario we need to create an Engine and associate a
    connection with the context.

    """

    engine = engine_from_config(poolclass=pool.NullPool)

    with closing(engine.connect()) as connection:
        context.configure(connection=connection, target_metadata=METADATA)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline(config=CONFIG)
else:
    run_migrations_online(config=CONFIG)
