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

import asyncio as aio
import concurrent.futures
import contextlib
import datetime as dt
import functools
import logging
import typing as t

import aiofiles
import aiohttp
import attr
import hikari as h
import lightbulb as lb
import yarl
from hmessage import HMessage
from pytz import utc

from . import cfg


class FeatureDisabledError(Exception):
    pass


@contextlib.contextmanager
def operation_timer(op_name, logger=logging.getLogger("main/" + __name__)):
    start_time = dt.datetime.now()
    logger.info("Announce started")
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


def weekend_period(today: dt.datetime = None) -> t.Tuple[dt.datetime, dt.datetime]:
    if today is None:
        today = dt.datetime.now()
    today = dt.datetime(today.year, today.month, today.day, tzinfo=utc)
    monday = today - dt.timedelta(days=today.weekday())
    # Weekend is friday 1700 UTC to Tuesday 1700 UTC
    friday = monday + dt.timedelta(days=4) + dt.timedelta(hours=17)
    tuesday = friday + dt.timedelta(days=4)
    return friday, tuesday


def week_period(today: dt.datetime = None) -> t.Tuple[dt.datetime, dt.datetime]:
    if today is None:
        today = dt.datetime.now()
    today = dt.datetime(today.year, today.month, today.day, tzinfo=utc)
    monday = today - dt.timedelta(days=today.weekday())
    start = monday + dt.timedelta(days=1) + dt.timedelta(hours=17)
    end = start + dt.timedelta(days=7)
    return start, end


def day_period(today: dt.datetime = None) -> t.Tuple[dt.datetime, dt.datetime]:
    if today is None:
        today = dt.datetime.now()
    today = dt.datetime(today.year, today.month, today.day, 17, tzinfo=utc)
    today_end = today + dt.timedelta(days=1)
    return today, today_end


async def follow_link_single_step(
    url: str, logger=logging.getLogger("main/" + __name__)
) -> str:
    async with aiohttp.ClientSession() as session:
        retries = 10
        retry_delay = 10
        for i in range(retries):
            async with session.get(url, allow_redirects=False) as resp:
                try:
                    return resp.headers["Location"]
                except KeyError:
                    # If we can't find the location key, warn and return the
                    # provided url itself
                    if resp.status >= 400:
                        logger.error(
                            "Could not find redirect for url "
                            + "{}, (status {})".format(url, resp.status)
                        )
                        if i < retries - 1:
                            logger.error("Retrying...")
                        await aio.sleep(retry_delay)
                        continue
                    else:
                        return url


@attr.s
class MessageFailureError(Exception):
    channel_id: int = attr.ib()
    message_kwargs: dict = attr.ib()
    source_exception_details: Exception = attr.ib()


async def find_duplicate_uncrossposted_message(
    message: HMessage,
    channel: h.GuildNewsChannel,
    lookback_days: int = 2,
) -> h.Message | None:
    async for channel_message in channel.fetch_history(
        after=dt.datetime.now(tz=utc) - dt.timedelta(days=lookback_days)
    ):
        channel_message_proto = HMessage.from_message(channel_message)

        if (
            h.MessageFlag.CROSSPOSTED not in channel_message.flags
            and channel_message_proto == message
        ):
            logging.error(
                "Found duplicate, uncrossposted lost sector message after reported "
                "failure to send. Returning message for crossposting if necessary..."
            )
            return channel_message
        else:
            return None


async def crosspost_message_with_retries(
    bot: lb.BotApp,
    channel: h.GuildNewsChannel | int,
    message_id: int,
):
    if isinstance(channel, int):
        channel = bot.cache.get_guild_channel(channel) or await bot.rest.fetch_channel(
            channel
        )
    if not isinstance(channel, h.GuildNewsChannel):
        logging.warning(
            "Attempted to crosspost a message in a non-news channel. Skipping..."
        )
        return
    crosspost_backoff = 30
    while True:
        try:
            await bot.rest.crosspost_message(channel.id, message_id)
        except Exception as e:
            if (
                isinstance(e, h.BadRequestError)
                and "This message has already been crossposted" in e.message
            ):
                # If the message has already been crossposted
                # then we can ignore the error
                break

            e.add_note("Failed to publish message with exception\n")
            logging.exception(e)
            await aio.sleep(crosspost_backoff)
            crosspost_backoff = crosspost_backoff * 2
        else:
            break


async def send_message(
    bot: lb.BotApp,
    msg_proto: HMessage,
    channel_id: int,
    crosspost: bool = True,
    deduplicate: bool = False,
) -> h.Message:
    send_backoff = 10
    while True:
        try:
            channel: h.TextableGuildChannel = (
                bot.cache.get_guild_channel(channel_id)
                or await bot.rest.fetch_channel(channel_id)
                or None
            )
            msg = await channel.send(**msg_proto.to_message_kwargs())
        except Exception as e:
            e.add_note("Failed to send lost sector with exception\n")
            logging.exception(e)

            if deduplicate and channel:
                # channel.send sometimes "fails" while still sending out
                # the correct message. In case this happens, check for
                # such a message, assign it to "msg" and continue forward
                # for it to be corssposted
                #
                # Wait before doing this to ensure that when
                # find_duplicate_uncrossposted_message is called and checks
                # the channel message history, the message will appear if
                # it was sent
                await aio.sleep(send_backoff / 2)
                msg = await find_duplicate_uncrossposted_message(msg_proto, channel)
                if msg:
                    break

            await aio.sleep(send_backoff)
            send_backoff = send_backoff * 2
        else:
            break

    if not crosspost:
        return msg

    await crosspost_message_with_retries(bot, channel, msg)

    return msg


async def download_linked_image(url: str) -> t.Union[str, None]:
    # Returns the name of the downloaded image
    # Throws an aiohttp.client_exceptions.InvalidURL on
    # an invalid url
    # ToDo: Implement a per URL lock on this function
    #       Also implement a naming scheme based on path
    #       And implement a name size limit as required
    async with aiohttp.ClientSession() as session:
        backoff_timer = 1
        try:
            while True:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        name = _get_uri_name(resp.url)
                        f = await aiofiles.open(name, mode="wb")
                        await f.write(await resp.read())
                        await f.close()
                        return name
                    else:
                        await aio.sleep(backoff_timer)
                        backoff_timer = backoff_timer + (1 / backoff_timer)
        except aiohttp.InvalidURL:
            return None


def _get_uri_name(url: str) -> str:
    return yarl.URL(url).name


async def run_in_thread_pool(func, *args, **kwargs):
    # Apply arguments without executing with functools partial
    partial_func = functools.partial(func, *args, **kwargs)
    # Execute in thread pool
    future = aio.get_event_loop().run_in_executor(
        concurrent.futures.ThreadPoolExecutor(), partial_func
    )
    await future
    exception = future.exception()
    if exception is not None:
        raise exception


async def alert_owner(
    *args: str,
    bot: lb.BotApp = None,
    channel: t.Union[None, int, h.TextableChannel],
    mention_mods: bool = True,
):
    # Sends an alert in the specified channels
    # logs the same alert
    # If no channels specified, returns the alert string
    alert = ""

    for arg in args:
        alert = alert + " " + str(arg)

    alert = "Warning:" + alert + " "

    if mention_mods:
        alert = alert + "<@&{}> ".format(cfg.control_discord_role_id)

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


def endl(*args: t.List[str]) -> str:
    # Returns a string with each argument separated by a newline
    return "\n".join([str(arg) for arg in args])


class space:
    zero_width = "\u200b"
    hair = "\u200a"
    six_per_em = "\u2006"
    thin = "\u2009"
    punctuation = "\u2008"
    four_per_em = "\u2005"
    three_per_em = "\u2004"
    figure = "\u2007"
    en = "\u2002"
    em = "\u2003"


def followable_name(*, id: int):
    return next((key for key, value in cfg.followables.items() if value == id), id)


def check_admin(func):
    async def wrapper(ctx: lb.Context, *args, **kwargs):
        if ctx.author.id not in cfg.admins:
            await ctx.respond("Only admins can use this command")
            return
        return await func(ctx, *args, **kwargs)

    return wrapper


def ensure_session(sessionmaker):
    """Decorator for functions that optionally want an sqlalchemy async session

    Provides an async session via the `session` parameter if one is not already
    provided via the same.

    Caution: Always put below `@classmethod` and `@staticmethod`"""

    def ensured_session(f: t.Coroutine):
        async def wrapper(*args, **kwargs):
            session = kwargs.pop("session", None)
            if session is None:
                async with sessionmaker() as session:
                    async with session.begin():
                        return await f(*args, **kwargs, session=session)
            else:
                return await f(*args, **kwargs, session=session)

        return wrapper

    return ensured_session
