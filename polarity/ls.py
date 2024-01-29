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

import asyncio as aio
import datetime as dt
import logging
import typing as t

import aiocron
import dateparser
import hikari as h
import lightbulb as lb
import tweepy
from aiohttp import InvalidURL
from hmessage import HMessage
from pytz import utc
from sector_accounting.sector_accounting import (
    DifficultySpecificSectorData,
    Rotation,
    Sector,
)

from . import cfg, schemas, utils
from .embeds import construct_emoji_substituter, re_user_side_emoji

logger = logging.getLogger(__name__)


twitter_ls_post_string = utils.endl(
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


def _fmt_count(emoji: str, count: int, width: int) -> str:
    if count:
        return "{} x `{}`".format(
            emoji,
            str(count if count != -1 else "?").rjust(width, " "),
        )
    else:
        return ""


def format_counts(
    legend_data: DifficultySpecificSectorData,
    master_data: DifficultySpecificSectorData,
    emoji_dict: t.Dict[str, h.Emoji],
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
        champs_string = utils.space.figure.join(
            filter(
                None,
                [
                    _fmt_count(emoji_dict["barrier"], data.barrier_champions, len_bar),
                    _fmt_count(
                        emoji_dict["overload"], data.overload_champions, len_oload
                    ),
                    _fmt_count(
                        emoji_dict["unstoppable"],
                        data.unstoppable_champions,
                        len_unstop,
                    ),
                ],
            )
        )
        shields_string = utils.space.figure.join(
            filter(
                None,
                [
                    _fmt_count(emoji_dict["arc"], data.arc_shields, len_arc),
                    _fmt_count(emoji_dict["void"], data.void_shields, len_void),
                    _fmt_count(emoji_dict["solar"], data.solar_shields, len_solar),
                    _fmt_count(emoji_dict["stasis"], data.stasis_shields, len_stasis),
                    _fmt_count(emoji_dict["strand"], data.strand_shields, len_strand),
                ],
            )
        )
        data_string = f"{utils.space.figure}|{utils.space.figure}".join(
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
        f"Legend:{utils.space.figure}"
        + data_strings[0]
        + f"\nMaster:{utils.space.hair}{utils.space.figure}"
        + data_strings[1]
    )


async def format_sector(
    emoji_dict: t.Dict[str, h.Emoji],
    date: dt.date = None,
    thumbnail: h.Attachment = None,
    secondary_image: h.Attachment = None,
    secondary_embed_title: str = "",
    secondary_embed_description: str = "",
) -> HMessage:
    buffer = 1  # Minute
    if date is None:
        date = dt.datetime.now(tz=utc) - dt.timedelta(hours=16, minutes=60 - buffer)
    else:
        date = date + dt.timedelta(minutes=buffer)
    sector: Sector = Rotation.from_gspread_url(
        cfg.sheets_ls_url, cfg.gsheets_credentials, buffer=5
    )()

    # Follow the hyperlink to have the newest image embedded
    try:
        ls_gfx_url = await utils.follow_link_single_step(sector.shortlink_gfx)
    except InvalidURL:
        ls_gfx_url = None

    # Surges to emojis
    surges = []
    for surge in sector.surges:
        surges += [str(emoji_dict.get(surge) or emoji_dict.get(surge.lower()))]

    # Threat to emoji
    threat = emoji_dict.get(sector.threat) or emoji_dict.get(sector.threat.lower())

    overcharged_weapon_emoji = (
        "⚔️" if sector.overcharged_weapon.lower() in ["sword", "glaive"] else "🔫"
    )

    if "(" in sector.name or ")" in sector.name:
        sector_name = sector.name.split("(")[0].strip()
        sector_location = sector.name.split("(")[1].split(")")[0].strip()
    else:
        sector_name = sector.name
        sector_location = None

    # Legendary weapon rewards
    legendary_weapon_rewards = sector.legendary_rewards

    legendary_weapon_rewards = re_user_side_emoji.sub(
        construct_emoji_substituter(emoji_dict), legendary_weapon_rewards
    )

    embed = (
        h.Embed(
            title="**Lost Sector Today**",
            description=(
                f"{emoji_dict['LS']}{utils.space.three_per_em}{sector_name.strip()}\n"
                + (
                    f"{emoji_dict['location']}{utils.space.three_per_em}{sector_location.strip()}"
                    if sector_location
                    else ""
                )
            ),
            color=cfg.embed_default_color,
            url="https://lostsectortoday.com/",
        )
        .add_field(
            name="Reward",
            value=str(emoji_dict["exotic_engram"])
            + f"{utils.space.three_per_em}Exotic {sector.reward} (If-Solo)",
        )
        .add_field(
            name="Champs and Shields",
            value=format_counts(sector.legend_data, sector.master_data, emoji_dict),
        )
        .add_field(
            name="Elementals",
            value=f"Surge: {utils.space.punctuation}{utils.space.hair}{utils.space.hair}"
            + " ".join(surges)
            + f"\nThreat: {threat}",
        )
        .add_field(
            name="Modifiers",
            value=str(emoji_dict["swords"])
            + f"{utils.space.three_per_em}{sector.to_sector_v1().modifiers}"
            + f"\n{overcharged_weapon_emoji}{utils.space.three_per_em}Overcharged {sector.overcharged_weapon}",
        )
        .add_field(
            "Legendary Weapons (If-Solo)",
            legendary_weapon_rewards,
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
            color=cfg.embed_default_color,
        )
        embed2.set_image(secondary_image)
        embeds = [embed, embed2]
    else:
        embeds = [embed]

    return HMessage(embeds=embeds)


def format_twitter_post(sector: Sector):
    weapon_emoji = (
        "⚔️" if sector.overcharged_weapon.lower() in ["sword", "glaive"] else "🔫"
    )
    return twitter_ls_post_string.format(sector=sector, weapon_emoji=weapon_emoji)


async def get_twitter_data_tuple(date: dt.date = None) -> t.Tuple[str, str]:
    date = date or dt.datetime.now(tz=utc)
    rot = Rotation.from_gspread_url(
        cfg.sheets_ls_url,
        cfg.gsheets_credentials,
        buffer=1,  # minutes
    )(date).to_sector_v1()
    return (
        format_twitter_post(rot),
        await utils.download_linked_image(rot.shortlink_gfx),
    )


async def discord_announcer(bot: lb.BotApp, check_enabled: bool = False):
    while True:
        retries = 0
        try:
            if (
                check_enabled
                and not await schemas.LostSectorPostSettings.get_discord_enabled()
            ):
                return
            hmessage = await format_sector()
        except Exception as e:
            logger.exception(e)
            aio.sleep(2**retries)
        else:
            break

    logger.info("Announcing lost sector to discord")
    await utils.send_message(bot, hmessage, crosspost=True, deduplicate=True)
    logger.info("Announced lost sector to discord")


def sub_group(parent: lb.CommandLike, name: str, description: str):
    @lb.command(name, description)
    @lb.implements(lb.SlashSubGroup)
    def _():
        pass

    parent.child(_)

    return _


@lb.command(
    "ls" if not cfg.test_env else "dev_ls",
    "Commands for Kyber",
    guilds=[cfg.control_discord_server_id],
)
@lb.implements(lb.SlashCommandGroup)
def ls_group():
    pass


ls_discord_group = sub_group(
    ls_group, "discord", "Discord lost sector announcement management"
)

ls_twitter_group = sub_group(
    ls_group, "twitter", "Twitter lost sector announcement management"
)


@ls_discord_group.child
@lb.option(
    "option", "Enable or disable", str, choices=["Enable", "Disable"], required=True
)
@lb.command(
    "auto",
    "Enable or disable discord automatic lost sector announcements",
    auto_defer=True,
    pass_options=True,
)
@lb.implements(lb.SlashSubCommand)
@utils.check_admin
async def ls_discord_control(ctx: lb.Context, option: str):
    option = True if option.lower() == "enable" else False
    enabled = await schemas.LostSectorPostSettings.get_discord_enabled()
    if option == enabled:
        return await ctx.respond(
            "Lost sector announcements are already {}".format(
                "enabled" if option else "disabled"
            )
        )
    else:
        await schemas.LostSectorPostSettings.set_discord_enabled(option)
        await ctx.respond(
            "Lost sector announcements now {}".format(
                "Enabled" if option else "Disabled"
            )
        )


@ls_twitter_group.child
@lb.option(
    "option", "Enable or disable", str, choices=["Enable", "Disable"], required=True
)
@lb.command(
    "auto",
    "Enable or disable twitter automatic lost sector announcements",
    auto_defer=True,
    pass_options=True,
)
@lb.implements(lb.SlashSubCommand)
@utils.check_admin
async def ls_twitter_control(ctx: lb.Context, option: str):
    option = True if option.lower() == "enable" else False
    enabled = await schemas.LostSectorPostSettings.get_twitter_enabled()
    if option == enabled:
        return await ctx.respond(
            "Lost sector announcements are already {}".format(
                "enabled" if option else "disabled"
            )
        )
    else:
        await schemas.LostSectorPostSettings.set_twitter_enabled(option)
        await ctx.respond(
            "Lost sector announcements now {}".format(
                "Enabled" if option else "Disabled"
            )
        )


@ls_discord_group.child
@lb.command("send", "Trigger a discord announcement manually", auto_defer=True)
@lb.implements(lb.SlashSubCommand)
@utils.check_admin
async def ls_discord_announce(ctx: lb.Context):
    await ctx.respond("Announcing to discord...")
    await discord_announcer(ctx.bot)
    await ctx.edit_last_response("Announced to discord")


@ls_twitter_group.child
@lb.command("send", "Trigger a twitter announcement manually", auto_defer=True)
@lb.implements(lb.SlashSubCommand)
@utils.check_admin
async def ls_twitter_announce(ctx: lb.Context):
    await ctx.respond("Announcing to twitter...")
    await twitter_announcer(ctx.app)
    await ctx.edit_last_response("Announced to twitter")


@ls_twitter_group.child
@lb.option("date", "Date to check", default="")
@lb.command(
    "text",
    "Get twitter text (makes it easy to copy)",
    auto_defer=True,
    pass_options=True,
)
@lb.implements(lb.SlashSubCommand)
@utils.check_admin
async def ls_twitter_text(ctx: lb.Context, date: str = ""):
    if date:
        date = dateparser.parse(date).replace(tzinfo=utc)
    else:
        date = dt.datetime.now(tz=utc)
    await ctx.respond(content=f"```\n{(await get_twitter_data_tuple(date))[0]}\n```")


@ls_group.child
@lb.command("today", "Check the latest lost sector information", auto_defer=True)
@lb.implements(lb.SlashSubCommand)
@utils.check_admin
async def ls_today(ctx: lb.Context):
    await ctx.respond("Checking lost sector information...")
    guild = ctx.app.cache.get_guild(
        cfg.kyber_discord_server_id
    ) or await ctx.app.rest.fetch_guild(cfg.kyber_discord_server_id)
    emoji_dict = {emoji.name: emoji for emoji in await guild.fetch_emojis()}

    sector = await format_sector(emoji_dict=emoji_dict)

    await ctx.edit_last_response(**sector.to_message_kwargs())


@lb.command("ls_update", "Update a lost sector post", ephemeral=True, auto_defer=True)
@lb.implements(lb.MessageCommand)
async def ls_update(ctx: lb.MessageContext):
    """Correct a mistake in the lost sector announcement"""

    if ctx.author.id not in cfg.admins:
        await ctx.respond("Only admins can use this command")
        return

    msg_to_update: h.Message = ctx.options.target

    async with schemas.db_session() as session:
        settings: schemas.LostSectorPostSettings = await session.get(
            schemas.LostSectorPostSettings, 0
        )
        if settings is None:
            await ctx.respond("Please enable autoposts before using this cmd")

        logger.info("Correcting posts")

        await ctx.edit_last_response("Updating post now")
        message = await format_sector()
        await msg_to_update.edit(**message.to_message_kwargs())
        await ctx.edit_last_response("Post updated")


class TwitterHandler:
    def __init__(self, twitter_v1: tweepy.API, twitter_v2: tweepy.Client) -> None:
        self._twitter_v1 = twitter_v1
        self._twitter_v2 = twitter_v2

    @classmethod
    def sign_in(cls) -> "TwitterHandler":
        self = cls(
            tweepy.API(
                tweepy.OAuth1UserHandler(
                    cfg.tw_cons_key,
                    cfg.tw_cons_secret,
                    cfg.tw_access_tok,
                    cfg.tw_access_tok_secret,
                ),
                tweepy.Client(
                    cfg.tw_bearer_tok,
                    cfg.tw_cons_key,
                    cfg.tw_cons_secret,
                    cfg.tw_access_tok,
                    cfg.tw_access_tok_secret,
                ),
            )
        )
        return self

    async def announce_to_twitter(self, bot):
        """Announce the lost sector to twitter

        Bot must be passed so that errors are logged to discord"""
        try:
            tweet_string, file_name = await get_twitter_data_tuple()
            await utils.run_in_thread_pool(
                self._announce_to_twitter_sync,
                tweet_string,
                file_name,
            )
        except ValueError as err:
            await utils.alert_owner(
                err.args[0],
                channel=cfg.alerts_channel,
                bot=bot,
                mention_mods=True,
            )

    def _announce_to_twitter_sync(self, tweet_string, attachment_file_name=None):
        if len(tweet_string) > 280:
            raise ValueError(
                "Lost sector post Tweet length more than 280 characters, not posting"
            )
        # If we have a lost sector graphic, the file name will not be none
        # or we can upload this graphic to twitter or use it
        if attachment_file_name is not None:
            # Upload the lost sector image
            media_id = int(
                self._twitter_v1.media_upload(
                    filename=attachment_file_name,
                ).media_id
            )

            # Use the lost sector image in the tweet
            self._twitter_v2.create_tweet(text=tweet_string, media_ids=[media_id])
        # If we don't have a lost sector graphic, we can't use it of course
        # so we proceed with a text only tweet
        else:
            self._twitter_v1.update_status(
                tweet_string,
            )


async def twitter_announcer(discord_bot: lb.BotApp, check_enabled=False):
    backoff_timer = 60
    while True:
        try:
            if (
                check_enabled
                and not await schemas.LostSectorPostSettings.get_twitter_enabled()
            ):
                return
            logger.info("Announcing lost sector to discord")
            await TwitterHandler().sign_in().announce_to_twitter(discord_bot)
        except Exception as e:
            e.add_note(
                f"Failed to post to twitter, retrying in {backoff_timer/60} minutes"
            )
            logger.exception(e)
            await aio.sleep(backoff_timer)
            backoff_timer *= 2
        else:
            logger.info("Announced lost sector to twitter")
            break


async def on_start_schedule_autoposts(event: lb.LightbulbStartedEvent):
    # Run every day at 17:00 UTC
    @aiocron.crontab("0 17 * * *", start=True)
    # Use below crontab for testing to post every minute
    # @aiocron.crontab("* * * * *", start=True)
    async def autopost_ls():
        await discord_announcer(event.app, check_enabled=True)

    # Run every day at 17:00 UTC
    @aiocron.crontab("0 17 * * *", start=True)
    # Use below crontab for testing to post every minute
    # @aiocron.crontab("* * * * *", start=True)
    async def autopost_ls_twitter():
        await twitter_announcer(event.app, check_enabled=True)


def register(bot: lb.BotApp) -> None:
    bot.command(ls_group)
    bot.command(ls_update)
    bot.listen(lb.LightbulbStartedEvent)(on_start_schedule_autoposts)
