import pytoml

from appdirs import user_config_dir
from minion.assets import Bin
from minion.core import Application
from minion.request import Response
from minion.routing import Router, TraversalMapper
from minion.traversal import TreeResource
from sqlalchemy import create_engine
from twisted.python.filepath import FilePath

from great.views import music


CONFIG_HOME = FilePath(user_config_dir("Great"))


def create_app(config=None):
    root = TreeResource(render=lambda request : Response(code=404))
    connection = engine_from_config(config=config).connect()
    bin = Bin().add(db=lambda bin: connection)
    app = Application(
        router=Router(mapper=TraversalMapper(root=root)), bin=bin,
    )

    music.init_app(app)

    return app


def engine_from_config(config=None, **kwargs):
    if config is None:
        config = load_config()
    return create_engine(config["db"]["url"], **kwargs)


def load_config():
    return pytoml.loads(CONFIG_HOME.child("config.toml").getContent())
