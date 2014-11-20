import json

from minion import Response
from minion.http import Headers
from minion.traversal import LeafResource, TreeResource
from sqlalchemy import String
from sqlalchemy.sql.expression import cast

from great.models import music
from great.models.core import ModelManager


class ModelResource(object):
    def __init__(self, manager):
        self.manager = manager

    def get_child(self, name, request):
        if not name:
            return self

        id = int(name)
        def render_detail(request):
            content = self.manager.detail(id=id)
            return self.render_json(content=content, request=request)

        return LeafResource(render=render_detail)

    def render(self, request):
        if request.method == b"GET":
            content = self.manager.list()
        elif request.method == b"PUT":
            content = self.manager.create(**json.load(request.content))
        elif request.method == b"DELETE":
            self.manager.delete(id=json.load(request.content)[u"id"])
            return Response(code=204)
        else:
            return Response(code=405)

        return self.render_json(content=content, request=request)

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

    db = app.bin.globals["db"]
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
            resource=ModelResource(
                manager=ModelManager(
                    db=db,
                    table=table,
                    detail_columns=detail_columns,
                ),
            )
        )

    app.router.root.set_child("music", music_resource)
