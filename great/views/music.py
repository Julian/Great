import json

from minion import Response
from sqlalchemy import String, select
from sqlalchemy.sql.expression import cast

from great.models import music


def create_endpoints_for(table, detail_columns, app, prefix="/"):
    """
    Create CRUD endpoints for the given table.

    """

    path = prefix + table.name + "/"

    @app.route(path, methods=["HEAD", "GET"])
    @app.bin.needs(["db"])
    def list_entities(request, db):
        rows = db.execute(select([table.c.id, table.c.name]))
        response = Response(json.dumps([dict(row) for row in rows]))
        response.headers.set("Content-Type", ["application/json"])
        return response


    @app.route(path + "<int:id>/", methods=["HEAD", "GET"])
    @app.bin.needs(["db"])
    def show_entity(request, id, db):
        columns = [table.c.id, table.c.name] + detail_columns
        entity = db.execute(select(columns).where(table.c.id == id)).fetchone()
        response = Response(json.dumps(dict(entity)))
        response.headers.set("Content-Type", ["application/json"])
        return response


def init_app(app):
    create_endpoints_for(
        music.albums,
        prefix="/music/",
        app=app,
        detail_columns=[
            music.albums.c.comments,
            music.albums.c.compilation,
            music.albums.c.live,
            cast(music.albums.c.mbid, String).label("mbid"),
            music.albums.c.pinned,
            music.albums.c.rating,
            music.albums.c.release_date,
            music.albums.c.type,
        ],
    )
    create_endpoints_for(
        music.artists,
        prefix="/music/",
        app=app,
        detail_columns=[
            music.artists.c.comments,
            cast(music.artists.c.created_at, String).label("created_at"),
            cast(music.artists.c.mbid, String).label("mbid"),
            cast(music.artists.c.modified_at, String).label("modified_at"),
            music.artists.c.pinned,
            music.artists.c.rating,
        ],
    )
