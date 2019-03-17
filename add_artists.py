#!/Users/julian/.local/share/virtualenvs/great/bin/pypy
"""
* group by artist
* canonical case
* find existing artist
"""
import csv
import subprocess
import sys

from great.models import music
from great.web import engine_from_config
from sqlalchemy import sql


e = engine_from_config()


def copy(text):
    subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE).communicate(
        text.encode("utf-8"),
    )


def canonicalize(artist):
    stripped = artist.strip()
    for each in "and", "for", "in", "of", "the":
        stripped = stripped.replace(" " + each.title() + " ", " " + each + " ")
    return stripped


def exists(artist):
    return e.execute(
        sql.exists(
            sql.select([music.artists]).where(music.artists.c.name == artist),
        ).select(),
    ).scalar()


with open("/dev/tty") as tty:
    for line in sys.stdin:
        artist = canonicalize(line[:-1].decode("utf-8"))
        if not exists(artist):
            copy(artist)
            print repr(artist)
            add = tty.readline().strip().decode("utf-8") or artist
            print "Adding:", repr(add)
            e.execute(music.artists.insert().values(name=add))
