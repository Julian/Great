#!/Users/julian/.local/share/virtualenvs/great/bin/pypy
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


def exists(artist):
    return e.execute(
        sql.exists(
            sql.select([music.artists]).where(
                music.artists.c.name.ilike(artist),
            ),
        ).select(),
    ).scalar()


with open("/dev/tty") as tty:
    for line in sys.stdin:
        artist = canonicalize(line[:-1].decode("utf-8"))
        if not exists(artist):
            copy(line[:-1].decode("utf-8"))
            print repr(artist)
            add = tty.readline().strip().decode("utf-8") or artist
            if add == artist or not exists(add):
                print "Adding:", repr(add)
                e.execute(music.artists.insert().values(name=add))
