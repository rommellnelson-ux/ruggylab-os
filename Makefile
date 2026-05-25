# Makefile – RuggyLab OS operational helper
# Usage: make <target>
# Default target: help

.DEFAULT_GOAL := help
COMPOSE        := docker compose
APP_SERVICE    := app
PYTHON         := python

# ── Help ──────────────────────────────────────────────────────────────────────
.PHONY: help
help: ## List all available targets
	@echo ""
	@echo "  RuggyLab OS – Makefile targets"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ── Docker ────────────────────────────────────────────────────────────────────
.PHONY: build
build: ## Build (or rebuild) the Docker image
	$(COMPOSE) build

.PHONY: up
up: ## Start all services in detached mode
	$(COMPOSE) up -d

.PHONY: down
down: ## Stop and remove containers (keeps volumes)
	$(COMPOSE) down

.PHONY: restart
restart: down up ## Restart all services

.PHONY: logs
logs: ## Tail the app service logs
	$(COMPOSE) logs -f $(APP_SERVICE)

.PHONY: ps
ps: ## Show running containers
	$(COMPOSE) ps

# ── Database ──────────────────────────────────────────────────────────────────
.PHONY: migrate
migrate: ## Run Alembic migrations inside the migrate service (profile: migrate)
	$(COMPOSE) --profile migrate up migrate

.PHONY: psql
psql: ## Open a psql shell inside the postgres container
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-ruggylab} $${POSTGRES_DB:-ruggylab}

# ── Redis ─────────────────────────────────────────────────────────────────────
.PHONY: redis-cli
redis-cli: ## Open a redis-cli shell inside the redis container
	$(COMPOSE) exec redis redis-cli

# ── Code quality ──────────────────────────────────────────────────────────────
.PHONY: lint
lint: ## Run ruff (lint + format check) and mypy
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .
	$(PYTHON) -m mypy app

.PHONY: format
format: ## Auto-fix ruff lint issues and reformat code
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m ruff format .

.PHONY: test
test: ## Run the test suite with pytest
	$(PYTHON) -m pytest --tb=short -q

.PHONY: security
security: ## Run bandit (SAST) and pip-audit (dependency audit)
	$(PYTHON) -m bandit -q -r app -c pyproject.toml
	pip-audit -r requirements.txt --ignore-vuln PYSEC-2025-183

# ── Cleanup ───────────────────────────────────────────────────────────────────
.PHONY: clean
clean: ## Stop containers AND delete all named volumes (DESTRUCTIVE)
	@echo "WARNING: This will permanently delete all Docker volumes (database data, etc.)."
	@read -p "Type 'yes' to confirm: " confirm && [ "$$confirm" = "yes" ] || (echo "Aborted."; exit 1)
	$(COMPOSE) down -v

.PHONY: clean-images
clean-images: ## Remove locally built images
	docker image prune -f --filter label=org.opencontainers.image.title="RuggyLab OS"
