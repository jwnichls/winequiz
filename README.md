# Wine Quiz

A multi-user wine quiz web-based game.

## Development

Dependencies are managed with [uv](https://docs.astral.sh/uv/):

```sh
uv sync
```

## Tests

```sh
uv run pytest
```

Tests use an in-memory SQLite database by default. To run them against
PostgreSQL, as CI does, point `TEST_DATABASE_URL` at an empty database
(this also runs the migration checks):

```sh
TEST_DATABASE_URL=postgresql://localhost/winequiz_test uv run pytest
```

Tests marked `xfail` document known bugs. They're strict, so fixing one
of those bugs makes its test fail until the marker is removed.

### Browser tests

`tests/e2e` plays real games in headless Chromium: several players, the
moderator and the big screen display, each in its own browser, against
the app running under gunicorn as in production. They're skipped by a
plain `pytest`; run them with:

```sh
uv run playwright install chromium   # once
uv run pytest -m e2e
```

They use a SQLite file by default. Set `E2E_DATABASE_URL` and
`E2E_REDIS_URL` to run the server against Postgres and Redis (CI does).
The pages load jQuery, Bootstrap and Socket.IO from CDNs, so these tests
need internet access.

## Deployment

Pushes to `main` run the unit and browser tests in GitHub Actions
(`.github/workflows/tests.yml`). Heroku deploys `main` automatically once
those checks pass.
