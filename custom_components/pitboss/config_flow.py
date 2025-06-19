"""Adds config flow for PitBoss."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_DEVICE_ID, CONF_MODEL, CONF_PASSWORD, CONF_PROTOCOL
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig
from pytboss import grills

from .const import ALL_PROTOCOLS, DEFAULT_PROTOCOL, DOMAIN, LOGGER


class PitBossFlowHandler(ConfigFlow, domain=DOMAIN):
    """Config flow for PitBoss."""

    VERSION = 1
    MINOR_VERSION = 3

    _device_id: str = ""

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle the Bluetooth discovery step."""
        self._device_id = discovery_info.name
        await self.async_set_unique_id(self._device_id.lower())
        self._abort_if_unique_id_configured()
        LOGGER.info(
            "Found PitBoss smoker: %s @ %s", discovery_info.name, discovery_info.address
        )
        self.context["title_placeholders"] = {"name": self._device_id}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the Bluetooth confirm step."""
        if user_input is None:
            return self.async_show_form(
                step_id="bluetooth_confirm",
                description_placeholders={"name": self._device_id},
            )
        return await self.async_step_more_info()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user step."""
        if not user_input:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({vol.Required(CONF_DEVICE_ID): str}),
            )

        self._device_id = user_input[CONF_DEVICE_ID]
        await self.async_set_unique_id(self._device_id.lower())
        self._abort_if_unique_id_configured()
        return await self.async_step_more_info()

    async def async_step_more_info(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the more info step."""
        if user_input is not None and CONF_MODEL in user_input:
            return self.async_create_entry(
                title=self._device_id,
                data={
                    CONF_DEVICE_ID: self._device_id,
                    CONF_MODEL: user_input[CONF_MODEL],
                    CONF_PASSWORD: user_input.get(CONF_PASSWORD, ""),
                    CONF_PROTOCOL: user_input.get(CONF_PROTOCOL, DEFAULT_PROTOCOL),
                },
            )
        return self._show_more_info_form("more_info")

    def _show_more_info_form(
        self,
        step_id: str,
        model: str | vol.Undefined = vol.UNDEFINED,
        password: str | vol.Undefined = vol.UNDEFINED,
        protocol: str | vol.Undefined = DEFAULT_PROTOCOL,
    ) -> ConfigFlowResult:
        """Show the more_info form."""
        control_board = self._device_id.split("-")[0]
        models = [g.name for g in grills.get_grills(control_board=control_board)]
        if not models:
            return self.async_abort(
                reason="unknown_grill",
                description_placeholders={"control_board": control_board},
            )
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MODEL, default=model): vol.In(models),
                    vol.Optional(CONF_PASSWORD, default=password): str,
                    vol.Required(CONF_PROTOCOL, default=protocol): SelectSelector(
                        SelectSelectorConfig(
                            options=list(ALL_PROTOCOLS), translation_key="protocol"
                        )
                    ),
                }
            ),
            description_placeholders={"name": self._device_id},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the reconfigure step."""
        reconfigure_entry = self._get_reconfigure_entry()
        if user_input is not None and CONF_MODEL in user_input:
            await self.async_set_unique_id(self._device_id.lower())
            self._abort_if_unique_id_mismatch()
            return self.async_update_reload_and_abort(
                reconfigure_entry,
                data_updates={
                    CONF_MODEL: user_input[CONF_MODEL],
                    CONF_PASSWORD: user_input.get(CONF_PASSWORD, ""),
                    CONF_PROTOCOL: user_input[CONF_PROTOCOL],
                },
            )

        self._device_id = reconfigure_entry.data[CONF_DEVICE_ID]
        model = reconfigure_entry.data[CONF_MODEL]
        password = reconfigure_entry.data.get(CONF_PASSWORD, "")
        protocol = reconfigure_entry.data.get(CONF_PROTOCOL, DEFAULT_PROTOCOL)
        return self._show_more_info_form("reconfigure", model, password, protocol)
