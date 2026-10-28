"""
Shared fixtures for the Wine Quiz tests.

Tests run against an in-memory SQLite database by default. Set
TEST_DATABASE_URL to a PostgreSQL URL to run them against Postgres,
which is what production uses (CI does this).
"""

import fakeredis
import pytest
from flask import template_rendered

from winequiz import create_app, socketio
from winequiz.db import db, Country, Grape, GrapeColorEnum, Quiz

from tests.helpers import TEST_DATABASE_URL, make_item


@pytest.fixture
def app():
    """
    A fresh app with empty database tables for each test
    """
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "BROKER_URL": None,
        "SQLALCHEMY_DATABASE_URI": TEST_DATABASE_URL,
    })

    app.extensions["presence_redis"] = fakeredis.FakeRedis()

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()
        db.engine.dispose()  # each app has its own pool; close it so connections don't pile up


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def templates(app):
    """
    Records (template name, context) for every template rendered
    """
    recorded = []

    def record(sender, template, context, **extra):
        recorded.append((template.name, context))

    template_rendered.connect(record, app)
    yield recorded
    template_rendered.disconnect(record, app)


@pytest.fixture
def socket_client(app, client):
    """
    A SocketIO test client that shares cookies with the HTTP client
    """
    sc = socketio.test_client(app, flask_test_client=client)
    sc.get_received()  # discard the after_connect greeting
    yield sc
    if sc.is_connected():
        sc.disconnect()


@pytest.fixture
def grapes(app):
    """
    Four red and two white grapes, keyed by name
    """
    data = [
        ("Merlot", GrapeColorEnum.RED, True),
        ("Pinot Noir", GrapeColorEnum.RED, False),
        ("Syrah", GrapeColorEnum.RED, True),
        ("Malbec", GrapeColorEnum.RED, True),
        ("Chardonnay", GrapeColorEnum.WHITE, False),
        ("Riesling", GrapeColorEnum.WHITE, False),
    ]
    grapes = {name: Grape(name=name, color=color, blendable=blendable)
              for name, color, blendable in data}
    db.session.add_all(grapes.values())
    db.session.commit()
    return grapes


@pytest.fixture
def countries(app):
    """
    Two old world and two new world countries, keyed by name
    """
    data = [
        ("France", True),
        ("Italy", True),
        ("Chile", False),
        ("Australia", False),
    ]
    countries = {name: Country(name=name, old_world=old_world)
                 for name, old_world in data}
    db.session.add_all(countries.values())
    db.session.commit()
    return countries


@pytest.fixture
def quiz(grapes, countries):
    """
    A two-wine quiz that has not started yet:
      Wine 1: Merlot, France, 2015 (red)
      Wine 2: Chardonnay, Chile, 2020 (white)
    """
    g, c = grapes, countries
    quiz = Quiz(
        name="Tuesday Tasting",
        moderator_code="secret-mod",
        duration_free_response=60,
        duration_multiple_choice=30,
    )
    quiz.items.append(make_item(
        1, g["Merlot"], c["France"], 2015,
        [g["Pinot Noir"], g["Syrah"], g["Malbec"]],
        [c["Italy"], c["Chile"], c["Australia"]],
        [2012, 2018, 2010],
    ))
    quiz.items.append(make_item(
        2, g["Chardonnay"], c["Chile"], 2020,
        [g["Riesling"], g["Merlot"], g["Syrah"]],
        [c["France"], c["Italy"], c["Australia"]],
        [2019, 2021, 2016],
    ))
    db.session.add(quiz)
    db.session.commit()
    return quiz
