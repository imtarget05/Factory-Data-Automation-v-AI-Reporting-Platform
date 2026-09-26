# Smart Manufacturing Platform — developer entry points
#   make setup   install dependencies and generate reproducible sample data
#   make test    generate sample data, then run the full test suite
#   make data    (re)generate data/raw/*.csv only
#   make lint    ruff check + ruff format check
PYTHON ?= python
DATA   := $(PYTHON) -m scripts.generate_sample_data

.PHONY: setup install data test lint run clean

setup: install data

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt pytest pytest-cov

data:
	$(DATA)

test: data
	$(PYTHON) -m pytest tests/ -v

lint:
	$(PYTHON) -m ruff check app/ tests/ scripts/
	$(PYTHON) -m ruff format --check app/ tests/ scripts/

run:
	$(PYTHON) -m app.etl.pipeline

clean:
	rm -f data/raw/*.csv data/processed/*.parquet data/exports/*.xlsx
