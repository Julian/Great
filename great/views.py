from flask import Blueprint, current_app

from great.models import music


great = Blueprint("great", __name__)
