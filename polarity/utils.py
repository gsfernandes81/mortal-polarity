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

import asyncio
import concurrent.futures
import contextlib
import datetime as dt
import functools
import logging
import re
from typing import List, Tuple, Union

import aiofiles
import aiohttp
import hikari
import lightbulb
import yarl
from pytz import utc
from sqlalchemy import update
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from . import cfg

url_regex = re.compile(
    "http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
)


Base = declarative_base()
db_engine = create_async_engine(cfg.db_url_async, connect_args={"timeout": 120})
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


@contextlib.contextmanager
def operation_timer(op_name, logger=logging.getLogger("main/" + __name__)):
    start_time = dt.datetime.now()
    logger.info("Announce started".format(name=op_name))
    yield
    end_time = dt.datetime.now()
    time_delta = end_time - start_time
    minutes = time_delta.seconds // 60
    seconds = time_delta.seconds % 60
    logger.info(
        "{name} finished in {mins} minutes and {secs} seconds".format(
            name=op_name, mins=minutes, secs=seconds
        )
    )


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


async def follow_link_single_step(
    url: str, logger=logging.getLogger("main/" + __name__)
) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get(url, allow_redirects=False) as resp:
            try:
                return resp.headers["Location"]
            except KeyError:
                # If we can't find the location key, warn and return the
                # provided url itself
                logger.info(
                    "Could not find redirect for url "
                    + "{}, returning as is".format(url)
                )
                return url


async def _send_embed(
    channel_id: int,
    event: hikari.Event,
    embed: hikari.Embed,
    channel_table,  # Must be the class of the channel, not an instance
    announce_if_guild=-1,  # Announce if channel is in this guild
    logger=logging.getLogger("main/" + __name__),
) -> None:
    try:
        channel = event.bot.cache.get_guild_channel(
            channel_id
        ) or await event.bot.rest.fetch_channel(channel_id)
        # Can add hikari.GuildNewsChannel for announcement channel support
        # could be useful if we automate more stuff for Kyber
        if isinstance(channel, hikari.TextableChannel):
            async with db_session() as session:
                async with session.begin():
                    channel_record = await session.get(channel_table, channel_id)
                    message = await channel.send(embed=embed)
                    channel_record.last_msg_id = message.id
                    if channel_record.server_id == announce_if_guild:
                        await event.bot.rest.crosspost_message(channel, message)

    except (hikari.ForbiddenError, hikari.NotFoundError):
        logger.warning(
            "Channel {} not found or not messageable, disabling posts in {}".format(
                channel_id, str(channel_table.__class__.__name__)
            )
        )
        async with db_session() as session:
            async with session.begin():
                await session.execute(
                    update(channel_table)
                    .where(channel_table.id == channel_id)
                    .values(enabled=False)
                )


async def _edit_embedded_message(
    message_id: int,
    channel_id: int,
    bot: hikari.GatewayBot,
    embed: hikari.Embed,
    announce_if_guild: int = -1,
    logger=logging.getLogger("main/" + __name__),
) -> None:
    try:
        msg: hikari.Message = bot.cache.get_message(
            message_id
        ) or await bot.rest.fetch_message(channel_id, message_id)
        if isinstance(msg, hikari.Message):
            await msg.edit(content="", embed=embed)
            try:
                if msg.guild_id == announce_if_guild:
                    await bot.rest.crosspost_message(channel_id, msg)
            except AttributeError:
                pass
            except hikari.BadRequestError as err:
                if not ("This message has already been crossposted" in str(err)):
                    raise err
    except (hikari.ForbiddenError, hikari.NotFoundError):
        logging.warning("Message {} not found or not editable".format(message_id))


async def _download_linked_image(url: str) -> str:
    # Returns the name of the downloaded image
    # Throws an aiohttp.client_exceptions.InvalidURL on
    # an invalid url
    # ToDo: Implement a per URL lock on this function
    #       Also implement a naming scheme based on path
    #       And implement a name size limit as required
    async with aiohttp.ClientSession() as session:
        backoff_timer = 1
        while True:
            async with session.get(url) as resp:
                if resp.status == 200:
                    name = _get_uri_name(resp.url)
                    f = await aiofiles.open(name, mode="wb")
                    await f.write(await resp.read())
                    await f.close()
                    return name
                else:
                    await asyncio.sleep(backoff_timer)
                    backoff_timer = backoff_timer + (1 / backoff_timer)


def _get_uri_name(url: str) -> str:
    return yarl.URL(url).name


async def _run_in_thread_pool(func, *args, **kwargs):
    # Apply arguments without executing with functools partial
    partial_func = functools.partial(func, *args, **kwargs)
    # Execute in thread pool
    future = asyncio.get_event_loop().run_in_executor(
        concurrent.futures.ThreadPoolExecutor(), partial_func
    )
    await future
    exception = future.exception()
    if exception is not None:
        raise exception


async def _discord_alert(
    *args: str,
    bot: lightbulb.BotApp = None,
    channel: Union[None, int, hikari.TextableChannel],
    mention_mods: bool = True,
    logger=logging.getLogger("main/" + __name__)
):
    # Sends an alert in the specified channels
    # logs the same alert
    # If no channels specified, returns the alert string
    alert = ""

    for arg in args:
        alert = alert + " " + str(arg)

    alert = "Warning:" + alert + " "

    if mention_mods:
        alert = alert + "<@&{}> ".format(cfg.admin_role)

    logger.warning(alert)

    # If we get a single channel, turn it into a len() = 1 list
    if isinstance(channel, int):
        if bot is None:
            raise ValueError("bot needs to be specified if channel is int")
        channel = bot.cache.get_guild_channel(channel) or await bot.rest.fetch_channel(
            channel
        )
    elif channel is None:
        return alert

    # Send the alert in the channel
    await channel.send(alert, role_mentions=True)
