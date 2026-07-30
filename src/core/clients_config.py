"""
clients_config.py — Multi-tenant client registry loader

Provides whitelist validation and client configuration lookup for the
multi-tenant Silhouette Brain.

Usage:
    from clients_config import is_valid_owner, get_client_config, get_view_scope

    if not is_valid_owner("alfonso"):
        raise HTTPException(403, "Unknown owner_id")
    
    allowed = get_view_scope("isabella")  # ['isabella', 'alfonso']
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional

LOG = logging.getLogger("silhouette-brain.clients")

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "clients.json"
_config_cache: Optional[dict] = None
_cache_lock = threading.Lock()


def _load_config(force_reload: bool = False) -> dict:
    """Load clients.json with simple in-memory caching."""
    global _config_cache

    if _config_cache is not None and not force_reload:
        return _config_cache

    with _cache_lock:
        if _config_cache is not None and not force_reload:
            return _config_cache

        if not _CONFIG_PATH.exists():
            LOG.error(f"clients.json not found at {_CONFIG_PATH}")
            _config_cache = {"clients": {}, "validation": {"strict_mode": True}}
            return _config_cache

        try:
            with open(_CONFIG_PATH) as f:
                _config_cache = json.load(f)
            LOG.info(f"Loaded {len(_config_cache.get('clients', {}))} clients from {_CONFIG_PATH}")
            return _config_cache
        except Exception as e:
            LOG.error(f"Failed to load clients.json: {e}")
            _config_cache = {"clients": {}, "validation": {"strict_mode": True}}
            return _config_cache


def is_valid_owner(owner_id: str) -> bool:
    """Check if owner_id is in the whitelist.

    Returns False for None, empty string, or unknown clients.
    In strict mode (default), rejects any unknown owner_id.
    """
    if not owner_id or not isinstance(owner_id, str):
        return False

    cfg = _load_config()
    clients = cfg.get("clients", {})
    validation = cfg.get("validation", {})

    if owner_id in clients:
        return True

    if validation.get("strict_mode", True) and validation.get("reject_unknown", True):
        if validation.get("log_rejections", True):
            LOG.warning(f"Rejected unknown owner_id: {owner_id}")
        return False

    return False


def get_client_config(owner_id: str) -> dict:
    """Return the full config dict for a client.

    Returns empty dict if owner_id is unknown.
    """
    if not owner_id:
        return {}
    cfg = _load_config()
    return cfg.get("clients", {}).get(owner_id, {})


def get_view_scope(owner_id: str) -> list[str]:
    """Return the list of owner_ids this client is allowed to view.

    Default: [owner_id] (only its own data).
    Extended: e.g. ['isabella', 'alfonso'] (own + others).
    System tenant 'default' can only view 'default'.
    """
    cfg = get_client_config(owner_id)
    scope = cfg.get("view_scope")
    if scope is None:
        return [owner_id]
    return scope


def get_default_owner() -> str:
    """Return the default owner_id (used for system memories)."""
    cfg = _load_config()
    return cfg.get("default_owner", "default")


def list_clients() -> list[str]:
    """Return all whitelisted owner_ids."""
    cfg = _load_config()
    return list(cfg.get("clients", {}).keys())


def is_system_owner(owner_id: str) -> bool:
    """True if owner_id is the internal system tenant."""
    cfg = get_client_config(owner_id)
    return cfg.get("is_system", False)


def reload_config() -> dict:
    """Force reload clients.json from disk. Returns the new config."""
    return _load_config(force_reload=True)


# Self-test (run with: python3 clients_config.py)
if __name__ == "__main__":
    print(f"Default owner: {get_default_owner()}")
    print(f"Whitelisted clients: {list_clients()}")
    print()
    for cid in list_clients():
        cfg = get_client_config(cid)
        print(f"  {cid}:")
        print(f"    name: {cfg.get('name')}")
        print(f"    view_scope: {get_view_scope(cid)}")
        print(f"    is_system: {is_system_owner(cid)}")
    print()
    print("Validation tests:")
    for test_id in ["alfonso", "isabella", "default", "hacker", "", None, "ALPHONSO"]:
        result = is_valid_owner(test_id)
        print(f"  is_valid_owner({test_id!r}) = {result}")
