"""
Defines the API routes for the wine quiz app.
"""

import json

from flask import (
    Blueprint,
    current_app,
    g,
    request,
    Response,
    url_for,
)
from werkzeug.exceptions import abort

from winequiz.db import get_db, Country, Grape

bp = Blueprint("api", __name__, url_prefix="/api/v1")


@bp.route("/grapes", methods=["GET"])
def get_grapes():
    """
    Returns a JSON list of grapes in our database
    """
    grapes = Grape.query.all()
    return {"success": True, "grapes": [grape.as_dict() for grape in grapes]}


@bp.route("/countries", methods=["GET"])
def get_countries():
    """
    Returns a JSON list of countries in our database
    """
    countries = Country.query.all()
    return {"success": True, "countries": [country.as_dict() for country in countries]}
