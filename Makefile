POETRY := $(shell command -v poetry 2> /dev/null)

ifdef POETRY
POETRY_CMD = poetry run
else
POETRY_CMD =
endif

deploy-dev:
	railway environment dev
	railway service mortal-polarity
	railway up -d

deploy-prod:
	railway environment production
	railway service mortal-polarity
	railway up -d

run-local: .env
	$(POETRY_CMD) honcho start

recreate-schemas: .env
	$(POETRY_CMD) honcho run python -m polarity.schemas --recreate-all

atlas-migration-plan: .env
	$(POETRY_CMD) honcho run atlas migrate diff --env sqlalchemy

atlas-migration-dry-run:
	@echo "$(POETRY_CMD) honcho run atlas migrate apply -u <MYSQL_URL> --dry-run"
	@$(POETRY_CMD) honcho run atlas migrate apply -u ${MYSQL_URL} --dry-run

atlas-migration-apply:
	@echo "$(POETRY_CMD) honcho run atlas migrate apply -u <MYSQL_URL>"
	@$(POETRY_CMD) honcho run atlas migrate apply -u ${MYSQL_URL}

test: .env
	$(POETRY_CMD) honcho run python -m pytest

.env:
	@echo "Please create a .env file with all variables as per polarity.cfg"
	@echo "and .env-example to be able to run this locally. Note that all"
	@echo "variables are required and the example values are not valid but"
	@echo "are there to show the approximate format of values."
	@exit 1
