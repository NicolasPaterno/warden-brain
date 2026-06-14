# warden-brain — common dev tasks. Run `make help` for the list.
# Mirrors the Go services' Makefiles so the polyrepo feels consistent.

IMAGE ?= warden-brain:dev

.DEFAULT_GOAL := help

.PHONY: help install lint fmt test run build docker-build docker-run

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Sync the virtualenv (incl. dev deps) from uv.lock
	uv sync

lint: ## Lint with ruff
	uv run ruff check .

fmt: ## Auto-format / fix lint issues with ruff
	uv run ruff check --fix .
	uv run ruff format .

test: ## Run the test suite
	uv run python -m pytest

run: ## Run the API locally with autoreload (reads .env)
	uv run uvicorn app.main:app --reload --port 8000

build: ## Build the Docker image
	docker build -t $(IMAGE) .

docker-run: ## Run the image, loading .env (Ollama on the host)
	docker run --rm -p 8000:8000 --env-file .env $(IMAGE)
