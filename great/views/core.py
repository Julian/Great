import configparser

from appdirs import user_config_dir
from minion import Application
from sqlalchemy import create_engine
from twisted.python.filepath import FilePath

from great.views import music


CONFIG_HOME = FilePath(user_config_dir("Great"))


def create_app():
    config = configparser.ConfigParser()
    config.read(CONFIG_HOME.child("config.ini").path)

    app = Application()
    app.bin.provides("db")(create_engine(config["db"]["url"]).connect)

    music.init_app(app)

    return app
