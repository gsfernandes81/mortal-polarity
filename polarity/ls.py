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
from typing import List, Tuple, Type

import hikari
import lightbulb
import tweepy
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
    _discord_alert,
    _download_linked_image,
    _edit_embedded_message,
    _run_in_thread_pool,
    db_session,
    follow_link_single_step,
    operation_timer,
)


class LostSectorPostSettings(BasePostSettings, Base):
    twitter_ls_post_string = (
        "Lost Sector Today\n\n"
        + "💠 {sector.name}\n\n"
        + "• Reward (If-Solo): {sector.reward}\n"
        + "• Champs: {sector.champions}\n"
        + "• Shields: {sector.shields}\n"
        + "• Burn: {sector.burn}\n"
        + "• Modifiers: {sector.modifiers}\n\n"
        + "ℹ️ : https://lostsectortoday.com/"
    )

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
            title="**Lost Sector Today**".format(**format_dict),
            description=(
                "⠀\n<:LS:849727805994565662> **{sector.name}\n\n".format(
                    **format_dict
                ).replace(" (", "** (", 1)
                + "• **Reward (If-Solo)**: {sector.reward}\n"
                + "• **Champs**: {sector.champions}\n"
                + "• **Shields**: {sector.shields}\n"
                + "• **Burn**: {sector.burn}\n"
                + "• **Modifiers**: {sector.modifiers}\n"
                + "\n"
                + "ℹ️ : <https://lostsectortoday.com/>"
            ).format(**format_dict),
            color=cfg.kyber_pink,
        ).set_image(ls_gfx_url)

    async def get_twitter_data_tuple(self, date: dt.date = None) -> Tuple[str, str]:
        date = date or dt.datetime.now(tz=utc)
        rot = Rotation.from_gspread_url(
            cfg.sheets_ls_url, cfg.gsheets_credentials, buffer=1  # minutes
        )()
        return (
            self.twitter_ls_post_string.format(
                sector=rot,
                month=month[date.month],
                day=date.day,
            ),
            await _download_linked_image(rot.shortlink_gfx),
        )


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
        # Create the twitter object:
        self._twitter = tweepy.API(
            tweepy.OAuth1UserHandler(
                cfg.tw_cons_key,
                cfg.tw_cons_secret,
                cfg.tw_access_tok,
                cfg.tw_access_tok_secret,
            )
        )

    def register(self, bot: lightbulb.BotApp) -> None:
        LostSectorSignal(bot).arm()
        LostSectorAutopostChannel.register(
            bot, self.autopost_cmd_group, LostSectorSignal
        )
        self.control_cmd_group.child(self.commands())
        bot.listen(LostSectorSignal)(self.announce_to_twitter)

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

                no_of_channels = len(channel_record_list)
                percentage_progress = 0
                none_counter = 0

                for idx, channel_record in enumerate(channel_record_list):

                    if channel_record.last_msg_id is None:
                        none_counter += 1
                        continue

                    await _edit_embedded_message(
                        channel_record.last_msg_id,
                        channel_record.id,
                        ctx.bot,
                        embed,
                        announce_if_guild=cfg.kyber_discord_server_id,
                    )

                    if percentage_progress < round(20 * (idx + 1) / no_of_channels) * 5:
                        percentage_progress = round(20 * (idx + 1) / no_of_channels) * 5
                        await ctx.edit_last_response(
                            "Updating posts: {}%\n".format(percentage_progress)
                        )
                await ctx.edit_last_response(
                    "{} posts corrected".format(no_of_channels - none_counter)
                )

    async def announce_to_twitter(self, event):
        try:
            async with db_session() as session:
                async with session.begin():
                    settings: LostSectorPostSettings = await session.get(
                        self.settings_table, 0
                    )
                    tweet_string, file_name = await settings.get_twitter_data_tuple()
            await _run_in_thread_pool(
                self._announce_to_twitter_sync,
                tweet_string,
                file_name,
            )
        except ValueError as err:
            _discord_alert(err.args[0], channel=cfg.alerts_channel_id, bot=event.bot)

    def _announce_to_twitter_sync(self, tweet_string, attachment_file_name=None):
        if len(tweet_string) > 280:
            raise ValueError(
                "Lost sector post Tweet length more than 280 characters, not posting"
            )
        # If we have a lost sector graphic, the file name will not be none
        # and we can upload this graphic to twitter and use it
        if attachment_file_name != None:
            # Upload the lost sector image
            media_id = int(
                self._twitter.media_upload(
                    filename=attachment_file_name,
                ).media_id
            )

            # Use the lost sector image in the tweet
            self._twitter.update_status(
                tweet_string,
                media_ids=[media_id],
            )
        # If we don't have a lost sector graphic, we can't use it of course
        # so we proceed with a text only tweet
        else:
            self._twitter.update_status(
                tweet_string,
            )


lost_sectors = LostSectors()
