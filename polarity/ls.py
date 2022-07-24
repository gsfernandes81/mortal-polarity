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
from calendar import month_name as month
from typing import Type

import aiohttp
import hikari
import lightbulb
from pytz import utc
from sector_accounting import Rotation

from . import cfg
from .autoannounce import (
    BaseChannelRecord,
    BaseCustomEvent,
    BasePostSettings,
    DailyResetSignal,
)
from .utils import Base, _create_or_get, db_session


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


@lightbulb.option(
    "option",
    "Enable or disable",
    type=str,
    choices=["Enable", "Disable"],
    required=True,
)
@lightbulb.command(
    "ls_announcements",
    "Enable or disable all automatic lost sector announcements",
    auto_defer=True,
    # The following NEEDS to be included in all privledged commands
    inherit_checks=True,
)
@lightbulb.implements(lightbulb.SlashSubCommand)
async def ls_autoposts_kyber_ctrl_cmd(ctx: lightbulb.Context):
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


def register(bot, usr_ctrl_cmd_group, kyber_ctrl_cmd_group):
    LostSectorSignal(bot).arm()
    LostSectorAutopostChannel.register_with_bot(
        bot, usr_ctrl_cmd_group, LostSectorSignal
    )
    kyber_ctrl_cmd_group.child(ls_autoposts_kyber_ctrl_cmd)
