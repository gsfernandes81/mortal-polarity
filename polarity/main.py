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

import hikari
import lightbulb
import uvloop
from lightbulb.ext import tasks

from . import (
    autopost,
    cfg,
    controller,
    debug_commands,
    ls,
    user_commands,
    xur,
    weekly_reset,
)

# Note: Alembic's env.py is set up to import Base from polarity.main
from .utils import Base

uvloop.install()
bot: lightbulb.BotApp = lightbulb.BotApp(**cfg.lightbulb_params)


# Switch to running this task once per bot run
# This is to work around an undiagnosed bug where the number of cumulative
# users seems to go down the longer the bot is running
@tasks.task(m=30, auto_start=True, wait_before_execution=False, max_executions=1)
async def autoupdate_status():
    if not bot.d.has_lightbulb_started:
        await bot.wait_for(lightbulb.events.LightbulbStartedEvent, timeout=None)
        bot.d.has_lightbulb_started = True

    total_users_approx = 0
    for guild in bot.cache.get_guilds_view():
        if isinstance(guild, hikari.Snowflake):
            guild = await bot.rest.fetch_guild(guild)
        total_users_approx += guild.approximate_active_member_count or 0
    await bot.update_presence(
        activity=hikari.Activity(
            name="{} users : )".format(total_users_approx),
            type=hikari.ActivityType.LISTENING,
        )
    )


if __name__ == "__main__":
    user_commands.register_all(bot)
    controller.register_all(bot)
    xur.XurControlCommands().register(
        bot, autopost.autopost_cmd_group, controller.kyber
    )
    weekly_reset.WeeklyResetPostControlCommands().register(
        bot, autopost.autopost_cmd_group, controller.kyber
    )
    ls.register(bot, autopost.autopost_cmd_group, controller.kyber)
    autopost.register(bot)
    tasks.load(bot)
    if cfg.test_env:
        debug_commands.register_all(bot)
    bot.run()
