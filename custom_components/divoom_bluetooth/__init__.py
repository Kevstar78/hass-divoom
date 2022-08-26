"""The Divoom Bluetooth Component."""
from __future__ import annotations

import logging
from pprint import pformat
import voluptuous as vol

from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.const import CONF_NAME, CONF_MAC, CONF_DEVICE_ID, Platform
from homeassistant.helpers.typing import ConfigType
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr
from .const import ATTR_SCORE_1, ATTR_SCORE_2, DOMAIN, CONF_MEDIA_DIR, CONF_DEVICE_TYPE, DEFAULT_DEVICE_ID

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_NAME): cv.string,
                vol.Required(CONF_MAC): cv.string,
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
    """Set up Divoom Bluetooth from a config entry."""
    _LOGGER.info(pformat(entry.data))

    assert entry.data[CONF_MAC] is not None

    hass.data.setdefault(DOMAIN, {
        ATTR_SCORE_1: 0,
        ATTR_SCORE_2: 0,
    })

    if not entry.options:
        hass.config_entries.async_update_entry(
            entry,
            options={},
        )

    await hass.config_entries.async_forward_entry_setups(
        entry, [Platform.LIGHT, Platform.NUMBER]
    )

    return True
