import configparser

from appdirs import user_config_dir
from minion import Application, Response
from minion.routers import TraversalRouter
from minion.traversal import TreeResource
from sqlalchemy import create_engine
from twisted.python.filepath import FilePath

from great.views import music


CONFIG_HOME = FilePath(user_config_dir("Great"))


def create_app(config=None):
    if config is None:
        config = configparser.ConfigParser()
        config.read(CONFIG_HOME.child("config.ini").path)

    root = TreeResource(render=lambda request : Response(code=404))
    app = Application(router=TraversalRouter(root=root))
    app.bin.globals["db"] = create_engine(config["db"]["url"]).connect()

    music.init_app(app)

    return app
