import uuid

from flask import Flask
from flask.ext.admin import Admin
from flask_debugtoolbar import DebugToolbarExtension

from great.models.core import db


def create_app(db_uri, debug=True):
    app = Flask(__name__)

    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
    db.init_app(app)

    admin = Admin(app, name="Great")

    if debug:
        app.debug = True
        app.config["SECRET_KEY"] = uuid.uuid4()
        toolbar = DebugToolbarExtension(app)

    from great import views
    app.register_blueprint(views.great)

    return app
