"""
The admin page route.
"""

from flask import Blueprint, render_template

from winequiz.db import get_db, Country, Grape, Quiz

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/")
def index():
    """
    The main admin route
    """
    return render_template("admin/index.html")


@bp.route("/grapes", methods=["GET"])
def grapes():
    """
    The grape editing page
    """
    grapes = Grape.query.all()
    
    return render_template("admin/grape.html", grapes=grapes)


@bp.route("/grapes", methods=["PUT"])
def add_grape():
    """
    Add a grape
    """
    return {"success": False, "message": "Not yet implemented"}


@bp.route("/grapes/<int:id>", methods=["DELETE"])
def remove_grape(id):
    """
    Remove a grape
    """
    return {"success": False, "message": "Not yet implemented"}


@bp.route("/countries", methods=["GET"])
def countries():
    """
    The country editing page
    """
    countries = Country.query.all()
    
    return render_template("admin/country.html", countries=countries)


@bp.route("/countries", methods=["PUT"])
def add_country():
    """
    Add a country
    """
    return {"success": False, "message": "Not yet implemented"}


@bp.route("/countries/<int:id>", methods=["DELETE"])
def remove_country(id):
    """
    Remove a country
    """
    return {"success": False, "message": "Not yet implemented"}
