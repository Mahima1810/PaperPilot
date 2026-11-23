# Contributing to PaperPilot

Thanks for your interest! Bug reports, ideas and pull requests are all welcome.

## Setup

```bash
git clone https://github.com/Mahima1810/paperpilot.git
cd paperpilot
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

## Before opening a pull request

1. `pytest` and `ruff check .` must pass.
2. Add or update a test for any behaviour change.
3. Keep PRs focused, one change per PR.
4. Describe *how you tested* in the PR description.

## Project layout

| Path | What it does |
|---|---|
| `app/pdf_parser.py` | PDF → pages → sections |
| `app/chunker.py` | Sections → overlapping, citable chunks |
| `app/retriever.py` | BM25 + TF-IDF hybrid search (RRF) |
| `app/answerer.py` | LLM / extractive answers and citation verification |
| `app/llm.py` | OpenAI-compatible chat client |
| `app/store.py` | On-disk cache + in-memory index |
| `app/main.py` | FastAPI routes |
| `frontend/` | Static web UI (no build step) |

## Good first issues

See the **Roadmap** in the README. Issues labelled `good first issue` are a good place to start.

## Ground rule

PaperPilot exists to give answers people can verify. Changes must never let an uncited claim reach the user.
