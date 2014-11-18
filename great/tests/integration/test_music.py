from datetime import datetime
from mock import patch
from unittest import TestCase

from minion.wsgi import wsgi_app
from webtest import TestApp

from great.models.core import METADATA
from great.web import create_app


class TestMusic(TestCase):
    def setUp(self):
        self.config = {"db" : {"url" : "sqlite://"}}
        self.great = create_app(config=self.config)
        self.app = TestApp(wsgi_app(self.great))

        METADATA.create_all(self.great.bin.provide("db"))

    def test_create_artist(self):
        response = self.app.put_json(
            b"/music/artists/", params={b"name" : b"John Smith"},
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

    def test_list_artists(self):
        self.app.put_json(b"/music/artists/", params={b"name" : b"John Smith"})
        self.app.put_json(b"/music/artists/", params={b"name" : b"Tom Jones"})
        self.assertEqual(
            self.app.get(b"/music/artists").json, [
                {u"id" : 1, u"name" : u"John Smith"},
                {u"id" : 2, u"name" : u"Tom Jones"},
            ],
        )

    def test_unknown_method(self):
        self.app.request(b"/music/artists", method=b"TRACE", status=405)
