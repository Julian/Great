from minion.assets import Bin
from minion.core import Application
from minion.request import Response
from minion.routing import Router, TraversalMapper
from minion.traversal import TreeResource
from sqlalchemy import create_engine

from great.views import music
import great.config


def create_app(config=None):
    root = TreeResource()
    bin = Bin().with_globals(engine=engine_from_config(config=config))
    app = Application(
        router=Router(mapper=TraversalMapper(root=root)), bin=bin,
    )

    music.init_app(bin=bin, root=root)

    return app


def engine_from_config(config=None, **kwargs):
    if config is None:
        config = great.config.load()
    return create_engine(config["db"]["url"], **kwargs)
