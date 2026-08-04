"""Adds config flow for PitBoss."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_DEVICE_ID, CONF_MODEL, CONF_PASSWORD, CONF_PROTOCOL
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig
from pytboss import grills

from .const import (
    ALL_PROTOCOLS,
    CONF_ENABLE_REMOTE_START,
    DEFAULT_PROTOCOL,
    DOMAIN,
    LOGGER,
)


def _models_on_board(control_board: str) -> list[str]:
    """Model names this control board is sold under.

    A module-level function so it can be handed to the executor.
    """
    return [g.name for g in grills.get_grills(control_board=control_board)]


class PitBossFlowHandler(ConfigFlow, domain=DOMAIN):
    """Config flow for PitBoss."""

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> PitBossOptionsFlow:
        """Return the options flow handler."""
        return PitBossOptionsFlow()

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

        # Typed by hand, so normalized: real device IDs are the uppercase
        # advertised name (prefix + MAC-derived hex), and the board lookup
        # behind the next step compares names case-sensitively -- a pasted
        # " pbl-3b22cd " aborted the flow for a fully supported grill.
        self._device_id = user_input[CONF_DEVICE_ID].strip().upper()
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
        return await self._show_more_info_form("more_info")

    async def _show_more_info_form(
        self,
        step_id: str,
        model: str | vol.Undefined = vol.UNDEFINED,
        password: str | vol.Undefined = vol.UNDEFINED,
        protocol: str | vol.Undefined = DEFAULT_PROTOCOL,
    ) -> ConfigFlowResult:
        """Show the more_info form."""
        control_board = self._device_id.split("-")[0]
        # In the executor, as `async_setup_entry` already does for
        # `get_grill`: the first of these reads and parses `grills.json`,
        # which is ~180 kB. On a fresh install this is what pays that cost,
        # since there is no entry yet whose setup could have warmed the
        # cache.
        models = await self.hass.async_add_executor_job(_models_on_board, control_board)
        # Reconfigure mirrors the tolerance setup already has: an entry from
        # the board-remap era can hold a model that was never sold under the
        # advertised prefix, and `async_setup_entry` deliberately keeps those
        # working by falling back to by-name resolution. Without this, that
        # same entry hits a hard `unknown_grill` abort here (unknown prefix),
        # or a model list its own stored model is not in -- so its owner
        # could not re-save a working configuration, and the only
        # submittable choices switched the entry onto a different board's
        # parsing routines.
        if isinstance(model, str) and model not in models:
            models = [model, *models]
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

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle a password the grill no longer accepts."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the grill's current password.

        Optional and defaulting to empty, because clearing the password on the
        grill is a supported thing to do -- the firmware treats an empty one
        as no authentication at all.
        """
        reauth_entry = self._get_reauth_entry()
        if user_input is not None:
            return self.async_update_reload_and_abort(
                reauth_entry,
                data_updates={CONF_PASSWORD: user_input.get(CONF_PASSWORD, "")},
            )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Optional(CONF_PASSWORD, default=""): str}),
            description_placeholders={
                "name": reauth_entry.data.get(CONF_DEVICE_ID, "")
            },
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
        return await self._show_more_info_form("reconfigure", model, password, protocol)


class PitBossOptionsFlow(OptionsFlow):
    """Options for PitBoss.

    The first options flow in this integration, added because remote start
    needs somewhere to be turned on deliberately rather than being available
    by default. Built as one field so anything else that wants an option --
    #277's temperature unit, the polling intervals from #351 -- extends this
    rather than introducing a second flow.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ENABLE_REMOTE_START,
                        default=self.config_entry.options.get(
                            CONF_ENABLE_REMOTE_START, False
                        ),
                    ): bool,
                }
            ),
        )
