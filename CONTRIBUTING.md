# Contributing and responsible use

Clip Arena Engine is an early-stage Python pipeline for finding candidate moments in authorized source videos and rendering vertical clips. Feedback about reproducibility, reliability, accessibility, and security is welcome.

## Development setup

- Python 3.12 (the version used by the GitHub Actions workflows)
- FFmpeg and FFprobe available on your PATH
- DejaVu fonts for subtitle rendering
- A virtual environment with dependencies installed from `requirements.txt`

```sh
python -m venv .venv
# On macOS/Linux:
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m engine.scan --help
python -m engine.render --help
```

The help commands are a lightweight entry-point check, not an end-to-end test. Full scanning and rendering require authorized source material and may need network access and model downloads.

## Reporting issues

Please describe the command used, expected behavior, actual behavior, Python and FFmpeg versions, and a minimal reproducible example. Remove credentials, browser cookies, personal identifiers, and private media links from logs. Use synthetic data or your own authorized test media; do not attach copyrighted campaign assets.

Useful areas for feedback include timestamp parsing, signal scoring, subtitle timing, input validation, rendering failures, and test coverage.

## Proposed contributions

Before proposing code changes, open an issue describing the improvement. Keep changes focused, document behavior changes, and include reproducible tests where possible. Do not trigger the production scan or render workflows merely to test a change; use local fixtures.

## Security and content rights

Never commit API keys, session cookies, authentication files, or private media. Report suspected secret exposure or security vulnerabilities privately to the repository owner, rather than posting exploit details in a public issue.

Only process media that you own or have explicit permission to use. The code, third-party dependencies, campaign artwork, and source videos have separate ownership and licensing considerations.

No open-source license has been verified for this repository yet. Public visibility alone does not grant permission to redistribute or modify its code. Licensing must be clarified by the rights holder before wider reuse.
