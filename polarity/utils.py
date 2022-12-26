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
from copy import copy
from typing import List, Tuple, Union

import aiofiles
import aiohttp
import attr
import hikari as h
import lightbulb as lb
import toolbox
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
db_engine = create_async_engine(
    cfg.db_url_async, connect_args={"timeout": 120}, pool_pre_ping=True
)
db_session = sessionmaker(db_engine, **cfg.db_session_kwargs)


class FeatureDisabledError(Exception):
    pass


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
    yield lambda t: (t - start_time).total_seconds()
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


def _embed_for_migration(original_embed: h.Embed):
    return copy(original_embed).set_footer(
        "Admins, please re-invite the bot before {} to continue receiving autoposts".format(
            cfg.migration_deadline
        )
    )


def _component_for_migration(bot: lb.BotApp):
    return (
        bot.rest.build_action_row()
        .add_button(h.ButtonStyle.LINK, cfg.migration_invite)
        .set_label("Re-Invite")
        .add_to_container()
        .add_button(h.ButtonStyle.LINK, cfg.migration_help)
        .set_label("Help")
        .add_to_container(),
    )


async def _bot_has_webhook_perms(
    bot: lb.BotApp,
    channel_id: Union[h.GuildChannel, h.Snowflakeish],
    skip_cache: bool = False,
) -> bool:
    if not skip_cache:
        channel = bot.cache.get_guild_channel(channel_id)
    else:
        channel = None
    if not channel:
        channel = await bot.rest.fetch_channel(channel_id)
    bot_member = await bot.rest.fetch_member(channel.guild_id, bot.get_me())
    return h.Permissions.MANAGE_WEBHOOKS in toolbox.calculate_permissions(
        bot_member, channel
    )


@attr.s
class MessageFailureError(Exception):
    channel_id: int = attr.ib()
    message_kwargs: dict = attr.ib()
    source_exception_details: Exception = attr.ib()


async def send_message(
    bot: lb.BotApp, channel_id: int, message_kwargs: dict, crosspost: bool = False
) -> h.Message:
    try:
        channel = bot.cache.get_guild_channel(
            channel_id
        ) or await bot.rest.fetch_channel(channel_id)

        message = await channel.send(**message_kwargs)
        if crosspost:
            await bot.rest.crosspost_message(channel, message)
    except Exception as e:
        raise MessageFailureError(channel_id, message_kwargs, e)
    else:
        return message


async def _edit_embedded_message(
    message_id: int,
    channel_id: int,
    bot: h.GatewayBot,
    embed: h.Embed,
    logger=logging.getLogger("main/" + __name__),
) -> None:
    try:
        msg: h.Message = bot.cache.get_message(
            message_id
        ) or await bot.rest.fetch_message(channel_id, message_id)

        if (
            msg.guild_id != cfg.kyber_discord_server_id
            and not await _bot_has_webhook_perms(bot, channel_id)
        ):
            await msg.edit(
                content="",
                embed=_embed_for_migration(embed),
                components=_component_for_migration(bot),
            )
        else:
            await msg.edit(content="", embed=embed, components=None)
        try:
            await bot.rest.crosspost_message(channel_id, msg)
        except AttributeError:
            pass
        except h.BadRequestError as err:
            if not ("This message has already been crossposted" in str(err)):
                raise err
    except (h.ForbiddenError, h.NotFoundError):
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


async def alert_owner(
    *args: str,
    bot: lb.BotApp = None,
    channel: Union[None, int, h.TextableChannel],
    mention_mods: bool = True
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
