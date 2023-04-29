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

import hikari as h
import lightbulb as lb
from lightbulb.ext import wtf
from . import cfg
from .autopost import WeekendResetSignal
from .autopost_url import (
    BaseUrlSignal,
    UrlAutopostsBase,
    UrlAutopostChannel,
    UrlPostSettings,
)
from .utils import Base, weekend_period


class XurPostSettings(UrlPostSettings, Base):
    embed_title: str = "Xur's Inventory and Location"
    embed_description: str = (
        "**Arrives:** {start_day_name}, {start_month} {start_day}\n"
        + "**Departs:** {end_day_name}, {end_month} {end_day}"
    )
    default_gfx_url: str = cfg.defaults.xur.gfx_url
    default_post_url: str = cfg.defaults.xur.post_url
    validity_period = staticmethod(weekend_period)
    embed_command_name = "Xur"
    embed_command_description = "Xur infographic and post"

    async def get_announce_embed(self, body: str = None, infographic=None) -> h.Embed:
        embed = await super().get_announce_embed()
        embed.description = body or embed.description
        if infographic:
            embed.set_image(infographic)
        return embed


class XurAutopostChannel(UrlAutopostChannel, Base):
    settings_records = XurPostSettings
    follow_channel = cfg.xur_follow_channel_id
    autopost_friendly_name = "Xur autoposts"


class XurSignal(BaseUrlSignal):
    settings_table = XurPostSettings
    trigger_on_signal = WeekendResetSignal


class XurAutopostsBase(UrlAutopostsBase):
    def commands(self) -> lb.SlashCommandGroup:
        # Announcement management commands for kyber
        return wtf.Command[
            wtf.Implements[lb.SlashSubGroup],
            wtf.Name[self.announcement_name.lower().replace(" ", "_")],
            wtf.Description[
                "{} announcement management".format(self.announcement_name)
            ],
            wtf.Guilds[cfg.control_discord_server_id],
            wtf.InheritChecks[True],
            wtf.Subcommands[
                # Autoposts Enable/Disable
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
                    wtf.Executes[self.autopost_ctrl],
                ],
                wtf.Command[
                    wtf.Name["infogfx_url"],
                    wtf.Description[
                        "Set the {} infographic url, to check and post".format(
                            self.announcement_name.lower()
                        )
                    ],
                    wtf.AutoDefer[True],
                    wtf.InheritChecks[True],
                    wtf.Options[
                        wtf.Option[
                            wtf.Name["url"],
                            wtf.Description["The url to set"],
                            wtf.Type[str],
                            wtf.Required[False],
                        ],
                    ],
                    wtf.Implements[lb.SlashSubCommand],
                    wtf.Executes[self.gfx_url],
                ],
                wtf.Command[
                    wtf.Name["post_url"],
                    wtf.Description[
                        "Set the {} post url, to check and post".format(
                            self.announcement_name.lower()
                        )
                    ],
                    wtf.AutoDefer[True],
                    wtf.InheritChecks[True],
                    wtf.Options[
                        wtf.Option[
                            wtf.Name["url"],
                            wtf.Description["The url to set"],
                            wtf.Type[str],
                            wtf.Required[False],
                        ],
                    ],
                    wtf.Implements[lb.SlashSubCommand],
                    wtf.Executes[self.post_url],
                ],
                wtf.Command[
                    wtf.Name["update"],
                    wtf.Description["Update a post"],
                    wtf.AutoDefer[True],
                    wtf.InheritChecks[True],
                    wtf.Options[
                        wtf.Option[
                            wtf.Name["body"],
                            wtf.Description["The infographic image to use"],
                            wtf.Type[str],
                            wtf.Required[False],
                            wtf.Default[None],
                        ],
                        wtf.Option[
                            wtf.Name["infographic"],
                            wtf.Description["The infographic image to use"],
                            wtf.Type[h.Attachment],
                            wtf.Required[False],
                            wtf.Default[None],
                        ],
                    ],
                    wtf.Implements[lb.SlashSubCommand],
                    wtf.Executes[self.rectify_announcement],
                ],
                wtf.Command[
                    wtf.Name["announce"],
                    wtf.Description["Trigger an announcement manually"],
                    wtf.AutoDefer[True],
                    wtf.InheritChecks[True],
                    wtf.Options[
                        wtf.Option[
                            wtf.Name["body"],
                            wtf.Description["The infographic image to use"],
                            wtf.Type[str],
                            wtf.Required[False],
                            wtf.Default[None],
                        ],
                        wtf.Option[
                            wtf.Name["infographic"],
                            wtf.Description["The infographic image to use"],
                            wtf.Type[h.Attachment],
                            wtf.Required[False],
                            wtf.Default[None],
                        ],
                    ],
                    wtf.Implements[lb.SlashSubCommand],
                    wtf.Executes[self.manual_announce],
                ],
            ],
        ]

    async def manual_announce(self, ctx: lb.Context):
        faux_event = self.autopost_trigger_signal.register(ctx.bot)
        await ctx.respond("Announcements being sent out now")
        await XurAutopostChannel._announcer(
            faux_event,
            body=ctx.options.body,
            infographic=ctx.options.infographic,
        )


xur = XurAutopostsBase(
    settings_table=XurPostSettings,
    channel_table=XurAutopostChannel,
    autopost_trigger_signal=XurSignal,
    default_gfx_url=cfg.defaults.xur.gfx_url,
    default_post_url=cfg.defaults.xur.post_url,
    announcement_name="Xur",
)
