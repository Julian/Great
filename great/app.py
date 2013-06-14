import os
import uuid

from flask import Flask
from flask.config import Config
from flask.ext.admin import Admin
from flask_debugtoolbar import DebugToolbarExtension

from great.models.core import db
import great


def create_config(root_path=None, *args, **kwargs):
    if root_path is None:
        root_path = os.path.abspath(os.path.dirname(great.__file__))

    config = Config(root_path, *args, **kwargs)
    config.from_object("great.config")
    config.from_envvar("GREAT_CONFIG")
    config.from_object(config)
    return config


def create_app(config=None):
    if config is None:
        config = create_config()

    app = Flask(__name__)
    app.config.update(config)

    db.init_app(app)

    admin = Admin(app, name="Great")

    if app.config["DEBUG"]:
        toolbar = DebugToolbarExtension(app)

    from great import views
    app.register_blueprint(views.great)

    return app
