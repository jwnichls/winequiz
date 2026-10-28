"""
Tests for the scoring logic in winequiz.scoring
"""

import pytest

from winequiz.db import db, Competitor
from winequiz.scoring import (
    calculate_points_for_answer,
    calculate_points_for_item,
    calculate_total_points,
    convert_to_competitor_hash,
    get_stats_for_item,
    sum_score_hashes,
    FREE_RESPONSE_CORRECT,
    MULTIPLE_CHOICE_CORRECT,
)

from tests.helpers import add_answer, add_competitor


def test_point_values():
    assert FREE_RESPONSE_CORRECT == 10
    assert MULTIPLE_CHOICE_CORRECT == 5


@pytest.mark.parametrize("grape_ok, country_ok, vintage_ok", [
    (False, False, False),
    (True, False, False),
    (False, True, False),
    (False, False, True),
    (True, True, False),
    (True, True, True),
])
@pytest.mark.parametrize("free_response, value", [
    (True, FREE_RESPONSE_CORRECT),
    (False, MULTIPLE_CHOICE_CORRECT),
])
def test_points_for_answer(quiz, grapes, countries, free_response, value,
                           grape_ok, country_ok, vintage_ok):
    item = quiz.items[0]  # Merlot, France, 2015
    alice = add_competitor(quiz, "Alice")
    answer = add_answer(
        alice,
        item,
        grapes["Merlot"] if grape_ok else grapes["Syrah"],
        countries["France"] if country_ok else countries["Italy"],
        2015 if vintage_ok else 2012,
        free_response=free_response,
    )

    expected = value * sum([grape_ok, country_ok, vintage_ok])
    assert calculate_points_for_answer(answer, item) == expected


def test_points_for_answer_to_a_different_item_is_zero(quiz, grapes, countries):
    item1, item2 = quiz.items
    alice = add_competitor(quiz, "Alice")
    answer = add_answer(alice, item1, grapes["Merlot"], countries["France"], 2015)

    assert calculate_points_for_answer(answer, item1) == 30
    assert calculate_points_for_answer(answer, item2) == 0


def test_points_for_empty_answer_is_zero(quiz):
    item = quiz.items[0]
    alice = add_competitor(quiz, "Alice")
    answer = add_answer(alice, item, None, None, None)

    assert calculate_points_for_answer(answer, item) == 0


def test_points_for_item_combines_free_response_and_multiple_choice(quiz, grapes, countries):
    item = quiz.items[0]
    alice = add_competitor(quiz, "Alice")
    bob = add_competitor(quiz, "Bob")
    carol = add_competitor(quiz, "Carol")

    # Alice: all correct in both rounds -> 30 + 15
    add_answer(alice, item, grapes["Merlot"], countries["France"], 2015, free_response=True)
    add_answer(alice, item, grapes["Merlot"], countries["France"], 2015, free_response=False)
    # Bob: wrong free response, grape and vintage right in multiple choice -> 0 + 10
    add_answer(bob, item, grapes["Syrah"], countries["Chile"], 2010, free_response=True)
    add_answer(bob, item, grapes["Merlot"], countries["Italy"], 2015, free_response=False)
    # Carol: never answered

    assert calculate_points_for_item(quiz, item) == {
        alice.id: 45,
        bob.id: 10,
        carol.id: 0,
    }


def test_points_for_item_only_counts_first_answer_of_each_kind(quiz, grapes, countries):
    item = quiz.items[0]
    alice = add_competitor(quiz, "Alice")
    add_answer(alice, item, grapes["Merlot"], countries["France"], 2015, free_response=True)
    add_answer(alice, item, grapes["Merlot"], countries["France"], 2015, free_response=True)
    add_answer(alice, item, grapes["Merlot"], None, None, free_response=False)
    add_answer(alice, item, grapes["Merlot"], None, None, free_response=False)

    assert calculate_points_for_item(quiz, item) == {alice.id: 30 + 5}


def test_points_for_item_ignores_other_items(quiz, grapes, countries):
    item1, item2 = quiz.items
    alice = add_competitor(quiz, "Alice")
    add_answer(alice, item2, grapes["Chardonnay"], countries["Chile"], 2020)

    assert calculate_points_for_item(quiz, item1) == {alice.id: 0}
    assert calculate_points_for_item(quiz, item2) == {alice.id: 30}


def test_points_for_item_with_no_competitors(quiz):
    assert calculate_points_for_item(quiz, quiz.items[0]) == {}


@pytest.mark.parametrize("hash1, hash2, expected", [
    ({}, {}, {}),
    ({1: 5}, {}, {1: 5}),
    ({}, {2: 7}, {2: 7}),
    ({1: 5, 2: 3}, {1: 10, 3: 1}, {1: 15, 2: 3, 3: 1}),
])
def test_sum_score_hashes(hash1, hash2, expected):
    assert sum_score_hashes(hash1, hash2) == expected


def test_sum_score_hashes_does_not_modify_inputs():
    hash1, hash2 = {1: 5}, {1: 10}
    sum_score_hashes(hash1, hash2)
    assert hash1 == {1: 5}
    assert hash2 == {1: 10}


def test_total_points_are_saved_to_competitors(quiz, grapes, countries):
    item1, item2 = quiz.items
    alice = add_competitor(quiz, "Alice")
    bob = add_competitor(quiz, "Bob")

    add_answer(alice, item1, grapes["Merlot"], countries["France"], 2015)  # 30
    add_answer(alice, item2, grapes["Chardonnay"], None, 2020)  # 20
    add_answer(alice, item2, grapes["Chardonnay"], countries["Chile"], 2020,
               free_response=False)  # 15
    add_answer(bob, item1, grapes["Syrah"], countries["France"], 2018)  # 10

    scores = calculate_total_points(quiz)

    assert scores == {alice.id: 65, bob.id: 10}
    db.session.expire_all()
    assert db.session.get(Competitor, alice.id).points == 65
    assert db.session.get(Competitor, bob.id).points == 10


def test_total_points_resets_stale_scores(quiz):
    alice = add_competitor(quiz, "Alice")
    alice.points = 999
    db.session.commit()

    assert calculate_total_points(quiz) == {alice.id: 0}
    db.session.expire_all()
    assert db.session.get(Competitor, alice.id).points == 0


def test_competitor_hash_is_sorted_by_score(quiz):
    alice = add_competitor(quiz, "Alice")
    bob = add_competitor(quiz, "Bob")
    carol = add_competitor(quiz, "Carol")

    leaderboard = convert_to_competitor_hash(quiz, {alice.id: 10, bob.id: 45})

    assert leaderboard == [
        {"id": bob.id, "name": "Bob", "score": 45},
        {"id": alice.id, "name": "Alice", "score": 10},
        {"id": carol.id, "name": "Carol", "score": 0},
    ]


def test_stats_for_item_counts_each_round_separately(quiz, grapes, countries):
    item = quiz.items[0]
    alice = add_competitor(quiz, "Alice")
    bob = add_competitor(quiz, "Bob")
    merlot, syrah = grapes["Merlot"].id, grapes["Syrah"].id
    france, italy = countries["France"].id, countries["Italy"].id

    add_answer(alice, item, grapes["Merlot"], countries["France"], 2015, free_response=True)
    add_answer(bob, item, grapes["Syrah"], countries["France"], 2012, free_response=True)
    add_answer(alice, item, grapes["Merlot"], countries["Italy"], 2015, free_response=False)
    add_answer(bob, item, grapes["Merlot"], countries["France"], 2015, free_response=False)
    # An answer to another item is not counted
    add_answer(bob, quiz.items[1], grapes["Syrah"], countries["Italy"], 1999)

    assert get_stats_for_item(quiz, item) == {
        "free_response": {
            "grapes": {merlot: 1, syrah: 1},
            "countries": {france: 2},
            "vintages": {2015: 1, 2012: 1},
        },
        "multiple_choice": {
            "grapes": {merlot: 2},
            "countries": {italy: 1, france: 1},
            "vintages": {2015: 2},
        },
    }


def test_stats_for_item_with_no_answers(quiz):
    empty = {"grapes": {}, "countries": {}, "vintages": {}}
    assert get_stats_for_item(quiz, quiz.items[0]) == {
        "free_response": empty,
        "multiple_choice": empty,
    }
