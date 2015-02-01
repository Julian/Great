from datetime import datetime
from uuid import UUID
import json

from characteristic import Attribute, attributes
from minion.renderers import JSON
from minion.request import Response
from minion.traversal import LeafResource, TreeResource
from sqlalchemy import String
from sqlalchemy.sql.expression import cast

from great.models import music
from great.models.core import ModelManager, NotFound


def _uuid_to_str(obj):
    if isinstance(obj, UUID):
        return obj.hex
    raise TypeError("{!r} is not JSON serializable".format(obj))


@attributes(
    [
        Attribute(name="manager"),
        Attribute(name="from_detail_json", default_value=json.load),
        Attribute(name="for_detail_json", default_value=lambda model : model),
    ],
)
class ModelResource(object):

    renderer = JSON(default=_uuid_to_str)

    def get_child(self, name, request):
        if not name:
            return self

        id = int(name)

        def render_detail(request):
            try:
                content = self.for_detail_json(self.manager.detail(id=id))
            except NotFound:
                return Response(code=404)
            return self.renderer.render(jsonable=content, request=request)

        return LeafResource(render=render_detail)

    def render(self, request):
        if request.method == b"GET":
            fields = [
                field
                for raw in request.url.query.get(b"fields", ())
                for field in raw.rstrip(b",").split(b",")
            ]
            content = self.manager.list(
                fields=fields,
            )
        elif request.method == b"POST":
            new = self.from_detail_json(request.content)
            content = self.for_detail_json(self.manager.create(**new))
        elif request.method == b"DELETE":
            self.manager.delete(id=json.load(request.content)[u"id"])
            return Response(code=204)
        else:
            return Response(code=405)

        return self.renderer.render(jsonable=content, request=request)


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
    release_date = album.get(u"release_date")
    if release_date is not None:
        album[u"release_date"] = datetime.strptime(
            release_date, "%Y-%m-%d"
        ).date()
    return album


def _album_for_json(album):
    release_date = album.get(u"release_date")
    if release_date is not None:
        album[u"release_date"] = release_date.strftime("%Y-%m-%d")
    return album
