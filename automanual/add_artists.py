#!/Users/julian/.local/share/virtualenvs/great/bin/pypy
import sys

from great.models import music
from great.web import engine_from_config
from pyperclip import copy
from sqlalchemy import sql
from titlecase import titlecase


e = engine_from_config()


def exists(artist):
    return e.execute(
        sql.exists(
            sql.select([music.artists]).where(music.artists.c.name == artist),
        ).select(),
    ).scalar()


with open("/dev/tty") as tty:
    for line in sys.stdin:
        artist = titlecase(line[:-1].decode("utf-8"))
        if not exists(artist):
            copy(artist)
            print repr(artist)
            add = tty.readline().strip().decode("utf-8") or artist
            print "Adding:", repr(add)
            e.execute(music.artists.insert().values(name=add))
