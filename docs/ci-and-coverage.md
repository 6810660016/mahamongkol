# CI and test coverage

## Scope and local commands

Use Python 3.13 to match CI and the Django version in `requirements.txt`.
Install development tools with:

```bash
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m coverage run manage.py test --noinput --settings=MongkolQ.test_settings
python -m coverage report --fail-under=80
python -m coverage html
```

Open `htmlcov/index.html` for the line-by-line report. Reports are generated,
ignored by Git, and uploaded as the `coverage-report` artifact in GitHub Actions.

`.coveragerc` measures line coverage of **all five applications**: `account`,
`bookings`, `dashboard`, `queues`, and `restaurants`, including service layers,
views, forms, models, permissions, and management commands. Only test files and
generated migrations are omitted. Django settings/bootstrap files and frontend
HTML, CSS, and JavaScript are outside this measurement. This is not a branch
coverage or browser-testing claim.

`MongkolQ.test_settings` uses an isolated SQLite test database, in-memory email,
and the fast MD5 password hasher for tests only. It must never be used to run the
production site. CI does not need real email credentials or production secrets.
PostgreSQL locking/concurrency behavior needs a separate integration test run.

## Lint rules

`ruff.toml` enables Python syntax/import errors, import ordering, naming,
Ruff-specific checks, timezone checks, and broad-exception checks. The existing
`MongkolQ` package name has a single-file naming exception to preserve imports.
Generated migration class attributes retain their existing RUF012 exception;
en dashes are allowed in opening-hour display strings.

## Required status check (repository admin)

The workflow runs on pushes, pull requests, and manual dispatches. Its stable job
name is **Ruff and Django tests** in the **CI** workflow. The job fails if Ruff,
Django checks, tests, or the 80% coverage gate fail.

After pushing this branch and seeing the check run at least once:

1. Open repository **Settings → Branches → Add branch protection rule** (or an
   equivalent repository ruleset) and target `main`.
2. Enable **Require a pull request before merging**.
3. Enable **Require status checks to pass before merging** and select the check
   **Ruff and Django tests** from GitHub Actions.
4. Enable **Require branches to be up to date before merging**.
5. Apply the rule to administrators too / disable bypass where the repository's
   settings allow it, and save.
6. Verify using a PR with a deliberately failing check; restore the code before
   merging. It should be blocked while the required check is failing.

Branch protection is a GitHub repository setting, not something `ci.yml` alone
can enforce. The account used for this task has push access but no admin access;
the rule has **not** been configured by this change. The repository owner must
complete these steps. Availability depends on the repository plan and visibility.

## Baseline and evidence

Base: `origin/main` at `1d74f60`. Measured with Python 3.13.18, Django 6.1.2,
Coverage 7.17.2, and SQLite using the test settings above.

- Existing suite: **332 tests passed**.
- Initial application line coverage: **95.74%** (1,305 / 1,363 statements).
- Full selected Ruff checks initially reported **26 findings**; all were fixed
  or handled by the narrowly documented conventions above.
- Additional tests cover SMTP/network delivery failures and unexpected
  programming errors in password reset, alongside narrowing exception handling.
- Final suite: **335 tests passed**; application line coverage **96.55%**
  (1,316 / 1,363 statements). Ruff and Django system checks both pass.

### Verification audit (2026-11-07)

- Installed `requirements-dev.txt` with pip into a second fresh Python 3.13
  environment; `pip check` found no dependency conflicts.
- Re-ran the workflow's Python commands with `DJANGO_SETTINGS_MODULE` set as in
  CI: **335 tests passed**, coverage **96.55%**, XML and HTML reports generated.
- Re-ran all **335 tests** in shuffled order with seed `7319`: passed.
- Validated `.github/workflows/ci.yml` with actionlint **1.7.12**: passed.
- Exercised the coverage gate using an intentionally partial test run in a
  separate coverage file: **43.07%** was rejected with exit code **2**.
- Exercised Ruff using an unused import passed through stdin: rejected with exit
  code **1**, without adding a broken file to the repository.
- Fixed an existing flaky OTP test: its incorrect code now always differs from
  the generated code, including when the generated code happens to be `000000`.

This audit ran on Windows. Docker's Linux engine was unavailable, so the Ubuntu
runner and GitHub-hosted checkout/cache/artifact steps still require a real
Actions run. Branch protection remains an admin action as described above.

Save the Actions run URL, successful job screenshot, and coverage artifact after
pushing. Local success alone is not evidence of a successful GitHub Actions run.

References: [GitHub Python CI](https://docs.github.com/en/actions/tutorials/build-and-test-code/python),
[Coverage configuration](https://coverage.readthedocs.io/en/latest/config.html).
