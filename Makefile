# wzSearch – common tasks. Run `make help` for the list.
#
# Python runs through uv (https://docs.astral.sh/uv/); Node is only needed for the
# frontend unit tests (`node --test`, no dependencies) and the optional browser e2e test.

PORT ?= 8000
# Public base URL for the permalinks in CSVs, feeds and the committed reports (CI passes the Pages URL).
SITE_URL ?= https://3-n.github.io/wzsearch/
export SITE_URL

.PHONY: help install data data-offline city city-offline rwdz test test-py test-js serve e2e report

help:
	@echo "make install       install Python deps (uv sync) and the e2e test dependency (npm)"
	@echo "make data          full live build: crawl the district + BAiPP lists, check GUNB RWDZ (permits),"
	@echo "                   parse, geocode, write site/data"
	@echo "make data-offline  rebuild site/data from data/manifest.json, the RWDZ extracts + caches, no network"
	@echo "make city          (draft) every Warsaw district into site/data/d/<slug>/ + site/data/districts.json;"
	@echo "                   DISTRICTS=bemowo,wola limits it (default: all)"
	@echo "make city-offline  (draft) the same from the manifests, extracts and caches, no network"
	@echo "make rwdz          only refresh the GUNB RWDZ extracts (data/raw/rwdz) and print their statistics"
	@echo "make test          Python tests (pytest) + frontend unit tests (node --test)"
	@echo "make serve         serve site/ on http://127.0.0.1:$(PORT) (Node dev server; python3 http.server without Node)"
	@echo "make e2e           browser smoke test (needs Chrome/Chromium; see tests/e2e)"
	@echo "make report        print the data-quality report (data/report.md)"

install:
	uv sync
	@if [ -f package.json ] && command -v npm >/dev/null 2>&1; then npm install --no-audit --no-fund; \
	else echo "npm not found – skipping e2e dependency (only needed for 'make e2e')"; fi

data:
	uv run python -m pipeline.build

data-offline:
	uv run python -m pipeline.build --offline

DISTRICTS ?= all

city:
	uv run python -m pipeline.city --districts $(DISTRICTS)

city-offline:
	uv run python -m pipeline.city --offline --districts $(DISTRICTS)

rwdz:
	uv run python -m pipeline.rwdz

test: test-py test-js

test-py:
	uv run pytest

test-js:
	@if [ -d tests/js ] && command -v node >/dev/null 2>&1; then node --test 'tests/js/*.test.mjs'; \
	else echo "node or tests/js not found – skipping frontend unit tests"; fi

serve:
	@if command -v node >/dev/null 2>&1; then node tests/e2e/server.mjs --port=$(PORT); \
	else echo "Serving site/ on http://127.0.0.1:$(PORT) (Ctrl+C to stop)"; python3 -m http.server --bind 127.0.0.1 -d site $(PORT); fi

e2e:
	npm run e2e

report:
	@cat data/report.md
