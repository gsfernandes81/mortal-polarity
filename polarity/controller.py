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
import logging
from typing import List

import lightbulb
from sqlalchemy import select

from . import cfg, schemas
from .autoannounce import XurSignal
from .utils import _edit_embedded_message, db_session, operation_timer


@lightbulb.add_checks(lightbulb.checks.has_roles(cfg.admin_role))
@lightbulb.command(
    "kyber",
    "Commands for Kyber",
    guilds=[
        cfg.kyber_discord_server_id,
    ],
)
@lightbulb.implements(lightbulb.SlashCommandGroup)
async def kyber():
    # Enables or disables lost sector announcements globally
    pass


@kyber.child
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
async def ls_announcements(ctx: lightbulb.Context):
    option = True if ctx.options.option.lower() == "enable" else False
    async with db_session() as session:
        async with session.begin():
            settings = await session.get(schemas.LostSectorPostSettings, 0)
            if settings is None:
                settings = schemas.LostSectorPostSettings(0, option)
                session.add(settings)
            else:
                settings.autoannounce_enabled = option
    await ctx.respond(
        "Lost sector announcements {}".format("Enabled" if option else "Disabled")
    )


@kyber.child
@lightbulb.command(
    "xur_announcements",
    "Xur announcement management",
    guilds=[
        cfg.kyber_discord_server_id,
    ],
    inherit_checks=True,
)
@lightbulb.implements(lightbulb.SlashSubGroup)
async def xur_announcements():
    pass


@xur_announcements.child
@lightbulb.option(
    "option",
    "Enable or disable",
    type=str,
    choices=["Enable", "Disable"],
    required=True,
)
@lightbulb.command(
    "autoposts",
    "Enable or disable all automatic lost sector announcements",
    auto_defer=True,
    # The following NEEDS to be included in all privledged commands
    inherit_checks=True,
)
@lightbulb.implements(lightbulb.SlashSubCommand)
async def xur_autoposts(ctx: lightbulb.Context):
    option = True if ctx.options.option.lower() == "enable" else False
    async with db_session() as session:
        async with session.begin():
            settings = await session.get(schemas.XurPostSettings, 0)
            if settings is None:
                settings = schemas.XurPostSettings(0, autoannounce_enabled=option)
                session.add(settings)
            else:
                settings.autoannounce_enabled = option
    await ctx.respond(
        "Xur announcements {}".format("Enabled" if option else "Disabled")
    )


@xur_announcements.child
@lightbulb.option(
    "url",
    "The url to set",
    type=str,
    required=False,
)
@lightbulb.command(
    "infographic_url",
    "Set the Xur infographic url, to check and post",
    auto_defer=True,
    inherit_checks=True,
)
@lightbulb.implements(lightbulb.SlashSubCommand)
async def xur_gfx_url(ctx: lightbulb.Context):
    url = ctx.options.url.lower() if ctx.options.url is not None else None
    async with db_session() as session:
        async with session.begin():
            settings: schemas.XurPostSettings = await session.get(
                schemas.XurPostSettings, 0
            )
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
                settings = schemas.XurPostSettings(0)
                settings.url = url
                await settings.initialise_url_params()
                session.add(settings)
            else:
                settings.url = url
    await ctx.respond("Xur Infographic url updated to <{}>".format(url))


@xur_announcements.child
@lightbulb.option(
    "url",
    "The url to set",
    type=str,
    required=False,
)
@lightbulb.command(
    "post_url",
    "Set the Xur infographic url, to check and post",
    auto_defer=True,
    inherit_checks=True,
)
@lightbulb.implements(lightbulb.SlashSubCommand)
async def xur_post_url(ctx: lightbulb.Context):
    url = ctx.options.url.lower() if ctx.options.url is not None else None
    async with db_session() as session:
        async with session.begin():
            settings: schemas.XurPostSettings = await session.get(
                schemas.XurPostSettings, 0
            )
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
                settings = schemas.XurPostSettings(0)
                settings.post_url = url
                session.add(settings)
            else:
                settings.post_url = url
    await ctx.respond("Xur Post url updated to <{}>".format(url))


@xur_announcements.child
@lightbulb.option(
    "change",
    "What has changed",
    type=str,
    required=False,
)
@lightbulb.command(
    "make_correction",
    "Update a post, optionally with text saying what has changed",
    auto_defer=True,
    inherit_checks=True,
)
@lightbulb.implements(lightbulb.SlashSubCommand)
async def xur_rectify_announcement(ctx: lightbulb.Context):
    """Correct a mistake in the xur announcement
    pull from urls again and update existing posts"""
    change = ctx.options.change if ctx.options.change else ""
    async with db_session() as session:
        async with session.begin():
            settings: schemas.XurPostSettings = await session.get(
                schemas.XurPostSettings, 0
            )
            if settings is None:
                await ctx.respond("Please enable xur autoposts before using this cmd")
            channel_record_list = (
                await session.execute(
                    select(schemas.XurAutopostChannel).where(
                        schemas.XurAutopostChannel.enabled == True
                    )
                )
            ).fetchall()
            channel_record_list = (
                [] if channel_record_list is None else channel_record_list
            )
            channel_record_list: List[schemas.XurAutopostChannel] = [
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


@xur_announcements.child
@lightbulb.command(
    "manual_announce",
    "Trigger an announcement manually",
    auto_defer=True,
    inherit_checks=True,
)
@lightbulb.implements(lightbulb.SlashSubCommand)
async def manual_xur_announce(ctx: lightbulb.Context):
    ctx.bot.dispatch(XurSignal(ctx.bot))
    await ctx.respond("Xur announcements being sent out now")


def register_all(bot: lightbulb.BotApp) -> None:
    bot.command(kyber)
