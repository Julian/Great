import json

from minion import Response
from sqlalchemy import select

from great.models import music


def create_endpoints_for(table, app, prefix="/"):
    """
    Create CRUD endpoints for the given table.

    """

    @app.route(prefix + table.name, methods=["HEAD", "GET"])
    @app.bin.needs(["db"])
    def list_entities(request, db):
        rows = db.execute(select([table.c.name]))
        response = Response(json.dumps([name for name, in rows]))
        response.headers.set("Content-Type", ["application/json"])
        return response


def init_app(app):
    for table in music.albums, music.artists:
        create_endpoints_for(table, prefix="/music/", app=app)
