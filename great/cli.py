import argparse

from great import extract
from great.models.core import Session, configure_db


def main(arguments):
    configure_db(arguments.db_uri)

    if arguments.command == "itunes":
        session = Session()
        tracks = extract.itunes_tracks(arguments.library_file)
        for track in tracks:
            session.add(extract.track_from_itunes(session, track))
        session.commit()


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
