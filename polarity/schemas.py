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
import datetime as dt
import functools
import logging
import re
from calendar import month_name as month
from typing import Type, Union

import aiohttp
import hikari
import lightbulb
from pytz import utc
from sector_accounting import Rotation
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, select
from sqlalchemy.orm import declarative_mixin, declared_attr
from sqlalchemy.sql.schema import Column

from . import cfg
from .utils import (
    Base,
    _send_embed_if_textable_channel,
    db_session,
    follow_link_single_step,
    operation_timer,
    weekend_period,
)


@declarative_mixin
class BasePostSettings:
    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()

    __mapper_args__ = {"eager_defaults": True}

    id = Column("id", Integer, primary_key=True)
    autoannounce_enabled = Column(
        "autoannounce_enabled", Boolean, default=True, server_default="t"
    )

    def __init__(self, id, autoannounce_enabled=True):
        self.id = id
        self.autoannounce_enabled = autoannounce_enabled

    async def get_announce_embed(self) -> hikari.Embed:
        pass


class LostSectorPostSettings(BasePostSettings, Base):
    async def get_announce_embed(self, date: dt.date = None) -> hikari.Embed:
        buffer = 1  # Minute
        if date is None:
            date = dt.datetime.now(tz=utc) - dt.timedelta(hours=16, minutes=60 - buffer)
        else:
            date = date + dt.timedelta(minutes=buffer)
        rot = Rotation.from_gspread_url(
            cfg.sheets_ls_url, cfg.gsheets_credentials, buffer=buffer
        )()

        # Follow the hyperlink to have the newest image embedded
        async with aiohttp.ClientSession() as session:
            async with session.get(
                rot.shortlink_gfx, allow_redirects=False
            ) as response:
                ls_gfx_url = str(response.headers["Location"])

        format_dict = {
            "month": month[date.month],
            "day": date.day,
            "sector": rot,
            "ls_url": ls_gfx_url,
        }

        return hikari.Embed(
            title="**Daily Lost Sector for {month} {day}**".format(**format_dict),
            description=(
                "<:LS:849727805994565662> **{sector.name}**:\n\n"
                + "• Exotic Reward (If Solo): {sector.reward}\n"
                + "• Champs: {sector.champions}\n"
                + "• Shields: {sector.shields}\n"
                + "• Burn: {sector.burn}\n"
                + "• Modifiers: {sector.modifiers}\n"
                + "\n"
                + "**More Info:** <https://kyber3000.com/LS>"
            ).format(**format_dict),
            color=cfg.kyber_pink,
        ).set_image(ls_gfx_url)


class XurPostSettings(BasePostSettings, Base):
    # url: the infographic url
    url = Column("url", String, nullable=False, default=cfg.defaults.xur.gfx_url)
    # post_url: hyperlink for the post title
    post_url = Column("post_url", String, default=cfg.defaults.xur.post_url)
    url_redirect_target = Column("url_redirect_target", String)
    url_last_modified = Column("url_last_modified", DateTime)
    url_last_checked = Column("url_last_checked", DateTime)
    # ToDo: Look for all armed url watchers at startup and start them again
    url_watcher_armed = Column(
        "url_watcher_armed", Boolean, default=False, server_default="f"
    )

    def __init__(
        self,
        id: int,
        url: str = cfg.defaults.xur.gfx_url,
        post_url: str = cfg.defaults.xur.post_url,
        autoannounce_enabled: bool = True,
    ):
        self.id = id
        self.url = url
        self.post_url = post_url
        self.autoannounce_enabled = autoannounce_enabled

    async def initialise_url_params(self):
        """
        Initialise the Url's redirect_target, last_modified and last_checked properties
        if they are set to None
        """
        if not (
            self.url_redirect_target == None
            or self.url_last_checked == None
            or self.url_last_modified == None
        ):
            return
        async with aiohttp.ClientSession() as session:
            async with session.get(self.url, allow_redirects=False) as resp:
                self.url_redirect_target = resp.headers["Location"]
                self.url_last_checked = dt.datetime.now()
                self.url_last_modified = dt.datetime.now()

    async def wait_for_url_update(self):
        async with db_session() as db_session_:
            async with db_session_.begin():
                db_session_.add(self)
                self.url_watcher_armed = True
            check_interval = 10
            async with aiohttp.ClientSession() as session:
                while True:
                    async with session.get(self.url, allow_redirects=False) as resp:
                        if resp.headers["Location"] != self.url_redirect_target:
                            async with db_session_.begin():
                                db_session_.add(self)
                                self.url_redirect_target = resp.headers["Location"]
                                self.url_last_modified = dt.datetime.now()
                                self.url_watcher_armed = False
                            return self
                        await asyncio.sleep(check_interval)

    async def get_announce_embed(
        self, correction: str = "", date: dt.date = None
    ) -> hikari.Embed:
        # Use the current date if none is specified
        if date is None:
            date = dt.datetime.now(tz=utc)
        # Get the period of validity for this message
        start_date, end_date = weekend_period(date)
        # Follow urls 1 step into redirects
        gfx_url = await follow_link_single_step(self.url)
        post_url = await follow_link_single_step(self.post_url)

        format_dict = {
            "start_month": month[start_date.month],
            "end_month": month[end_date.month],
            "start_day": start_date.day,
            "start_day_name": start_date.strftime("%A"),
            "end_day": end_date.day,
            "end_day_name": end_date.strftime("%A"),
            "post_url": post_url,
            "gfx_url": gfx_url,
        }
        return (
            hikari.Embed(
                title=("Xur's Inventory and Location").format(**format_dict),
                url=format_dict["post_url"],
                description=(
                    "**Arrives:** {start_day_name}, {start_month} {start_day}\n"
                    + "**Departs:** {end_day_name}, {end_month} {end_day}"
                ).format(**format_dict),
                color=cfg.kyber_pink,
            )
            .set_image(format_dict["gfx_url"])
            .set_footer(correction)
        )


@declarative_mixin
class BaseChannelRecord:
    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()

    __mapper_args__ = {"eager_defaults": True}

    id = Column("id", BigInteger, primary_key=True)
    # Note: if server_id is -1 then this is a dm channel
    server_id = Column("server_id", BigInteger)
    last_msg_id = Column("last_msg_id", BigInteger)
    enabled = Column("enabled", Boolean)

    # Settings object for this channel type
    settings_records: Type[BasePostSettings]

    def __init__(self, id: int, server_id: int, enabled: bool):
        self.id = id
        self.server_id = server_id
        self.enabled = enabled

    @classmethod
    def register_with_bot(
        cls,
        bot: lightbulb.BotApp,
        cmd_group: lightbulb.SlashCommandGroup,
        announce_event: Type[hikari.Event],
    ):
        cmd_group.child(
            lightbulb.option(
                "option",
                "Enabled or disabled",
                type=str,
                choices=["Enable", "Disable"],
                required=True,
            )(
                lightbulb.command(
                    "".join(re.findall("[A-Z][^A-Z]*", cls.__name__)[:-2]).lower(),
                    "Lost sector auto posts",
                    auto_defer=True,
                    guilds=cfg.kyber_discord_server_id,
                    inherit_checks=True,
                )(
                    lightbulb.implements(lightbulb.SlashSubCommand)(
                        functools.partial(cls.autopost_ctrl_usr_cmd, cls)
                    )
                )
            )
        )
        bot.listen(announce_event)(functools.partial(cls.announcer, cls))

    # Note this is a classmethod with cls supplied by functools.partial
    # from within the cls.register_with_bot function
    @staticmethod
    async def autopost_ctrl_usr_cmd(
        # Command for the user to be able to control autoposts in their server
        cls,
        ctx: lightbulb.Context,
    ) -> None:
        channel_id: int = ctx.channel_id
        server_id: int = ctx.guild_id if ctx.guild_id is not None else -1
        option: bool = True if ctx.options.option.lower() == "enable" else False
        bot = ctx.bot
        if await cls._check_bot_has_message_perms(bot, channel_id):
            async with db_session() as session:
                async with session.begin():
                    channel = await session.get(cls, channel_id)
                    if channel is None:
                        channel = cls(channel_id, server_id, option)
                        session.add(channel)
                    else:
                        channel.enabled = option
            await ctx.respond(
                " ".join(re.findall("[A-Z][^A-Z]*", cls.__name__)[:-2])
                + " autoposts {}".format("enabled" if option else "disabled")
            )
        else:
            await ctx.respond(
                'The bot does not have the "Send Messages" or the'
                + ' "Send Messages in Threads" permission here'
            )

    @staticmethod
    async def _check_bot_has_message_perms(
        bot: lightbulb.BotApp, channel: Union[hikari.TextableChannel, int]
    ) -> bool:
        if not isinstance(channel, hikari.TextableChannel):
            channel = await bot.rest.fetch_channel(channel)
        if isinstance(channel, hikari.TextableChannel):
            if isinstance(channel, hikari.TextableGuildChannel):
                guild = await channel.fetch_guild()
                self_member = await bot.rest.fetch_member(guild, bot.get_me())
                perms = lightbulb.utils.permissions_in(channel, self_member)
                # Check if we have the send messages permission in the channel
                # Refer to hikari.Permissions to see how / why this works
                # Note: Hikari doesn't recognize threads
                # Channel types 10, 11, 12 and 15 are thread types as specified in:
                # https://discord.com/developers/docs/resources/channel#channel-object-channel-types
                # If the channel is a thread, we need to check for the SEND_MESSAGES_IN_THREADS perm
                if channel.type in [10, 11, 12, 15]:
                    return (
                        hikari.Permissions.SEND_MESSAGES_IN_THREADS & perms
                    ) == hikari.Permissions.SEND_MESSAGES_IN_THREADS
                else:
                    return (
                        hikari.Permissions.SEND_MESSAGES & perms
                    ) == hikari.Permissions.SEND_MESSAGES
            else:
                return True

    # Note this is a classmethod with cls supplied by functools.partial
    # from within the cls.register_with_bot function
    @staticmethod
    async def announcer(cls, event):
        async with db_session() as session:
            async with session.begin():
                settings: BasePostSettings = await session.get(cls.settings_records, 0)
            async with session.begin():
                channel_id_list = (
                    await session.execute(select(cls).where(cls.enabled == True))
                ).fetchall()
                channel_id_list = [] if channel_id_list is None else channel_id_list
                channel_id_list = [channel[0].id for channel in channel_id_list]

            logging.info(
                # Note, need to implement regex to specify which announcement
                # is being carried out in these logs
                "Announcing {} posts to {} channels".format(
                    "base", len(channel_id_list)
                )
            )
            with operation_timer("Base announce"):
                embed = await settings.get_announce_embed()
                await asyncio.gather(
                    *[
                        _send_embed_if_textable_channel(
                            channel_id,
                            event,
                            embed,
                            cls,
                        )
                        for channel_id in channel_id_list
                    ]
                )


class LostSectorAutopostChannel(BaseChannelRecord, Base):
    settings_records: Type[BasePostSettings] = LostSectorPostSettings


class XurAutopostChannel(BaseChannelRecord, Base):
    settings_records: Type[BasePostSettings] = XurPostSettings


class Commands(Base):
    __tablename__ = "commands"
    __mapper_args__ = {"eager_defaults": True}
    name = Column("name", String, primary_key=True)
    description = Column("description", String)
    response = Column("response", String)

    def __init__(self, name, description, response):
        super().__init__()
        self.name = name
        self.description = description
        self.response = response
