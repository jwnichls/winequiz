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


class IntEnum(types.TypeDecorator):
    """
    An enum with values represented by an integer
    """

    impl = Integer
    python_type = None
    cache_ok = True

    def __init__(self, enumtype, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._enumtype = enumtype

    def process_bind_param(self, value, dialect):
        """
        Overridden from TypeDecorator
        """
        return value.value

    def process_result_value(self, value, dialect):
        """
        Overridden from TypeDecorator
        """
        return self._enumtype(value)

    def process_literal_param(self, value, dialect):
        """
        Overridden from TypeDecorator
        """
        return f"{self.process_bind_param(value, dialect)}"


GRAPE_COLOR_LABELS = [
    "White",
    "Red",
]


class GrapeColorEnum(enum.IntEnum):
    """
    An enumeration of grape colors
    """

    WHITE = 0
    RED = 1

    def __str__(self):
        """
        Returns a string equivalent of the enum value
        """
        return GRAPE_COLOR_LABELS[self._value_]


class Grape(db.Model):
    """
    Represents a grape from which wine might be made
    """

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    color = db.Column(IntEnum(GrapeColorEnum), nullable=False)
    blendable = db.Column(db.Boolean, nullable=False)

    def __repr__(self):
        """
        Returns a string representation of this class instance
        """
        return f"<Grape {self.id} '{self.name}' ({self.color})>"

    def as_dict(self):
        """
        Returns the contents of this structure as a python dictionary
        """
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}    


class Country(db.Model):
    """
    Represents a country from which wine might originate
    """

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    old_world = db.Column(db.Boolean, nullable=False)

    def __repr__(self):
        """
        Returns a string representation of this class instance
        """
        country_str = f"<Country {self.id} '{self.name}' ("
        if self.old_world:
            country_str += "Old World)>"
        else:
            country_str += "New World)>"

        return country_str

    def as_dict(self):
        """
        Returns the contents of this structure as a python dictionary
        """
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}    


class QuizItem(db.Model):
    """
    Represents a particular quiz
    """

    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quiz.id"), nullable=False)
    order = db.Column(db.Integer, nullable=False)
    grape_id = db.Column(db.Integer, db.ForeignKey("grape.id"), nullable=False)
    country_id = db.Column(db.Integer, db.ForeignKey("country.id"), nullable=False)
    vintage = db.Column(db.Integer, nullable=False)
    grape_alternate_one = db.Column(db.Integer, db.ForeignKey("grape.id"), nullable=False)
    grape_alternate_two = db.Column(db.Integer, db.ForeignKey("grape.id"), nullable=False)
    grape_alternate_three = db.Column(db.Integer, db.ForeignKey("grape.id"), nullable=False)
    country_alternate_one = db.Column(db.Integer, db.ForeignKey("country.id"), nullable=False)
    country_alternate_two = db.Column(db.Integer, db.ForeignKey("country.id"), nullable=False)
    country_alternate_three = db.Column(db.Integer, db.ForeignKey("country.id"), nullable=False)
    vintage_alternate_one = db.Column(db.Integer, nullable=False)
    vintage_alternate_two = db.Column(db.Integer, nullable=False)
    vintage_alternate_three = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        """
        Returns a string representation of this class instance
        """
        return f"<QuizItem {self.id} for quiz {self.quiz.name}: {self.grape.name}, {self.country.name}, {self.vintage}>"

    def as_dict(self):
        """
        Returns the contents of this structure as a python dictionary
        """
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class Competitor(db.Model):
    """
    Represents a competitor in a quiz
    """

    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quiz.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    points = db.Column(db.Integer, nullable=False, default=0)
    # TODO: record answers for later display

    def __repr__(self):
        """
        Returns a string representation of this class instance
        """
        return f"<Competitor {self.id} '{self.name}' in quiz {self.quiz.name}>"

    def as_dict(self):
        """
        Returns the contents of this structure as a python dictionary
        """
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class Answer(db.Model):
    """
    Represents an answer to a question
    """
    
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quiz.id"), nullable=False)
    quiz_item_id = db.Column(db.Integer, db.ForeignKey("quiz_item.id"), nullable=False)
    free_response = db.Column(db.Boolean, nullable=False)
    competitor_id = db.Column(db.Integer, db.ForeignKey("competitor.id"), nullable=False)
    grape_id = db.Column(db.Integer, db.ForeignKey("grape.id"), nullable=True)
    country_id = db.Column(db.Integer, db.ForeignKey("country.id"), nullable=True)
    vintage = db.Column(db.Integer, nullable=True)

    def __repr__(self):
        """
        Returns a string representation of this class instance
        """
        return f"<Answer {self.id} for quiz {self.quiz.name} and item {self.quiz_item.id}>"

    def as_dict(self):
        """
        Returns the contents of this structure as a python dictionary
        """
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


QUIZ_STATE_LABELS = [
    "Not Started",
    "Lobby Open",
    "Free Response Period",
    "Multiple Choice Period",
    "Question Recap",
    "Quiz Recap",
]


class QuizStateEnum(enum.IntEnum):
    """
    An enumeration of quiz states
    """

    NOT_STARTED = 0
    LOBBY_OPEN = 1
    FREE_RESPONSE = 2
    MULTIPLE_CHOICE = 3
    QUESTION_RECAP = 4
    QUIZ_RECAP = 5

    def __str__(self):
        """
        Returns a string equivalent of the enum value
        """
        return QUIZ_STATE_LABELS[self._value_]


class Quiz(db.Model):
    """
    Represents a particular quiz
    """

    id = db.Column(db.Integer, primary_key=True)
    created = db.Column(db.DateTime, nullable=False, server_default=func.now())
    name = db.Column(db.String(120), nullable=False)
    moderator_code = db.Column(db.String(36), nullable=False, server_default='gen_random_uuid()')
    duration_free_response = db.Column(db.Integer, nullable=False, default=300)
    duration_multiple_choice = db.Column(db.Integer, nullable=False, default=300)
    items = db.relationship("QuizItem", backref="quiz", order_by="QuizItem.order", lazy=False)
    competitors = db.relationship("Competitor", backref="quiz", order_by="Competitor.id", lazy=True)
    state = db.Column(IntEnum(QuizStateEnum), nullable=False, default=QuizStateEnum.NOT_STARTED)
    current_item = db.Column(db.Integer, nullable=False, default=0)

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
