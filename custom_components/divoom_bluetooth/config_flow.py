import profile
import voluptuous as vol
from typing import Any, Final, Tuple
import bluetooth
import logging

from homeassistant import config_entries
from homeassistant.const import CONF_MAC, CONF_DEVICE_ID
from homeassistant.data_entry_flow import AbortFlow, FlowResult

from pprint import pformat

from .const import CONF_DEVICE_TYPE, DOMAIN

_LOGGER = logging.getLogger(__name__)

def format_unique_id(address: str) -> str:
    """Format the unique ID."""
    return address.replace(":", "").lower()

def discover_devices(device_id: int) -> list[tuple[str, str]]:
    """Discover Bluetooth devices."""
    try:
        _LOGGER.debug("Discovering devices on device_id: %d", device_id)
        result = bluetooth.discover_devices(
            duration=10,
            lookup_names=True,
            flush_cache=True,
            lookup_class=False,
            device_id=device_id,
        )
    except OSError as ex:
        # OSError is generally thrown if a bluetooth device isn't found
        _LOGGER.error("Couldn't discover bluetooth devices: %s", ex)
        return []
    _LOGGER.debug("Bluetooth devices discovered = %d", len(result))
    return result  # type: ignore[no-any-return]

@config_entries.HANDLERS.register(DOMAIN)
class DivoomBluetoothConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Divoom Bluetooth config flow."""
    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        _LOGGER.debug("init DivoomBluetoothConfigFlow")
        self._device_id = None
        self._bt_devices: list(Tuple[str, str]) = None

    async def async_step_device_id(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return self.async_show_form(
            step_id="discover_devices",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ID): vol.All(
                        vol.Coerce(int), vol.Range(min=-1)
                    ),
                }
            ),
        )

    async def async_step_discover_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        device_id = user_input[CONF_DEVICE_ID]

        _LOGGER.debug(pformat(user_input))
        _LOGGER.debug("device id: {}".format(device_id))
        _LOGGER.debug("discovering devices")

        self._bt_devices = await self.hass.async_add_executor_job(discover_devices, device_id)

        if not self._bt_devices:
            raise AbortFlow("no_devices_found")

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MAC): vol.In(
                        {
                            mac: name
                            for mac, name in self._bt_devices
                        }
                    ),
                }
            ),
        )

    async def async_step_user(
            self, user_input: dict[str, Any] | None = None
        ) -> FlowResult:
            """Handle the user step to pick discovered device."""

            _LOGGER.debug(pformat(user_input))

            return await self.async_step_device_id()
            
            if CONF_DEVICE_ID in user_input:
                self._device_id = user_input[CONF_DEVICE_ID]

            if not self._bt_device:
                return await self.async_step_discover_devices()

            if CONF_MAC in user_input:
                self._bt_device = user_input[CONF_MAC]
            
            return self.async_create_entry(
                title=name,
                data={
                    **user_input,
                    CONF_MAC: self._discovery_info.address,
                    CONF_DEVICE_TYPE: "pixoo",
                },
            )


    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm a single device."""
        _LOGGER.debug(pformat(user_input))

        assert user_input[CONF_MAC] is not None
        if user_input is not None:
            return await self._async_create_entry_from_discovery(user_input)

    async def _async_create_entry_from_discovery(
        self, user_input: dict[str, Any]
    ) -> FlowResult:
        """Create an entry from a discovery."""
        assert self._bt_devices is not None
        mac = user_input[CONF_MAC]
        name = [x for x in self._bt_devices if x[0] == mac][0][1]
        assert name is not None

        _LOGGER.debug("creating entry for: {} mac: {}".format(name, mac))
        return self.async_create_entry(
            title=name,
            data={
                **user_input,
                CONF_MAC: mac,
                CONF_DEVICE_TYPE: "pixoo",
            },
        )