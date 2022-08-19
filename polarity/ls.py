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

import hikari
import lightbulb
from lightbulb.ext import wtf
from pytz import utc
from sector_accounting import Rotation
from sqlalchemy import select

from . import cfg
from .autopost import (
    AutopostsBase,
    BaseChannelRecord,
    BaseCustomEvent,
    BasePostSettings,
    DailyResetSignal,
)
from .utils import (
    Base,
    _create_or_get,
    _edit_embedded_message,
    db_session,
    follow_link_single_step,
    operation_timer,
)


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
        ls_gfx_url = await follow_link_single_step(rot.shortlink_gfx)

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


class LostSectorAutopostChannel(BaseChannelRecord, Base):
    settings_records: Type[BasePostSettings] = LostSectorPostSettings


class LostSectorSignal(BaseCustomEvent):
    async def conditional_daily_reset_repeater(self, event: DailyResetSignal) -> None:
        if await self.is_autoannounce_enabled():
            event.bot.dispatch(self)

    async def is_autoannounce_enabled(self):
        settings = await _create_or_get(
            LostSectorPostSettings, 0, autoannounce_enabled=True
        )
        return settings.autoannounce_enabled

    def arm(self) -> None:
        self.bot.listen()(self.conditional_daily_reset_repeater)


async def ls_control(ctx: lightbulb.Context):
    option = True if ctx.options.option.lower() == "enable" else False
    async with db_session() as session:
        async with session.begin():
            settings = await session.get(LostSectorPostSettings, 0)
            if settings is None:
                settings = LostSectorPostSettings(0, option)
                session.add(settings)
            else:
                settings.autoannounce_enabled = option
    await ctx.respond(
        "Lost sector announcements {}".format("Enabled" if option else "Disabled")
    )


async def ls_announce(ctx: lightbulb.Context):
    ctx.bot.dispatch(LostSectorSignal(ctx.bot))
    await ctx.respond("Announcing now")


class LostSectors(AutopostsBase):
    def __init__(self):
        super().__init__()
        self.settings_table = LostSectorPostSettings
        self.autopost_channel_table = LostSectorAutopostChannel

    def register(self, bot: lightbulb.BotApp) -> None:
        LostSectorSignal(bot).arm()
        LostSectorAutopostChannel.register(
            bot, self.autopost_cmd_group, LostSectorSignal
        )
        logging.warning(self.autopost_cmd_group)
        self.control_cmd_group.child(self.commands())

    def commands(self):
        return wtf.Command[
            wtf.Implements[lightbulb.SlashSubGroup],
            wtf.Name["ls"],
            wtf.Description["Lost sector announcement management"],
            wtf.Guilds[cfg.control_discord_server_id],
            wtf.InheritChecks[True],
            wtf.Subcommands[
                wtf.Command[
                    wtf.Name["autoposts"],
                    wtf.Description["Enable or disable automatic announcements"],
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
                    wtf.Executes[ls_control],
                ],
                wtf.Command[
                    wtf.Name["update"],
                    wtf.Description[
                        "Update a lost sector post, optionally with text saying what has changed"
                    ],
                    wtf.Executes[self.update],
                    wtf.InheritChecks[True],
                    wtf.Implements[lightbulb.SlashSubCommand],
                ],
                wtf.Command[
                    wtf.Name["announce"],
                    wtf.Description["Trigger an announcement manually"],
                    wtf.AutoDefer[True],
                    wtf.InheritChecks[True],
                    wtf.Implements[lightbulb.SlashSubCommand],
                    wtf.Executes[ls_announce],
                ],
            ],
        ]

    async def update(self, ctx: lightbulb.Context):
        """Correct a mistake in the announcement"""
        change = ctx.options.change if ctx.options.change else ""
        async with db_session() as session:
            async with session.begin():
                settings: LostSectorPostSettings = await session.get(
                    self.settings_table, 0
                )
                if settings is None:
                    await ctx.respond("Please enable autoposts before using this cmd")

                channel_record_list = (
                    await session.execute(
                        select(self.autopost_channel_table).where(
                            self.autopost_channel_table.enabled == True
                        )
                    )
                ).fetchall()
                channel_record_list = (
                    [] if channel_record_list is None else channel_record_list
                )
                channel_record_list: List[BaseChannelRecord] = [
                    channel[0] for channel in channel_record_list
                ]
            logging.info("Correcting posts")
            with operation_timer("Announce correction"):
                await ctx.respond("Correcting posts now")
                embed = await settings.get_announce_embed(
                    change,
                )
                await asyncio.gather(
                    *[
                        _edit_embedded_message(
                            channel_record.last_msg_id,
                            channel_record.id,
                            ctx.bot,
                            embed,
                            announce_if_guild=cfg.kyber_discord_server_id,
                        )
                        for channel_record in channel_record_list
                    ],
                    return_exceptions=True
                )
                await ctx.edit_last_response("Posts corrected")


lost_sectors = LostSectors()
