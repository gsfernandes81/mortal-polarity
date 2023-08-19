deploy-dev:
	railway environment dev
	railway service mortal-polarity
	railway up -d

deploy-prod:
	railway environment production
	railway service mortal-polarity
	railway up -d

run-local:
	poetry run honcho start

test:
	poetry run honcho run python -m pytest