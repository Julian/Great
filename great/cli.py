import argparse

from great import extract
from great.models.core import db
from great.app import create_app


def main(arguments):
    app = create_app(arguments.db_uri)

    if arguments.command == "itunes":
        tracks = extract.itunes_tracks(arguments.library_file)
        for track in tracks:
            db.session.add(extract.track_from_itunes(db.session, track))
        db.session.commit()


parser = argparse.ArgumentParser(description="Great: a ratings collector")
parser.add_argument(
    "--db-uri", default="sqlite:///great.db", help="The, database URI to use.",
)

subparsers = parser.add_subparsers(dest="command")

itunes = subparsers.add_parser("itunes")
itunes.add_argument(
    "--library-file",
    help="An iTunes Library (XML) file to parse",
    default="iTunes Library File.xml",
)
