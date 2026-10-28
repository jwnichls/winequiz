"""
End-to-end tests that play real games: several players, a moderator and
the large screen display, each in their own headless browser.
"""

import os

import pytest
from playwright.sync_api import expect

from winequiz.db import db, Competitor, Quiz, QuizStateEnum


RED_GRAPES = ["", "Merlot", "Pinot Noir", "Syrah", "Malbec"]
WHITE_GRAPES = ["", "Chardonnay", "Riesling", "Sauvignon Blanc", "Chenin Blanc"]


def everyone_sees(screens, section):
    for screen in screens:
        screen.expect_showing(section)


def test_full_game(screens, quiz):
    moderator = screens.moderator(quiz).join()
    display = screens.display(quiz).join()
    alice = screens.player(quiz, "Alice").join()
    bob = screens.player(quiz, "Bob").join()
    carol = screens.player(quiz, "Carol").join()
    players = [alice, bob, carol]
    everyone = players + [display]

    expect(moderator.competitors()).to_have_text(["Alice", "Bob", "Carol"])
    expect(moderator.page.locator("#quizstate")).to_have_text("Not Started")

    # Lobby: everyone can see who else is here
    moderator.advance("Lobby Open")
    everyone_sees(everyone, "lobby")
    expect(alice.page.locator("#competitors li")).to_have_text(["Bob", "Carol"])
    expect(display.section("lobby").locator("p.competitor-name")).to_have_text(
        ["Alice", "Bob", "Carol"])

    # Wine 1 (Merlot, France, 2015), free response: only red grapes offered
    moderator.advance("Free Response Period")
    everyone_sees(everyone, "free-response")
    for player in players:
        expect(player.page.locator("#grape option")).to_have_text(RED_GRAPES)

    alice.answer_free_response("Merlot", "France", 2015)  # 30
    bob.answer_free_response("Merlot", "Italy", 2012)  # 10
    # Carol doesn't answer

    expect(display.answered_dot("free-response", "Alice")).to_have_class("dot answered")
    expect(display.answered_dot("free-response", "Bob")).to_have_class("dot answered")
    expect(display.answered_dot("free-response", "Carol")).to_have_class("dot no-answer")

    # Wine 1, multiple choice: the real answer and three alternatives
    moderator.advance("Multiple Choice Period")
    everyone_sees(everyone, "multiple-choice")
    expect(alice.page.locator("#grape_radio label span")).to_have_text(
        ["Merlot", "Pinot Noir", "Syrah", "Malbec"])
    expect(alice.page.locator("#country_radio label span")).to_have_text(
        ["France", "Italy", "Chile", "Australia"])
    expect(alice.page.locator("#vintage_radio label span")).to_have_text(
        ["2010", "2012", "2015", "2018"])
    expect(display.answered_dot("multiple-choice", "Alice")).to_have_class("dot no-answer")

    alice.answer_multiple_choice("Merlot", "France", 2015)  # 15
    bob.answer_multiple_choice("Syrah", "France", 2018)  # 5
    carol.answer_multiple_choice("Merlot", "Italy", 2010)  # 5

    for name in ["Alice", "Bob", "Carol"]:
        expect(display.answered_dot("multiple-choice", name)).to_have_class("dot answered")

    # Wine 1 recap: scores for this wine, but the answers stay secret until
    # the end of the competition
    moderator.advance("Question Recap")
    everyone_sees(everyone, "question-recap")
    wine1_scores = [("Alice", 45), ("Bob", 15), ("Carol", 5)]
    for screen in everyone:
        assert screen.scoreboard("#question_scoreboard", 3) == wine1_scores
    expect(display.section("question-recap")).to_contain_text(
        "Correct answers will be revealed at the end of the competition")
    expect(display.page.locator("#correct_grape")).to_have_count(0)

    # Wine 2 (Chardonnay, Chile, 2020): a white, with a fresh form
    moderator.advance("Free Response Period")
    everyone_sees(everyone, "free-response")
    expect(alice.page.locator("#grape option")).to_have_text(WHITE_GRAPES)
    expect(alice.page.locator("small.free-success")).to_be_hidden()
    expect(alice.page.locator("#grape")).to_have_value("-1")

    alice.answer_free_response("Riesling", "Chile", 2019)  # 10
    bob.answer_free_response("Chardonnay", "Chile", 2020)  # 30
    carol.answer_free_response("Chardonnay", "France", 2020)  # 20

    moderator.advance("Multiple Choice Period")
    everyone_sees(everyone, "multiple-choice")
    alice.answer_multiple_choice("Chardonnay", "Chile", 2019)  # 10
    # Bob doesn't answer
    carol.answer_multiple_choice("Chardonnay", "Chile", 2020)  # 15

    moderator.advance("Question Recap")
    for screen in everyone:
        assert screen.scoreboard("#question_scoreboard", 3) == [
            ("Carol", 35), ("Bob", 30), ("Alice", 20)]

    # Final results
    moderator.advance("Quiz Recap")
    everyone_sees(everyone, "quiz-recap")
    final_scores = [("Alice", 65), ("Bob", 45), ("Carol", 40)]
    for screen in everyone:
        assert screen.scoreboard("#final_scoreboard", 3) == final_scores

    db.session.expire_all()
    assert db.session.get(Quiz, quiz.id).state == QuizStateEnum.QUIZ_RECAP
    saved = {c.name: c.points for c in Competitor.query.filter_by(quiz_id=quiz.id)}
    assert saved == dict(final_scores)

    leaderboard = alice.context.new_page()
    leaderboard.goto(alice.url("/leaderboard"))
    expect(leaderboard.locator("tbody tr td:first-child")).to_have_text(["Alice", "Bob", "Carol"])


def test_moderator_can_step_back(screens, quiz):
    moderator = screens.moderator(quiz).join()
    alice = screens.player(quiz, "Alice").join()

    moderator.advance("Lobby Open")
    moderator.advance("Free Response Period")
    alice.answer_free_response("Merlot", "France", 2015)
    moderator.advance("Multiple Choice Period")
    alice.expect_showing("multiple-choice")

    moderator.reverse("Free Response Period")

    alice.expect_showing("free-response")
    # The page reloads the answer that was already submitted
    expect(alice.page.locator("#grape")).to_have_value(str(quiz.items[0].grape_id))
    expect(alice.page.locator("#vintage")).to_have_value("2015")


def test_player_who_reloads_keeps_their_answer(screens, quiz):
    moderator = screens.moderator(quiz).join()
    alice = screens.player(quiz, "Alice").join()
    moderator.advance("Lobby Open")
    moderator.advance("Free Response Period")
    alice.answer_free_response("Syrah", "Chile", 2012)

    with alice.joined():
        alice.page.reload()

    alice.expect_showing("free-response")
    expect(alice.page.locator("#grape option:checked")).to_have_text("Syrah")
    expect(alice.page.locator("#country option:checked")).to_have_text("Chile")
    expect(alice.page.locator("#vintage")).to_have_value("2012")

    # Coming back through the join link goes straight to the game
    with alice.joined():
        alice.page.goto(alice.url("/join"))
    expect(alice.page).to_have_url(alice.url("/player"))


def test_late_joiner_lands_in_current_question(screens, quiz):
    moderator = screens.moderator(quiz).join()
    alice = screens.player(quiz, "Alice").join()
    moderator.advance("Lobby Open")
    moderator.advance("Free Response Period")

    dave = screens.player(quiz, "Dave").join()

    dave.expect_showing("free-response")
    expect(dave.page.locator("#grape option")).to_have_text(RED_GRAPES)
    expect(moderator.competitors()).to_have_text(["Alice", "Dave"])
    dave.answer_free_response("Merlot", "France", 2015)
    expect(alice.page.locator("#competitors li")).to_have_text(["Dave"])


def test_taken_name_is_rejected(screens, quiz):
    screens.player(quiz, "Alice").join()
    impostor = screens.player(quiz, "Alice")

    impostor.page.goto(impostor.url("/join"))
    impostor.page.fill("#competitor_name", "Alice")
    impostor.page.click("#join")

    expect(impostor.page).to_have_url(impostor.url("/join"))
    expect(impostor.page.locator(".alert-warning")).to_have_text("Player name is already used...sorry!")


def test_player_who_leaves_is_removed_from_lists(screens, quiz):
    moderator = screens.moderator(quiz).join()
    alice = screens.player(quiz, "Alice").join()
    bob = screens.player(quiz, "Bob").join()
    moderator.advance("Lobby Open")
    expect(moderator.competitors()).to_have_text(["Alice", "Bob"])
    expect(alice.page.locator("#competitors li")).to_have_text(["Bob"])

    bob.close()

    expect(moderator.competitors()).to_have_text(["Alice"])
    expect(alice.page.locator("#competitors li")).to_have_count(0)


@pytest.mark.skipif(not os.getenv("E2E_REDIS_URL"),
                    reason="presence tracking needs Redis (set E2E_REDIS_URL)")
def test_player_with_two_tabs_stays_until_both_close(screens, quiz):
    moderator = screens.moderator(quiz).join()
    alice = screens.player(quiz, "Alice").join()
    second_tab = alice.context.new_page()
    with second_tab.expect_console_message(
            lambda message: message.text.startswith("Quiz state changed!")):
        second_tab.goto(alice.url("/player"))
    expect(moderator.competitors()).to_have_text(["Alice"])

    alice.page.close()
    # Give a wrongly announced departure time to arrive
    moderator.page.wait_for_timeout(1000)
    expect(moderator.competitors()).to_have_text(["Alice"])

    second_tab.close()
    expect(moderator.competitors()).to_have_count(0)


def test_wrong_moderator_code_is_refused(screens, quiz):
    moderator = screens.moderator(quiz)
    moderator.page.goto(moderator.url("/join_as_mod"))
    moderator.page.fill("#moderator_code", "guess")

    with moderator.page.expect_response(lambda r: r.url.endswith("/moderator")) as response:
        moderator.page.click("#join")

    assert response.value.status == 401
