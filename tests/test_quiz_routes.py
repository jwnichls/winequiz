"""
Tests for the HTTP routes in winequiz.quiz
"""

import pytest

from winequiz.db import db, Answer, Competitor, Quiz, QuizStateEnum
from winequiz.quiz import WINE_QUIZ_COOKIE_NAME

from tests.helpers import add_answer, add_competitor, events_named, login_as, set_state


@pytest.fixture
def other_quiz(app):
    quiz = Quiz(name="Other Quiz", moderator_code="other-mod")
    db.session.add(quiz)
    db.session.commit()
    return quiz


def answer_payload(grapes, countries, grape="Merlot", country="France", vintage=2015):
    return {
        "grape": grapes[grape].id if grape else None,
        "country": countries[country].id if country else None,
        "vintage": vintage,
    }


# Quiz overview and joining

def test_show_quiz(client, quiz):
    response = client.get(f"/quiz/{quiz.id}")

    assert response.status_code == 200
    assert b"Tuesday Tasting" in response.data
    assert b"Not Started" in response.data


def test_display_page(client, quiz):
    add_competitor(quiz, "Alice")
    set_state(quiz, QuizStateEnum.LOBBY_OPEN)

    response = client.get(f"/quiz/{quiz.id}/display")

    assert response.status_code == 200
    assert f'quizRoomName = "quiz{quiz.id}"'.encode() in response.data
    assert b"current_quiz_state = 1;" in response.data
    assert b"Alice" in response.data


def test_join_page_for_new_visitor(client, quiz):
    response = client.get(f"/quiz/{quiz.id}/join")
    assert response.status_code == 200
    assert f"/quiz/{quiz.id}/createplayer".encode() in response.data


def test_join_redirects_returning_competitor_to_player_page(client, quiz):
    login_as(client, add_competitor(quiz, "Alice"))

    response = client.get(f"/quiz/{quiz.id}/join")

    assert response.status_code == 302
    assert response.location == f"/quiz/{quiz.id}/player"


def test_join_ignores_cookie_from_another_quiz(client, quiz, other_quiz):
    login_as(client, add_competitor(other_quiz, "Alice"))
    assert client.get(f"/quiz/{quiz.id}/join").status_code == 200


def test_join_ignores_cookie_for_deleted_competitor(client, quiz):
    client.set_cookie(WINE_QUIZ_COOKIE_NAME, "9999")
    assert client.get(f"/quiz/{quiz.id}/join").status_code == 200


def test_checkname_available(client, quiz):
    response = client.post(f"/quiz/{quiz.id}/checkname", json={"name": "Alice"})
    assert response.get_json() == {"success": True, "valid": True}


def test_checkname_taken(client, quiz):
    add_competitor(quiz, "Alice")
    response = client.post(f"/quiz/{quiz.id}/checkname", json={"name": "Alice"})
    assert response.get_json() == {"success": True, "valid": False}


def test_checkname_is_scoped_to_quiz(client, quiz, other_quiz):
    add_competitor(other_quiz, "Alice")
    response = client.post(f"/quiz/{quiz.id}/checkname", json={"name": "Alice"})
    assert response.get_json()["valid"] is True


def test_checkname_without_name(client, quiz):
    response = client.post(f"/quiz/{quiz.id}/checkname", json={})
    assert response.get_json() == {"success": True, "valid": False}


def test_checkname_requires_json(client, quiz):
    response = client.post(f"/quiz/{quiz.id}/checkname", data={"name": "Alice"})
    assert response.status_code == 500


def test_create_player(client, quiz):
    response = client.post(f"/quiz/{quiz.id}/createplayer",
                           data={"competitor_name": "Alice"})

    [alice] = Competitor.query.all()
    assert (alice.name, alice.quiz_id, alice.points) == ("Alice", quiz.id, 0)
    assert response.status_code == 302
    assert response.location == f"/quiz/{quiz.id}/player"
    assert client.get_cookie(WINE_QUIZ_COOKIE_NAME).value == str(alice.id)


def test_create_player_with_taken_name(client, quiz):
    add_competitor(quiz, "Alice")

    response = client.post(f"/quiz/{quiz.id}/createplayer",
                           data={"competitor_name": "Alice"}, follow_redirects=True)

    assert Competitor.query.count() == 1
    assert response.request.path == f"/quiz/{quiz.id}/join"
    assert b"Player name is already used" in response.data
    assert client.get_cookie(WINE_QUIZ_COOKIE_NAME) is None


def test_create_player_without_name(client, quiz):
    response = client.post(f"/quiz/{quiz.id}/createplayer", data={})

    assert response.status_code == 302
    assert response.location == f"/quiz/{quiz.id}/join"
    assert Competitor.query.count() == 0


def test_player_page(client, templates, quiz):
    alice = add_competitor(quiz, "Alice")
    login_as(client, alice)

    response = client.get(f"/quiz/{quiz.id}/player")

    assert response.status_code == 200
    [(name, context)] = templates
    assert name == "quiz/player.html"
    assert context["competitor"].id == alice.id
    assert context["quiz"].id == quiz.id


def test_player_page_without_cookie_redirects_to_join(client, quiz):
    response = client.get(f"/quiz/{quiz.id}/player")
    assert response.status_code == 302
    assert response.location == f"/quiz/{quiz.id}/join"


def test_player_page_with_other_quizs_cookie_redirects_to_join(client, quiz, other_quiz):
    login_as(client, add_competitor(other_quiz, "Alice"))
    response = client.get(f"/quiz/{quiz.id}/player")
    assert response.location == f"/quiz/{quiz.id}/join"


def test_kill_cookie(client, quiz):
    login_as(client, add_competitor(quiz, "Alice"))

    response = client.get("/quiz/killcookie")

    assert response.status_code == 302
    assert response.location == "/"
    assert client.get_cookie(WINE_QUIZ_COOKIE_NAME) is None


# Submitting and retrieving answers

@pytest.fixture
def alice(client, quiz):
    """
    A competitor who is logged in on the test client
    """
    alice = add_competitor(quiz, "Alice")
    login_as(client, alice)
    return alice


def test_submit_free_response(client, quiz, alice, grapes, countries):
    set_state(quiz, QuizStateEnum.FREE_RESPONSE)

    response = client.post(f"/quiz/{quiz.id}/submit_free_response",
                           json=answer_payload(grapes, countries))

    assert response.get_json() == {"success": True}
    [answer] = Answer.query.all()
    assert answer.free_response is True
    assert answer.competitor_id == alice.id
    assert answer.quiz_item_id == quiz.items[0].id
    assert (answer.grape_id, answer.country_id, answer.vintage) == (
        grapes["Merlot"].id, countries["France"].id, 2015)


def test_submit_multiple_choice(client, quiz, alice, grapes, countries):
    set_state(quiz, QuizStateEnum.MULTIPLE_CHOICE)

    response = client.post(f"/quiz/{quiz.id}/submit_multiple_choice",
                           json=answer_payload(grapes, countries))

    assert response.get_json() == {"success": True}
    assert Answer.query.one().free_response is False


def test_submit_answers_to_current_item(client, quiz, alice, grapes, countries):
    set_state(quiz, QuizStateEnum.FREE_RESPONSE, current_item=1)

    client.post(f"/quiz/{quiz.id}/submit_free_response",
                json=answer_payload(grapes, countries, "Chardonnay", "Chile", 2020))

    assert Answer.query.one().quiz_item_id == quiz.items[1].id


def test_resubmitting_updates_the_answer(client, quiz, alice, grapes, countries):
    set_state(quiz, QuizStateEnum.FREE_RESPONSE)
    url = f"/quiz/{quiz.id}/submit_free_response"

    client.post(url, json=answer_payload(grapes, countries, "Syrah", None, None))
    client.post(url, json=answer_payload(grapes, countries, "Merlot", "Italy", 2012))

    [answer] = Answer.query.all()
    assert (answer.grape_id, answer.country_id, answer.vintage) == (
        grapes["Merlot"].id, countries["Italy"].id, 2012)


def test_free_response_and_multiple_choice_are_stored_separately(
        client, quiz, alice, grapes, countries):
    set_state(quiz, QuizStateEnum.FREE_RESPONSE)
    client.post(f"/quiz/{quiz.id}/submit_free_response",
                json=answer_payload(grapes, countries, "Syrah"))
    set_state(quiz, QuizStateEnum.MULTIPLE_CHOICE)
    client.post(f"/quiz/{quiz.id}/submit_multiple_choice",
                json=answer_payload(grapes, countries, "Merlot"))

    answers = {a.free_response: a.grape_id for a in Answer.query.all()}
    assert answers == {True: grapes["Syrah"].id, False: grapes["Merlot"].id}


def test_complete_answer_is_announced(client, socket_client, quiz, alice, grapes, countries):
    set_state(quiz, QuizStateEnum.FREE_RESPONSE)
    socket_client.emit("join", {"room": f"quiz{quiz.id}", "competitor": -1})
    socket_client.get_received()

    client.post(f"/quiz/{quiz.id}/submit_free_response",
                json=answer_payload(grapes, countries))

    assert events_named(socket_client.get_received(), "full_answer_received") == [
        {"id": alice.id, "name": "Alice"}
    ]


def test_partial_answer_is_not_announced(client, socket_client, quiz, alice, grapes, countries):
    set_state(quiz, QuizStateEnum.FREE_RESPONSE)
    socket_client.emit("join", {"room": f"quiz{quiz.id}", "competitor": -1})
    socket_client.get_received()

    client.post(f"/quiz/{quiz.id}/submit_free_response",
                json=answer_payload(grapes, countries, vintage=None))

    assert events_named(socket_client.get_received(), "full_answer_received") == []


@pytest.mark.parametrize("kind", ["submit_free_response", "submit_multiple_choice"])
def test_submit_requires_competitor_cookie(client, quiz, grapes, countries, kind):
    set_state(quiz, QuizStateEnum.FREE_RESPONSE)
    response = client.post(f"/quiz/{quiz.id}/{kind}", json=answer_payload(grapes, countries))

    assert response.status_code == 500
    assert Answer.query.count() == 0


@pytest.mark.parametrize("kind", ["submit_free_response", "submit_multiple_choice"])
def test_submit_rejects_competitor_from_another_quiz(
        client, quiz, other_quiz, grapes, countries, kind):
    set_state(quiz, QuizStateEnum.FREE_RESPONSE)
    login_as(client, add_competitor(other_quiz, "Mallory"))

    response = client.post(f"/quiz/{quiz.id}/{kind}", json=answer_payload(grapes, countries))

    assert response.status_code == 500
    assert Answer.query.count() == 0


@pytest.mark.parametrize("kind", ["submit_free_response", "submit_multiple_choice"])
def test_submit_requires_json(client, quiz, alice, kind):
    set_state(quiz, QuizStateEnum.FREE_RESPONSE)
    response = client.post(f"/quiz/{quiz.id}/{kind}", data={"grape": "1"})
    assert response.status_code == 500


@pytest.mark.xfail(strict=True,
                   reason="Known bug: answers are accepted after the answering period, "
                          "so a player can change answers once the correct ones are shown")
@pytest.mark.parametrize("state, kind", [
    (QuizStateEnum.MULTIPLE_CHOICE, "submit_free_response"),
    (QuizStateEnum.QUESTION_RECAP, "submit_free_response"),
    (QuizStateEnum.QUESTION_RECAP, "submit_multiple_choice"),
])
def test_submit_rejected_outside_its_answering_period(
        client, quiz, alice, grapes, countries, state, kind):
    set_state(quiz, state)

    response = client.post(f"/quiz/{quiz.id}/{kind}", json=answer_payload(grapes, countries))

    assert response.status_code >= 400
    assert Answer.query.count() == 0


def test_get_answer_when_none_submitted(client, quiz, alice):
    set_state(quiz, QuizStateEnum.FREE_RESPONSE)
    assert client.get(f"/quiz/{quiz.id}/answer").get_json() == {"success": True}


def test_get_answer_returns_answer_for_current_period(client, quiz, alice, grapes, countries):
    item = quiz.items[0]
    fr = add_answer(alice, item, grapes["Syrah"], countries["Italy"], 2012, free_response=True)
    mc = add_answer(alice, item, grapes["Merlot"], None, None, free_response=False)

    set_state(quiz, QuizStateEnum.FREE_RESPONSE)
    data = client.get(f"/quiz/{quiz.id}/answer").get_json()
    assert data["answer"]["id"] == fr.id
    assert data["answer"]["vintage"] == 2012

    set_state(quiz, QuizStateEnum.MULTIPLE_CHOICE)
    data = client.get(f"/quiz/{quiz.id}/answer").get_json()
    assert data["answer"]["id"] == mc.id
    assert data["answer"]["country_id"] is None


@pytest.mark.parametrize("state", [
    QuizStateEnum.NOT_STARTED,
    QuizStateEnum.LOBBY_OPEN,
    QuizStateEnum.QUESTION_RECAP,
    QuizStateEnum.QUIZ_RECAP,
])
def test_get_answer_only_during_answering_periods(client, quiz, alice, state):
    set_state(quiz, state)
    assert client.get(f"/quiz/{quiz.id}/answer").status_code == 500


def test_get_answer_requires_competitor_cookie(client, quiz):
    set_state(quiz, QuizStateEnum.FREE_RESPONSE)
    assert client.get(f"/quiz/{quiz.id}/answer").status_code == 500


# Moderator

def test_join_as_moderator_page(client, quiz):
    response = client.get(f"/quiz/{quiz.id}/join_as_mod")
    assert response.status_code == 200
    assert f"/quiz/{quiz.id}/moderator".encode() in response.data


def test_moderator_with_code_in_form(client, quiz):
    response = client.post(f"/quiz/{quiz.id}/moderator",
                           data={"moderator_code": "secret-mod"})
    assert response.status_code == 200


def test_moderator_with_code_in_query(client, quiz):
    assert client.get(f"/quiz/{quiz.id}/moderator?modcode=secret-mod").status_code == 200


@pytest.mark.parametrize("request_kwargs", [
    {"method": "POST", "data": {"moderator_code": "wrong"}},
    {"method": "GET", "query_string": {"modcode": "wrong"}},
    {"method": "GET"},
])
def test_moderator_requires_correct_code(client, quiz, request_kwargs):
    response = client.open(f"/quiz/{quiz.id}/moderator", **request_kwargs)
    assert response.status_code == 401


def test_moderator_code_for_another_quiz_is_rejected(client, quiz, other_quiz):
    response = client.get(f"/quiz/{quiz.id}/moderator?modcode=other-mod")
    assert response.status_code == 401


# Results

def test_leaderboard_is_sorted_by_points(client, templates, quiz):
    for name, points in [("Alice", 20), ("Bob", 45), ("Carol", 5)]:
        competitor = add_competitor(quiz, name)
        competitor.points = points
    db.session.commit()

    response = client.get(f"/quiz/{quiz.id}/leaderboard")

    assert response.status_code == 200
    [(_, context)] = templates
    assert [c.name for c in context["competitors"]] == ["Bob", "Alice", "Carol"]
    assert response.data.index(b"Bob") < response.data.index(b"Alice") < response.data.index(b"Carol")


def test_rescore(client, quiz, grapes, countries):
    alice = add_competitor(quiz, "Alice")
    add_answer(alice, quiz.items[0], grapes["Merlot"], countries["France"], None)

    response = client.get(f"/quiz/{quiz.id}/rescore")

    assert response.status_code == 302
    assert response.location == f"/quiz/{quiz.id}/leaderboard"
    db.session.expire_all()
    assert db.session.get(Competitor, alice.id).points == 20


def test_merge_competitors(client, quiz, grapes, countries):
    item1, item2 = quiz.items
    alice = add_competitor(quiz, "Alice")
    alice_again = add_competitor(quiz, "Alice 2")
    add_answer(alice, item1, grapes["Merlot"], countries["France"], 2015)
    add_answer(alice_again, item2, grapes["Chardonnay"], countries["Chile"], 2020)
    alice_id, dup_id = alice.id, alice_again.id

    response = client.get(f"/quiz/{quiz.id}/merge/{dup_id}/to/{alice_id}")

    assert response.status_code == 302
    assert response.location == f"/quiz/{quiz.id}/leaderboard"
    db.session.expire_all()
    assert db.session.get(Competitor, dup_id) is None
    assert {a.competitor_id for a in Answer.query.all()} == {alice_id}

    client.get(f"/quiz/{quiz.id}/rescore")
    db.session.expire_all()
    assert db.session.get(Competitor, alice_id).points == 60


@pytest.mark.parametrize("path", [
    "/quiz/9999/merge/1/to/2",
    "/quiz/{quiz}/merge/9999/to/{alice}",
    "/quiz/{quiz}/merge/{alice}/to/9999",
])
def test_merge_competitors_not_found(client, quiz, path):
    alice = add_competitor(quiz, "Alice")
    url = path.format(quiz=quiz.id, alice=alice.id)
    assert client.get(url).status_code == 404
    assert Competitor.query.count() == 1


def test_breakdown(client, templates, quiz, grapes, countries):
    item1, item2 = quiz.items
    alice = add_competitor(quiz, "Alice")
    # Wine 1: free response grape + vintage right, multiple choice all right
    add_answer(alice, item1, grapes["Merlot"], countries["Italy"], 2015, free_response=True)
    add_answer(alice, item1, grapes["Merlot"], countries["France"], 2015, free_response=False)
    # Wine 2: never answered

    response = client.get(f"/quiz/{quiz.id}/competitor/{alice.id}/breakdown")

    assert response.status_code == 200
    [(_, context)] = templates
    wine1, wine2 = context["wines"]
    assert wine1 == {
        "wine_idx": 1,
        "item_id": item1.id,
        "grape_id": grapes["Merlot"].id,
        "country_id": countries["France"].id,
        "vintage": 2015,
        "fr_grape_id": grapes["Merlot"].id,
        "fr_country_id": countries["Italy"].id,
        "fr_vintage": 2015,
        "mr_grape_id": grapes["Merlot"].id,
        "mr_country_id": countries["France"].id,
        "mr_vintage": 2015,
        "grape_points": 15,
        "country_points": 5,
        "vintage_points": 15,
    }
    assert wine2["wine_idx"] == 2
    assert (wine2["grape_points"], wine2["country_points"], wine2["vintage_points"]) == (0, 0, 0)
    assert "fr_grape_id" not in wine2


@pytest.mark.parametrize("path", [
    "/quiz/9999/competitor/{alice}/breakdown",
    "/quiz/{quiz}/competitor/9999/breakdown",
])
def test_breakdown_not_found(client, quiz, path):
    alice = add_competitor(quiz, "Alice")
    assert client.get(path.format(quiz=quiz.id, alice=alice.id)).status_code == 404


def test_answer_stats(client, templates, quiz, grapes, countries):
    item = quiz.items[0]
    alice = add_competitor(quiz, "Alice")
    add_answer(alice, item, grapes["Merlot"], countries["France"], 2015)

    response = client.get(f"/quiz/{quiz.id}/answer/{item.id}/stats")

    assert response.status_code == 200
    [(_, context)] = templates
    assert context["item"].id == item.id
    assert context["stats"]["free_response"]["grapes"] == {grapes["Merlot"].id: 1}


def test_answer_stats_for_another_quizs_item(client, quiz, other_quiz):
    item = quiz.items[0]
    assert client.get(f"/quiz/{other_quiz.id}/answer/{item.id}/stats").status_code == 404
    assert client.get(f"/quiz/{quiz.id}/answer/9999/stats").status_code == 404


def test_competitors_answer_status(client, quiz, grapes, countries):
    item = quiz.items[0]
    alice = add_competitor(quiz, "Alice")  # complete free response answer
    bob = add_competitor(quiz, "Bob")  # partial free response answer
    carol = add_competitor(quiz, "Carol")  # only a multiple choice answer
    add_answer(alice, item, grapes["Merlot"], countries["France"], 2015)
    add_answer(bob, item, grapes["Merlot"], None, 2015)
    add_answer(carol, item, grapes["Merlot"], countries["France"], 2015, free_response=False)

    set_state(quiz, QuizStateEnum.FREE_RESPONSE)
    data = client.get(f"/quiz/{quiz.id}/competitors").get_json()
    assert data == {"success": True, "competitors": [
        {"id": alice.id, "name": "Alice", "answered": True},
        {"id": bob.id, "name": "Bob", "answered": False},
        {"id": carol.id, "name": "Carol", "answered": False},
    ]}

    set_state(quiz, QuizStateEnum.MULTIPLE_CHOICE)
    data = client.get(f"/quiz/{quiz.id}/competitors").get_json()
    assert [c["answered"] for c in data["competitors"]] == [False, False, True]

    set_state(quiz, QuizStateEnum.QUESTION_RECAP)
    data = client.get(f"/quiz/{quiz.id}/competitors").get_json()
    assert [c["answered"] for c in data["competitors"]] == [False, False, False]


@pytest.mark.parametrize("path", ["leaderboard", "competitors", "rescore"])
def test_missing_quiz_is_404(client, path):
    assert client.get(f"/quiz/9999/{path}").status_code == 404


@pytest.mark.xfail(strict=True,
                   reason="Known bug: these pages don't check that the quiz exists and "
                          "crash (500) or render an empty page instead of returning 404")
@pytest.mark.parametrize("method, path", [
    ("get", ""),
    ("get", "/join"),
    ("get", "/display"),
    ("get", "/join_as_mod"),
    ("get", "/moderator?modcode=x"),
    ("post", "/checkname"),
    ("post", "/createplayer"),
])
def test_pages_for_missing_quiz_are_404(app, client, method, path):
    app.config["PROPAGATE_EXCEPTIONS"] = False  # see the 500 a browser would get
    response = getattr(client, method)(f"/quiz/9999{path}", json={"name": "Z"})
    assert response.status_code == 404


@pytest.mark.parametrize("cookie", ["not-a-number", ""])
def test_malformed_cookie_is_treated_as_no_competitor(client, quiz, cookie):
    client.set_cookie(WINE_QUIZ_COOKIE_NAME, cookie)

    assert client.get(f"/quiz/{quiz.id}/join").status_code == 200
    assert client.get(f"/quiz/{quiz.id}/player").location == f"/quiz/{quiz.id}/join"
