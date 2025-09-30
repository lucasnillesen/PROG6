"""
Management of EAN to file mappings.

The mapping between EAN codes and printer files along with optional
printer serials and bed temperature thresholds is persisted in a
JSON file.
"""

import json
from typing import Dict, Any
from .constants import MAPPING_FILE

def read_mapping() -> Dict[str, Any]:
    """Read the EAN mapping file and return it as a dictionary."""
    if not MAPPING_FILE.exists():
        return {}
    try:
        return json.loads(MAPPING_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def write_mapping(mapping: Dict[str, Any]) -> None:
    """Write the EAN mapping to disk in a pretty-printed form."""
    try:
        MAPPING_FILE.write_text(
            json.dumps(mapping, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception as e:
        # In production this should be logged
        print(f"Kon EAN mapping niet schrijven: {e}")