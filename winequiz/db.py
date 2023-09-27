"""
The database model for the flask app.

We use SQLAlchemy and Alembic to manage the database.  If you change
any of the data structures in this file, you likely need to run

flask db migrate -m "description of your change"

to automatically produce code to modify the database, and then run

flask db upgrade

to update your actual database.
"""


import enum

from flask import g
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy import Integer, types
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB


db = SQLAlchemy()


def init_db(app):
    """
    Initialize the database
    """
    db.init_app(app)
    Migrate(app, db, compare_type=True)


def get_db():
    """
    A global helper to get a reference to the database object
    """
    if "db" not in g:
        # pylint: disable=assigning-non-slot
        g.db = db

    return g.db


class Quiz(db.Model):
    """
    Represents a particular quiz
    """

    id = db.Column(db.Integer, primary_key=True)
    created = db.Column(db.DateTime, nullable=False, server_default=func.now())
    name = db.Column(db.String(120), nullable=False)

    def __repr__(self):
        """
        Returns a string representation of this class instance
        """
        return f"<Quiz {self.id} '{self.name}' on {self.created}>"

    def as_dict(self):
        """
        Returns the contents of this structure as a python dictionary
        """
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
