[↑ Docs index](../README.md) · Technical

# 19 — Testing and quality

The project has 206 test files (about 38,000 lines) that mirror `src/`. Most of them run offline against trimmed
snapshots of the real pages. The `db` tests run against a throw-away PostgreSQL database created per test session,
and the `live` tests crawl the real websites, but only when asked to. On top of
[ruff](https://docs.astral.sh/ruff/) and [mypy](https://mypy.readthedocs.io/), six **convention test files** enforce
the house rules (typing, class layout, exceptions, logging, prose) by parsing the source with `ast`. This chapter
lists the commands, the markers, the fixtures, the conventions and the static checks.

## Contents

- [Commands](#commands)
- [Layout of the tests](#layout-of-the-tests)
- [Markers](#markers)
- [Database tests](#database-tests)
- [Offline fixtures](#offline-fixtures)
- [Shared fixtures](#shared-fixtures)
- [GUI tests](#gui-tests)
- [Convention tests](#convention-tests)
- [Static checks](#static-checks)
- [VS Code launch configurations](#vs-code-launch-configurations)
- [See also](#see-also)

## Commands

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy        # static checks
uv run install-stack --test                                                 # start + migrate the test PostgreSQL (port 5433)
STORAGE_TEST_DATABASE_URL=postgresql+asyncpg://crawler:crawler@localhost:5433/poc_crawler_test uv run pytest
uv run pytest --live -m live                                                # smoke tests against the real websites
uv run pytest tests/crawler/cloud/aws                                       # one folder
uv run pytest --cov=src --cov-branch --cov-report=term-missing              # coverage (as the launch configuration)
```

Without `STORAGE_TEST_DATABASE_URL`, the `db` tests are skipped and everything else runs. `pytest` options come from
[`pyproject.toml`](../../pyproject.toml): `testpaths = ["tests"]`, `pythonpath = ["src", "."]`,
`asyncio_mode = "auto"` ([pytest-asyncio](https://pytest-asyncio.readthedocs.io/)) and `--strict-markers`.

## Layout of the tests

The tests mirror `src/` (e.g. `tests/crawler/cloud/aws/` for the AWS catalogue and marketplace crawlers), and no
folder holds more than 5 Python files.

```mermaid
xychart-beta horizontal
    title "Test files per folder (206)"
    x-axis ["crawler", "gui", "models", "storage", "analytics", "conventions", "scripts", "llm", "root", "live", "logger", "taxonomy", "catalogue", "classifier"]
    y-axis "Files" 0 --> 90
    bar [82, 33, 33, 22, 9, 6, 6, 4, 3, 2, 2, 2, 1, 1]
```

```mermaid
pie showData
    title Test lines per folder (about 38,300)
    "crawler" : 19651
    "gui" : 6756
    "models" : 3336
    "storage" : 2981
    "analytics" : 1532
    "conventions" : 794
    "llm" : 591
    "scripts" : 523
    "classifier" : 404
    "others (logger, catalogue, taxonomy, live)" : 806
    "root (conftest and 3 files)" : 964
```

The three root files are [`test_main.py`](../../tests/test_main.py) (the `CRAWLER_SOURCE` dispatch),
[`test_package_entrypoint.py`](../../tests/test_package_entrypoint.py) and
[`test_vscode_launch.py`](../../tests/test_vscode_launch.py) (see below).

## Markers

| Marker | Meaning | Enabled by |
|---|---|---|
| `db` | Needs a PostgreSQL server (40 files). | `STORAGE_TEST_DATABASE_URL` set; skipped otherwise. |
| `live` | Crawls the real websites, opens the browser (`tests/live/`: [`test_live_crawlers.py`](../../tests/live/test_live_crawlers.py), [`test_live_statistics.py`](../../tests/live/test_live_statistics.py)). | `pytest --live` ([`pytest_addoption`](../../tests/conftest.py#L59)); skipped otherwise. |

`--strict-markers` turns any other marker into an error.

## Database tests

The test server is the `postgres-test` service of [`compose.yaml`](../../compose.yaml) (port 5433, data on `tmpfs`,
`fsync`, `full_page_writes` and `synchronous_commit` off: fast and disposable; see
[20-operations.md](20-operations.md)).

```mermaid
sequenceDiagram
    autonumber
    participant PT as pytest session
    participant F as database_url fixture
    participant PG as postgres-test (5433)
    participant MG as DatabaseMigrator
    participant T as each db test
    PT->>F: first db test requests it
    alt STORAGE_TEST_DATABASE_URL unset
        F-->>PT: pytest.skip
    else set
        F->>PG: CREATE DATABASE poc_crawler_test_uuid12 TEMPLATE template0
        F->>MG: upgrade() to head (0008) + taxonomy seed
        loop every db test
            T->>PG: storage fixture: open Storage, TRUNCATE every table RESTART IDENTITY CASCADE
            T->>PG: test body (batch_size 3, pool_size 2)
        end
        PT->>F: session teardown
        F->>PG: DROP DATABASE ... WITH (FORCE)
    end
```

- [`database_url`](../../tests/conftest.py#L327) (session scope) creates one database per session from
  `template0`, which no session uses, so concurrent test runs never wait for each other.
- [`storage_settings`](../../tests/conftest.py#L344) uses `batch_size = 3`, so the tests write several batches and
  exercise the progressive writer.
- [`storage`](../../tests/conftest.py#L350) truncates every table before each test.
- `pytest-xdist` is not a dependency; the fixture would give one database per worker if it were added.

## Offline fixtures

[`tests/fixtures/`](../../tests/fixtures/) holds trimmed snapshots of the real responses:

```mermaid
pie showData
    title Recorded snapshots (191 files)
    "crawler: catalogue pages and sitemaps" : 92
    "marketplace: API answers and pages" : 79
    "stats: Synergy articles and CDX" : 14
    "metrics: EDGAR, Wikidata, PeeringDB, GitHub" : 6
```

[`make_response`](../../tests/conftest.py#L100) builds a Scrapling `Response` from a snapshot, and
[`crawl_page`](../../tests/conftest.py#L130) feeds it to a crawler's `parse` and collects the items and follow-up
requests. A website change therefore never breaks the offline suite; the `live` tests catch it.

## Shared fixtures

[`tests/conftest.py`](../../tests/conftest.py) sets `QT_QPA_PLATFORM=offscreen` and provides:

| Fixture | Scope | Role |
|---|---|---|
| [`isolated_ca_bundle`](../../tests/conftest.py#L73) | autouse | Points the merged CA bundle at a temporary folder. |
| [`no_language_model`](../../tests/conftest.py#L83) | autouse | Unsets `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` and `CRAWLER_LLM_CONFIG`: no test ever calls a model. |
| [`stealth_session_cls`](../../tests/conftest.py#L90) | autouse | Replaces Scrapling's `AsyncStealthySession` (no browser), except for `live` tests. |
| [`make_response`](../../tests/conftest.py#L100), [`metric_page`](../../tests/conftest.py#L117), [`crawl_page`](../../tests/conftest.py#L130) | function | Offline crawling. |
| [`make_catalogue`](../../tests/conftest.py#L306), [`make_marketplace`](../../tests/conftest.py#L244), [`make_software`](../../tests/conftest.py#L273), [`make_report`](../../tests/conftest.py#L300) | function | Model builders. |
| [`seed_catalogue`](../../tests/conftest.py#L380), [`seed_marketplace`](../../tests/conftest.py#L385) | helpers | Write items through the real writer. |
| [`gui_loop`](../../tests/conftest.py#L360), [`offline_loop`](../../tests/conftest.py#L398), [`fill_table`](../../tests/conftest.py#L390) | function | A real `StorageLoop` on the test database, a never-started one, and page injection into a `PagedTableModel`. |
| [`isolated_logging`](../../tests/conftest.py#L218) and the logging payloads | function | Logging configuration tests. |

## GUI tests

The 33 GUI test files use [pytest-qt](https://pytest-qt.readthedocs.io/) (`qtbot`) on the offscreen platform. Pure
widget tests use `offline_loop` and `fill_table`; integration tests use `gui_loop` on the test database and wait for
the queued `finished` signal (see [18-gui-architecture.md](18-gui-architecture.md)).

## Convention tests

[`tests/conventions/`](../../tests/conventions/) parses the source with `ast` and fails on any breach. Each file also
tests its own checker on accepted and rejected samples.

| File | Test | Rule |
|---|---|---|
| [`code/test_crawler_conventions.py`](../../tests/conventions/code/test_crawler_conventions.py) | `test_classes_follow_the_method_layout` | In analytics, catalogue, classifier, crawler, gui, llm, storage, taxonomy and scripts: special methods first, then the `# Internal Helpers Methods #` banner (`_x`), then `# Publicly Exposed Methods #`. No `staticmethod` or `classmethod`. A method comes after the methods it calls. `parse` comes last. |
| same | `test_gui_modules_hold_one_class_each` | At most one class per `src/gui` module. |
| [`code/test_typing_conventions.py`](../../tests/conventions/code/test_typing_conventions.py) | `test_project_follows_typing_conventions` | `Any` only for `*args`/`**kwargs`; no `object` in annotations; `Dict`/`List` rather than `dict[]`/`list[]`; `Union`/`Optional` rather than `\|`; `Optional[X]` rather than `Union[X, None]`. |
| [`code/test_validator_conventions.py`](../../tests/conventions/code/test_validator_conventions.py) | `test_field_validators_run_in_before_mode`, `test_field_validators_are_not_decorated_with_classmethod` | Pydantic `field_validator(mode="before")`, without `@classmethod`. |
| [`errors/test_error_logging_convention.py`](../../tests/conventions/errors/test_error_logging_convention.py) | `test_raised_exceptions_are_logged_as_errors` | Outside `models/`, every `raise X` comes right after `logger.error()` or `.exception()`. A bare re-raise is exempt. |
| [`errors/test_exception_conventions.py`](../../tests/conventions/errors/test_exception_conventions.py) | `test_exceptions_are_only_defined_in_exception_modules` | Exceptions live only in `exception.py` modules. |
| same | `test_exception_module_has_a_single_root_error` | One root `Exception` subclass per `exception.py`; every class name ends in `Error`. |
| same | `test_every_package_raising_errors_has_an_exception_module` | The set of exception modules is fixed at 17. |
| same | `test_raised_exceptions_come_from_the_package_exception_module` | A raised exception is imported from the `exception.py` of its own package or a parent. |
| [`test_prose_conventions.py`](../../tests/conventions/test_prose_conventions.py) | `test_no_semicolons_in_prose` | No `;` in comments, docstrings or log messages (src, scripts, tests). |

```mermaid
mindmap
  root((House rules))
    Typing
      typing Dict List Optional Union
      no Any no object
      mypy disallow_any_generics
    Classes
      one class per GUI module
      helpers banner then public banner
      callee before caller
      parse last
      no staticmethod or classmethod
    Errors
      exception.py per package
      one root Error
      ERROR log before raise
    Models
      Pydantic validators mode before
    Prose
      Google docstrings
      no semicolons
    Folders
      at most 5 py files
```

## Static checks

| Tool | Configuration ([`pyproject.toml`](../../pyproject.toml)) |
|---|---|
| [ruff](https://docs.astral.sh/ruff/) | Line length 120, target `py314`. Rules E, W, F, I, N, D (Google docstrings), UP, B, SIM, G, PT, RUF and ANN401 (no `Any` in signatures, except `*args`/`**kwargs`). UP006/UP035/UP007/UP045 are ignored to keep `typing.Dict`, `List`, `Union`, `Optional`. Qt override names (`rowCount`, `paintEvent`…) are allowed in camelCase. Tests are exempt from D. |
| [mypy](https://mypy.readthedocs.io/) | Python 3.14, files `src`, `scripts`, `tests`, the `pydantic.mypy` plugin, `warn_unused_ignores`, `disallow_any_generics`. `asyncpg` has no types and is ignored. Stubs: `scipy-stubs`, `types-pyyaml`. |

## VS Code launch configurations

[`.vscode/launch.json`](../../.vscode/launch.json) defines "Crawler: run target", "Crawler: run target (step into
libraries)", "GUI: catalogue explorer", "Tests: all", "Tests: current file", "Tests: coverage report" and "Tests:
debug from Test Explorer". Its inputs offer every `CloudProvider` plus `all` (default `scaleway`) and every
`CRAWLER_SOURCE` (default `catalogue`).

[`test_vscode_launch.py`](../../tests/test_vscode_launch.py) keeps the file honest: the target options must equal the
`CloudProvider` values plus `all`, the source options must equal `main.SOURCES`, the names must be unique, every
configuration must use `debugpy` with `${workspaceFolder}/.venv/bin/python`, and the module configurations must be
exactly `pytest` and `gui.window.app`.

## See also

- [20-operations.md](20-operations.md): `install-stack --test` and the Compose test service.
- [12-crawler-framework.md](12-crawler-framework.md): what the crawler tests exercise.
- [13-storage.md](13-storage.md): the writer and repositories the `db` tests exercise.
- [18-gui-architecture.md](18-gui-architecture.md): the storage loop used by `gui_loop`.

[← Previous](18-gui-architecture.md) · [Next →](20-operations.md)
