# SPDX-License-Identifier: GPL-3.0-or-later
"""Serve the bundled dashboard card and register it as a Lovelace resource."""
import logging
import os

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CARD_FILENAME = "entity-controller-card.js"
CARD_URL = f"/{DOMAIN}_frontend/{CARD_FILENAME}"
WWW_DIR = os.path.join(os.path.dirname(__file__), "www")


def card_resource_url(version):
    """The resource URL including a cache-busting version query."""
    return f"{CARD_URL}?v={version}"


async def async_setup_frontend(hass, version):
    """Serve www/ and make sure the card is in the dashboard resources.

    The static path is registered right away. The Lovelace resource list is
    only available once the ``lovelace`` integration has loaded, so that part
    runs after HA has started. Both steps are best effort: if anything is
    missing the card can still be added by hand as a dashboard resource, and
    the log says so.
    """
    await _async_register_static_path(hass)

    async def _on_started(_event):
        await async_register_resource(hass, version)

    if hass.is_running:
        await async_register_resource(hass, version)
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _on_started)


async def _async_register_static_path(hass):
    path = os.path.join(WWW_DIR, CARD_FILENAME)
    try:
        # HA >= 2024.6
        from homeassistant.components.http import StaticPathConfig
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, path, cache_headers=False)]
        )
    except ImportError:
        # older HA
        hass.http.register_static_path(CARD_URL, path, cache_headers=False)
    _LOGGER.debug("frontend :: serving %s at %s", path, CARD_URL)


def _lovelace_resources(hass):
    """Return the Lovelace resource collection, or None when not available."""
    lovelace = hass.data.get("lovelace")
    if lovelace is None:
        return None
    if isinstance(lovelace, dict):  # HA < 2024.x kept a plain dict
        return lovelace.get("resources")
    return getattr(lovelace, "resources", None)


async def async_register_resource(hass, version):
    """Add (or re-version) the card in the storage-mode resource list.

    Returns "created", "updated", "unchanged" or "skipped".
    """
    url = card_resource_url(version)
    resources = _lovelace_resources(hass)
    if resources is None or not hasattr(resources, "async_create_item"):
        _LOGGER.warning(
            "frontend :: dashboard resources are not managed by HA (YAML mode or lovelace not loaded); "
            "add %s as a JavaScript module resource by hand", url
        )
        return "skipped"
    try:
        if hasattr(resources, "loaded") and not resources.loaded:
            await resources.async_load()
        for item in resources.async_items():
            if str(item.get("url", "")).split("?")[0] == CARD_URL:
                if item["url"] == url:
                    return "unchanged"
                await resources.async_update_item(item["id"], {"res_type": "module", "url": url})
                _LOGGER.info("frontend :: dashboard resource updated to %s", url)
                return "updated"
        await resources.async_create_item({"res_type": "module", "url": url})
        _LOGGER.info("frontend :: dashboard resource %s registered", url)
        return "created"
    except Exception:  # noqa: BLE001 - never let the dashboard side break the integration
        _LOGGER.exception(
            "frontend :: could not register the dashboard resource; add %s as a JavaScript module resource by hand",
            url,
        )
        return "skipped"
