"""Adds config flow for Blueprint."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.const import CONF_DEVICE_ID, CONF_MODEL
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig

from .const import DOMAIN, LOGGER

from pytboss import grills


class BlueprintFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Blueprint."""

    VERSION = 1

    _discovered_name: str | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> config_entries.FlowResult:
        """Handle the Bluetooth discovery step."""
        # TODO: Consider checking for the GATT services.
        LOGGER.info(
            "Found PitBoss smoker: %s @ %s", discovery_info.name, discovery_info.address
        )
        self._discovered_name = discovery_info.name
        await self.async_set_unique_id(self._discovered_name.lower())
        self._abort_if_unique_id_configured()
        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Prompts the user to select their grill model."""
        errors = {}

        if user_input is not None:
            return self.async_create_entry(
                title=self._discovered_name,
                data={
                    **user_input,
                    CONF_DEVICE_ID: self._discovered_name,
                },
            )

        # TODO: Allow the user to input the Grill device id
        if not self._discovered_name:
            errors["base"] = "not_found"

        control_board = (self._discovered_name or "").split("-")[0]
        models = [g.name for g in grills.get_grills(control_board=control_board)]
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_MODEL): vol.In(models)}),
            description_placeholders={"name": self._discovered_name},
            errors=errors,
        )
