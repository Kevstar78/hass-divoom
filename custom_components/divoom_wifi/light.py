"""Platform for Divoom Wifi Light integration"""
from __future__ import annotations

import os
import voluptuous as vol
import logging
import requests

from pprint import pformat
from typing import Any

import homeassistant.helpers.config_validation as cv
from homeassistant.components.light import (
    LightEntityFeature, PLATFORM_SCHEMA, LightEntity, ColorMode, ATTR_BRIGHTNESS, ATTR_RGB_COLOR, ATTR_EFFECT,
)
from homeassistant.const import CONF_NAME, CONF_MAC, CONF_IP_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import device_registry as dr, entity_platform, service
from homeassistant.helpers.event import (
    async_track_state_change_event, Event
)

from .const import ATTR_SCORE_1, ATTR_SCORE_2, DOMAIN, CONF_DEVICE_TYPE, CONF_MEDIA_DIR, CONF_MEDIA_DIR_DEFAULT, SERVICE_SHOW_IMAGE
from .pixoo import Pixoo
from .pixoo import Channel

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME): cv.string,
    vol.Required(CONF_MAC): cv.string,
    vol.Required(CONF_IP_ADDRESS): cv.string,
    vol.Required(CONF_DEVICE_TYPE): cv.string,
    vol.Required(CONF_MEDIA_DIR, default=CONF_MEDIA_DIR_DEFAULT): cv.string,
})

def show_image(divoomWifiDevice: Pixoo, image_path: str) -> None:
    try:
        image_path = requests.get(image_path, stream=True).raw
    except:
        pass
    divoomWifiDevice.draw_image(image_path, pad_resample=True)
    divoomWifiDevice.push(reload_counter=True)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Divoom Wifi Light based on config entry"""
    if entry is None:
        return
        
    _LOGGER.info(pformat(entry.data))

    media_dir = CONF_MEDIA_DIR_DEFAULT
    if CONF_MEDIA_DIR in entry.data:
        media_dir = entry.data[CONF_MEDIA_DIR]

    data = {
        "name": entry.title,
        "mac": entry.data[CONF_MAC],
        "ip_adress": entry.data[CONF_IP_ADDRESS],
        "device_type": entry.data[CONF_DEVICE_TYPE],
        "media_directory": media_dir
    }

    divoomWifiDevice = hass.data[DOMAIN]["divoom_device"]

    async_add_entities([
        DivoomWifiLight(data, divoomWifiDevice),
    ])
    
    platform = entity_platform.async_get_current_platform()
    
    platform.async_register_entity_service(
      SERVICE_SHOW_IMAGE,
      {
        vol.Required("image_path"): cv.string,
      },
      "async_show_image"
      )

#def setup_platform(
#    hass: HomeAssistant,
#    config: ConfigType,
#    add_entities: AddEntitiesCallback,
#    discovery_info: DiscoveryInfoType
#) -> None:
#    """Set up Divoom Bluetooth Light Platform"""
#    # We only want this platform to be set up via discovery.
#    if discovery_info is None:
#        return
#        
#    _LOGGER.info(pformat(config))
#    _LOGGER.info(pformat(discovery_info))
#
#    light = {
#        "name": discovery_info[CONF_NAME],
#        "mac": discovery_info[CONF_MAC],
#        "device_type": discovery_info[CONF_DEVICE_TYPE],
#        "media_directory": discovery_info[CONF_MEDIA_DIR]
#    }
#
#    add_entities([DivoomWifiLight(light)])

class DivoomWifiLight(LightEntity):
    """Representation of Divoom Wifi light"""

    def __init__(self, data, divoomWifiDevice: Pixoo) -> None:
        """Initialize a Divoom Wifi light"""
        self._attr_name = data["name"]
        self._attr_unique_id = data["mac"]
        self._device_type = data["device_type"]
        self._media_directory = data["media_directory"]

        self._attr_effect_list = [
            "FACES",
            "CLOUD",
            "VISUALIZER",
            "CUSTOM"
        ]

        self._attr_device_info = {
            "name": data["name"],
            "manufacturer": "divoom",
            "model": data["device_type"]#,
#            "connections": {
#                (dr.CONNECTION_NETWORK_MAC, data["mac"])
        }
#        }
        
#        if not os.path.isdir(self._media_directory):
#            raise "media_directory {0} does not exist (or access denied), divoom_wifi may not work properly".format(self._media_directory)
        
        self._divoomWifiDevice = divoomWifiDevice
#        self._divoomWifiDevice.connect()


    async def async_added_to_hass(self):
        _LOGGER.debug("light added to hass")
        entity_id = self.entity_id[self.entity_id.find('.') + 1:]
        entity_ids = ["number.{}_score_1".format(entity_id), "number.{}_score_2".format(entity_id)]
        _LOGGER.debug("setting up state change tracking for scores")
        _LOGGER.debug(pformat(entity_ids))

        self.async_on_remove( # calls returned unsub function on remove
            async_track_state_change_event(self.hass, entity_ids, self.async_score_changed)
        )


    @property
    def supported_color_modes(self) -> set[ColorMode] | set[str] | None:
        """Flag supported color modes."""
        scm = set()
        if self._device_type == "pixoo":
            scm.add(ColorMode.BRIGHTNESS)
            scm.add(ColorMode.RGB)
            scm.add(ColorMode.ONOFF)
        
        return scm

    @property
    def supported_features(self) -> int:
        return LightEntityFeature.EFFECT

    async def async_score_changed(self, event: Event):
        _LOGGER.debug(pformat(event))

    async def async_turn_on(self, **kwargs: Any) -> None:
        if ATTR_BRIGHTNESS in kwargs:
            await self.hass.async_add_executor_job(self._divoomWifiDevice.set_brightness, int(kwargs.get(ATTR_BRIGHTNESS, 255) / 255 * 100))
        else:
            await self.hass.async_add_executor_job(self._divoomWifiDevice.set_brightness, self._attr_brightness)

        if ATTR_RGB_COLOR in kwargs:
            await self.hass.async_add_executor_job(self._divoomWifiDevice.fill, kwargs.get(ATTR_RGB_COLOR, (255, 255, 255)))
            await self.hass.async_add_executor_job(self._divoomWifiDevice.push)
        
        if ATTR_EFFECT in kwargs:
            await self.hass.async_add_executor_job(self._divoomWifiDevice.set_channel, Channel[kwargs.get(ATTR_EFFECT, "CUSTOM")])

        await self.hass.async_add_executor_job(self._divoomWifiDevice.turn_on)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.hass.async_add_executor_job(self._divoomWifiDevice.turn_off)

    async def async_device_update(self, warning: bool = True) -> None:
        await self.hass.async_add_executor_job(self._divoomWifiDevice.update_config)
        self._attr_is_on = bool(self._divoomWifiDevice.device_config["LightSwitch"])
        self._attr_brightness = int(self._divoomWifiDevice.device_config["Brightness"] * 2.55)
#        self._attr_rgb_color = self._divoomWifiDevice.color

    async def async_show_image(self, image_path: str) -> None:
        await self.hass.async_add_executor_job(show_image, self._divoomWifiDevice, image_path)
        