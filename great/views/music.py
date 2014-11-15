import json

from minion import Response
from minion.http import Headers
from minion.traversal import LeafResource, TreeResource
from sqlalchemy import String, select
from sqlalchemy.sql.expression import cast

from great.models import music


class EntityResource(object):
    def __init__(self, app, table, detail_columns):
        self.app = app
        self.table = table
        self.detail_columns = [table.c.id, table.c.name] + detail_columns

    def list(self, db):
        rows = db.execute(select([self.table.c.id, self.table.c.name]))
        return [dict(row) for row in rows]

    def detail(self, db, id):
        query = select(self.detail_columns).where(self.table.c.id == id)
        return dict(db.execute(query).fetchone())

    def get_child(self, name, request):
        if not name:
            return self

        id = int(name)
        def render_detail(request):
            db = self.app.bin.provide("db", request=request)
            content = self.detail(db=db, id=id)
            return self.render_json(content=content, request=request)

        return LeafResource(render=render_detail)

    def render(self, request):
        db = self.app.bin.provide("db", request=request)
        return self.render_json(content=self.list(db=db), request=request)

    def render_json(self, request, content):
        machine_json = request.headers.get("Accept") == ["application/json"]
        indent = None if machine_json else 2
        return Response(
            headers=Headers([("Content-Type", ["application/json"])]),
            content=json.dumps(content, indent=indent),
        )


def init_app(app):
    music_resource = TreeResource(
        render=lambda request : Response("Music"),
    )

    for table, detail_columns in (
        (
            music.albums, [
                music.albums.c.comments,
                music.albums.c.compilation,
                music.albums.c.live,
                cast(music.albums.c.mbid, String).label("mbid"),
                music.albums.c.pinned,
                music.albums.c.rating,
                music.albums.c.release_date,
                music.albums.c.type,
            ],
        ),
        (
            music.artists, [
                music.artists.c.comments,
                cast(music.artists.c.created_at, String).label("created_at"),
                cast(music.artists.c.mbid, String).label("mbid"),
                cast(music.artists.c.modified_at, String).label("modified_at"),
                music.artists.c.pinned,
                music.artists.c.rating,
            ],
        ),
    ):
        music_resource.set_child(
            name=table.name,
            resource=EntityResource(
                app=app,
                table=table,
                detail_columns=detail_columns,
            )
        )

    app.router.root.set_child("music", music_resource)
