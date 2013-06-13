from flask import Blueprint, render_template

from great.models import music


great = Blueprint("great", __name__)


@great.route("/")
def index():
    return render_template("index.j2")


@great.route("/music/")
def show_tracks():
    return render_template(
        "tracks.j2",
        tracks=music.Track.query.order_by(music.Track.rating.desc()).limit(100),
    )
