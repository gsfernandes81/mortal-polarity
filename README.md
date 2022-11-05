# mortal-polarity

Setting up the dev environment:

1. Get a working poetry installation
2. `poetry install`
3. Set up `.env` with environment variables referencing polarity.cfg
4. `poetry shell` to jump into the virtualenv

Running code locally:

0. `poetry shell`
1. `honcho start release` (mainly if a db migration is needed)
2. `honcho start clock`

Running code locally with docker:
NOTE: Migrations not set up yet

1. `docker build -t polarity .`
2. `docker run --env-file=.env polarity`