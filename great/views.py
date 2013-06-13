from flask import Blueprint, render_template


great = Blueprint("great", __name__)


@great.route("/")
def index():
    return render_template("index.j2")
