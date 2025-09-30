"""
Configuration management for the refactored web interface.

This module abstracts the loading and saving of configuration values
persisted in a JSON file.  It merges sensible defaults with values
read from disk and handles error conditions gracefully.  When the
configuration cannot be read the defaults are written back to
disk so subsequent reads will succeed.

"""

import json
from typing import Dict, Any
from .constants import CONFIG_FILE, BED_TEMP_THRESHOLD

DEFAULT_CONFIG: Dict[str, Any] = {
    "default_min_bed_temp": 35.0,
    "dark_mode": False,
    "browser_notifications": False,
}

def load_config() -> Dict[str, Any]:
    cfg = DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        cfg.update(data)
    except Exception:
        save_config(cfg)
    return cfg

def save_config(cfg: Dict[str, Any]) -> None:
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Kon config niet schrijven: {e}")