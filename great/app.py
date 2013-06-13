import uuid

from flask import Flask
from flask.ext.admin import Admin
from flask_debugtoolbar import DebugToolbarExtension

from great.models.core import db


def create_app(config=()):
    app = Flask(__name__)

    app.config.from_object("great.config")
    app.config.from_envvar("GREAT_CONFIG")
    app.config.from_object(config)

    db.init_app(app)

    admin = Admin(app, name="Great")

    if app.config["DEBUG"]:
        toolbar = DebugToolbarExtension(app)

    from great import views
    app.register_blueprint(views.great)

    return app
