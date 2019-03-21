#!/Users/julian/.local/share/virtualenvs/great/bin/pypy
import json
import sys

from great.models import music
from great.web import engine_from_config
from pyperclip import copy
from sqlalchemy import sql
from titlecase import titlecase


e = engine_from_config()


def canonicalize(artist):
    if artist.isupper():
        return artist
    return titlecase(artist)


def spotify_uri(artist):
    return e.execute(
        sql.select(
            [
                music.artists.c.id,
                music.artists.c.name,
                music.artists.c.spotify_uri,
            ],
        ).where(music.artists.c.name.like(artist)),
    ).fetchone()


with open("/dev/tty") as tty:
    for line in sys.stdin:
        as_dict = json.loads(line)
        artist, uri = canonicalize(as_dict["name"]), as_dict["uri"]
        result = spotify_uri(artist)
        if result is None:
            print "Didn't find:", artist
        elif result.spotify_uri is None:
            e.execute(
                sql.update(music.artists).where(
                    music.artists.c.id == result.id,
                ).values(spotify_uri=as_dict["uri"]),
            )
        elif result.spotify_uri != uri:
            sys.exit(
                "Wat! {!r} has current ID {!r}, not {!r}".format(
                    artist, result.spotify_uri, uri,
                ),
            )
