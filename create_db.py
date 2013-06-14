#! /usr/bin/env python
import os

from alembic.config import Config
from alembic import command

from great.app import create_config


config = create_config()
alembic_config = Config(os.path.join(os.path.dirname(__file__), "alembic.ini"))
command.stamp(alembic_config, "head")
