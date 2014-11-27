from datetime import datetime
from unittest import TestCase

from minion.wsgi import wsgi_app
from webtest import TestApp

from great.models.core import METADATA
from great.web import create_app


class ApplicationTestMixin(object):
    def setUp(self):
        super(ApplicationTestMixin, self).setUp()
        self.config = {"db" : {"url" : "sqlite://"}}
        self.great = create_app(config=self.config)
        self.app = TestApp(wsgi_app(self.great))

        METADATA.create_all(self.great.bin.provide("db"))


class TestArtist(ApplicationTestMixin, TestCase):
    def test_create_artist(self):
        response = self.app.post_json(
            b"/music/artists/", params={u"name" : u"John Smith"},
        )
        self.assertEqual(
            response.json, {
                u"id" : 1,
                u"name" : u"John Smith",
                u"mbid" : None,
                u"rating" : None,
                u"comments" : None,
                u"pinned" : False,
                u"created_at" : response.json[u"created_at"],
                u"modified_at" : response.json[u"created_at"],
            },
        )

    def test_detail_artist(self):
        response = self.app.post_json(
            b"/music/artists/", params={u"name" : u"John Smith"},
        )
        artist = {
            u"id" : 1,
            u"name" : u"John Smith",
            u"mbid" : None,
            u"rating" : None,
            u"comments" : None,
            u"pinned" : False,
            u"created_at" : response.json[u"created_at"],
            u"modified_at" : response.json[u"created_at"],
        }
        self.assertEqual(response.json, artist)

        response = self.app.get(b"/music/artists/1")
        self.assertEqual(response.json, artist)

    def test_nonexisting_detail_artist(self):
        self.app.get(b"/music/artists/1", status=404)

    def test_delete_artist(self):
        self.app.post_json(b"/music/artists/", params={b"name" : b"Jim Smith"})
        self.assertEqual(
            self.app.get(b"/music/artists").json,
            [{u"id" : 1, u"name" : u"Jim Smith"}],
        )
        response = self.app.delete_json(b"/music/artists/", params={u"id" : 1})
        self.assertFalse(self.app.get(b"/music/artists").json)
        self.assertEqual(response.status_code, 204)

    def test_list_artists(self):
        self.app.post_json(b"/music/artists/", params={u"name" : u"Jim Smith"})
        self.app.post_json(b"/music/artists/", params={u"name" : u"Tom Jones"})
        self.assertEqual(
            self.app.get(b"/music/artists").json, [
                {u"id" : 1, u"name" : u"Jim Smith"},
                {u"id" : 2, u"name" : u"Tom Jones"},
            ],
        )

    def test_unknown_method(self):
        self.app.request(b"/music/artists", method=b"TRACE", status=405)


class TestAlbum(ApplicationTestMixin, TestCase):
    def test_create_album(self):
        response = self.app.post_json(
            b"/music/albums/", params={
                u"name" : u"Total Beats",
                u"release_date" : u"2001-05-05",
            },
        )
        self.assertEqual(
            response.json, {
                u"id" : 1,
                u"name" : u"Total Beats",
                u"mbid" : None,
                u"rating" : None,
                u"comments" : None,
                u"compilation" : False,
                u"live" : False,
                u"type" : u"lp",
                u"pinned" : False,
                u"release_date" : u"2001-05-05",
            },
        )

    def test_detail_album(self):
        response = self.app.post_json(
            b"/music/albums/", params={
                u"name" : u"Total Beats",
                u"release_date" : u"2001-05-05",
            },
        )
        album = {
            u"id" : 1,
            u"name" : u"Total Beats",
            u"mbid" : None,
            u"rating" : None,
            u"comments" : None,
            u"compilation" : False,
            u"live" : False,
            u"type" : u"lp",
            u"pinned" : False,
            u"release_date" : u"2001-05-05",
        }
        self.assertEqual(response.json, album)

        response = self.app.get(b"/music/albums/1")
        self.assertEqual(response.json, album)

    def test_nonexisting_detail_album(self):
        self.app.get(b"/music/albums/1", status=404)

    def test_delete_album(self):
        response = self.app.post_json(
            b"/music/albums/", params={
                u"name" : u"Total Beats",
                u"release_date" : u"2001-05-05",
            },
        )
        self.assertEqual(
            self.app.get(b"/music/albums").json,
            [{u"id" : 1, u"name" : u"Total Beats"}],
        )
        response = self.app.delete_json(b"/music/albums/", params={u"id" : 1})
        self.assertFalse(self.app.get(b"/music/albums").json)
        self.assertEqual(response.status_code, 204)

    def test_list_albums(self):
        self.app.post_json(
            b"/music/albums/", params={
                u"name" : u"Total Beats",
                u"release_date" : u"2001-05-05",
            },
        )
        self.app.post_json(
            b"/music/albums/", params={
                u"name" : u"Ace of Space",
                u"release_date" : u"2002-02-02",
            },
        )
        self.assertEqual(
            self.app.get(b"/music/albums").json, [
                {u"id" : 1, u"name" : u"Total Beats"},
                {u"id" : 2, u"name" : u"Ace of Space"},
            ],
        )

    def test_unknown_method(self):
        self.app.request(b"/music/albums", method=b"TRACE", status=405)
