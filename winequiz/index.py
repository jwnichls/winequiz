"""
The main front page route.
"""

from flask import Blueprint, render_template

from winequiz.db import get_db, Quiz

bp = Blueprint("index", __name__)


@bp.route("/")
def index():
    """
    The main index route
    """
    return render_template("index/index.html")
