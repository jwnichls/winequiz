"""
Tests for the index, admin and API routes
"""

import pytest

from winequiz.db import db, Quiz, QuizItem, QuizStateEnum


def new_quiz_form(grapes, countries, wines=2, **overrides):
    """
    Form data like the new quiz page submits
    """
    g = list(grapes.values())
    c = list(countries.values())
    form = {
        "name": "Friday Flight",
        "moderator_code": "flight-mod",
        "duration_free_response": "90",
        "duration_multiple_choice": "45",
    }
    for i in range(1, wines + 1):
        form.update({
            f"grape_{i}": str(g[i - 1].id),
            f"country_{i}": str(c[i - 1].id),
            f"vintage_{i}": str(2010 + i),
        })
        for j in range(3):
            form.update({
                f"alt_grape_{i}_{j}": str(g[(i + j) % len(g)].id),
                f"alt_country_{i}_{j}": str(c[(i + j) % len(c)].id),
                f"alt_vintage_{i}_{j}": str(2000 + j),
            })
    form.update(overrides)
    return form


def test_index_lists_only_active_quizzes(client, templates, grapes, countries):
    by_state = {}
    for state in QuizStateEnum:
        quiz = Quiz(name=f"Quiz {state.name}", moderator_code="m", state=state)
        db.session.add(quiz)
        by_state[state] = quiz
    db.session.commit()

    response = client.get("/")

    assert response.status_code == 200
    [(name, context)] = templates
    assert name == "index/index.html"
    listed = {quiz.state for quiz in context["quizes"]}
    assert listed == {
        QuizStateEnum.LOBBY_OPEN,
        QuizStateEnum.FREE_RESPONSE,
        QuizStateEnum.MULTIPLE_CHOICE,
        QuizStateEnum.QUESTION_RECAP,
    }
    assert b"Quiz LOBBY_OPEN" in response.data
    assert b"Quiz NOT_STARTED" not in response.data
    assert b"Quiz QUIZ_RECAP" not in response.data


def test_index_with_no_quizzes(client):
    assert client.get("/").status_code == 200


def test_new_quiz_form(client):
    response = client.get("/new")
    assert response.status_code == 200
    assert b"<form" in response.data


def test_create_quiz(client, templates, grapes, countries):
    response = client.post("/new", data=new_quiz_form(grapes, countries, wines=2))

    assert response.status_code == 200
    assert b"Friday Flight" in response.data
    [quiz] = Quiz.query.all()
    [(name, context)] = templates
    assert name == "index/quiz_success.html"
    assert context["quiz"].id == quiz.id
    assert quiz.name == "Friday Flight"
    assert quiz.moderator_code == "flight-mod"
    assert quiz.duration_free_response == 90
    assert quiz.duration_multiple_choice == 45
    assert quiz.state is QuizStateEnum.NOT_STARTED

    g = list(grapes.values())
    c = list(countries.values())
    assert [item.order for item in quiz.items] == [1, 2]
    first = quiz.items[0]
    assert (first.grape_id, first.country_id, first.vintage) == (g[0].id, c[0].id, 2011)
    assert [first.grape_alternate_one, first.grape_alternate_two,
            first.grape_alternate_three] == [g[1].id, g[2].id, g[3].id]
    assert [first.country_alternate_one, first.country_alternate_two,
            first.country_alternate_three] == [c[1].id, c[2].id, c[3].id]
    assert [first.vintage_alternate_one, first.vintage_alternate_two,
            first.vintage_alternate_three] == [2000, 2001, 2002]


def test_create_quiz_uses_highest_wine_number(client, grapes, countries):
    client.post("/new", data=new_quiz_form(grapes, countries, wines=4))
    assert QuizItem.query.count() == 4


def test_create_quiz_with_no_wines(client, grapes, countries):
    response = client.post("/new", data=new_quiz_form(grapes, countries, wines=0))

    assert response.status_code == 200
    assert Quiz.query.one().items == []


def test_create_quiz_rejects_bad_wine_number(client, grapes, countries):
    form = new_quiz_form(grapes, countries, wines=1, grape_x="1")

    assert client.post("/new", data=form).status_code == 500
    assert Quiz.query.count() == 0


def test_admin_index(client):
    assert client.get("/admin/").status_code == 200


def test_admin_grapes_lists_grapes(client, templates, grapes):
    response = client.get("/admin/grapes")

    assert response.status_code == 200
    assert {g.name for g in templates[0][1]["grapes"]} == set(grapes)
    for name in grapes:
        assert name.encode() in response.data


def test_admin_countries_lists_countries(client, templates, countries):
    response = client.get("/admin/countries")

    assert response.status_code == 200
    assert {c.name for c in templates[0][1]["countries"]} == set(countries)
    assert b"Australia" in response.data


@pytest.mark.parametrize("method, url", [
    ("put", "/admin/grapes"),
    ("delete", "/admin/grapes/1"),
    ("put", "/admin/countries"),
    ("delete", "/admin/countries/1"),
])
def test_admin_editing_is_not_implemented(client, method, url):
    response = getattr(client, method)(url)

    assert response.status_code == 200
    assert response.get_json() == {"success": False, "message": "Not yet implemented"}


def test_api_grapes(client, grapes):
    data = client.get("/api/v1/grapes").get_json()

    assert data["success"] is True
    by_name = {g["name"]: g for g in data["grapes"]}
    assert set(by_name) == set(grapes)
    assert by_name["Merlot"] == {
        "id": grapes["Merlot"].id, "name": "Merlot", "color": 1, "blendable": True,
    }
    assert by_name["Riesling"]["color"] == 0


def test_api_countries(client, countries):
    data = client.get("/api/v1/countries").get_json()

    assert data["success"] is True
    by_name = {c["name"]: c for c in data["countries"]}
    assert by_name["France"] == {"id": countries["France"].id, "name": "France", "old_world": True}
    assert by_name["Chile"]["old_world"] is False


def test_api_with_empty_database(client):
    assert client.get("/api/v1/grapes").get_json() == {"success": True, "grapes": []}
    assert client.get("/api/v1/countries").get_json() == {"success": True, "countries": []}


def test_unknown_page_is_404(client):
    assert client.get("/no-such-page").status_code == 404
