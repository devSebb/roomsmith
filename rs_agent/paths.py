"""Where the plugin keeps its data.

Resolution order:
1. ``ROOMSMITH_DATA_DIR`` environment variable (tests, isolated runs)
2. Hermes's public ``plugins.plugin_storage.plugin_data_dir("roomsmith")``
   -> ``<hermes home>/plugin-data/roomsmith/`` (follows the active profile)
3. ``$HERMES_HOME/plugin-data/roomsmith`` or ``~/.hermes/plugin-data/roomsmith``

Imports of Hermes are lazy so this module also works outside Hermes.
"""

from __future__ import annotations

import os
from pathlib import Path

PLUGIN_NAME = "roomsmith"
DB_FILENAME = "data.db"


def data_dir() -> Path:
    override = os.environ.get("ROOMSMITH_DATA_DIR")
    if override:
        p = Path(override).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        return p
    try:
        from plugins.plugin_storage import plugin_data_dir  # Hermes public API

        return Path(plugin_data_dir(PLUGIN_NAME))
    except Exception:
        home = os.environ.get("HERMES_HOME")
        base = Path(home).expanduser() if home else Path.home() / ".hermes"
        p = base / "plugin-data" / PLUGIN_NAME
        p.mkdir(parents=True, exist_ok=True)
        return p


def db_path() -> Path:
    return data_dir() / DB_FILENAME
