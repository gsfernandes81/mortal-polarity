# Copyright © 2019-present gsfernandes81

# This file is part of "mortal-polarity".

# mortal-polarity is free software: you can redistribute it and/or modify it under the
# terms of the GNU Affero General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later version.

# "mortal-polarity" is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE. See the GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License along with
# mortal-polarity. If not, see <https://www.gnu.org/licenses/>.

import abc
import json
import ssl
import typing as t
from os import getenv as __getenv

import hikari as h
from sqlalchemy.ext.asyncio import AsyncSession


def _getenv(var_name: str, default: t.Optional[str] = None) -> str:
    var = __getenv(var_name)
    if var is None:
        if default is not None:
            # print(f"Loaded {var_name} with default value {default}")
            return default
        raise ValueError(f"Environment variable {var_name} not set")
    else:
        # print(f"Loaded {var_name}")
        pass
    return str(var)


def _test_env(var_name: str) -> list[int] | bool:
    test_env = _getenv(var_name, default="false")
    test_env = test_env.lower()
    test_env = (
        [int(env.strip()) for env in test_env.split(",")]
        if test_env != "false"
        else False
    )
    return test_env


def _lightbulb_params() -> dict:
    lightbulb_params = {"token": discord_token}
    if test_env:
        lightbulb_params["default_enabled_guilds"] = test_env
    else:
        lightbulb_params["default_enabled_guilds"] = [
            kyber_discord_server_id,
            control_discord_server_id,
        ]
    return lightbulb_params


def _db_urls(var_name: str, var_name_alternative) -> tuple[str, str]:
    try:
        db_url = _getenv(var_name)
    except ValueError:
        db_url = _getenv(var_name_alternative)

    __repl_till = db_url.find("://")
    db_url = db_url[__repl_till:]
    db_url_async = "mysql+asyncmy" + db_url
    db_url = "mysql" + db_url
    return db_url, db_url_async


def _db_config():
    db_session_kwargs_sync = {
        "expire_on_commit": False,
    }
    db_session_kwargs = db_session_kwargs_sync | {
        "class_": AsyncSession,
    }

    db_connect_args = {}
    if _getenv("MYSQL_SSL", "true") == "true":
        ssl_ctx = ssl.create_default_context(
            cafile="/etc/ssl/certs/ca-certificates.crt"
        )
        ssl_ctx.verify_mode = ssl.CERT_REQUIRED
        db_connect_args.update({"ssl": ssl_ctx})

    db_engine_args = {
        "max_overflow": -1,
        "isolation_level": "READ COMMITTED",
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    }
    return db_session_kwargs, db_session_kwargs_sync, db_connect_args, db_engine_args


def _sheets_credentials(
    proj_id: str,
    priv_key_id: str,
    priv_key: str,
    client_email: str,
    client_id: str,
    client_x509_cert_url: str,
) -> dict[str, str]:
    gsheets_credentials = {
        "type": "service_account",
        "project_id": _getenv(proj_id),
        "private_key_id": _getenv(priv_key_id),
        "private_key": _getenv(priv_key).replace("\\n", "\n"),
        "client_email": _getenv(client_email),
        "client_id": _getenv(client_id),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": _getenv(client_x509_cert_url),
    }
    return gsheets_credentials


###### Environment variables ######

# Discord control server config
control_discord_server_id = int(_getenv("CONTROL_DISCORD_SERVER_ID"))
control_discord_role_id = int(_getenv("CONTROL_DISCORD_ROLE_ID"))
admins = [int(admin.strip()) for admin in _getenv("ADMINS").split(",")]
kyber_discord_server_id = int(_getenv("KYBER_DISCORD_SERVER_ID"))
log_channel = int(_getenv("LOG_CHANNEL_ID"))
alerts_channel = int(_getenv("ALERTS_CHANNEL_ID"))

# Discord environment config
discord_token = _getenv("DISCORD_TOKEN")
test_env = _test_env("TEST_ENV")

# Discord constants
embed_default_color = h.Color(int(_getenv("EMBED_DEFAULT_COLOR"), 16))
embed_error_color = h.Color(int(_getenv("EMBED_ERROR_COLOR"), 16))
followables: t.Dict[str, int] = json.loads(_getenv("FOLLOWABLES"), parse_int=int)

# Database URLs
db_url, db_url_async = _db_urls("MYSQL_PRIVATE_URL", "MYSQL_URL")

# Sheets credentials & URLs
gsheets_credentials = _sheets_credentials(
    "SHEETS_PROJECT_ID",
    "SHEETS_PRIVATE_KEY_ID",
    "SHEETS_PRIVATE_KEY",
    "SHEETS_CLIENT_EMAIL",
    "SHEETS_CLIENT_ID",
    "SHEETS_CLIENT_X509_CERT_URL",
)
sheets_ls_url = _getenv("SHEETS_LS_URL")

# Bungie credentials
bungie_api_key = _getenv("BUNGIE_API_KEY")
bungie_client_id = _getenv("BUNGIE_CLIENT_ID")
bungie_client_secret = _getenv("BUNGIE_CLIENT_SECRET")


port = int(_getenv("PORT", 8080))
#### Environment variables end ####

###################################

####### Configs & constants #######

(
    db_session_kwargs,
    db_session_kwargs_sync,
    db_connect_args,
    db_engine_args,
) = _db_config()
lightbulb_params = _lightbulb_params()


class defaults(abc.ABC):
    class xur(abc.ABC):
        gfx_url = "https://kyber3000.com/Xur"
        post_url = "https://kyber3000.com/Xurpost"

    class weekly_reset(abc.ABC):
        gfx_url = "https://kyber3000.com/Reset"
        post_url = "https://kyber3000.com/Resetpost"


##### Configs & constants end #####
