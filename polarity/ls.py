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
import logging
import typing as t

import aiocron
import hikari as h
import lightbulb as lb
from aiohttp import InvalidURL
from hmessage import HMessage
from sector_accounting.sector_accounting import (
    DifficultySpecificSectorData,
    Rotation,
    Sector,
)

from . import cfg, schemas, utils
from .autopost import make_autopost_control_commands
from .embeds import construct_emoji_substituter, re_user_side_emoji

logger = logging.getLogger(__name__)


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
        f"Expert:{utils.space.figure}"
        + data_strings[0]
        + f"\nMaster:{utils.space.hair}{utils.space.figure}"
        + data_strings[1]
    )


async def get_emoji_dict(bot: lb.BotApp):
    guild = bot.cache.get_guild(
        cfg.kyber_discord_server_id
    ) or await bot.rest.fetch_guild(cfg.kyber_discord_server_id)
    return {emoji.name: emoji for emoji in await guild.fetch_emojis()}


async def format_sector(
    bot: lb.BotApp,
) -> HMessage:
    emoji_dict = await get_emoji_dict(bot)
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

    embed = h.Embed(
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

    embed.add_field(
        name="Rewards (If-Solo)",
        value=str(emoji_dict["exotic_engram"])
        + f"{utils.space.three_per_em}Exotic {sector.reward}",
    )

    if await schemas.AutoPostSettings.get_lost_sector_legendary_weapons_enabled():
        embed.add_field(
            "Legendary Weapons (If-Solo)",
            legendary_weapon_rewards,
        )

        embed.add_field(
            "Drop Rate (with no champions left)",
            "Expert: 70%\n" "Master: 100% + double perks on weapons",
        )

    embed.add_field(
        name="Champs and Shields",
        value=format_counts(sector.legend_data, sector.master_data, emoji_dict),
    )
    embed.add_field(
        name="Elementals",
        value=f"Surge: {utils.space.punctuation}{utils.space.hair}{utils.space.hair}"
        + " ".join(surges)
        + f"\nThreat: {threat}",
    )
    embed.add_field(
        name="Modifiers",
        value=str(emoji_dict["swords"])
        + f"{utils.space.three_per_em}{sector.to_sector_v1().modifiers}"
        + f"\n{overcharged_weapon_emoji}{utils.space.three_per_em}Overcharged {sector.overcharged_weapon}",
    )

    if ls_gfx_url:
        embed.set_image(ls_gfx_url)

    return HMessage(embeds=[embed])


async def discord_announcer(
    bot: lb.BotApp,
    channel_id: int,
    construct_message_coro: t.Coroutine[t.Any, t.Any, HMessage] = None,
    check_enabled: bool = False,
    enabled_check_coro: t.Coroutine[t.Any, t.Any, bool] = None,
    publish_message: bool = True,
):
    while True:
        retries = 0
        try:
            if check_enabled and not await enabled_check_coro():
                return
            hmessage = await construct_message_coro(bot)
        except Exception as e:
            logger.exception(e)
            retries += 1
            await aio.sleep(min(2**retries, 300))
        else:
            break

    logger.info("Announcing lost sector to discord")
    await utils.send_message(
        bot,
        hmessage,
        channel_id=channel_id,
        crosspost=publish_message,
        deduplicate=True,
    )
    logger.info("Announced lost sector to discord")


@lb.option(
    "option", "Enable or disable", str, choices=["Enable", "Disable"], required=True
)
@lb.command(
    "legendary_weapons",
    "Control lost sector legendary weapon announcements",
    auto_defer=True,
    pass_options=True,
)
@lb.implements(lb.SlashSubCommand)
async def control_legendary_weapons(ctx: lb.Context, option: str):
    """Enable or disable lost sector legendary weapon announcements"""

    desired_setting: bool = True if option.lower() == "enable" else False
    current_setting = (
        await schemas.AutoPostSettings.get_lost_sector_legendary_weapons_enabled()
    )

    if desired_setting == current_setting:
        return await ctx.respond(
            f"Lost sector legendary weapon announcements are already {'enabled' if desired_setting else 'disabled'}"
        )

    await schemas.AutoPostSettings.set_lost_sector_legendary_weapons(
        enabled=desired_setting
    )
    await ctx.respond(
        f"Lost sector legendary weapon announcements now {'enabled' if desired_setting else 'disabled'}"
    )


def sub_group(parent: lb.CommandLike, name: str, description: str):
    @lb.command(name, description)
    @lb.implements(lb.SlashSubGroup)
    def _():
        pass

    parent.child(_)

    return _


@lb.command("ls_update", "Update a lost sector post", ephemeral=True, auto_defer=True)
@lb.implements(lb.MessageCommand)
async def ls_update(ctx: lb.MessageContext):
    """Correct a mistake in the lost sector announcement"""

    if ctx.author.id not in cfg.admins:
        await ctx.respond("Only admins can use this command")
        return

    msg_to_update: h.Message = ctx.options.target

    async with schemas.db_session() as session:
        settings: schemas.AutoPostSettings = await session.get(
            schemas.AutoPostSettings, 0
        )
        if settings is None:
            await ctx.respond("Please enable autoposts before using this cmd")

        logger.info("Correcting posts")

        await ctx.edit_last_response("Updating post now")

        message = await format_sector(ctx.app)
        await msg_to_update.edit(**message.to_message_kwargs())
        await ctx.edit_last_response("Post updated")


async def on_start_schedule_autoposts(event: lb.LightbulbStartedEvent):
    # Run every day at 17:00 UTC
    @aiocron.crontab("0 17 * * *", start=True)
    # Use below crontab for testing to post every minute
    # @aiocron.crontab("* * * * *", start=True)
    async def autopost_ls():
        await discord_announcer(
            event.app,
            channel_id=cfg.followables["lost_sector"],
            check_enabled=True,
            enabled_check_coro=schemas.AutoPostSettings.get_lost_sector_enabled,
            construct_message_coro=format_sector,
        )


def register(bot: lb.BotApp) -> None:
    autopost_control_parent_group = make_autopost_control_commands(
        "ls",
        schemas.AutoPostSettings.get_lost_sector_enabled,
        schemas.AutoPostSettings.set_lost_sector,
        cfg.followables["lost_sector"],
        format_sector,
        message_announcer_coro=discord_announcer,
    )

    autopost_control_parent_group.child(control_legendary_weapons)

    bot.command(autopost_control_parent_group)

    bot.command(ls_update)
    bot.listen(lb.LightbulbStartedEvent)(on_start_schedule_autoposts)
