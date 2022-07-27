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

from . import cfg
from .autopost import WeekendResetSignal
from .autopost_url import (
    BaseUrlSignal,
    ControlCommandsImpl,
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


class XurAutopostChannel(UrlAutopostChannel, Base):
    settings_records = XurPostSettings


class XurSignal(BaseUrlSignal):
    settings_table = XurPostSettings
    trigger_on_signal = WeekendResetSignal


class XurControlCommands(ControlCommandsImpl):
    announcement_name = "Xur"
    settings_table = XurPostSettings
    autopost_channel_table = XurAutopostChannel
    autopost_trigger_signal = XurSignal
    default_gfx_url = cfg.defaults.xur.gfx_url
    default_post_url = cfg.defaults.xur.post_url
