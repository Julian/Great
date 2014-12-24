from datetime import datetime
import json

from characteristic import Attribute, attributes
from minion import Response
from minion.http import Headers, MediaRange
from minion.traversal import LeafResource, TreeResource
from sqlalchemy import String
from sqlalchemy.sql.expression import cast

from great.models import music
from great.models.core import ModelManager, NotFound


@attributes(
    [
        Attribute(name="manager"),
        Attribute(name="from_detail_json", default_value=json.load),
        Attribute(name="for_detail_json", default_value=lambda model : model),
    ],
)
class ModelResource(object):
    def get_child(self, name, request):
        if not name:
            return self

        id = int(name)
        def render_detail(request):
            try:
                content = self.for_detail_json(self.manager.detail(id=id))
            except NotFound:
                return Response(code=404)
            return self.render_json(content=content, request=request)

        return LeafResource(render=render_detail)

    def render(self, request):
        if request.method == b"GET":
            content = self.manager.list()
        elif request.method == b"POST":
            new = self.from_detail_json(request.content)
            content = self.for_detail_json(self.manager.create(**new))
        elif request.method == b"DELETE":
            self.manager.delete(id=json.load(request.content)[u"id"])
            return Response(code=204)
        else:
            return Response(code=405)

        return self.render_json(content=content, request=request)

    def render_json(self, request, content):
        machine_json = request.accept.media_types[-1] == MediaRange(
            type="application", subtype="json",
        )
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
    for table, detail_columns, from_detail_json, for_detail_json in (
        (
            music.albums,
            [
                music.albums.c.comments,
                music.albums.c.compilation,
                music.albums.c.live,
                cast(music.albums.c.mbid, String).label("mbid"),
                music.albums.c.pinned,
                music.albums.c.rating,
                music.albums.c.release_date,
                music.albums.c.type,
            ],
            _album_from_json,
            _album_for_json,
        ),
        (
            music.artists,
            [
                music.artists.c.comments,
                cast(music.artists.c.created_at, String).label("created_at"),
                cast(music.artists.c.mbid, String).label("mbid"),
                cast(music.artists.c.modified_at, String).label("modified_at"),
                music.artists.c.pinned,
                music.artists.c.rating,
            ],
            json.load,
            lambda artist : artist,
        ),
    ):
        music_resource.set_child(
            name=table.name,
            resource=ModelResource(
                from_detail_json=from_detail_json,
                for_detail_json=for_detail_json,
                manager=ModelManager(
                    db=db,
                    table=table,
                    detail_columns=detail_columns,
                ),
            )
        )

    app.router.mapper.root.set_child("music", music_resource)


def _album_from_json(detail):
    album = json.load(detail)
    album[u"release_date"] = datetime.strptime(
        album[u"release_date"], "%Y-%m-%d",
    ).date()
    return album


def _album_for_json(album):
    album[u"release_date"] = album[u"release_date"].strftime("%Y-%m-%d")
    return album
