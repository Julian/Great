from minion import Application
from sqlalchemy import create_engine

from great.views import music


def create_app():
    app = Application()
    engine = create_engine("sqlite:///great.db")
    app.bin.provides("db")(engine.connect)
    music.init_app(app)
    return app
