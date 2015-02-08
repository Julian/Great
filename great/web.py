import configparser

from appdirs import user_config_dir
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
    app = Application(router=Router(mapper=TraversalMapper(root=root)))
    app.bin.globals["db"] = engine_from_config(config=config).connect()

    music.init_app(app)

    return app


def engine_from_config(config=None, **kwargs):
    if config is None:
        config = load_config()
    return create_engine(config["db"]["url"], **kwargs)


def load_config():
    config = configparser.ConfigParser()
    config.read(CONFIG_HOME.child("config.ini").path)
    return config
