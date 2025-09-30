"""
Centralised constants for the user interface.

"""

from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent

STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

UPLOAD_FOLDER = BASE_DIR / "uploads"
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

PRINTER_FILE = STORAGE_DIR / "printers.json"
CONFIG_FILE = STORAGE_DIR / "config.json"
MAPPING_FILE = BASE_DIR / "ean_mapping.json"


try:
    from config import BED_TEMP_THRESHOLD
except Exception:
    BED_TEMP_THRESHOLD = 40.0  # default


SECRET_KEY = os.environ.get("SECRET_KEY", "replace-this-secret-key")