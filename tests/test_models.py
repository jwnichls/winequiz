"""
Tests for the database models in winequiz.db
"""

import pytest

from winequiz.db import (
    db,
    get_db,
    Answer,
    Grape,
    GrapeColorEnum,
    Quiz,
    QuizStateEnum,
)

from tests.helpers import add_answer, add_competitor


def test_grape_color_labels():
    assert str(GrapeColorEnum.WHITE) == "White"
    assert str(GrapeColorEnum.RED) == "Red"


def test_quiz_state_labels():
    assert [str(state) for state in QuizStateEnum] == [
        "Not Started",
        "Lobby Open",
        "Free Response Period",
        "Multiple Choice Period",
        "Question Recap",
        "Quiz Recap",
    ]


def test_quiz_states_are_ordered():
    assert [state.value for state in QuizStateEnum] == list(range(6))


def test_get_db_returns_shared_instance(app):
    assert get_db() is db
    assert get_db() is get_db()


def test_int_enum_round_trips_through_database(grapes):
    db.session.expire_all()
    merlot = Grape.query.filter_by(name="Merlot").one()
    chardonnay = Grape.query.filter_by(name="Chardonnay").one()

    assert merlot.color is GrapeColorEnum.RED
    assert chardonnay.color is GrapeColorEnum.WHITE


def test_int_enum_can_be_used_in_filters(quiz):
    quiz.state = QuizStateEnum.FREE_RESPONSE
    db.session.commit()

    found = Quiz.query.filter(Quiz.state == QuizStateEnum.FREE_RESPONSE).all()
    assert found == [quiz]
    assert Quiz.query.filter(Quiz.state == QuizStateEnum.LOBBY_OPEN).all() == []


def test_grape_repr_and_dict(grapes):
    merlot = grapes["Merlot"]

    assert repr(merlot) == f"<Grape {merlot.id} 'Merlot' (Red)>"
    assert merlot.as_dict() == {
        "id": merlot.id,
        "name": "Merlot",
        "color": GrapeColorEnum.RED,
        "blendable": True,
    }


def test_country_repr_reflects_world(countries):
    france = countries["France"]
    chile = countries["Chile"]

    assert repr(france) == f"<Country {france.id} 'France' (Old World)>"
    assert repr(chile) == f"<Country {chile.id} 'Chile' (New World)>"
    assert chile.as_dict() == {"id": chile.id, "name": "Chile", "old_world": False}


def test_quiz_defaults(grapes, countries):
    quiz = Quiz(name="Defaults", moderator_code="m")
    db.session.add(quiz)
    db.session.commit()
    db.session.refresh(quiz)

    assert quiz.state is QuizStateEnum.NOT_STARTED
    assert quiz.current_item == 0
    assert quiz.duration_free_response == 300
    assert quiz.duration_multiple_choice == 300
    assert quiz.created is not None
    assert quiz.items == []
    assert quiz.competitors == []


def test_quiz_items_are_ordered(quiz):
    item1, item2 = quiz.items
    item1.order, item2.order = 2, 1
    db.session.commit()
    db.session.expire_all()

    reloaded = db.session.get(Quiz, quiz.id)
    assert [item.id for item in reloaded.items] == [item2.id, item1.id]


def test_quiz_item_relationship_and_dict(quiz):
    item = quiz.items[0]

    assert item.quiz is quiz
    assert item.as_dict()["vintage"] == 2015


@pytest.mark.xfail(strict=True, raises=AttributeError,
                   reason="Known bug: QuizItem has no grape/country relationships for __repr__")
def test_quiz_item_repr(quiz):
    item = quiz.items[0]
    assert repr(item) == (
        f"<QuizItem {item.id} for quiz Tuesday Tasting: Merlot, France, 2015>"
    )


def test_quiz_repr_and_dict(quiz):
    assert repr(quiz).startswith(f"<Quiz {quiz.id} 'Tuesday Tasting' on ")
    data = quiz.as_dict()
    assert data["name"] == "Tuesday Tasting"
    assert data["moderator_code"] == "secret-mod"
    assert data["state"] is QuizStateEnum.NOT_STARTED


def test_competitors_are_ordered_by_id(quiz):
    alice = add_competitor(quiz, "Alice")
    bob = add_competitor(quiz, "Bob")
    db.session.expire_all()

    assert [c.name for c in db.session.get(Quiz, quiz.id).competitors] == ["Alice", "Bob"]
    assert alice.quiz.id == quiz.id
    assert repr(bob) == f"<Competitor {bob.id} 'Bob' in quiz Tuesday Tasting>"
    assert bob.as_dict() == {"id": bob.id, "quiz_id": quiz.id, "name": "Bob", "points": 0}


def test_answer_allows_partial_responses(quiz, grapes):
    alice = add_competitor(quiz, "Alice")
    item = quiz.items[0]
    answer = add_answer(alice, item, grapes["Merlot"], None, None)

    stored = db.session.get(Answer, answer.id)
    assert stored.grape_id == grapes["Merlot"].id
    assert stored.country_id is None
    assert stored.vintage is None


@pytest.mark.xfail(strict=True, raises=AttributeError,
                   reason="Known bug: Answer has no quiz/quiz_item relationships for __repr__")
def test_answer_repr(quiz, grapes):
    alice = add_competitor(quiz, "Alice")
    item = quiz.items[0]
    answer = add_answer(alice, item, grapes["Merlot"], None, None)
    assert repr(answer) == f"<Answer {answer.id} for quiz Tuesday Tasting and item {item.id}>"
