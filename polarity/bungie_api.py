import asyncio
import datetime as dt
import json
import os
import sys
import typing as t
import zipfile
from pathlib import Path
from pprint import pformat
from uuid import uuid4

import aiofiles
import aiohttp
import aiohttp.web
import aiosqlite
import lightbulb as lb
from yarl import URL

from . import cfg, schemas

BUNGIE_NET = "https://www.bungie.net"
API_ROOT = BUNGIE_NET + "/Platform"

API_GET_MEMBERSHIPS = API_ROOT + "/User/GetMembershipsForCurrentUser/"
API_MANIFEST = API_ROOT + "/Destiny2/Manifest/"
API_OAUTH = (
    BUNGIE_NET
    + "/en/OAuth/Authorize?client_id={client_id}&response_type=code&state={state}"
)
API_OAUTH_GET_TOKEN = API_ROOT + "/App/OAuth/token/"
API_PROFILE = (
    API_ROOT + "/Destiny2/{membership_type}/Profile/{membership_id}/?components=100"
)
API_VENDORS = API_ROOT + "/Destiny2/Vendors/"
API_VENDORS_AUTHENTICATED = (
    API_ROOT
    + "/Destiny2/{membershipType}"
    + "/Profile/{destinyMembershipId}"
    + "/Character/{characterId}"
    + "/Vendors/{vendorHash}"
    + "/?components={components}"
)
XUR_VENDOR_HASH = 2190858386
XUR_STRANGE_GEAR_VENDOR_HASH = 3751514131

ARMOR_TYPE_NAMES = (
    "Helmet",
    "Gauntlets",
    "Chest Armor",
    "Leg Armor",
    "Hunter Cloak",
    "Titan Mark",
    "Warlock Bond",
)

DESTINY_CLASSES_ENUM = ("Titan", "Hunter", "Warlock")

components = (
    # "300,"  # DestinyComponentType.ItemInstances
    "302,"  # DestinyComponentType.ItemPerks
    "304,"  # DestinyComponentType.ItemStats
    # "305,"  # DestinyComponentType.ItemSockets
    # "306,"  # DestinyComponentType.ItemTalentGrids
    # "307,"  # DestinyComponentType.ItemCommonData
    # "308,"  # DestinyComponentType.ItemPlugStates
    # "310,"  # DestinyComponentType.ItemReusablePlugs
    "400,"  # DestinyComponentType.Vendors
    "402"  # DestinyComponentType.VendorSales
)


manifest_table_names = [
    # "DestinyClassDefinition",
    # "DestinyPlaceDefinition",
    # "DestinyPlugSetDefinition",
    "DestinySandboxPerkDefinition",
    "DestinyStatDefinition",
    # "DestinyStatGroupDefinition",
    "DestinyEquipmentSlotDefinition",
    "DestinyCollectibleDefinition",
    "DestinyDestinationDefinition",
    "DestinyInventoryItemDefinition",
    "DestinyPresentationNodeDefinition",
    "DestinyVendorDefinition",
]


DESTINY_ITEM_TYPE_WEAPON = 3
DESTINY_ITEM_TYPE_ARMOR = 2


def likely_emoji_name(name: str) -> str:
    return name.replace(" ", "_").replace("-", "_").lower()


class OAuthStateManager:
    _oauth_state_codes: t.Dict[str, dt.datetime] = {}
    _access_token: t.Optional[str] = None
    _access_token_expires: t.Optional[dt.datetime] = None

    @classmethod
    def generate_oauth_state_code(cls):
        while True:
            state_code = str(uuid4())
            if cls.check_state_code_exists(state_code):
                continue
            else:
                expiry = dt.datetime.now() + dt.timedelta(minutes=5)
                cls._oauth_state_codes[state_code] = expiry
                break

        return state_code

    @classmethod
    def consume_oauth_state_code(cls, state_code: str):
        expiry_date = cls._oauth_state_codes.pop(state_code)
        if expiry_date <= dt.datetime.now():
            raise ValueError("State code has expired or is incorrect.")

    @classmethod
    def check_state_code_exists(cls, state_code: str):
        try:
            if cls._oauth_state_codes[state_code] > dt.datetime.now():
                return True
            else:
                cls._oauth_state_codes.pop(state_code)
                return False
        except KeyError:
            return False

    # Note, chaining @classmethod and @property is deprecated in
    # python 3.13, hence the getter method here
    @classmethod
    def get_access_token(cls) -> str | None:
        if cls._access_token_expires and cls._access_token_expires > dt.datetime.now():
            return cls._access_token

    @classmethod
    def set_access_token(cls, access_token, access_token_expires: int):
        """NOTE: This is not stored in the db, and is instead a class variable"""
        cls._access_token = access_token
        cls._access_token_expires = dt.datetime.now() + dt.timedelta(
            seconds=access_token_expires * 0.8  # 20% Factor of Safety
        )

    @classmethod
    def clear_access_token(cls):
        cls._access_token = None
        cls._access_token_expires = None


async def _get_latest_manifest(api_key: str) -> str:
    # Prep the manifest directory
    Path("manifest").mkdir(exist_ok=True)

    # Get the latest manifest url from the API
    async with aiohttp.ClientSession() as session:
        async with session.get(
            API_MANIFEST, headers={"X-API-Key": api_key}
        ) as response:
            manifest_url_fragment = (await response.json())["Response"][
                "mobileWorldContentPaths"
            ]["en"]

    manifest_url_filename = manifest_url_fragment.split("/")[-1]
    # Check if the manifest is already downloaded
    if os.path.exists("manifest/" + manifest_url_filename):
        return "manifest/" + manifest_url_filename

    manifest_url = BUNGIE_NET + manifest_url_fragment

    async with aiohttp.ClientSession() as session:
        async with session.get(manifest_url) as response:
            manifest_zip = await response.read()

    async with aiofiles.open("manifest.zip", "wb") as file:
        await file.write(manifest_zip)

    # Cleanup manifest directory
    for file in os.listdir("manifest"):
        os.remove("manifest/" + file)

    def _extract():
        # Extract the newly downloaded manifest
        with zipfile.ZipFile("manifest.zip", "r") as zip_ref:
            zip_ref.extractall("manifest")

    await asyncio.get_event_loop().run_in_executor(None, _extract)

    manifest_path = "manifest/" + os.listdir("manifest")[0]
    return manifest_path


async def _build_manifest_dict(manifest_path: str):
    # connect to the manifest
    async with aiosqlite.connect(manifest_path) as con:
        # create a cursor object
        cur = await con.cursor()
        all_data = {}
        # for every table name in the dictionary
        for table_name in manifest_table_names:
            # get a list of all the jsons from the table
            await cur.execute("SELECT json from " + table_name)
            # this returns a list of tuples: the first item in each tuple is our json
            items = await cur.fetchall()
            # create a list of jsons
            item_jsons = [json.loads(item[0]) for item in items]
            # create a dictionary with the hashes as keys
            # and the jsons as values
            item_dict = {}
            for item in item_jsons:
                # add that dictionary to our all_data using the name of the table
                # as a key.
                item_dict[item["hash"]] = item
            all_data[table_name] = item_dict
    return all_data


class VendorNotFound(Exception):
    def __init__(self, message, api_response=None):
        self.message = message
        self.api_response = api_response

    def __str__(self) -> str:
        return super().__str__() + "\n" + pformat(self.api_response)


class APIOffline(Exception):
    def __init__(self, api_response):
        self.message = "The Bungie API is currently offline"
        self.api_response = api_response

    def __str__(self) -> str:
        return self.message + "\n" + pformat(self.api_response)


class DestinyMembership:
    @classmethod
    async def from_api(
        cls,
        session: aiohttp.ClientSession,
        access_token: str,
    ) -> t.Self:
        url = API_GET_MEMBERSHIPS
        headers = {
            "Authorization": f"Bearer {access_token}",
            "X-API-Key": schemas.BungieCredentials.api_key,
        }

        async with session.get(url, headers=headers) as resp:
            resp = (await resp.json())["Response"]
            return cls.from_api_response(resp)

    @classmethod
    def from_api_response(cls, response) -> t.Self:
        destiny_memberships = response["destinyMemberships"]
        primary_membership_id = response["primaryMembershipId"]

        for membership in destiny_memberships:
            if membership["membershipId"] == primary_membership_id:
                primary_membership_type = membership["membershipType"]
                break

        try:
            return cls(primary_membership_id, primary_membership_type)
        except NameError:
            raise ValueError(
                "Could not find primary destiny membership type for this bungie "
                "account"
            )

    def __init__(
        self,
        membership_id: int,
        membership_type: int,
    ):
        self.membership_id = int(membership_id)
        self.membership_type = int(membership_type)

    def __repr__(self):
        return f"Destiny Membership: {self.membership_id} ({self.membership_type})"

    async def get_character_id(
        self,
        session: aiohttp.ClientSession,
        access_token: str,
        character_index: int = 0,
    ):
        url = API_PROFILE.format(
            membership_type=self.membership_type,
            membership_id=self.membership_id,
        )
        headers = {
            "Authorization": f"Bearer {access_token}",
            "X-API-Key": schemas.BungieCredentials.api_key,
        }

        async with session.get(url, headers=headers) as resp:
            data = await resp.json()
            return data["Response"]["profile"]["data"]["characterIds"][character_index]


class DestinyItem:
    @classmethod
    def from_sale_item(
        cls,
        sale_item: dict,
        # reusable_plugs: dict,
        stats: dict,
        perks: dict,
        manifest_table: dict,
    ):
        hash_ = sale_item["itemHash"]

        manifest_entry = manifest_table["DestinyInventoryItemDefinition"][hash_]

        name: str = manifest_entry["displayProperties"]["name"]
        rarity: str = manifest_entry["inventory"].get("tierTypeName", "Unknown Rarity")
        class_: int = manifest_entry["classType"]
        class_: str = (
            DESTINY_CLASSES_ENUM[class_]
            if class_ < len(DESTINY_CLASSES_ENUM)
            else "Unknown"
        )
        bucket: int = manifest_entry["inventory"]["bucketTypeHash"]
        bucket: dict | None = manifest_table["DestinyEquipmentSlotDefinition"].get(
            bucket
        )
        if bucket:
            bucket: str = (
                bucket["displayProperties"]
                .get("name", "Unknown Slot")
                .replace("Armor", "")
                .strip()
            )

        item_type: int = manifest_entry["itemType"]
        item_type_friendly_name: str = manifest_entry["itemTypeDisplayName"]

        collectible_set_name = (
            (
                DestinyCollectible.from_collectible_hash(
                    manifest_entry["collectibleHash"], manifest_table
                )
                .parent_nodes[0]
                .name
            )
            if "collectibleHash" in manifest_entry
            else None
        )

        costs_data = sale_item.get("costs", [])
        costs = {}
        for cost in costs_data:
            item_hash = cost.get("itemHash", 0)
            quantity = cost.get("quantity", 0)
            if item_hash:
                item_name = (
                    manifest_table["DestinyInventoryItemDefinition"]
                    .get(item_hash, {})
                    .get("displayProperties", {})
                    .get("name", "")
                )

            else:
                item_name = ""
            if item_name:
                costs[item_name] = quantity

        cls = cls.get_appropriate_subclass(item_type)
        self: t.Self = cls(
            name=name,
            hash_=hash_,
            rarity=rarity,
            class_=class_,
            bucket=bucket,
            item_type=item_type,
            item_type_friendly_name=item_type_friendly_name,
            collectible_set_name=collectible_set_name,
            costs=costs,
        )
        self: t.Self = self.with_stats(stats, manifest_table)
        self: t.Self = self.with_perks(perks, manifest_table)

        return self

    def __init__(
        self,
        name: str,
        hash_: int,
        rarity: str,
        class_: str,
        bucket: str,
        item_type: int,
        item_type_friendly_name: str,
        collectible_set_name: str = None,
        costs: t.Dict[str, int] = {},
    ):
        self.name = name
        self.hash = hash_
        self.rarity = rarity
        self.class_ = class_
        self.bucket = bucket
        self.item_type = item_type
        self.item_type_friendly_name = item_type_friendly_name
        self.collectible_set_name = collectible_set_name
        self.costs = costs

    def __repr__(self):
        return (
            f"{self.name}\n"
            + f" - Rarity: {self.rarity}\n"
            + f" - Type: {self.item_type_friendly_name}\n"
        )

    @staticmethod
    def get_appropriate_subclass(item_type: int) -> t.Type[t.Self]:
        if item_type == DESTINY_ITEM_TYPE_WEAPON:
            return DestinyWeapon
        elif item_type == DESTINY_ITEM_TYPE_ARMOR:
            return DestinyArmor
        else:
            return DestinyItem

    @property
    def is_armor(self) -> bool:
        return self.item_type == DESTINY_ITEM_TYPE_ARMOR

    @property
    def is_weapon(self) -> bool:
        return self.item_type == DESTINY_ITEM_TYPE_WEAPON

    @property
    def is_catalyst(self) -> bool:
        return "catalyst" in self.name.lower()

    @property
    def is_exotic(self) -> bool:
        return self.rarity == "Exotic"

    @property
    def is_legendary(self) -> bool:
        return self.rarity == "Legendary"

    @property
    def lightgg_url(self) -> str:
        return f"https://light.gg/db/items/{self.hash}"

    @property
    def expected_emoji_name(self) -> str:
        return likely_emoji_name(self.item_type_friendly_name)

    def with_reusable_plugs(self, plugs: t.Dict[str, list], manifest_table: dict):
        return self

    def with_stats(
        self,
        stats: t.Dict[str, t.Dict[str, int]]
        | t.Dict[str, t.Dict[str, t.Dict[str, int]]],
        manifest_table: dict,
    ) -> t.Self:
        self._stats = {}

        if not stats:
            return self

        if "stats" in stats:
            stats = stats["stats"]

        for stat_group in stats.values():
            stat_hash = stat_group["statHash"]
            stat_value = stat_group["value"]

            stat_name = (
                manifest_table["DestinyStatDefinition"]
                .get(int(stat_hash), {})
                .get("displayProperties", {})
                .get("name")
            )
            if stat_name:
                self._stats[stat_name] = stat_value

        return self

    @property
    def stats(self) -> dict:
        return self._stats

    def with_perks(
        self,
        perks: t.Dict[str, t.Dict[str, t.Any]]
        | t.Dict[str, t.Dict[str, t.Dict[str, t.Any]]],
        manifest_table: dict,
    ) -> t.Self:
        self._perks = []

        if not perks:
            return self

        if "perks" in perks:
            perks = perks["perks"]

        for perk_group in perks:
            perk_group: t.Dict[str, t.Any]
            perk_entry = manifest_table["DestinySandboxPerkDefinition"][
                perk_group["perkHash"]
            ]
            perk_name = perk_entry["displayProperties"]["name"]

            if not perk_name:
                continue

            self._perks.append(perk_name)

        return self

    @property
    def perks(self) -> t.List[str]:
        return self._perks


class DestinyWeapon(DestinyItem):
    def __init__(self, *, perks: t.Tuple[t.Tuple[str]] = None, **kwargs):
        super().__init__(**kwargs)
        self._perks = perks

    @staticmethod
    def _plugs_to_perks(
        plugs_array: t.Dict[str, list], manifest_table: dict
    ) -> t.Tuple[str]:
        # CAUTION: This cannot yet differentiate between masterworks, kill trackets and
        #          actual perks
        if "plugs" in plugs_array:
            plugs_array: dict = plugs_array["plugs"]

        perks = []
        for plugs in plugs_array.values():
            perks_in_array_segment = []
            for plug in plugs:
                plug_hash = plug["plugItemHash"]
                plug_json = manifest_table["DestinyInventoryItemDefinition"][plug_hash]
                perks_in_array_segment.append(plug_json["displayProperties"]["name"])
            perks.append(tuple(perks_in_array_segment))

        return tuple(perks)

    def with_reusable_plugs(self, plugs: t.Dict[str, list], manifest_table: dict):
        self._perks = self._plugs_to_perks(plugs, manifest_table)
        return self

    def __repr__(self):
        return super().__repr__() + (
            f" - Perks: {self._perks_representation(self.perks)}\n"
            if self.perks
            else ""
        )

    @staticmethod
    def _perks_representation(perks: t.Tuple[t.Tuple[str]]) -> str:
        _perks = []
        for perk_group in perks:
            _perks.append(" / ".join(perk_group))
        return " + ".join(_perks)


class DestinyArmor(DestinyItem):
    _tracked_stats = [
        "Mobility",
        "Resilience",
        "Recovery",
        "Discipline",
        "Intellect",
        "Strength",
    ]

    def __init__(
        self,
        *,
        stats: t.Dict[str, int] = {},
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._stats = stats
        self._intrinsic_stats_added = False

        for stat in self._tracked_stats:
            if stat not in self.stats:
                self.stats[stat] = 0

    @staticmethod
    def _get_stat_name(manifest_table: dict, hash_: int):
        return (
            manifest_table["DestinyStatDefinition"]
            .get(int(hash_), {})
            .get("displayProperties", {})
            .get("name")
        )

    def _add_intrinsic_stats(self, manifest_table: dict):
        if self._intrinsic_stats_added:
            return

        manifest_entry: dict = manifest_table["DestinyInventoryItemDefinition"][
            self.hash
        ]

        stats: dict = manifest_entry.get("stats", {})
        stats = stats.get("stats", {})

        for stat_hash, stat_dict in stats.items():
            stat_name = self._get_stat_name(manifest_table, stat_hash)
            stat_value = stat_dict["value"]
            if stat_name and stat_name in self.stats:
                self.stats[stat_name] += stat_value

        self._intrinsic_stats_added = True

    def _plugs_to_stats(
        self,
        plugs: t.Dict[
            str,  # -------------------> Key always seems to be "plugs" here
            t.Dict[
                str | int,  # ---------> Key is always an int as a str
                t.List[  # ------------> List with a single element :(
                    t.Dict[
                        str,  # -------> Only "canInsert", "enabled", or "plugItemHash"
                        bool | int,  # > Either bool, bool or int respectively
                    ],
                ],
            ],
        ],
        manifest_table: dict,
    ) -> t.Tuple[int]:
        plugs: t.Dict[
            str | int,  # ---------> Key is always an int as a str
            t.List[  # ------------> List with a single element :(
                t.Dict[
                    str,  # -------> Only "canInsert", "enabled", or "plugItemHash"
                    bool | int,  # > Either bool, bool or int respectively
                ],
            ],
        ] = plugs["plugs"]

        for plug in plugs.values():
            plug: t.List[  # ------------> List with a single element :(
                t.Dict[
                    str,  # -------> Only "canInsert", "enabled", or "plugItemHash"
                    bool | int,  # > Either bool, bool or int respectively
                ],
            ]
            for plug_dict in plug:
                plug_dict: t.Dict[
                    str,  # -------> Only "canInsert", "enabled", or "plugItemHash"
                    bool | int,  # > Either bool, bool or int respectively
                ]
                plug_item_hash = plug_dict["plugItemHash"]

                # Pull the plug json from the manifest and work with that to calculate
                # the stats
                plug_json = manifest_table["DestinyInventoryItemDefinition"][
                    plug_item_hash
                ]
                if plug_json["itemType"] == 19:
                    plug_stats: dict = plug_json["investmentStats"]
                    for stat_value in plug_stats:
                        stat_hash = stat_value["statTypeHash"]
                        stat_value = stat_value["value"]
                        stat_name = self._get_stat_name(manifest_table, stat_hash)
                        if stat_name and stat_name in self.stats:
                            self.stats[stat_name] += stat_value

    def with_reusable_plugs(self, plugs: t.Dict[str, list], manifest_table: dict):
        self._plugs = plugs
        # self._plugs_to_stats(plugs, manifest_table)
        # self._add_intrinsic_stats(manifest_table)
        return self

    @property
    def armor_set_name(self) -> str | None:
        if not self.is_armor or self.is_exotic:
            return None
        return self.collectible_set_name

    @property
    def stats(self) -> dict:
        self._stats = {name: self._stats.get(name, 0) for name in self._tracked_stats}
        return self._stats

    @stats.setter
    def stats(self, stats: dict):
        self._stats = {name: stats.get(name, 0) for name in self._tracked_stats}

    @property
    def stat_total(self) -> int:
        return sum(self.stats.values())

    def __repr__(self):
        return (
            super().__repr__()
            + (f" - Armor Set: {self.armor_set_name}\n" if self.armor_set_name else "")
            + (
                (
                    " - Stats:\n"
                    + "\n".join(
                        f"   * {stat_name}: {stat_value}"
                        for stat_name, stat_value in self.stats.items()
                    )
                    + "\n"
                    + f"   * Total: {self.stat_total}"
                )
                if self.stats
                else ""
            )
            + "\n"
        )


class DestinyCollectible:
    @classmethod
    def from_collectible_hash(cls, collectible_hash: int, manifest_table: dict):
        return cls(
            manifest_table["DestinyCollectibleDefinition"][collectible_hash],
            manifest_table,
        )

    def __init__(self, collectible_json: dict, manifest_table: dict):
        self._json = collectible_json
        self.name = collectible_json.get("displayProperties", {}).get("name")
        self.description = collectible_json.get("displayProperties", {}).get(
            "description"
        )
        self.hash = collectible_json.get("hash")
        self.collectible_index = collectible_json.get("index")
        self.collectible_item_hash = collectible_json.get("itemHash")
        parent_node_hashes = collectible_json.get("parentNodeHashes")
        self.parent_nodes = [
            DestinyPresentationNode.from_node_hash(hash_, manifest_table)
            for hash_ in parent_node_hashes
        ]


class DestinyPresentationNode:
    @classmethod
    def from_node_hash(cls, node_hash: int, manifest_table: dict):
        return cls(
            manifest_table["DestinyPresentationNodeDefinition"][node_hash],
            manifest_table,
        )

    def __init__(self, node_json: dict, manifest_table: dict):
        self._json = node_json
        self.name = node_json.get("displayProperties", {}).get("name")
        self.hash = node_json.get("hash")


class DestinyVendor:
    @classmethod
    async def request_from_api(
        cls,
        access_token: str,
        destiny_membership: DestinyMembership,
        character_id: int,
        vendor_hash: int = XUR_VENDOR_HASH,
        manifest_table: dict | None = None,
        manifest_entry: dict | None = None,
    ) -> t.Self:
        """Request a DestinyVendor object from the Bungie API.

        Will raise a VendorNotFound exception if the vendor is not found."""
        async with aiohttp.ClientSession() as session:
            response = await session.get(
                API_VENDORS_AUTHENTICATED.format(
                    membershipType=destiny_membership.membership_type,
                    destinyMembershipId=destiny_membership.membership_id,
                    characterId=character_id,
                    vendorHash=vendor_hash,
                    components=components,
                ),
                headers={
                    "X-API-Key": schemas.BungieCredentials.api_key,
                    "Authorization": f"Bearer {access_token}",
                },
            )
            response = await response.json()

            if response["ErrorCode"] == 1627:
                raise VendorNotFound("Vendor not found", api_response=response)

            response = response["Response"]

        return cls.from_vendors_api_response(
            response=response,
            manifest_table=manifest_table,
            manifest_entry=manifest_entry,
        )

    @classmethod
    def from_vendors_api_response(
        cls,
        response: dict,
        manifest_table: dict | None = None,
        manifest_entry: dict | None = None,
    ) -> t.Self:
        hash_ = response["vendor"]["data"]["vendorHash"]
        if manifest_entry is None and manifest_table is None:
            raise ValueError("Either manifest_table or manifest_entry must be provided")

        if manifest_entry is None:
            manifest_entry = manifest_table["DestinyVendorDefinition"][hash_]

        name = manifest_entry.get("displayProperties", {}).get("name")

        _locations_list = manifest_entry.get("locations")
        _location_index = response["vendor"]["data"]["vendorLocationIndex"]

        if _locations_list and _location_index < len(_locations_list):
            _destination_hash = _locations_list[_location_index]["destinationHash"]
            location = manifest_table["DestinyDestinationDefinition"][
                _destination_hash
            ]["displayProperties"]["name"]
        else:
            location = None

        _sale_items: dict = response["sales"]["data"]
        # _plugs_for_sale_items: dict = response["itemComponents"]["reusablePlugs"][
        #     "data"
        # ]
        _stats_for_sale_items: dict = response["itemComponents"]["stats"]["data"]
        _perks_for_sale_items: dict = response["itemComponents"]["perks"]["data"]

        destiny_items_for_sale = []
        for _sale_item_key in _sale_items.keys():
            # _plugs_for_sale_item = _plugs_for_sale_items.get(_sale_item_key, {})
            _destiny_item_for_sale = DestinyItem.from_sale_item(
                sale_item=_sale_items[_sale_item_key],
                # reusable_plugs=_plugs_for_sale_item,
                stats=_stats_for_sale_items.get(_sale_item_key, {}),
                perks=_perks_for_sale_items.get(_sale_item_key, {}),
                manifest_table=manifest_table,
            )
            destiny_items_for_sale.append(_destiny_item_for_sale)

        return cls(
            name=name,
            hash_=hash_,
            location=location,
            sale_items=destiny_items_for_sale,
        )

    def __init__(
        self,
        name: str,
        hash_: int,
        location: str = None,
        sale_items: t.List[DestinyItem] = [],
    ):
        self.name = name
        self.hash_ = hash_
        self.location = location
        self.sale_items = sale_items

    def __repr__(self):
        repr_ = f"{self.name}" + f" - {self.location}" if self.location else ""
        repr_ += "\n" + "\n".join(f" - {item}" for item in self.sale_items)
        return repr_

    # Implement addition of vendors to add their sale items
    # Keeping all other properties of self
    def __add__(self, other: t.Self) -> t.Self:
        return DestinyVendor(
            name=self.name,
            hash_=self.hash_,
            location=self.location,
            sale_items=self.sale_items + other.sale_items,
        )


# Get a url to send the user to for OAuth
def oauth_url():
    state_code = OAuthStateManager.generate_oauth_state_code()
    return (URL(BUNGIE_NET) / "en/OAuth/Authorize").with_query(
        client_id=schemas.BungieCredentials.client_id,
        response_type="code",
        state=state_code,
    )


class APIOfflineException(Exception):
    pass


async def check_bungie_api_online(raise_exception: bool = False) -> bool:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{API_ROOT}/App/FirstParty",
            headers={"X-API-Key": schemas.BungieCredentials.api_key},
        ) as response:
            response = await response.json()
            if response["ErrorCode"] in [0, 1]:
                return True
            elif raise_exception:
                raise APIOfflineException(response)
            else:
                return False


def webserver_runner_preparation() -> aiohttp.web.AppRunner:
    app = aiohttp.web.Application()
    routes = aiohttp.web.RouteTableDef()

    @routes.get("/oauth/callback")
    async def handle_oauth_callback(request):
        # Extract the code from the callback URL
        try:
            code = request.query.get("code", "")
            state_code = request.query.get("state", "")

            OAuthStateManager.consume_oauth_state_code(state_code)

        except KeyError:
            return aiohttp.web.Response(text="Invalid callback URL")

        except ValueError:
            return aiohttp.web.Response(text="URL has expired or is incorrect")

        # Exchange the code for an access token

        async with aiohttp.ClientSession() as session:
            async with session.post(
                API_OAUTH_GET_TOKEN,
                data={
                    "client_id": schemas.BungieCredentials.client_id,
                    "client_secret": schemas.BungieCredentials.client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
                },
            ) as response:
                response_json = await response.json()

        OAuthStateManager.set_access_token(
            response_json["access_token"], response_json["expires_in"]
        )
        await schemas.BungieCredentials.set_refresh_token(
            refresh_token=response_json["refresh_token"],
            refresh_token_expires=response_json["refresh_expires_in"],
        )

        return aiohttp.web.Response(text="You can close this tab/window now.")

    app.add_routes(routes)
    runner = aiohttp.web.AppRunner(app)
    return runner


async def _wait_for_token_from_login(
    runner: aiohttp.web.AppRunner,
) -> str:
    print("Waiting for access token...")
    sys.stdout.flush()

    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "0.0.0.0", cfg.port)
    await site.start()

    while not (_access_token := OAuthStateManager.get_access_token()):
        await asyncio.sleep(1)

    await runner.shutdown()
    await runner.cleanup()

    return _access_token


async def refresh_api_tokens(
    runner: aiohttp.web.AppRunner, with_login: bool = False
) -> t.Coroutine[t.Any, t.Any, str]:
    if with_login:
        OAuthStateManager.clear_access_token()
        _access_token = await _wait_for_token_from_login(runner)
        return _access_token

    bungie_credentials = await schemas.BungieCredentials.get_credentials()
    if not bungie_credentials:
        raise ValueError("Bungie credentials are not set, please log in")
    elif dt.datetime.now() > bungie_credentials.refresh_token_expires:
        raise ValueError("Bungie credentials have expired, please log in again")

    async with aiohttp.ClientSession() as session:
        async with session.post(
            API_OAUTH_GET_TOKEN,
            data={
                "client_id": schemas.BungieCredentials.client_id,
                "client_secret": schemas.BungieCredentials.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": bungie_credentials.refresh_token,
            },
        ) as response:
            response_json = await response.json()
            _access_token = response_json["access_token"]
            _refresh_token = response_json["refresh_token"]
            _refresh_token_expires = response_json["refresh_expires_in"]

    await schemas.BungieCredentials.set_refresh_token(
        refresh_token=_refresh_token,
        refresh_token_expires=_refresh_token_expires,
    )

    return _access_token


@lb.command("bungie", "Bungie API related commands")
@lb.implements(lb.SlashCommandGroup)
async def bungie():
    pass


@bungie.child
@lb.command("login", "Log in to the app with a Bungie account", ephemeral=True)
@lb.implements(lb.SlashSubCommand)
async def login(ctx: lb.Context):
    await ctx.respond(f"Please log in at {oauth_url()}")
    await refresh_api_tokens(runner=ctx.app.d.webserver_runner, with_login=True)
    await ctx.edit_last_response(content="Successfully logged in")


@bungie.child
@lb.command(
    "account_numbers",
    "Get the character id, destiny membership id and membership type",
    ephemeral=True,
    auto_defer=True,
)
@lb.implements(lb.SlashSubCommand)
async def account_numbers(ctx: lb.Context):
    access_token = await refresh_api_tokens(runner=ctx.app.d.webserver_runner)

    async with aiohttp.ClientSession() as session:
        destiny_membership = await DestinyMembership.from_api(session, access_token)
        character_id = await destiny_membership.get_character_id(session, access_token)

    await ctx.respond(
        "```"
        f"Destiny Character ID: {character_id}\n"
        f"Destiny Membership ID: {destiny_membership.membership_id}\n"
        f"Destiny Membership Type: {destiny_membership.membership_type}"
        "```"
    )


def register(bot: lb.BotApp):
    bot.d.webserver_runner = webserver_runner_preparation()
    bot.command(bungie)


async def main():
    runner = webserver_runner_preparation()
    manifest_table = await _build_manifest_dict(
        await _get_latest_manifest(schemas.BungieCredentials.api_key)
    )

    access_token = await refresh_api_tokens(runner)

    async with aiohttp.ClientSession() as session:
        destiny_membership = await DestinyMembership.from_api(session, access_token)
        character_id = await destiny_membership.get_character_id(session, access_token)

    for vendor_hash in [XUR_VENDOR_HASH]:
        vendor = await DestinyVendor.request_from_api(
            destiny_membership=destiny_membership,
            character_id=character_id,
            access_token=OAuthStateManager.get_access_token(),
            manifest_table=manifest_table,
            vendor_hash=vendor_hash,
        )
        print(vendor)
        [print(item) for item in vendor.sale_items if item.is_armor or item.is_weapon]
