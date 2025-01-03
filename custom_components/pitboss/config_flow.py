"""Adds config flow for PitBoss."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_DEVICE_ID, CONF_MODEL
from pytboss import grills

from .const import DOMAIN, LOGGER


class BlueprintFlowHandler(ConfigFlow, domain=DOMAIN):
    """Config flow for Blueprint."""

    VERSION = 1

    _discovered_name: str = ""

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle the Bluetooth discovery step."""
        LOGGER.info(
            "Found PitBoss smoker: %s @ %s", discovery_info.name, discovery_info.address
        )
        self._discovered_name = discovery_info.name
        await self.async_set_unique_id(self._discovered_name.lower())
        self._abort_if_unique_id_configured()
        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Prompts the user to select their grill model."""
        if user_input is not None:
            self._discovered_name = user_input[CONF_DEVICE_ID]

        if not self._discovered_name:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({vol.Required(CONF_DEVICE_ID): str}),
            )

        return await self.async_step_select_model()

    async def async_step_select_model(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None and CONF_MODEL in user_input:
            return self.async_create_entry(
                title=self._discovered_name,
                data={
                    CONF_DEVICE_ID: self._discovered_name,
                    CONF_MODEL: user_input[CONF_MODEL],
                },
            )

        control_board = self._discovered_name.split("-")[0]
        models = [g.name for g in grills.get_grills(control_board=control_board)]
        if not models:
            return self.async_abort(
                reason="unknown_grill",
                description_placeholders={"control_board": control_board},
            )
        return self.async_show_form(
            step_id="select_model",
            data_schema=vol.Schema({vol.Required(CONF_MODEL): vol.In(models)}),
            description_placeholders={"name": self._discovered_name},
        )
