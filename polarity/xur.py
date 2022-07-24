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
import logging
from calendar import month_name as month
from typing import List, Type

import aiohttp
import hikari
import lightbulb
import lightbulb.ext.wtf as wtf
from pytz import utc
from sqlalchemy import Column, select
from sqlalchemy.types import Boolean, DateTime, String

from . import cfg
from .autoannounce import (
    BaseChannelRecord,
    BaseCustomEvent,
    BasePostSettings,
    WeekendResetSignal,
)
from .utils import (
    Base,
    _create_or_get,
    _edit_embedded_message,
    db_session,
    follow_link_single_step,
    operation_timer,
    weekend_period,
)


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


class XurAutopostChannel(BaseChannelRecord, Base):
    settings_records: Type[BasePostSettings] = XurPostSettings


class XurSignal(BaseCustomEvent):
    async def conditional_weekend_reset_repeater(
        self, event: WeekendResetSignal
    ) -> None:
        if not await self.is_autoannounce_enabled():
            return

        settings: XurPostSettings = await _create_or_get(XurPostSettings, 0)

        # Debug code
        if cfg.test_env and cfg.trigger_without_url_update:
            event.bot.dispatch(self)

        await settings.wait_for_url_update()
        event.bot.dispatch(self)

    async def is_autoannounce_enabled(self):
        settings = await _create_or_get(XurPostSettings, 0, autoannounce_enabled=True)
        return settings.autoannounce_enabled

    def arm(self) -> None:
        self.bot.listen()(self.conditional_weekend_reset_repeater)

    async def wait_for_url_update(self):
        settings: XurPostSettings = await _create_or_get(XurPostSettings, 0)
        await settings.wait_for_url_update()


async def xur_autoposts(ctx: lightbulb.Context):
    option = True if ctx.options.option.lower() == "enable" else False
    async with db_session() as session:
        async with session.begin():
            settings = await session.get(XurPostSettings, 0)
            if settings is None:
                settings = XurPostSettings(0, autoannounce_enabled=option)
                session.add(settings)
            else:
                settings.autoannounce_enabled = option
    await ctx.respond(
        "Xur announcements {}".format("Enabled" if option else "Disabled")
    )


async def xur_gfx_url(ctx: lightbulb.Context):
    url = ctx.options.url.lower() if ctx.options.url is not None else None
    async with db_session() as session:
        async with session.begin():
            settings: XurPostSettings = await session.get(XurPostSettings, 0)
            if ctx.options.url is None:
                await ctx.respond(
                    (
                        "The current Xur Infographic url is <{}>\n"
                        + "The default Xur Infographic url is <{}>"
                    ).format(
                        "unset" if settings is None else settings.url,
                        cfg.defaults.xur.gfx_url,
                    )
                )
                return
            if settings is None:
                settings = XurPostSettings(0)
                settings.url = url
                await settings.initialise_url_params()
                session.add(settings)
            else:
                settings.url = url
    await ctx.respond("Xur Infographic url updated to <{}>".format(url))


async def xur_post_url(ctx: lightbulb.Context):
    url = ctx.options.url.lower() if ctx.options.url is not None else None
    async with db_session() as session:
        async with session.begin():
            settings: XurPostSettings = await session.get(XurPostSettings, 0)
            if ctx.options.url is None:
                await ctx.respond(
                    (
                        "The current Xur Post url is <{}>\n"
                        + "The default Xur Post url is <{}>"
                    ).format(
                        "unset" if settings is None else settings.post_url,
                        cfg.defaults.xur.post_url,
                    )
                )
                return
            if settings is None:
                settings = XurPostSettings(0)
                settings.post_url = url
                session.add(settings)
            else:
                settings.post_url = url
    await ctx.respond("Xur Post url updated to <{}>".format(url))


async def xur_rectify_announcement(ctx: lightbulb.Context):
    """Correct a mistake in the xur announcement
    pull from urls again and update existing posts"""
    change = ctx.options.change if ctx.options.change else ""
    async with db_session() as session:
        async with session.begin():
            settings: XurPostSettings = await session.get(XurPostSettings, 0)
            if settings is None:
                await ctx.respond("Please enable xur autoposts before using this cmd")
            channel_record_list = (
                await session.execute(
                    select(XurAutopostChannel).where(XurAutopostChannel.enabled == True)
                )
            ).fetchall()
            channel_record_list = (
                [] if channel_record_list is None else channel_record_list
            )
            channel_record_list: List[XurAutopostChannel] = [
                channel[0] for channel in channel_record_list
            ]
        logging.info("Correcting xur posts")
        with operation_timer("Xur announce correction"):
            await ctx.respond("Correcting posts now")
            embed = await settings.get_announce_embed(
                settings.url,
                settings.post_url,
                change,
            )
            await asyncio.gather(
                *[
                    _edit_embedded_message(
                        channel_record.last_msg_id,
                        channel_record.id,
                        ctx.bot,
                        embed,
                    )
                    for channel_record in channel_record_list
                ]
            )
            await ctx.edit_last_response("Posts corrected")


async def manual_xur_announce(ctx: lightbulb.Context):
    ctx.bot.dispatch(XurSignal(ctx.bot))
    await ctx.respond("Xur announcements being sent out now")


# Xur management commands for kyber
xur_announcements = wtf.Command[
    wtf.Implements[lightbulb.SlashSubGroup],
    wtf.Name["xur"],
    wtf.Description["Xur announcement management"],
    wtf.Guilds[cfg.kyber_discord_server_id],
    wtf.InheritChecks[True],
    wtf.Subcommands[
        # Autoposts Enable/Disable
        wtf.Command[
            wtf.Name["autoposts"],
            wtf.Description[
                "Enable or disable all automatic lost sector announcements"
            ],
            wtf.AutoDefer[True],
            wtf.InheritChecks[True],
            wtf.Options[
                wtf.Option[
                    wtf.Name["option"],
                    wtf.Description["Enable or disable"],
                    wtf.Type[str],
                    wtf.Choices["Enable", "Disable"],
                    wtf.Required[True],
                ],
            ],
            wtf.Implements[lightbulb.SlashSubCommand],
            wtf.Executes[xur_autoposts],
        ],
        wtf.Command[
            wtf.Name["infogfx_url"],
            wtf.Description["Set the Xur infographic url, to check and post"],
            wtf.AutoDefer[True],
            wtf.InheritChecks[True],
            wtf.Options[
                wtf.Option[
                    wtf.Name["url"],
                    wtf.Description["The url to set"],
                    wtf.Type[str],
                    wtf.Required[False],
                ],
            ],
            wtf.Implements[lightbulb.SlashSubCommand],
            wtf.Executes[xur_gfx_url],
        ],
        wtf.Command[
            wtf.Name["post_url"],
            wtf.Description["Set the Xur infographic url, to check and post"],
            wtf.AutoDefer[True],
            wtf.InheritChecks[True],
            wtf.Options[
                wtf.Option[
                    wtf.Name["url"],
                    wtf.Description["The url to set"],
                    wtf.Type[str],
                    wtf.Required[False],
                ],
            ],
            wtf.Implements[lightbulb.SlashSubCommand],
            wtf.Executes[xur_post_url],
        ],
        wtf.Command[
            wtf.Name["update"],
            wtf.Description[
                "Update a post, optionally with text saying what has changed"
            ],
            wtf.AutoDefer[True],
            wtf.InheritChecks[True],
            wtf.Options[
                wtf.Option[
                    wtf.Name["change"],
                    wtf.Description["What has changed"],
                    wtf.Type[str],
                    wtf.Required[False],
                ],
            ],
            wtf.Implements[lightbulb.SlashSubCommand],
            wtf.Executes[xur_rectify_announcement],
        ],
        wtf.Command[
            wtf.Name["announce"],
            wtf.Description["Trigger an announcement manually"],
            wtf.AutoDefer[True],
            wtf.InheritChecks[True],
            wtf.Implements[lightbulb.SlashSubCommand],
            wtf.Executes[manual_xur_announce],
        ],
    ],
]


def register(bot, usr_ctrl_cmd_group, kyber_ctrl_cmd_group):
    XurSignal(bot).arm()
    XurAutopostChannel.register_with_bot(bot, usr_ctrl_cmd_group, XurSignal)
    kyber_ctrl_cmd_group.child(xur_announcements)
