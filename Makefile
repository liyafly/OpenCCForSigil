.PHONY: install test lint check package spec-bundle clean

install:
	mise install
	mise exec -- uv sync --locked

test:
	mise exec -- uv run pytest

lint:
	mise exec -- ruff check .

check: lint test
	mise exec -- uv run python tools/build_plugin.py --check

package:
	mise exec -- uv run python tools/build_plugin.py

spec-bundle:
	mise exec -- uv run python tools/build_spec_bundle.py

clean:
	rm -rf .pytest_cache .ruff_cache build dist
