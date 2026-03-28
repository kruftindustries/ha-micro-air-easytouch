"""Config flow for MicroAirEasyTouch integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from bleak import BleakScanner

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow
from homeassistant.data_entry_flow import FlowResult
from homeassistant.const import CONF_ADDRESS, CONF_PASSWORD, CONF_USERNAME

from .micro_air_easytouch.parser import MicroAirEasyTouchBluetoothDeviceData
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SCAN_TIMEOUT = 10.0


class MicroAirEasyTouchConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MicroAirEasyTouch."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_device: MicroAirEasyTouchBluetoothDeviceData | None = None
        self._discovered_devices: dict[str, str] = {}

    async def _async_scan_devices(self) -> dict[str, str]:
        """Perform an active BLE scan and return {address: 'Name (address)'}."""
        devices: dict[str, str] = {}
        current_addresses = self._async_current_ids()
        try:
            discovered = await BleakScanner.discover(timeout=SCAN_TIMEOUT)
            for d in discovered:
                if d.address in current_addresses:
                    continue
                name = d.name or "Unknown"
                devices[d.address] = f"{name} ({d.address})"
        except Exception as err:
            _LOGGER.warning("BLE scan failed: %s", err)
        return devices

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle the bluetooth discovery step."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        device = MicroAirEasyTouchBluetoothDeviceData(password=None, email=None)
        if not device.supported(discovery_info):
            return self.async_abort(reason="not_supported")
        self._discovery_info = discovery_info
        self._discovered_device = device
        return await self.async_step_password()

    async def async_step_password(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle password and email entry."""
        errors = {}
        if user_input is not None:
            try:
                assert self._discovered_device is not None
                self._discovered_device._email = user_input[CONF_USERNAME]
                self._discovered_device._password = user_input[CONF_PASSWORD]
                return await self.async_step_bluetooth_confirm(user_input)
            except Exception:
                errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="password",
            data_schema=vol.Schema({
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }),
            errors=errors,
        )

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm discovery."""
        assert self._discovered_device is not None
        device = self._discovered_device
        assert self._discovery_info is not None
        discovery_info = self._discovery_info
        title = device.title or device.get_device_name() or discovery_info.name
        if user_input is not None:
            return self.async_create_entry(
                title=title,
                data={
                    CONF_USERNAME: self._discovered_device._email,
                    CONF_PASSWORD: self._discovered_device._password,
                    CONF_ADDRESS: discovery_info.address,
                }
            )

        self._set_confirm_only()
        placeholders = {"name": title}
        self.context["title_placeholders"] = placeholders
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders=placeholders
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the user step to pick discovered device or enter manually."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            device = MicroAirEasyTouchBluetoothDeviceData(password=None, email=None)
            self._discovered_device = device
            return await self.async_step_password()

        # Try HA's cached Bluetooth discoveries for EasyTouch devices
        current_addresses = self._async_current_ids()
        for discovery_info in async_discovered_service_info(self.hass, False):
            address = discovery_info.address
            if address in current_addresses or address in self._discovered_devices:
                continue
            device = MicroAirEasyTouchBluetoothDeviceData(password=None)
            if device.supported(discovery_info):
                self._discovered_devices[address] = (
                    device.title or device.get_device_name() or discovery_info.name
                )

        if self._discovered_devices:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {vol.Required(CONF_ADDRESS): vol.In(self._discovered_devices)}
                ),
            )

        # No EasyTouch devices found — fall through to manual entry with active scan
        return await self.async_step_manual()

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Active BLE scan showing all nearby devices as a dropdown."""
        errors = {}
        if user_input is not None:
            if user_input.get("rescan", False):
                return await self.async_step_manual()

            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"EasyTouch {address}",
                data={
                    CONF_ADDRESS: address,
                    CONF_USERNAME: user_input[CONF_USERNAME],
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                },
            )

        # Active BLE scan — queries the adapter directly
        all_devices = await self._async_scan_devices()

        if all_devices:
            schema = vol.Schema({
                vol.Required(CONF_ADDRESS): vol.In(all_devices),
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional("rescan", default=False): bool,
            })
        else:
            # No BLE devices found at all — free text entry
            schema = vol.Schema({
                vol.Required(CONF_ADDRESS): str,
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional("rescan", default=False): bool,
            })

        return self.async_show_form(
            step_id="manual",
            data_schema=schema,
            errors=errors,
        )
