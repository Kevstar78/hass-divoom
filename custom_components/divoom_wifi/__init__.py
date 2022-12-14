"""The Divoom Wifi Component."""
from __future__ import annotations

import logging
import asyncio
from pprint import pformat
import voluptuous as vol

from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.const import CONF_NAME, CONF_MAC, CONF_IP_ADDRESS, CONF_DEVICE_ID, Platform
from homeassistant.config_entries import ConfigEntry
from .pixoo import Pixoo
from .const import DOMAIN, CONF_MEDIA_DIR, CONF_DEVICE_TYPE, DEFAULT_DEVICE_ID

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.LIGHT, Platform.NUMBER]

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_NAME): cv.string,
                vol.Required(CONF_MAC): cv.string,
                vol.Required(CONF_IP_ADDRESS): cv.string,
                vol.Required(CONF_DEVICE_TYPE): cv.string,
                vol.Required(CONF_MEDIA_DIR, default="pixelart"): cv.string,
                vol.Optional(CONF_DEVICE_ID, default=DEFAULT_DEVICE_ID): vol.All(
                    vol.Coerce(int), vol.Range(min=-1)
                ),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Divoom Wifi from a config entry."""
    _LOGGER.info(pformat(entry.data))

    assert entry.data[CONF_MAC] is not None
    assert entry.data[CONF_IP_ADDRESS] is not None
    assert entry.data[CONF_DEVICE_TYPE] is not None

    if not entry.options:
        hass.config_entries.async_update_entry(
            entry,
            options={},
        )

    hass.data.setdefault(DOMAIN, {
        "divoom_device": None
    })

    divoomWifiDevice = None
    if entry.data[CONF_DEVICE_TYPE] == "pixoo":
        divoomWifiDevice = await hass.async_add_executor_job(Pixoo, entry.data[CONF_IP_ADDRESS])
    else:
        raise "device_type {0} does not exist, divoom_wifi will not work".format(entry.data[CONF_DEVICE_TYPE])

    hass.data[DOMAIN]["divoom_device"] = divoomWifiDevice

    for component in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload config entry"""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in PLATFORMS
            ]
        )
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    return unload_ok

