"""
Fixtures for the end-to-end browser tests.

These start the real app under gunicorn with the gevent worker (as the
Procfile does) and drive it with headless Chromium through Playwright.
They are skipped by a plain `pytest` run; run them with:

    uv run playwright install chromium   # once
    uv run pytest -m e2e

The server uses a SQLite file by default. Set E2E_DATABASE_URL to use
PostgreSQL, and E2E_REDIS_URL to run Socket.IO's message queue and
presence tracking through Redis, as in production (CI does both). The
pages load jQuery, Bootstrap and Socket.IO from CDNs, so the tests need
internet access.
"""

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import expect

from winequiz import create_app
from winequiz.db import db, Country, Grape, GrapeColorEnum, Quiz

from tests.helpers import make_item


REPO_ROOT = Path(__file__).parent.parent.parent

expect.set_options(timeout=10_000)


def pytest_collection_modifyitems(items):
    for item in items:
        if "/e2e/" in str(item.path):
            item.add_marker(pytest.mark.e2e)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_until_serving(url, process, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Server exited with code {process.returncode}")
        try:
            urllib.request.urlopen(url, timeout=1)
            return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"Server did not start within {timeout}s")


@pytest.fixture(scope="session")
def server_config(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e2e")
    return {
        "SECRET_KEY": "e2e-secret",
        "SQLALCHEMY_DATABASE_URI": os.getenv("E2E_DATABASE_URL", f"sqlite:///{tmp}/e2e.db"),
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "BROKER_URL": os.getenv("E2E_REDIS_URL"),
    }


@pytest.fixture(scope="session")
def db_app(server_config):
    """
    An app sharing the server's database, for seeding and checking data
    """
    app = create_app({**server_config, "BROKER_URL": None})
    with app.app_context():
        db.drop_all()
        db.create_all()
        seed_wines()
        yield app
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture(scope="session")
def live_server(server_config, db_app, tmp_path_factory):
    """
    The base URL of the app running under gunicorn
    """
    settings = tmp_path_factory.mktemp("settings") / "settings.py"
    settings.write_text("".join(f"{k} = {v!r}\n" for k, v in server_config.items()))
    port = free_port()
    env = {**os.environ, "WINE_QUIZ_SETTINGS": str(settings)}
    env.pop("ON_HEROKU", None)

    process = subprocess.Popen(
        [sys.executable, "-m", "gunicorn", "--worker-class", "gevent", "-w", "1",
         "-b", f"127.0.0.1:{port}", "winequiz:create_app()"],
        cwd=REPO_ROOT,
        env=env,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        wait_until_serving(f"{base_url}/api/v1/grapes", process)
        yield base_url
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.fixture(autouse=True)
def fresh_session(db_app):
    """
    See the server's latest writes in each test
    """
    db.session.expire_all()
    yield
    db.session.rollback()


GRAPES = [
    ("Merlot", GrapeColorEnum.RED),
    ("Pinot Noir", GrapeColorEnum.RED),
    ("Syrah", GrapeColorEnum.RED),
    ("Malbec", GrapeColorEnum.RED),
    ("Chardonnay", GrapeColorEnum.WHITE),
    ("Riesling", GrapeColorEnum.WHITE),
    ("Sauvignon Blanc", GrapeColorEnum.WHITE),
    ("Chenin Blanc", GrapeColorEnum.WHITE),
]
COUNTRIES = [("France", True), ("Italy", True), ("Chile", False), ("Australia", False)]


def seed_wines():
    db.session.add_all(Grape(name=name, color=color, blendable=True) for name, color in GRAPES)
    db.session.add_all(Country(name=name, old_world=old) for name, old in COUNTRIES)
    db.session.commit()


@pytest.fixture
def quiz(db_app):
    """
    A new two-wine quiz:
      Wine 1: Merlot, France, 2015 (red)
      Wine 2: Chardonnay, Chile, 2020 (white)
    """
    g = {grape.name: grape for grape in Grape.query.all()}
    c = {country.name: country for country in Country.query.all()}
    quiz = Quiz(name="Harvest Party", moderator_code="e2e-mod")
    quiz.items.append(make_item(
        1, g["Merlot"], c["France"], 2015,
        [g["Pinot Noir"], g["Syrah"], g["Malbec"]],
        [c["Italy"], c["Chile"], c["Australia"]],
        [2012, 2018, 2010],
    ))
    quiz.items.append(make_item(
        2, g["Chardonnay"], c["Chile"], 2020,
        [g["Riesling"], g["Sauvignon Blanc"], g["Chenin Blanc"]],
        [c["France"], c["Italy"], c["Australia"]],
        [2019, 2021, 2016],
    ))
    db.session.add(quiz)
    db.session.commit()
    return quiz


# Each screen gets its own browser context, so it has its own cookies like
# a separate device.

STATE_SECTIONS = ["lobby", "free-response", "multiple-choice", "question-recap", "quiz-recap"]


class Screen:
    def __init__(self, browser, base_url, quiz):
        self.context = browser.new_context()
        self.page = self.context.new_page()
        self.base_url = base_url
        self.quiz = quiz

    def url(self, path=""):
        return f"{self.base_url}/quiz/{self.quiz.id}{path}"

    def joined(self):
        """
        Waits until the page has joined the quiz's socket room, which the
        server answers with the current quiz state
        """
        return self.page.expect_console_message(
            lambda message: message.text.startswith("Quiz state changed!")
        )

    def section(self, name):
        return self.page.locator(f"div.{name}")

    def expect_showing(self, name):
        expect(self.section(name)).to_be_visible()
        for other in STATE_SECTIONS:
            if other != name:
                expect(self.section(other)).to_be_hidden()

    def scoreboard(self, selector, rows):
        """
        The (name, score) rows of a scoreboard, once it has the given number
        """
        expect(self.page.locator(f"{selector} tr")).to_have_count(rows)
        cells = self.page.locator(f"{selector} tr").evaluate_all(
            "rows => rows.map(r => [...r.cells].map(c => c.textContent))"
        )
        return [(name, int(score)) for name, score in cells]

    def close(self):
        self.context.close()


class Player(Screen):
    def __init__(self, browser, base_url, quiz, name):
        super().__init__(browser, base_url, quiz)
        self.name = name

    def join(self):
        self.page.goto(self.url("/join"))
        self.page.fill("#competitor_name", self.name)
        with self.joined():
            self.page.click("#join")
        expect(self.page).to_have_url(self.url("/player"))
        return self

    def grape_options(self):
        return self.page.locator("#grape option").all_text_contents()

    def answer_free_response(self, grape=None, country=None, vintage=None):
        if grape is not None:
            expect(self.page.locator("#grape option", has_text=grape)).to_have_count(1)
            self.page.select_option("#grape", label=grape)
        if country is not None:
            self.page.select_option("#country", label=country)
        if vintage is not None:
            self.page.fill("#vintage", str(vintage))
        with self.page.expect_response(lambda r: "submit_free_response" in r.url) as response:
            self.page.click("#free_submit")
        assert response.value.ok
        expect(self.page.locator("small.free-success")).to_be_visible()

    def answer_multiple_choice(self, grape=None, country=None, vintage=None):
        for group, choice in [("grape", grape), ("country", country), ("vintage", vintage)]:
            if choice is not None:
                self.page.locator(f"#{group}_radio label", has_text=str(choice)).click()
        with self.page.expect_response(lambda r: "submit_multiple_choice" in r.url) as response:
            self.page.click("#multi_submit")
        assert response.value.ok
        expect(self.page.locator("small.multi-success")).to_be_visible()

    def choices(self, group):
        return self.page.locator(f"#{group}_radio label span").all_text_contents()


class Moderator(Screen):
    def join(self):
        self.page.goto(self.url("/join_as_mod"))
        self.page.fill("#moderator_code", self.quiz.moderator_code)
        with self.joined():
            self.page.click("#join")
        return self

    def advance(self, expected_state):
        self.page.click("#next")
        expect(self.page.locator("#quizstate")).to_have_text(expected_state)

    def reverse(self, expected_state):
        self.page.click("#reverse")
        expect(self.page.locator("#quizstate")).to_have_text(expected_state)

    def competitors(self):
        return self.page.locator("#competitors li")


class Display(Screen):
    def join(self):
        with self.joined():
            self.page.goto(self.url("/display"))
        return self

    def answered_dot(self, section, competitor_name):
        return self.section(section).locator(
            "p.competitor-name", has_text=competitor_name
        ).locator(".dot")


@pytest.fixture
def screens(browser, live_server):
    """
    Opens screens for a quiz and closes them at the end of the test
    """
    opened = []

    class Factory:
        def player(self, quiz, name):
            opened.append(Player(browser, live_server, quiz, name))
            return opened[-1]

        def moderator(self, quiz):
            opened.append(Moderator(browser, live_server, quiz))
            return opened[-1]

        def display(self, quiz):
            opened.append(Display(browser, live_server, quiz))
            return opened[-1]

    yield Factory()
    for screen in opened:
        screen.close()
