.PHONY: help install demo run seed test lint fmt docker-build docker-run clean

PORT ?= 8000
PY ?= python3
VENV := .venv
BIN := $(VENV)/bin

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

$(BIN)/activate:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements-dev.txt

install: $(BIN)/activate ## Create the virtualenv and install dependencies

seed: install ## Seed a demo user + sample session
	$(BIN)/python -m scripts.seed

demo: seed ## One command: seed and launch locally (prints the URL)
	@echo ""
	@echo "  InterviewCoach is starting on http://127.0.0.1:$(PORT)"
	@echo "  Demo login:  demo@interviewcoach.dev  /  demopass123"
	@echo "  Running in offline mode (no API key needed). Ctrl-C to stop."
	@echo ""
	$(BIN)/python -m uvicorn app.main:app --host 127.0.0.1 --port $(PORT) --reload

run: install ## Launch the server without seeding
	$(BIN)/python -m uvicorn app.main:app --host 0.0.0.0 --port $(PORT)

test: install ## Run the test suite
	$(BIN)/python -m pytest -q

lint: install ## Lint with ruff
	$(BIN)/ruff check app scripts tests

fmt: install ## Auto-fix lint issues
	$(BIN)/ruff check --fix app scripts tests

docker-build: ## Build the Docker image
	docker build -t interviewcoach .

docker-run: docker-build ## Run the container on $(PORT)
	docker run --rm -p $(PORT):8000 interviewcoach

clean: ## Remove caches, the venv, and the local SQLite db
	rm -rf $(VENV) .pytest_cache **/__pycache__ app/__pycache__ tests/__pycache__ scripts/__pycache__
	rm -f interviewcoach.db
