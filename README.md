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

If running in WSL2 and testing bungie api functionality:
Run the below in an admin powershell prompt to make sure the port for oauth
authentication is forwarded
```
netsh interface portproxy add v4tov4 listenport=<external port> listenaddress=0.0.0.0 connectport=<internal port> connectaddress=<WSL2 IP address from hostname -I in WSL2>
```
And of course, set up forwarding on your router
Also make sure ssl is set up correctly

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