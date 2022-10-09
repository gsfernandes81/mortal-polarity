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

import lightbulb

from . import cfg
from .utils import _discord_alert
from .reset_signaller import (
    remote_daily_reset,
    remote_weekend_reset,
    remote_weekly_reset,
)


@lightbulb.command(
    name="trigger_daily_reset",
    description="Sends a daily reset signal",
    guilds=(cfg.test_env,),
    auto_defer=True,
)
@lightbulb.implements(lightbulb.SlashCommand)
async def daily_reset(ctx: lightbulb.Context) -> None:
    # Move from internal signalling to http signalling for these
    # commands, which makes them a more reliable test
    # ctx.bot.dispatch(autopost.DailyResetSignal(ctx.bot))
    await remote_daily_reset()
    await ctx.respond("Daily reset signal sent")


@lightbulb.command(
    name="trigger_weekly_reset",
    description="Sends a weekly reset signal",
    guilds=(cfg.test_env,),
)
@lightbulb.implements(lightbulb.SlashCommand)
async def weekly_reset(ctx: lightbulb.Context) -> None:
    # Move from internal signalling to http signalling for these
    # commands, which makes them a more reliable test
    # ctx.bot.dispatch(autopost.WeeklyResetSignal(ctx.bot))
    await remote_weekly_reset()
    await ctx.respond("Weekly reset signal sent")


@lightbulb.command(
    name="trigger_weekend_reset",
    description="Sends a weekend reset signal",
    guilds=(cfg.test_env,),
)
@lightbulb.implements(lightbulb.SlashCommand)
async def weekend_reset(ctx: lightbulb.Context) -> None:
    # Move from internal signalling to http signalling for these
    # commands, which makes them a more reliable test
    # ctx.bot.dispatch(autopost.WeekendResetSignal(ctx.bot))
    await remote_weekend_reset()
    await ctx.respond("Weekend reset signal sent")


@lightbulb.option(
    name="text",
    description="Text to alert with",
    type=str,
    default="Testing testing",
)
@lightbulb.command(
    name="test_alert",
    description="Sends a test alert",
    guilds=(cfg.test_env,),
)
@lightbulb.implements(lightbulb.SlashCommand)
async def test_alert(ctx: lightbulb.Context) -> None:
    await _discord_alert(
        ctx.options.text,
        bot=ctx.bot,
        channel=cfg.alerts_channel_id,
        mention_mods=True,
    )
    await ctx.respond("Done")


def register_all(bot: lightbulb.BotApp) -> None:
    for command in [
        daily_reset,
        weekly_reset,
        weekend_reset,
        test_alert,
    ]:
        bot.command(command)
