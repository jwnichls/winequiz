"""
Helpers shared by the Wine Quiz tests
"""

import os

from winequiz.db import db, Answer, Competitor, QuizItem
from winequiz.quiz import WINE_QUIZ_COOKIE_NAME


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")
USING_POSTGRES = TEST_DATABASE_URL.startswith("postgres")


def make_item(order, grape, country, vintage, alt_grapes, alt_countries, alt_vintages):
    return QuizItem(
        order=order,
        grape_id=grape.id,
        country_id=country.id,
        vintage=vintage,
        grape_alternate_one=alt_grapes[0].id,
        grape_alternate_two=alt_grapes[1].id,
        grape_alternate_three=alt_grapes[2].id,
        country_alternate_one=alt_countries[0].id,
        country_alternate_two=alt_countries[1].id,
        country_alternate_three=alt_countries[2].id,
        vintage_alternate_one=alt_vintages[0],
        vintage_alternate_two=alt_vintages[1],
        vintage_alternate_three=alt_vintages[2],
    )


def set_state(quiz, state, current_item=0):
    """
    Put a quiz directly into a given state
    """
    quiz.state = state
    quiz.current_item = current_item
    db.session.commit()


def add_competitor(quiz, name):
    competitor = Competitor(quiz_id=quiz.id, name=name)
    db.session.add(competitor)
    db.session.commit()
    return competitor


def add_answer(competitor, item, grape, country, vintage, free_response=True):
    answer = Answer(
        quiz_id=item.quiz_id,
        quiz_item_id=item.id,
        competitor_id=competitor.id,
        free_response=free_response,
        grape_id=grape.id if grape is not None else None,
        country_id=country.id if country is not None else None,
        vintage=vintage,
    )
    db.session.add(answer)
    db.session.commit()
    return answer


def login_as(client, competitor):
    """
    Give the test client the cookie that identifies a competitor
    """
    client.set_cookie(WINE_QUIZ_COOKIE_NAME, str(competitor.id))


def events_named(received, name):
    """
    The payloads of every socket event with the given name
    """
    return [event["args"][0] for event in received if event["name"] == name]
