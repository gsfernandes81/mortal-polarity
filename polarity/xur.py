import datetime as dt
import typing as t

import aiohttp
import hikari as h
import lightbulb as lb
from hmessage import HMessage
from sector_accounting import xur as xur_support_data

from . import bungie_api as api
from . import cfg, schemas
from .embeds import substitute_user_side_emoji
from .ls import make_autopost_control_commands


def xur_departure_string(post_date_time: dt.datetime | None = None) -> str:
    # Find the closest Tuesday in the future and set the time
    # to 1700 UTC on that day
    if post_date_time is None:
        post_date_time = dt.datetime.now(tz=dt.timezone.utc)

    # Find the next Tuesday
    days_ahead = 1 - post_date_time.weekday()
    days = days_ahead % 7
    post_date_time = post_date_time + dt.timedelta(days=days)

    # Set the time to 1700 UTC
    post_date_time = post_date_time.replace(hour=17, minute=0, second=0, microsecond=0)

    # Convert to unix time
    xur_unix_departure_time = int(post_date_time.timestamp())

    return f":timek:  Xûr departs <t:{xur_unix_departure_time}:R>\n"


def xur_location_fragment(
    xur_location: str, xur_locations: xur_support_data.XurLocations
) -> str:
    xur_location = xur_locations[xur_location]
    return f"## **__Location__**\n:location: {str(xur_location)}\n"


def armor_stat_line_format(armor: api.DestinyArmor, simple_mode: bool = False) -> str:
    if simple_mode:
        return f"- Stat: {armor.stat_total}"
    stats = armor.stats
    stat_line = "- "
    for stat_name, stat_value in stats.items():
        stat_line += f":rotate: {stat_value} "

    stat_line += f"\n- Total: {armor.stat_total}"
    return stat_line


def exotic_armor_fragment(exotic_armor_pieces: t.List[api.DestinyArmor]) -> str:
    subfragments: t.List[str] = []
    for armor_piece in exotic_armor_pieces:
        subfragments.append(
            f":{armor_piece.class_.lower().capitalize()}:  [{armor_piece.name} "
            + f"({armor_piece.bucket})]({armor_piece.lightgg_url})\n"
            + armor_stat_line_format(armor_piece)
        )
    return "## **__Exotic Armor__**\n" + "\n".join(subfragments) + "\n"


def weapon_line_format(
    weapon: api.DestinyWeapon,
    include_weapon_type: bool,
    include_perks: t.List[int],
    include_lightgg_link: bool,
    include_emoji: bool = True,
) -> str:
    weapon_line = weapon.name

    if include_emoji:
        weapon_line = f":weapon: {weapon_line}"

    if include_weapon_type:
        weapon_line += f" ({weapon.item_type_friendly_name})"
    if include_perks:
        perks = []
        for perk_index in include_perks:
            if perk_index >= len(weapon.perks):
                continue

            perk_options = weapon.perks[perk_index]
            if isinstance(perk_options, tuple):
                perks.append(" / ".join(perk_options))
            else:
                perks.append(perk_options)

        perks = ": " + ", ".join(perks)
        weapon_line += perks

    if include_lightgg_link:
        weapon_line = f"[{weapon_line}]({weapon.lightgg_url})"

    return weapon_line


def exotic_weapons_fragment(exotic_weapons: t.List[api.DestinyWeapon]) -> str:
    exotic_weapons_fragment_ = "## **__Exotic Weapons__**\n\n"
    for exotic_weapon in exotic_weapons:
        exotic_weapons_fragment_ += (
            weapon_line_format(
                exotic_weapon,
                include_weapon_type=False if exotic_weapon.name == "Hawkmoon" else True,
                include_perks=[1] if exotic_weapon.name == "Hawkmoon" else [],
                include_lightgg_link=True,
            )
            + "\n"
        )
    return exotic_weapons_fragment_


def legendary_armor_fragement(
    legendary_armor_pieces: t.List[api.DestinyArmor],
    xur_armor_sets_data: xur_support_data.XurArmorSets,
) -> str:
    armor_sets = set()
    for armor_piece in legendary_armor_pieces:
        armor_set_name = armor_piece.armor_set_name
        if armor_set_name:
            armor_sets.add(armor_set_name)

    subfragments = []
    subfragments.append("## **__Legendary Armor__**")
    subfragments.append("")

    for armor_set_name in armor_sets:
        armor_set = xur_armor_sets_data[armor_set_name]
        subfragments.append(f":armor: {armor_set}")

    subfragments.append("")

    return "\n".join(subfragments)


def legendary_weapons_fragment(legendary_weapons: t.List[api.DestinyArmor]) -> str:
    subfragments = []
    subfragments.append("## **__Legendary Weapons__**")
    subfragments.append("")

    for weapon in legendary_weapons:
        subfragments.append(
            weapon_line_format(
                weapon,
                include_weapon_type=True,
                include_perks=[-4, -3],
                include_lightgg_link=True,
            )
        )

    return "\n".join(subfragments)


XUR_FOOTER = """\n\n[**View More**](https://kyber3000.com/D2-Xur) ↗ 

Have a great weekend! :gscheer:"""


async def format_xur_vendor(
    vendor: api.DestinyVendor,
    bot: lb.BotApp = {},
) -> HMessage:
    xur_locations = xur_support_data.XurLocations.from_gspread_url(
        cfg.sheets_ls_url, cfg.gsheets_credentials
    )
    xur_armor_sets = xur_support_data.XurArmorSets.from_gspread_url(
        cfg.sheets_ls_url, cfg.gsheets_credentials
    )

    description = "# [XÛR'S LOOT](https://kyber3000.com/D2-Xur)\n\n"
    description += xur_departure_string()
    description += xur_location_fragment(vendor.location, xur_locations)
    description += exotic_armor_fragment(
        [item for item in vendor.sale_items if item.is_exotic and item.is_armor]
    )
    description += exotic_weapons_fragment(
        [item for item in vendor.sale_items if item.is_exotic and item.is_weapon]
    )
    description += legendary_armor_fragement(
        [item for item in vendor.sale_items if item.is_armor and item.is_legendary],
        xur_armor_sets,
    )
    description += legendary_weapons_fragment(
        [item for item in vendor.sale_items if item.is_weapon and item.is_legendary]
    )

    description += XUR_FOOTER
    description = await substitute_user_side_emoji(bot, description)
    message = HMessage(
        embeds=[
            h.Embed(
                title="WEEK 20",
                description=description,
                color=h.Color(cfg.embed_default_color),
                url="https://kyberscorner.com",
            )
        ]
    )
    return message


async def xur_message_constructor(bot: lb.BotApp) -> HMessage:
    access_token = await api.refresh_api_tokens(bot.d.webserver_runner)

    async with aiohttp.ClientSession() as session:
        destiny_membership = await api.DestinyMembership.from_api(session, access_token)
        character_id = await destiny_membership.get_character_id(session, access_token)

    xur: api.DestinyVendor = await api.DestinyVendor.request_from_api(
        destiny_membership=destiny_membership,
        character_id=character_id,
        access_token=access_token,
        manifest_table=await api._build_manifest_dict(
            await api._get_latest_manifest(schemas.BungieCredentials.api_key)
        ),
        vendor_hash=api.XUR_VENDOR_HASH,
    )

    return await format_xur_vendor(xur, bot=bot)


def register(bot: lb.BotApp) -> None:
    bot.command(
        make_autopost_control_commands(
            autopost_name="xur",
            enabled_getter=schemas.AutoPostSettings.get_xur_enabled,
            enabled_setter=schemas.AutoPostSettings.set_xur,
            channel_id=cfg.followables["xur"],
            message_constructor_coro=xur_message_constructor,
        )
    )
