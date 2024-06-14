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
import typing as t

import lightbulb as lb
from hmessage import HMessage

from . import cfg, utils

logger = logging.getLogger(__name__)


def make_autopost_control_commands(
    autopost_name: str,
    enabled_getter: t.Coroutine[t.Any, t.Any, bool],
    enabled_setter: t.Coroutine[t.Any, t.Any, None],
    channel_id: int,
    message_constructor_coro: t.Coroutine[t.Any, t.Any, HMessage],
    message_announcer_coro: t.Coroutine[t.Any, t.Any, None] = None,
) -> t.Callable:
    @lb.command(
        autopost_name if not cfg.test_env else "dev_" + autopost_name,
        "Commands for Kyber",
        guilds=[cfg.control_discord_server_id],
    )
    @lb.implements(lb.SlashCommandGroup)
    def parent_group():
        pass

    @parent_group.child
    @lb.option(
        "option", "Enable or disable", str, choices=["Enable", "Disable"], required=True
    )
    @lb.command(
        "auto",
        "Enable or disable automated announcements",
        auto_defer=True,
        pass_options=True,
    )
    @lb.implements(lb.SlashSubCommand)
    @utils.check_admin
    async def autopost_control(ctx: lb.Context, option: str):
        option = True if option.lower() == "enable" else False
        enabled = await enabled_getter()
        if option == enabled:
            return await ctx.respond(
                "{} announcements are already {}".format(
                    autopost_name.capitalize(),
                    "enabled" if option else "disabled",
                )
            )
        else:
            await enabled_setter(enabled=option)
            await ctx.respond(
                "{} announcements now {}".format(
                    autopost_name.capitalize(),
                    "Enabled" if option else "Disabled",
                )
            )

    @parent_group.child
    @lb.option("publish", "Publish the announcement", bool, default=True)
    @lb.command(
        "send",
        "Trigger a discord announcement manually",
        auto_defer=True,
        pass_options=True,
    )
    @lb.implements(lb.SlashSubCommand)
    @utils.check_admin
    async def manual_announce(ctx: lb.Context, publish: bool):
        await ctx.respond("Announcing...")
        try:
            await message_announcer_coro(
                bot=ctx.bot,
                channel_id=channel_id,
                check_enabled=False,
                construct_message_coro=message_constructor_coro,
                publish_message=publish,
            )
        except Exception as e:
            logger.exception(e)
            await ctx.edit_last_response("An error occurred!\n" + str(e))
        else:
            await ctx.edit_last_response("Announced")

    @parent_group.child
    @lb.command("show", "Check what the post will look like", auto_defer=True)
    @lb.implements(lb.SlashSubCommand)
    @utils.check_admin
    async def show(ctx: lb.Context):
        await ctx.respond("Gathering data...")
        try:
            message: HMessage = await message_constructor_coro(ctx.app)
        except Exception as e:
            logger.exception(e)
            await ctx.edit_last_response("An error occurred!\n" + str(e))
        else:
            await ctx.edit_last_response(**message.to_message_kwargs())

    return parent_group
