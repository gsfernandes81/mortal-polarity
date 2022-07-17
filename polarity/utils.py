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

import datetime as dt
import re
from typing import Tuple

import aiohttp
import hikari
from pytz import utc
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from . import cfg

url_regex = re.compile(
    "http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
)


Base = declarative_base()
db_engine = create_async_engine(cfg.db_url_async)
db_session = sessionmaker(db_engine, **cfg.db_session_kwargs)


class RefreshCmdListEvent(hikari.Event):
    def __init__(self, bot: hikari.GatewayBot, sync: bool = True):
        super().__init__()
        # Whether to run the sync_application_commands method of the app
        self.bot = bot
        self.sync = sync

    @property
    def app(self):
        return self.bot

    def dispatch(self):
        self.bot.event_manager.dispatch(self)


async def _create_or_get(cls, id, **kwargs):
    async with db_session() as session:
        async with session.begin():
            instance = await session.get(cls, id)
            if instance is None:
                instance = cls(id, **kwargs)
                session.add(instance)
    return instance


def weekend_period(today: dt.datetime = None) -> Tuple[dt.datetime, dt.datetime]:
    if today is None:
        today = dt.datetime.now()
    today = dt.datetime(today.year, today.month, today.day, tzinfo=utc)
    monday = today - dt.timedelta(days=today.weekday())
    # Weekend is friday 1700 UTC to Tuesday 1700 UTC
    friday = monday + dt.timedelta(days=4) + dt.timedelta(hours=17)
    tuesday = friday + dt.timedelta(days=4)
    return friday, tuesday


def week_period(today: dt.datetime = None) -> Tuple[dt.datetime, dt.datetime]:
    if today is None:
        today = dt.datetime.now()
    today = dt.datetime(today.year, today.month, today.day, tzinfo=utc)
    monday = today - dt.timedelta(days=today.weekday())
    start = monday + dt.timedelta(days=1) + dt.timedelta(hours=17)
    end = start + dt.timedelta(days=7)
    return start, end


def day_period(today: dt.datetime = None) -> Tuple[dt.datetime, dt.datetime]:
    if today is None:
        today = dt.datetime.now()
    today = dt.datetime(today.year, today.month, today.day, 17, tzinfo=utc)
    today_end = today + dt.timedelta(days=1)
    return today, today_end


async def follow_link_single_step(url: str) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get(url, allow_redirects=False) as resp:
            return resp.headers["Location"]
