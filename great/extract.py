"""
Tools for extracting pre-existing data from data sources.

"""

import plistlib

from great.models import music


def itunes_tracks(library_path):
    """
    Extract the tracks from an iTunes Library (XML) file.

    """

    return plistlib.readPlist(library_path)["Tracks"].itervalues()


def track_from_itunes(session, track):
    artist, artists = track.get("Artist"), []
    if artist is not None:
        artists.append(music.Artist.get_or_create(session, name=artist))

    album = music.Album.get_or_create(
        session,
        name=track.get("Album"),
        rating=track["Album Rating"] / 10 if "Album Rating" in track else None
    )

    disc = music.Disc.get_or_create(
        session, album=album, number=track.get("Disc Number"),
    )

    composer, composers = track.get("Composer"), []
    if composer is not None:
        composers.append(music.Composer.get_or_create(session, name=composer))

    return music.Track(
        name=track["Name"],
        comments=track.get("Comments"),
        rating=track["Rating"] / 10 if "Rating" in track else None,
        created_at=track["Date Added"],
        modified_at=track["Date Modified"],
        genre=track.get("Genre"),
        year=track.get("Year"),
        play_count=track.get("Play Count"),
        played_at=track.get("Play Date UTC"),
        skip_count=track.get("Skip Count"),
        skipped_at=track.get("Skip Date UTC"),
        number=track.get("Track Number"),
        artists=artists,
        composers=composers,
        disc=disc,
    )
