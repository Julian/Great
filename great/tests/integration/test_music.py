from unittest import TestCase

from hyperlink import URL
from minion import wsgi
from webtest import TestApp

from great.models.core import METADATA
from great.web import create_app


class ApplicationTestMixin(object):
    def setUp(self):
        super(ApplicationTestMixin, self).setUp()
        self.config = {"db": {"url": "sqlite://"}}
        self.great = create_app(config=self.config)
        self.app = TestApp(wsgi.create_app(self.great))

        METADATA.create_all(self.great.bin.provide("engine").connect())

    def create(self, **params):
        return self.app.post_json(self.url.to_text(), params=params).json

    def delete(self, **params):
        return self.app.delete_json(self.url.to_text(), params=params)

    def list(self, **params):
        return self.app.get(self.url.to_text(), params=params).json

    def tracked(self, **params):
        return self.app.get(
            self.url.child(u"tracked").to_text(),
            params=params,
        ).json

    def test_invalid_json(self):
        self.app.post(self.url.to_text(), params="", status=400)

    def test_unknown_method(self):
        self.app.request(self.url.to_text(), method=b"TRACE", status=405)


class TestArtist(ApplicationTestMixin, TestCase):

    url = URL(path=[u"music", u"artists"], rooted=True)

    def test_create_artist(self):
        response = self.create(name="John Smith")
        self.assertEqual(
            response, {
                u"id": 1,
                u"name": u"John Smith",
                u"mbid": None,
                u"rating": None,
                u"comments": None,
                u"pinned": False,
                u"created_at": response[u"created_at"],
                u"modified_at": response[u"created_at"],
            },
        )

    def test_detail_artist(self):
        response = self.create(name=u"John Smith")
        artist = {
            u"id": 1,
            u"name": u"John Smith",
            u"mbid": None,
            u"rating": None,
            u"comments": None,
            u"pinned": False,
            u"created_at": response[u"created_at"],
            u"modified_at": response[u"created_at"],
        }
        self.assertEqual(response, artist)

        response = self.app.get(b"/music/artists/1")
        self.assertEqual(response.json, artist)

    def test_nonexisting_detail_artist(self):
        self.app.get(b"/music/artists/1", status=404)

    def test_delete_artist(self):
        self.create(name=b"Jim Smith")
        self.assertEqual(self.list(), [{u"id": 1, u"name": u"Jim Smith"}])

        response = self.delete(id=1)
        self.assertEqual(response.status_code, 204)

        self.assertFalse(self.list())

    def test_list_artists(self):
        self.create(name=u"Jim Smith")
        self.create(name=u"Tom Jones")
        self.assertEqual(
            self.list(), [
                {u"id": 1, u"name": u"Jim Smith"},
                {u"id": 2, u"name": u"Tom Jones"},
            ],
        )

    def test_list_artists_fields(self):
        self.create(name=u"A", mbid=u"1" * 32)
        self.create(name=u"B")
        self.assertEqual(
            self.list(fields="mbid"), [
                {u"id": 1, u"name": u"A", u"mbid": u"1" * 32},
                {u"id": 2, u"name": u"B", u"mbid": None},
            ],
        )

    def test_tracked_artists(self):
        self.create(name=u"A", tracked=True)
        self.create(name=u"B")
        self.create(name=u"C", tracked=True)
        self.assertEqual(
            self.tracked(), [
                {u"id": 1, u"name": u"A"},
                {u"id": 3, u"name": u"C"},
            ],
        )

    def test_list_artists_multiple_fields(self):
        self.create(name=u"A", mbid=u"1" * 32)
        self.create(name=u"B", rating=8)
        self.assertEqual(
            self.list(fields="mbid,rating,"), [
                {
                    u"id": 1,
                    u"name": u"A",
                    u"mbid": u"1" * 32,
                    "rating": None,
                },
                {u"id": 2, u"name": u"B", u"mbid": None, "rating": 8},
            ],
        )


class TestAlbum(ApplicationTestMixin, TestCase):

    url = URL(path=[u"music", u"albums"], rooted=True)

    def test_create_album(self):
        response = self.create(name=u"Total Beats", release_date=u"2001-05-05")
        self.assertEqual(
            response, {
                u"id": 1,
                u"name": u"Total Beats",
                u"mbid": None,
                u"rating": None,
                u"comments": None,
                u"compilation": False,
                u"live": False,
                u"type": u"lp",
                u"pinned": False,
                u"release_date": u"2001-05-05",
            },
        )

    def test_detail_album(self):
        response = self.create(name=u"Total Beats", release_date=u"2001-05-05")
        album = {
            u"id": 1,
            u"name": u"Total Beats",
            u"mbid": None,
            u"rating": None,
            u"comments": None,
            u"compilation": False,
            u"live": False,
            u"type": u"lp",
            u"pinned": False,
            u"release_date": u"2001-05-05",
        }
        self.assertEqual(response, album)

        response = self.app.get(b"/music/albums/1")
        self.assertEqual(response.json, album)

    def test_nonexisting_detail_album(self):
        self.app.get(b"/music/albums/1", status=404)

    def test_delete_album(self):
        self.create(name=u"Total Beats", release_date=u"2001-05-05")
        self.assertEqual(self.list(), [{u"id": 1, u"name": u"Total Beats"}])

        response = self.delete(id=1)
        self.assertEqual(response.status_code, 204)

        self.assertFalse(self.list())

    def test_list_albums(self):
        self.create(name=u"Total Beats", release_date=u"2001-05-05")
        self.create(name=u"Ace of Space", release_date=u"2002-02-02")
        self.assertEqual(
            self.list(), [
                {u"id": 1, u"name": u"Total Beats"},
                {u"id": 2, u"name": u"Ace of Space"},
            ],
        )

    def test_list_albums_fields(self):
        self.create(name=u"A", mbid=u"1" * 32)
        self.create(name=u"B")
        self.assertEqual(
            self.list(fields="mbid"), [
                {u"id": 1, u"name": u"A", u"mbid": u"1" * 32},
                {u"id": 2, u"name": u"B", u"mbid": None},
            ],
        )

    def test_list_albums_multiple_fields(self):
        self.create(name=u"A", mbid=u"1" * 32)
        self.create(name=u"B", rating=8)
        self.assertEqual(
            self.list(fields="mbid,rating,"), [
                {
                    u"id": 1,
                    u"name": u"A",
                    u"mbid": u"1" * 32,
                    "rating": None,
                },
                {u"id": 2, u"name": u"B", u"mbid": None, "rating": 8},
            ],
        )
