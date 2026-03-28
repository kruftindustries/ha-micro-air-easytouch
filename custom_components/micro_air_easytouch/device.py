"""Device utilities for MicroAirEasyTouch"""

from __future__ import annotations

import logging

from bleak import BLEDevice

from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def get_ble_device(hass: HomeAssistant, address: str) -> BLEDevice | None:
    """Get a BLEDevice by address, falling back to a direct BLEDevice if HA cache misses."""
    ble_device = async_ble_device_from_address(hass, address)
    if ble_device:
        return ble_device
    _LOGGER.debug("BLE device %s not in HA cache, creating direct BLEDevice", address)
    return BLEDevice(address=address, name="EasyTouch")
