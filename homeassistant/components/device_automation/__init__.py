"""Helpers for device automations."""
import asyncio
import logging
from typing import Callable, cast

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.const import CONF_DOMAIN
from homeassistant.core import split_entity_id, HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_registry import async_entries_for_device
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration, IntegrationNotFound

DOMAIN = "device_automation"

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass, config):
    """Set up device automation."""
    hass.components.websocket_api.async_register_command(
        websocket_device_automation_list_actions
    )
    hass.components.websocket_api.async_register_command(
        websocket_device_automation_list_conditions
    )
    hass.components.websocket_api.async_register_command(
        websocket_device_automation_list_triggers
    )
    return True


async def async_device_condition_from_config(
    hass: HomeAssistant, config: ConfigType, config_validation: bool = True
) -> Callable[..., bool]:
    """Wrap action method with state based condition."""
    if config_validation:
        config = cv.DEVICE_CONDITION_SCHEMA(config)
    integration = await async_get_integration(hass, config[CONF_DOMAIN])
    platform = integration.get_platform("device_automation")
    return cast(
        Callable[..., bool],
        platform.async_condition_from_config(config, config_validation),  # type: ignore
    )


async def _async_get_device_automations_from_domain(hass, domain, fname, device_id):
    """List device automations."""
    integration = None
    try:
        integration = await async_get_integration(hass, domain)
    except IntegrationNotFound:
        _LOGGER.warning("Integration %s not found", domain)
        return None

    try:
        platform = integration.get_platform("device_automation")
    except ImportError:
        # The domain does not have device automations
        return None

    if hasattr(platform, fname):
        return await getattr(platform, fname)(hass, device_id)


async def _async_get_device_automations(hass, fname, device_id):
    """List device automations."""
    device_registry, entity_registry = await asyncio.gather(
        hass.helpers.device_registry.async_get_registry(),
        hass.helpers.entity_registry.async_get_registry(),
    )

    domains = set()
    automations = []
    device = device_registry.async_get(device_id)
    for entry_id in device.config_entries:
        config_entry = hass.config_entries.async_get_entry(entry_id)
        domains.add(config_entry.domain)

    entities = async_entries_for_device(entity_registry, device_id)
    for entity in entities:
        domains.add(split_entity_id(entity.entity_id)[0])

    device_automations = await asyncio.gather(
        *(
            _async_get_device_automations_from_domain(hass, domain, fname, device_id)
            for domain in domains
        )
    )
    for device_automation in device_automations:
        if device_automation is not None:
            automations.extend(device_automation)

    return automations


@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "device_automation/action/list",
        vol.Required("device_id"): str,
    }
)
async def websocket_device_automation_list_actions(hass, connection, msg):
    """Handle request for device actions."""
    device_id = msg["device_id"]
    actions = await _async_get_device_automations(hass, "async_get_actions", device_id)
    connection.send_result(msg["id"], actions)


@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "device_automation/condition/list",
        vol.Required("device_id"): str,
    }
)
async def websocket_device_automation_list_conditions(hass, connection, msg):
    """Handle request for device conditions."""
    device_id = msg["device_id"]
    conditions = await _async_get_device_automations(
        hass, "async_get_conditions", device_id
    )
    connection.send_result(msg["id"], conditions)


@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "device_automation/trigger/list",
        vol.Required("device_id"): str,
    }
)
async def websocket_device_automation_list_triggers(hass, connection, msg):
    """Handle request for device triggers."""
    device_id = msg["device_id"]
    triggers = await _async_get_device_automations(
        hass, "async_get_triggers", device_id
    )
    connection.send_result(msg["id"], triggers)
