.PHONY: install run test lint typecheck check

install:
	python -m pip install -e '.[dev]'

run:
	uvicorn saas_ops.main:app --reload

test:
	pytest -q

lint:
	ruff check .

typecheck:
	mypy

check: lint typecheck test

