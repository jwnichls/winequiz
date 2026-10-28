"""
Tests for the SocketIO events in winequiz.websocket, including the quiz
state machine they drive (winequiz.quiz.advance_quiz_state and friends).

The events are sent the same way the moderator, display and player pages
send them.
"""

import pytest

from winequiz import socketio
from winequiz.db import db, Competitor, Quiz, QuizStateEnum

from tests.helpers import add_answer, add_competitor, events_named, set_state


MODERATOR = -1  # the competitor id the moderator and display pages join with


def join(socket_client, quiz, competitor_id=MODERATOR):
    socket_client.emit("join", {"room": f"quiz{quiz.id}", "competitor": competitor_id})
    return socket_client.get_received()


def advance(socket_client, quiz, code="secret-mod"):
    socket_client.emit("advance_quiz_state", {"moderator_code": code}, f"quiz{quiz.id}")
    return events_named(socket_client.get_received(), "quiz_state_changed")


def reverse(socket_client, quiz, code="secret-mod"):
    socket_client.emit("reverse_quiz_state", {"moderator_code": code}, f"quiz{quiz.id}")
    return events_named(socket_client.get_received(), "quiz_state_changed")


def reload(quiz):
    db.session.expire_all()
    return db.session.get(Quiz, quiz.id)


def test_connect_sends_greeting(app, client):
    sc = socketio.test_client(app, flask_test_client=client)

    assert sc.is_connected()
    assert events_named(sc.get_received(), "after_connect") == [{"data": "Connected!"}]


def test_moderator_join_receives_current_state(socket_client, quiz):
    received = join(socket_client, quiz)

    assert events_named(received, "quiz_state_changed") == [{
        "id": quiz.id,
        "name": "Tuesday Tasting",
        "state": QuizStateEnum.NOT_STARTED,
        "state_string": "Not Started",
    }]
    assert events_named(received, "competitor_joined") == []


def test_competitor_join_is_announced(socket_client, quiz):
    alice = add_competitor(quiz, "Alice")

    received = join(socket_client, quiz, alice.id)

    assert len(events_named(received, "quiz_state_changed")) == 1
    assert events_named(received, "competitor_joined") == [{"id": alice.id, "name": "Alice"}]


def test_competitor_join_is_broadcast_to_others_in_room(app, client, socket_client, quiz):
    alice = add_competitor(quiz, "Alice")
    moderator = socketio.test_client(app, flask_test_client=client)
    join(moderator, quiz)

    join(socket_client, quiz, alice.id)

    assert events_named(moderator.get_received(), "competitor_joined") == [
        {"id": alice.id, "name": "Alice"}
    ]


def test_competitor_cannot_join_another_quizs_room(socket_client, quiz):
    other = Quiz(name="Other", moderator_code="x")
    db.session.add(other)
    db.session.commit()
    outsider = add_competitor(other, "Mallory")

    assert join(socket_client, quiz, outsider.id) == []


@pytest.mark.parametrize("room", ["quiz9999", "lobby"])
def test_join_ignores_unknown_rooms(socket_client, quiz, room):
    socket_client.emit("join", {"room": room, "competitor": MODERATOR})
    assert socket_client.get_received() == []


def test_full_quiz_progression(socket_client, quiz):
    join(socket_client, quiz)

    expected = [
        (QuizStateEnum.LOBBY_OPEN, 0),
        (QuizStateEnum.FREE_RESPONSE, 0),
        (QuizStateEnum.MULTIPLE_CHOICE, 0),
        (QuizStateEnum.QUESTION_RECAP, 0),
        (QuizStateEnum.FREE_RESPONSE, 1),
        (QuizStateEnum.MULTIPLE_CHOICE, 1),
        (QuizStateEnum.QUESTION_RECAP, 1),
        (QuizStateEnum.QUIZ_RECAP, 2),
        (QuizStateEnum.QUIZ_RECAP, 2),  # advancing past the end stays put
    ]
    for state, current_item in expected:
        events = advance(socket_client, quiz)
        assert [event["state"] for event in events] == [state]
        assert events[0]["state_string"] == str(state)
        current = reload(quiz)
        assert (current.state, current.current_item) == (state, current_item)


def test_full_quiz_reversal(socket_client, quiz):
    set_state(quiz, QuizStateEnum.QUIZ_RECAP, current_item=2)
    join(socket_client, quiz)

    expected = [
        (QuizStateEnum.QUESTION_RECAP, 1),
        (QuizStateEnum.MULTIPLE_CHOICE, 1),
        (QuizStateEnum.FREE_RESPONSE, 1),
        (QuizStateEnum.QUESTION_RECAP, 0),
        (QuizStateEnum.MULTIPLE_CHOICE, 0),
        (QuizStateEnum.FREE_RESPONSE, 0),
        (QuizStateEnum.LOBBY_OPEN, 0),
        (QuizStateEnum.NOT_STARTED, 0),
        (QuizStateEnum.NOT_STARTED, 0),  # reversing before the start stays put
    ]
    for state, current_item in expected:
        events = reverse(socket_client, quiz)
        assert [event["state"] for event in events] == [state]
        current = reload(quiz)
        assert (current.state, current.current_item) == (state, current_item)


@pytest.mark.parametrize("change", [advance, reverse])
@pytest.mark.parametrize("code", ["wrong-code", ""])
def test_state_changes_require_moderator_code(socket_client, quiz, change, code):
    set_state(quiz, QuizStateEnum.LOBBY_OPEN)
    join(socket_client, quiz)

    assert change(socket_client, quiz, code=code) == []
    assert reload(quiz).state is QuizStateEnum.LOBBY_OPEN


def test_state_changes_are_broadcast_to_the_room(app, client, socket_client, quiz):
    alice = add_competitor(quiz, "Alice")
    player = socketio.test_client(app, flask_test_client=client)
    join(player, quiz, alice.id)
    join(socket_client, quiz)
    player.get_received()  # joining re-broadcasts the current state to the room

    advance(socket_client, quiz)

    states = [e["state"] for e in events_named(player.get_received(), "quiz_state_changed")]
    assert states == [QuizStateEnum.LOBBY_OPEN]


def test_free_response_state_reveals_only_grape_color(socket_client, quiz):
    set_state(quiz, QuizStateEnum.LOBBY_OPEN)
    join(socket_client, quiz)

    [event] = advance(socket_client, quiz)  # wine 1 is a red

    assert event["grape_color"] == 1
    assert set(event) == {"id", "name", "state", "state_string", "grape_color"}

    advance(socket_client, quiz)
    advance(socket_client, quiz)
    [event] = advance(socket_client, quiz)  # wine 2 is a white

    assert event["state"] == QuizStateEnum.FREE_RESPONSE
    assert event["grape_color"] == 0


def test_multiple_choice_state_sends_sorted_options(socket_client, quiz, grapes, countries):
    set_state(quiz, QuizStateEnum.FREE_RESPONSE)
    join(socket_client, quiz)

    [event] = advance(socket_client, quiz)

    g, c = grapes, countries
    assert event["grapes"] == sorted(
        g[name].id for name in ["Merlot", "Pinot Noir", "Syrah", "Malbec"]
    )
    assert event["countries"] == sorted(
        c[name].id for name in ["France", "Italy", "Chile", "Australia"]
    )
    assert event["vintages"] == [2010, 2012, 2015, 2018]
    assert "correct_grape" not in event


def test_question_recap_reveals_answers_and_scores(socket_client, quiz, grapes, countries):
    item = quiz.items[0]
    alice = add_competitor(quiz, "Alice")
    bob = add_competitor(quiz, "Bob")
    add_answer(alice, item, grapes["Merlot"], countries["France"], 2015)
    add_answer(bob, item, grapes["Merlot"], countries["Italy"], 2015, free_response=False)
    set_state(quiz, QuizStateEnum.MULTIPLE_CHOICE)
    join(socket_client, quiz)

    [event] = advance(socket_client, quiz)

    assert event["correct_grape"] == grapes["Merlot"].id
    assert event["correct_country"] == countries["France"].id
    assert event["correct_vintage"] == 2015
    assert event["scores"] == [
        {"id": alice.id, "name": "Alice", "score": 30},
        {"id": bob.id, "name": "Bob", "score": 10},
    ]
    stats = event["stats"]
    assert stats["free_response"]["vintages"] == {"2015": 1}
    assert stats["multiple_choice"]["countries"] == {str(countries["Italy"].id): 1}


def test_quiz_recap_sends_final_scores_and_saves_points(socket_client, quiz, grapes, countries):
    item1, item2 = quiz.items
    alice = add_competitor(quiz, "Alice")
    bob = add_competitor(quiz, "Bob")
    add_answer(alice, item1, grapes["Merlot"], None, None)  # 10
    add_answer(bob, item1, grapes["Merlot"], countries["France"], None)  # 20
    add_answer(bob, item2, None, countries["Chile"], None, free_response=False)  # 5
    set_state(quiz, QuizStateEnum.QUESTION_RECAP, current_item=1)
    join(socket_client, quiz)

    [event] = advance(socket_client, quiz)

    assert event["state"] == QuizStateEnum.QUIZ_RECAP
    assert event["final_scores"] == [
        {"id": bob.id, "name": "Bob", "score": 25},
        {"id": alice.id, "name": "Alice", "score": 10},
    ]
    db.session.expire_all()
    assert db.session.get(Competitor, alice.id).points == 10
    assert db.session.get(Competitor, bob.id).points == 25


def test_competitor_left_is_broadcast(app, client, socket_client, quiz):
    alice = add_competitor(quiz, "Alice")
    join(socket_client, quiz)
    player = socketio.test_client(app, flask_test_client=client)

    player.emit("competitor_left", {"competitor_id": alice.id})

    assert events_named(socket_client.get_received(), "competitor_left") == [
        {"id": alice.id, "name": "Alice"}
    ]


def test_competitor_left_for_unknown_competitor_is_ignored(socket_client, quiz):
    join(socket_client, quiz)
    socket_client.emit("competitor_left", {"competitor_id": 9999})
    assert socket_client.get_received() == []


@pytest.mark.xfail(strict=True, raises=TypeError,
                   reason="Known bug: player.html sends the room as a second argument, "
                          "which the competitor_left handler does not accept")
def test_competitor_left_as_sent_by_player_page(app, client, socket_client, quiz):
    alice = add_competitor(quiz, "Alice")
    join(socket_client, quiz)
    player = socketio.test_client(app, flask_test_client=client)

    player.emit("competitor_left", {"competitor_id": alice.id}, f"quiz{quiz.id}")

    assert events_named(socket_client.get_received(), "competitor_left") == [
        {"id": alice.id, "name": "Alice"}
    ]
