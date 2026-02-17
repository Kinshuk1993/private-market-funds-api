# Code Quality Guide

Automated code formatting, import sorting, and linting for the Titanbay Private Markets API.

---

## Overview

| Tool | Purpose | Config Location |
| ------ | --------- | ----------------- |
| **black** | Code formatter (opinionated, deterministic) | `pyproject.toml` |
| **isort** | Import sorter (groups & alphabetizes imports) | `pyproject.toml` |
| **flake8** | Linter (catches bugs, style violations, unused code) | `setup.cfg` |

All three tools are installed via `requirements.txt` and configured to work together without conflicts.

---

## Quick Start

```bash
# From the titanbay-service directory
pip install -r requirements.txt
```

### Check (Dry Run — No Changes)

```bash
# Check formatting
black --check app/ tests/

# Check import order
isort --check app/ tests/

# Lint for errors
flake8 app/ tests/
```

### Fix (Auto-Format)

```bash
# Format code
black app/ tests/

# Sort imports
isort app/ tests/

# Note: flake8 only reports — it does not auto-fix
```

### Run All Three in One Command

```bash
# Check all (CI mode — fails on any issue)
black --check app/ tests/ && isort --check app/ tests/ && flake8 app/ tests/

# Fix then lint
black app/ tests/ && isort app/ tests/ && flake8 app/ tests/
```

---

## Tool Details

### Black — Code Formatter

**What it does:**
Black is an opinionated Python code formatter. It reformats your code to a single, consistent style — ending all debates about formatting. It modifies whitespace, line breaks, trailing commas, and string quotes to produce deterministic output.

**Why we need it in production:**

- **Eliminates formatting debates** — Every developer produces identical formatting, reducing noise in code reviews to focus on logic, not style.
- **Prevents merge conflicts** — Consistent formatting means fewer diff conflicts when multiple engineers edit the same file.
- **Enforces readability** — At scale (10+ engineers), inconsistent formatting makes code harder to scan and understand.
- **Deterministic output** — Running black twice produces the same result, making it safe to run in CI and pre-commit hooks.

**Configuration** (`pyproject.toml`):

```toml
[tool.black]
line-length = 99
target-version = ["py312"]
```

- **line-length = 99**: Slightly wider than PEP 8's 79 to reduce unnecessary line wrapping on modern wide monitors, while still fitting comfortably in side-by-side diffs.
- **target-version**: Ensures black uses Python 3.12+ syntax features.

**Examples of what black fixes:**

```python
# Before
def create_fund(self,fund_in:FundCreate)->Fund:
    fund=Fund(**fund_in.model_dump())
    return fund

# After
def create_fund(self, fund_in: FundCreate) -> Fund:
    fund = Fund(**fund_in.model_dump())
    return fund
```

---

### isort — Import Sorter

**What it does:**
isort automatically sorts Python imports into a standard order: standard library → third-party → first-party → local. Within each group, imports are alphabetized and split between `import` and `from ... import` statements.

**Why we need it in production:**

- **Prevents duplicate imports** — isort detects and removes duplicate import lines.
- **Standardizes grouping** — Makes it immediately clear which dependencies are external vs. internal, critical when auditing third-party dependencies for security vulnerabilities.
- **Reduces merge conflicts** — Alphabetical ordering means two developers adding different imports to the same file produce compatible diffs instead of conflicts.
- **Pairs with black** — The `profile = "black"` setting ensures isort's output is compatible with black's formatting, preventing the two tools from fighting each other.

**Configuration** (`pyproject.toml`):

```toml
[tool.isort]
profile = "black"
line_length = 99
known_first_party = ["app"]
sections = ["FUTURE", "STDLIB", "THIRDPARTY", "FIRSTPARTY", "LOCALFOLDER"]
```

- **profile = "black"**: Matches black's formatting expectations (trailing commas, multi-line style).
- **known_first_party = ["app"]**: Ensures `from app.core.cache import cache` is sorted into the first-party group, not third-party.

**Example of what isort fixes:**

```python
# Before
from uuid import uuid4
from app.models.fund import Fund
import logging
from sqlalchemy.exc import IntegrityError
from datetime import datetime

# After
import logging
from datetime import datetime
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.models.fund import Fund
```

---

### flake8 — Linter

**What it does:**
flake8 is a static analysis tool that checks Python code for:

- **Syntax errors** (e.g. missing colons, unclosed brackets)
- **PEP 8 style violations** (e.g. missing blank lines, whitespace issues)
- **Logical errors** (e.g. unused imports, undefined names, unreachable code)
- **Complexity warnings** (e.g. functions that are too complex)

Unlike black and isort, flake8 **does not modify files** — it only reports issues for you to fix.

**Why we need it in production:**

- **Catches real bugs** — Unused imports often indicate dead code or refactoring mistakes. Undefined names cause `NameError` at runtime. flake8 catches these before deployment.
- **Enforces code hygiene** — In a team of 10+ engineers, small issues compound: unused variables, bare excepts, mutable default arguments. flake8 prevents these from entering the codebase.
- **Complements black** — black handles formatting; flake8 catches logical issues that black intentionally ignores (unused imports, undefined names, etc.).
- **CI gate** — flake8 runs in seconds and provides a fast feedback loop in CI, catching issues before code review.

**Configuration** (`setup.cfg`):

```ini
[flake8]
max-line-length = 99
extend-ignore = E203, W503, E501
per-file-ignores = __init__.py:F401
```

- **max-line-length = 99**: Matches black's line length to prevent conflicts.
- **E203**: Ignored because black formats slices differently from PEP 8 (`x[1 : 2]`).
- **W503**: Ignored because black prefers line breaks before binary operators (PEP 8 changed its recommendation).
- **E501**: Ignored because black already handles line length.
- **F401 in `__init__.py`**: Import re-exports in `__init__.py` files are intentional (barrel exports), not unused.

**Example of what flake8 catches:**

```python
import os          # F401 — imported but never used
from typing import List

def process(data):
    result = transform(data)  # F841 — 'result' assigned but never used
    return data
```

---

## How the Tools Work Together

```bash
┌──────────────────────────────────────────────────────┐
│                    Developer Workflow                  │
│                                                       │
│  1. Write code                                        │
│  2. Run: black app/ tests/         → Format code      │
│  3. Run: isort app/ tests/         → Sort imports     │
│  4. Run: flake8 app/ tests/        → Catch bugs       │
│  5. Run: pytest                    → Verify behaviour  │
│  6. Commit                                            │
└──────────────────────────────────────────────────────┘
```

The tools are designed to run in this order:

1. **black** first — reformats everything
2. **isort** second — sorts imports (compatible with black via `profile = "black"`)
3. **flake8** last — catches any remaining issues that formatting can't fix

Running them in a different order may cause false positives (e.g. flake8 reporting line-length issues that black would fix).

---

## Configuration Files

| File | Tools Configured | Why This File |
| ------ | ----------------- | --------------- |
| `pyproject.toml` | pytest, coverage, black, isort | Modern Python standard for tool config |
| `setup.cfg` | flake8 | flake8 does not support `pyproject.toml` natively |

Both files live in the project root (`titanbay-service/`).

---

## CI Integration

### GitHub Actions

```yaml
name: Code Quality

on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"

      - name: Install dependencies
        run: |
          cd titanbay-service
          pip install -r requirements.txt

      - name: Check formatting (black)
        run: |
          cd titanbay-service
          black --check app/ tests/

      - name: Check imports (isort)
        run: |
          cd titanbay-service
          isort --check app/ tests/

      - name: Lint (flake8)
        run: |
          cd titanbay-service
          flake8 app/ tests/
```

### Pre-Commit Hook (Optional)

You can automate formatting on every commit using [pre-commit](https://pre-commit.com/):

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/psf/black
    rev: 24.4.2
    hooks:
      - id: black
        args: [--line-length=99]

  - repo: https://github.com/pycqa/isort
    rev: 5.13.2
    hooks:
      - id: isort
        args: [--profile=black]

  - repo: https://github.com/pycqa/flake8
    rev: 7.0.0
    hooks:
      - id: flake8
```

Install: `pip install pre-commit && pre-commit install`

---

## Troubleshooting

| Problem | Solution |
| --------- | ---------- |
| `black` and `isort` fight each other | Ensure `profile = "black"` in isort config |
| flake8 reports line-length errors | Ensure `max-line-length = 99` matches black |
| flake8 reports unused imports in `__init__.py` | Add `per-file-ignores = __init__.py:F401` |
| `E203` false positives on slices | Add `E203` to `extend-ignore` |
| Tools not found | Run `pip install -r requirements.txt` |

---

## Why Code Quality Tools Matter

In a production codebase maintained by a team:

1. **Consistency** — Every file looks the same. New team members can read any file without adjusting to different styles.
2. **Speed** — Code reviews focus on logic, not formatting. Reviewers don't waste time with "add a space here" comments.
3. **Safety** — flake8 catches real bugs (unused imports, undefined names) before they reach production.
4. **Scalability** — As the codebase grows from 1K to 100K lines, automated quality gates prevent technical debt from accumulating.
5. **Onboarding** — New engineers run `black && isort && flake8` and instantly produce code that matches the team's standards.
