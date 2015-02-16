from datetime import datetime

from txmusicbrainz.client import MusicBrainz

from great import __url__, __version__
from great.models.music import albums, artists


class Retriever(object):
    """
    A retriever syncs data down from MusicBrainz into the local database.

    """

    def __init__(self, engine, musicbrainz_client=None):
        if musicbrainz_client is None:
            musicbrainz_client = MusicBrainz(
                app_name=__package__,
                app_version=__version__,
                contact_info=__url__,
            )

        self.engine = engine
        self.musicbrainz_client = musicbrainz_client


def artist_from_musicbrainz(musicbrainz_artist, **kwargs):
    return artists.insert().values(
        mbid=musicbrainz_artist["id"],
        name=musicbrainz_artist["name"],
        **kwargs
    )


def album_from_musicbrainz(release_group, **kwargs):
    type = release_group[u"primary-type"].lower()
    if type == u"album":
        type = u"lp"

    compilation = u"Compilation" in release_group[u"secondary-types"]
    release_date = release_group[u"first-release-date"]

    return albums.insert().values(
        mbid=release_group[u"id"],
        name=release_group[u"title"],
        release_date=datetime.strptime(release_date, "%Y-%m-%d").date(),
        type=type,
        compilation=compilation,
        **kwargs
    )
