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
import functools
import logging
from asyncio import sleep
from calendar import month_name as month
from typing import List, Tuple, Type
from random import randint

import aiohttp
import hikari as h
import lightbulb as lb
import tweepy
from lightbulb.ext import tasks, wtf
from pytz import utc
from sector_accounting import Rotation, Sector
from sector_accounting.sector_accounting import DifficultySpecificSectorData
from sqlalchemy import select
from hmessage import HMessage

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
    _download_linked_image,
    _edit_message,
    _run_in_thread_pool,
    alert_owner,
    db_session,
    endl,
    follow_link_single_step,
    operation_timer,
    space,
)

logger = logging.getLogger(__name__)

LS_EMOJI = "<:LS:849727805994565662>"
SOLAR_EMOJI = "<:solar:849726154540974183>"
ARC_EMOJI = "<:arc:849725765063016508>"
VOID_EMOJI = "<:void:849726137181405204>"
STASIS_EMOJI = "<:stasis:1092891643490873384>"
STRAND_EMOJI = "<:strand:1096267542890287126> "
BARRIER_EMOJI = "<:barrier:1098297383974088876>"
OVERLOAD_EMOJI = "<:overload:1098296903290069123>"
UNSTOPPABLE_EMOJI = "<:unstoppable:1098296844955693056>"
SWORDS_EMOJI = "<:swords:849729529076514866>"
LOCATION_EMOJI = "<:location:1086525796031676556>"
EXOTIC_ENGRAM_EMOJI = "<:exotic_engram:849898122083434506>"


ROTATION_UPDATE_INTERVAL = 60

rotation_global = None


@tasks.task(
    s=ROTATION_UPDATE_INTERVAL,
    auto_start=True,
    wait_before_execution=False,
)
async def rotation_update_task():
    global rotation_global
    try:
        # Introduce a 5% jitter to the update interval
        # to avoid potential ratelimit issues
        await sleep(randint(0, int(ROTATION_UPDATE_INTERVAL / 20)))
        rotation_global = Rotation.from_gspread_url(
            cfg.sheets_ls_url, cfg.gsheets_credentials, buffer=5
        )
    except Exception as e:
        logging.error(e)


def _fmt_count(emoji: str, count: int, width: int) -> str:
    if count:
        return "{} x `{}`".format(
            emoji,
            str(count if count != -1 else "?").rjust(width, " "),
        )
    else:
        return ""


def format_sector_data_for_discord(
    legend_data: DifficultySpecificSectorData, master_data: DifficultySpecificSectorData
) -> str:
    len_bar = len(
        str(max(legend_data.barrier_champions, master_data.barrier_champions, key=abs))
    )
    len_oload = len(
        str(
            max(legend_data.overload_champions, master_data.overload_champions, key=abs)
        )
    )
    len_unstop = len(
        str(
            max(
                legend_data.unstoppable_champions,
                master_data.unstoppable_champions,
                key=abs,
            )
        )
    )
    len_arc = len(str(max(legend_data.arc_shields, master_data.arc_shields, key=abs)))
    len_void = len(
        str(max(legend_data.void_shields, master_data.void_shields, key=abs))
    )
    len_solar = len(
        str(max(legend_data.solar_shields, master_data.solar_shields, key=abs))
    )
    len_stasis = len(
        str(max(legend_data.stasis_shields, master_data.stasis_shields, key=abs))
    )
    len_strand = len(
        str(max(legend_data.strand_shields, master_data.strand_shields, key=abs))
    )

    data_strings = []

    for data in [legend_data, master_data]:
        champs_string = space.figure.join(
            filter(
                None,
                [
                    _fmt_count(BARRIER_EMOJI, data.barrier_champions, len_bar),
                    _fmt_count(OVERLOAD_EMOJI, data.overload_champions, len_oload),
                    _fmt_count(
                        UNSTOPPABLE_EMOJI, data.unstoppable_champions, len_unstop
                    ),
                ],
            )
        )
        shields_string = space.figure.join(
            filter(
                None,
                [
                    _fmt_count(ARC_EMOJI, data.arc_shields, len_arc),
                    _fmt_count(VOID_EMOJI, data.void_shields, len_void),
                    _fmt_count(SOLAR_EMOJI, data.solar_shields, len_solar),
                    _fmt_count(STASIS_EMOJI, data.stasis_shields, len_stasis),
                    _fmt_count(STRAND_EMOJI, data.strand_shields, len_strand),
                ],
            )
        )
        data_string = f"{space.figure}|{space.figure}".join(
            filter(
                None,
                [
                    champs_string,
                    shields_string,
                ],
            )
        )
        data_strings.append(data_string)

    return (
        f"Legend:{space.figure}"
        + data_strings[0]
        + f"\nMaster:{space.hair}{space.figure}"
        + data_strings[1]
    )


class LostSectorPostSettings(BasePostSettings, Base):
    twitter_ls_post_string = endl(
        "Lost Sector Today",
        "",
        "🗺️ {sector.name}",
        "🏆 Exotic {sector.reward}",
        "",
        "👹 {sector.champions}",
        "🛡️ {sector.shields}",
        "☢️ {sector.burn} Threat",
        "{weapon_emoji} {sector.overcharged_weapon} Overcharge",
        "💪 {sector.surge} Surge",
        "🛠️ {sector.modifiers}",
        "",
        "🔗 lostsectortoday.com",
    )

    @classmethod
    def format_twitter_post(cls, sector: Sector):
        weapon_emoji = (
            "⚔️" if sector.overcharged_weapon.lower() in ["sword", "glaive"] else "🔫"
        )
        return cls.twitter_ls_post_string.format(
            sector=sector, weapon_emoji=weapon_emoji
        )

    async def get_announce_message(
        self,
        date: dt.date = None,
        thumbnail: h.Attachment = None,
        secondary_image: h.Attachment = None,
        secondary_embed_title: str = "",
        secondary_embed_description: str = "",
    ) -> h.Embed:
        buffer = 1  # Minute
        if date is None:
            date = dt.datetime.now(tz=utc) - dt.timedelta(hours=16, minutes=60 - buffer)
        else:
            date = date + dt.timedelta(minutes=buffer)
        sector: Sector = rotation_global()

        # Follow the hyperlink to have the newest image embedded
        try:
            ls_gfx_url = await follow_link_single_step(sector.shortlink_gfx)
        except aiohttp.InvalidURL:
            ls_gfx_url = None

        # Surges to emojis
        _surges = [surge.lower() for surge in sector.surges]
        surges = []
        if "solar" in _surges:
            surges += [SOLAR_EMOJI]
        if "arc" in _surges:
            surges += [ARC_EMOJI]
        if "void" in _surges:
            surges += [VOID_EMOJI]
        if "stasis" in _surges:
            surges += [STASIS_EMOJI]
        if "strand" in _surges:
            surges += [STRAND_EMOJI]

        # Threat to emoji
        threat = sector.threat.lower()
        if threat == "solar":
            threat = SOLAR_EMOJI
        elif threat == "arc":
            threat = ARC_EMOJI
        elif threat == "void":
            threat = VOID_EMOJI
        elif threat == "stasis":
            threat = STASIS_EMOJI
        elif threat == "strand":
            threat = STRAND_EMOJI

        overcharged_weapon_emoji = (
            "⚔️" if sector.overcharged_weapon.lower() in ["sword", "glaive"] else "🔫"
        )

        if "(" in sector.name or ")" in sector.name:
            sector_name = sector.name.split("(")[0].strip()
            sector_location = sector.name.split("(")[1].split(")")[0].strip()
        else:
            sector_name = sector.name
            sector_location = None

        embed = (
            h.Embed(
                title="**Lost Sector Today**",
                description=(
                    f"{LS_EMOJI}{space.three_per_em}{sector_name}\n"
                    + (
                        f"{LOCATION_EMOJI}{space.three_per_em}{sector_location}\n"
                        if sector_location
                        else ""
                    )
                    + f"\n"
                ),
                color=cfg.kyber_pink,
                url="https://lostsectortoday.com/",
            )
            .add_field(
                name=f"Reward",
                value=f"{EXOTIC_ENGRAM_EMOJI}{space.three_per_em}Exotic {sector.reward} (If-Solo)",
            )
            .add_field(
                name=f"Champs and Shields",
                value=format_sector_data_for_discord(
                    sector.legend_data, sector.master_data
                ),
            )
            .add_field(
                name=f"Elementals",
                value=f"Surge: {space.punctuation}{space.hair}{space.hair}"
                + " ".join(surges)
                + f"\nThreat: {threat}",
            )
            .add_field(
                name=f"Modifiers",
                value=f"{SWORDS_EMOJI}{space.three_per_em}{sector.to_sector_v1().modifiers}"
                + f"\n{overcharged_weapon_emoji}{space.three_per_em}Overcharged {sector.overcharged_weapon}",
            )
        )

        if ls_gfx_url:
            embed.set_image(ls_gfx_url)

        if thumbnail:
            embed.set_thumbnail(thumbnail)

        if secondary_image:
            embed2 = h.Embed(
                title=secondary_embed_title,
                description=secondary_embed_description,
                color=cfg.kyber_pink,
            )
            embed2.set_image(secondary_image)
            embeds = [embed, embed2]
        else:
            embeds = [embed]

        return HMessage(embeds=embeds)

    async def get_twitter_data_tuple(self, date: dt.date = None) -> Tuple[str, str]:
        date = date or dt.datetime.now(tz=utc)
        rot = Rotation.from_gspread_url(
            cfg.sheets_ls_url, cfg.gsheets_credentials, buffer=1  # minutes
        )().to_sector_v1()
        return (
            self.format_twitter_post(rot),
            await _download_linked_image(rot.shortlink_gfx),
        )


class LostSectorAutopostChannel(BaseChannelRecord, Base):
    settings_records: Type[BasePostSettings] = LostSectorPostSettings
    follow_channel = cfg.followables["lost_sector"]
    autopost_friendly_name = "Lost sector autoposts"

    @classmethod
    def register(
        cls,
        bot: lb.BotApp,
        cmd_group: lb.SlashCommandGroup,
        announce_event: Type[h.Event],
    ):
        cls.control_command_name = "lost sector"

        @cmd_group.child
        @lb.app_command_permissions(dm_enabled=False)
        @lb.command("lost", "Lost sector autoposts", inherit_checks=True)
        @lb.implements(lb.SlashSubGroup)
        async def lost(ctx: lb.Context) -> None:
            pass

        lost.child(
            lb.app_command_permissions(dm_enabled=False)(
                lb.option(
                    "option",
                    "Enabled or disabled",
                    type=str,
                    choices=["Enable", "Disable"],
                    required=True,
                )(
                    lb.command(
                        "sector",
                        "{} auto posts".format(cls.control_command_name.capitalize()),
                        auto_defer=True,
                        guilds=cfg.control_discord_server_id,
                        inherit_checks=True,
                    )(
                        lb.implements(lb.SlashSubCommand)(
                            functools.partial(cls.autopost_ctrl_usr_cmd, cls)
                        )
                    )
                )
            )
        )

        bot.listen(announce_event)(cls.announcer)


class LostSectorSignal(BaseCustomEvent):
    # Whether bot listen has been called on conditional_reset_repeater
    _signal_linked: bool = False

    @classmethod
    async def conditional_daily_reset_repeater(cls, event: DailyResetSignal) -> None:
        """Dispatched self if autoannounces are enabled in the settings object"""
        if await cls.is_autoannounce_enabled():
            cls.dispatch_with(bot=event.app)

    @classmethod
    async def is_autoannounce_enabled(cls):
        """Checks if autoannounces are enabled in the settings object"""
        settings = await _create_or_get(
            LostSectorPostSettings, 0, autoannounce_enabled=True
        )
        return settings.autoannounce_enabled

    @classmethod
    def register(cls, bot) -> None:
        self = super().register(bot)
        if not cls._signal_linked:
            bot.listen()(cls.conditional_daily_reset_repeater)
            cls._signal_linked = True
        return self


class LostSectorTwitterSignal(BaseCustomEvent):
    "Signal to trigger a twitter specific lost sector post"
    pass


class LostSectorDiscordSignal(BaseCustomEvent):
    "Signal to trigger a discord specific lost sector post"
    pass


async def ls_control(ctx: lb.Context):
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


async def ls_announce(ctx: lb.Context):
    await ctx.respond("Announcing now")
    LostSectorSignal.dispatch_with(bot=ctx.bot)


async def ls_twitter_announce(ctx: lb.Context):
    await ctx.respond("Announcing to twitter now")
    LostSectorTwitterSignal.dispatch_with(bot=ctx.bot)


async def ls_discord_announce(ctx: lb.Context):
    await ctx.respond("Announcing to discord now")
    LostSectorDiscordSignal.dispatch_with(bot=ctx.bot)


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
        self._twitter_v2 = tweepy.Client(
            cfg.tw_bearer_tok,
            cfg.tw_cons_key,
            cfg.tw_cons_secret,
            cfg.tw_access_tok,
            cfg.tw_access_tok_secret,
        )

    def register(self, bot: lb.BotApp) -> None:
        LostSectorSignal.register(bot)
        LostSectorAutopostChannel.register(
            bot, self.autopost_cmd_group, LostSectorSignal
        )
        self.control_cmd_group.child(self.commands())
        # Temporarily disable twitter announcements
        # bot.listen(LostSectorSignal)(self.announce_to_twitter)
        # bot.listen(LostSectorTwitterSignal)(self.announce_to_twitter)
        bot.listen(LostSectorDiscordSignal)(LostSectorAutopostChannel.announcer)

    def commands(self):
        return wtf.Command[
            wtf.Implements[lb.SlashSubGroup],
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
                    wtf.Implements[lb.SlashSubCommand],
                    wtf.Executes[ls_control],
                ],
                wtf.Command[
                    wtf.Name["update"],
                    wtf.Description[
                        "Update a lost sector post, optionally with text saying what has changed"
                    ],
                    wtf.Executes[self.update],
                    wtf.InheritChecks[True],
                    wtf.Implements[lb.SlashSubCommand],
                ],
                wtf.Command[
                    wtf.Name["announce"],
                    wtf.Description["Trigger an announcement manually"],
                    wtf.AutoDefer[True],
                    wtf.InheritChecks[True],
                    wtf.Implements[lb.SlashSubCommand],
                    wtf.Executes[ls_announce],
                ],
                wtf.Command[
                    wtf.Name["announce_twitter"],
                    wtf.Description["Trigger a twitter announcement manually"],
                    wtf.AutoDefer[True],
                    wtf.InheritChecks[True],
                    wtf.Implements[lb.SlashSubCommand],
                    wtf.Executes[ls_twitter_announce],
                ],
                wtf.Command[
                    wtf.Name["announce_discord"],
                    wtf.Description["Trigger a discord-only announcement manually"],
                    wtf.AutoDefer[True],
                    wtf.InheritChecks[True],
                    wtf.Implements[lb.SlashSubCommand],
                    wtf.Executes[ls_discord_announce],
                ],
            ],
        ]

    async def update(self, ctx: lb.Context):
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
            logger.info("Correcting posts")
            with operation_timer("Announce correction", logger):
                await ctx.respond("Correcting posts now")
                message = await settings.get_announce_message()
                no_of_channels = len(channel_record_list)
                percentage_progress = 0
                none_counter = 0

                for idx, channel_record in enumerate(channel_record_list):
                    if channel_record.last_msg_id is None:
                        none_counter += 1
                        continue

                    await _edit_message(
                        channel_record.last_msg_id,
                        channel_record.id,
                        ctx.bot,
                        message.to_message_kwargs(),
                        logger=logger,
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
            await alert_owner(
                err.args[0],
                channel=cfg.alerts_channel_id,
                bot=event.bot,
                mention_mods=True,
            )

    def _announce_to_twitter_sync(self, tweet_string, attachment_file_name=None):
        if len(tweet_string) > 280:
            raise ValueError(
                "Lost sector post Tweet length more than 280 characters, not posting"
            )
        # If we have a lost sector graphic, the file name will not be none
        # or we can upload this graphic to twitter or use it
        if attachment_file_name != None:
            # Upload the lost sector image
            media_id = int(
                self._twitter.media_upload(
                    filename=attachment_file_name,
                ).media_id
            )

            # Use the lost sector image in the tweet
            self._twitter_v2.create_tweet(text=tweet_string, media_ids=[media_id])
        # If we don't have a lost sector graphic, we can't use it of course
        # so we proceed with a text only tweet
        else:
            self._twitter.update_status(
                tweet_string,
            )


lost_sectors = LostSectors()
