import profile
import voluptuous as vol
from typing import Any, Final, Tuple
#import bluetooth
import logging

from homeassistant import config_entries
from homeassistant.const import CONF_MAC, CONF_IP_ADDRESS, CONF_DEVICE_ID, CONF_NAME
from homeassistant.data_entry_flow import AbortFlow, FlowResult
import homeassistant.config_validation as cv

from .pixoo import discover_wifi_devices

from pprint import pformat

from .const import CONF_DEVICE_TYPE, DOMAIN

_LOGGER = logging.getLogger(__name__)

def format_unique_id(address: str) -> str:
    """Format the unique ID."""
    return address.replace(":", "").lower()
    

def discover_devices() -> dict[str, Any]:
    """Discover Wifi devices."""
    try:
#        _LOGGER.debug("Discovering devices on device_id: %d", device_id)
        result = discover_wifi_devices()
    except OSError as ex:
        # OSError is generally thrown if a bluetooth device isn't found
        _LOGGER.error("Couldn't discover wifi devices: %s", ex)
        return []
        
    if result["ReturnCode"] != 0:
        _LOGGER.error("Couldn't discover wifi devices")
        return []

    _LOGGER.debug("Wifi devices discovered = %d", len(result["DeviceList"]))
    return result["DeviceList"]  # type: ignore[no-any-return]

@config_entries.HANDLERS.register(DOMAIN)
class DivoomWifiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Divoom Wifi config flow."""
    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        _LOGGER.debug("init DivoomWifiConfigFlow")
        self._device_id = None
        self._wifi_devices: list(dict[str, Any]) = None

#    async def async_step_device_id(
#        self, user_input: dict[str, Any] | None = None
#    ) -> FlowResult:
#        return self.async_show_form(
#            step_id="discover_devices",
#            data_schema=vol.Schema(
#                {
#                    vol.Required(CONF_DEVICE_ID): vol.All(
#                        vol.Coerce(int), vol.Range(min=-1)
#                    ),
#                }
#            ),
#        )


    async def async_step_user(
        self, user_input: dict[str, Any] = None
    ) -> FlowResult:
      
        if user_input is not None:
#            device_id = user_input[CONF_DEVICE_ID]
            return self.async_create_entry(
                 title=user_input[CONF_NAME],
                 data={
                     **user_input,
                     CONF_DEVICE_TYPE: "pixoo",
                 },
             )
#            _LOGGER.debug(pformat(user_input))
#            _LOGGER.debug("device id: {}".format(device_id))

        else:
            self._wifi_devices = await self.hass.async_add_executor_job(discover_devices)
            device_list = self._wifi_devices["DeviceList"]

            if device_list == []:
                _LOGGER.debug("no_devices_found")
                device_name = ""
                device_ip = ""
                device_mac = ""
                device_id = ""
            else:
                device_name = device_list[0]["DeviceName"]
                device_ip = device_list[0]["DevicePrivateIP"]
                device_mac = device_list[0]["DeviceMac"]
                device_id = device_list[0]["DeviceId"]

            DEVICE_SCHEMA = vol.Schema(
              {vol.Optional(CONF_NAME, default=device_name): cv.string,
               vol.Required(CONF_IP_ADDRESS, default=device_ip): cv.string,
               vol.Required(CONF_MAC, default=device_mac): cv.string,
               vol.Optional(CONF_DEVICE_ID, default=device_id): cv.int
              }
            )

        return self.async_show_form(
            step_id="user",
            data_schema=DEVICE_SCHEMA
        )

#     async def async_step_user(
#             self, user_input: dict[str, Any] = None
#         ) -> FlowResult:
#             """Handle the user step to connect to device."""

#             _LOGGER.debug(pformat(user_input))

# #            return await self.async_step_device_id()
            
# #            if CONF_DEVICE_ID in user_input:
# #                self._device_id = user_input[CONF_DEVICE_ID]

# #            if not self._bt_device:
# #                return await self.async_step_discover_devices()

#             if CONF_IP_ADDRESS in user_input:
#                 self._bt_device = user_input[CONF_IP_ADDRESS]
            
#             return self.async_create_entry(
#                 title=name,
#                 data={
#                     **user_input,
#                     CONF_MAC: self._discovery_info.address,
#                     CONF_DEVICE_TYPE: "pixoo",
#                 },
#             )


#    async def async_step_confirm(
#        self, user_input: dict[str, Any] | None = None
#    ) -> FlowResult:
#        """Confirm a single device."""
#        _LOGGER.debug(pformat(user_input))
#
#        assert user_input[CONF_MAC] is not None
#        if user_input is not None:
#            return await self._async_create_entry_from_discovery(user_input)
#
#    async def _async_create_entry_from_discovery(
#        self, user_input: dict[str, Any]
#    ) -> FlowResult:
#        """Create an entry from a discovery."""
#        assert self._wifi_devices is not None
#        mac = user_input[CONF_MAC]
#        name = [x for x in self._wifi_devices if x[0] == mac][0][1]
#        assert name is not None
#
#        _LOGGER.debug("creating entry for: {} mac: {}".format(name, mac))
#        return self.async_create_entry(
#            title=name,
#            data={
#                **user_input,
#                CONF_MAC: mac,
#                CONF_DEVICE_TYPE: "pixoo",
#            },
#        )