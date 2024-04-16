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


import logging

import hikari as h
import lightbulb as lb
import miru as m
import uvloop
from lightbulb.ext import tasks

from . import bungie_api, cfg, controller, ls, posts, source, xur

uvloop.install()
bot: lb.BotApp = lb.BotApp(**cfg.lightbulb_params)

logger = logging.getLogger(__name__)


async def update_status(guild_count: int):
    await bot.update_presence(
        activity=h.Activity(
            name="{} servers : )".format(guild_count),
            type=h.ActivityType.LISTENING,
        )
    )


@bot.listen()
async def on_start_guild_count(event: lb.LightbulbStartedEvent):
    bot.d.guild_count = len(await bot.rest.fetch_my_guilds())
    await update_status(bot.d.guild_count)


@bot.listen()
async def on_guild_add(event: h.events.GuildJoinEvent):
    bot.d.guild_count += 1
    await update_status(bot.d.guild_count)


@bot.listen()
async def on_guild_rm(event: h.events.GuildLeaveEvent):
    bot.d.guild_count -= 1
    await update_status(bot.d.guild_count)


if __name__ == "__main__":
    m.install(bot)
    ls.register(bot)
    source.register(bot)
    controller.register(bot)
    posts.register(bot)
    bungie_api.register(bot)
    xur.register(bot)
    tasks.load(bot)
    bot.run()
