.PHONY: install test lint verify-vendor differential differential-jieba check package artifact-check clean

PLUGIN_VERSION := $(shell awk -F'"' '/^PLUGIN_VERSION/ {print $$2}' plugin/OpenCCForSigil/app/version.py)

install:
	mise install
	mise exec -- uv sync --locked

test:
	mise exec -- uv run pytest

lint:
	mise exec -- ruff check .

verify-vendor:
	mise exec -- uv run python tools/verify_vendor.py

differential:
	mise exec -- uv run python tools/differential_test.py --corpus tests/fixtures/opencc_smoke.jsonl

differential-jieba:
	mise exec -- uv run python tools/differential_jieba_test.py --corpus tests/fixtures/opencc_jieba_smoke.jsonl

check: lint test verify-vendor differential differential-jieba
	mise exec -- uv run python tools/build_plugin.py --check

package:
	mise exec -- uv run python tools/build_plugin.py

artifact-check:
	mise exec -- uv run python tools/validate_artifact.py dist/OpenCCForSigil_$(PLUGIN_VERSION).zip

clean:
	rm -rf .pytest_cache .ruff_cache build dist
