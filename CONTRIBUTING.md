# Contributing to libipynb

Thank you for your interest in contributing to libipynb.

## Development Setup

```bash
git clone https://gitlab.recruitize.ai/sialkot/cantt-smallize/libipynb.git
cd libipynb
python -m venv .venv
.venv/Scripts/activate  # Windows
pip install -e ".[test,reference]"
```

## Running Tests

```bash
pytest tests/ -v
```

## Code Style

This project uses [Ruff](https://docs.astral.sh/ruff/) for formatting and linting.

```bash
ruff format .
ruff check .
```

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(model): add cell attachment support
fix(codec): handle missing nbformat field
test(security): add resource limit enforcement tests
```
