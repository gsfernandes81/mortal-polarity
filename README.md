# mortal-polarity

Setting up the dev environment:

1. Get a working [Poetry](https://python-poetry.org/) installation
2. Run `poetry install` in the root of the git clone
3. `poetry shell` to jump into the virtualenv
4. [Optional] Set up the `.env` with environment variables refering to `polarity/cfg.py` & `.env-example`

Running code locally:

```
make run-local
```

Running tests locally:

```
make test
```

Running code locally with docker:

```
docker build -t polarity .
docker run --env-file=.env polarity
```

Deploying code to [railway](https://railway.app/)

0. Make sure you have the [railway cli](https://docs.railway.app/develop/cli) installed and are logged in
1. `make deploy-dev` to deploy to the dev instance
2. **CAUTION**: `make deploy-prod` to deploy to the production instance