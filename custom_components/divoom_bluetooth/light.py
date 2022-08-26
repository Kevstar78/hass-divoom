"""Platform for Divoom Bluetooth Light integration"""
from __future__ import annotations

import os
import voluptuous as vol
import logging

from pprint import pformat
from typing import Any

import homeassistant.helpers.config_validation as cv
from homeassistant.components.light import (
    LightEntityFeature, PLATFORM_SCHEMA, LightEntity, ColorMode, ATTR_BRIGHTNESS, ATTR_RGB_COLOR, ATTR_EFFECT,
)
from homeassistant.const import CONF_NAME, CONF_MAC
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import device_registry as dr

from .const import ATTR_SCORE_1, ATTR_SCORE_2, DOMAIN, CONF_DEVICE_TYPE, CONF_MEDIA_DIR, CONF_MEDIA_DIR_DEFAULT
from .devices.pixoo import Pixoo

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME): cv.string,
    vol.Required(CONF_MAC): cv.string,
    vol.Required(CONF_DEVICE_TYPE): cv.string,
    vol.Required(CONF_MEDIA_DIR, default=CONF_MEDIA_DIR_DEFAULT): cv.string,
})

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Divoom Bluetooth Light based on config entry"""
    if entry is None:
        return
        
    _LOGGER.info(pformat(entry.data))

    media_dir = CONF_MEDIA_DIR_DEFAULT
    if CONF_MEDIA_DIR in entry.data:
        media_dir = entry.data[CONF_MEDIA_DIR]

    light = {
        "name": entry.title,
        "mac": entry.data[CONF_MAC],
        "device_type": entry.data[CONF_DEVICE_TYPE],
        "media_directory": media_dir
    }

    async_add_entities([DivoomBluetoothLight(light)])

def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType
) -> None:
    """Set up Divoom Bluetooth Light Platform"""
    # We only want this platform to be set up via discovery.
    if discovery_info is None:
        return
        
    _LOGGER.info(pformat(config))
    _LOGGER.info(pformat(discovery_info))

    light = {
        "name": discovery_info[CONF_NAME],
        "mac": discovery_info[CONF_MAC],
        "device_type": discovery_info[CONF_DEVICE_TYPE],
        "media_directory": discovery_info[CONF_MEDIA_DIR]
    }

    add_entities([DivoomBluetoothLight(light)])

class DivoomBluetoothLight(LightEntity):
    """Representation of Divoom Bluetooth light"""

    def __init__(self, light) -> None:
        """Initialize a Divoom Bluetooth light"""
        self._attr_name = light["name"]
        self._attr_unique_id = light["mac"]
        self._device_type = light["device_type"]
        self._media_directory = light["media_directory"]

        self._attr_effect_list = [
            "Light",
            "Clock",
            "Effect 1",
            "Effect 2",
            "Effect 3",
            "Visualization 1",
            "Visualization 2",
            "Visualization 3",
            "Design",
            "Score",
        ]

        self._attr_device_info = {
            "name": light["name"],
            "manufacturer": "divoom",
            "model": light["device_type"],
            "connections": {
                (dr.CONNECTION_BLUETOOTH, light["mac"])
            }
        }
        
        if self._device_type == "pixoo":
            self._light = Pixoo(light["mac"], logger=_LOGGER)
        else:
            raise "device_type {0} does not exist, divoom_bluetooth will not work".format(self._device_type)
        
        if not os.path.isdir(self._media_directory):
            raise "media_directory {0} does not exist (or access denied), divoom_bluetooth may not work properly".format(self._media_directory)

        self._score_1 = None
        self._score_2 = None
        
        self._light.connect()

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

    @property
    def score_1(self) -> int:
        return self._score_1

    @property
    def score_2(self) -> int:
        return self._score_2

    async def async_turn_on(self, **kwargs: Any) -> None:
        if ATTR_BRIGHTNESS in kwargs:
            self._light.set_brightness(kwargs.get(ATTR_BRIGHTNESS, 255))
        else:
            self._light.set_brightness(self._attr_brightness or 255)

        if ATTR_RGB_COLOR in kwargs:
            self._light.set_color(kwargs.get(ATTR_RGB_COLOR, (255, 255, 255)))
        
        if ATTR_EFFECT in kwargs:
            self._light.set_mode(kwargs.get(ATTR_EFFECT, "Light"))

        self._light.score_1 = self._score_1
        self._light.score_2 = self._score_2

        self._light.turn_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._light.turn_off()

    async def async_device_update(self, warning: bool = True) -> None:
        self._attr_is_on = self._light.is_on
        self._attr_brightness = int(self._light.brightness / 100 * 255)
        self._attr_rgb_color = self._light.color
        self._score_1 = self.hass.data[DOMAIN][ATTR_SCORE_1]
        self._score_2 = self.hass.data[DOMAIN][ATTR_SCORE_2]

