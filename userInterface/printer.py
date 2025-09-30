"""
Printer model for the refactored user interface.

Each printer is initially created with only the static fields persisted
across restarts (name, ip, serial, access_code, esp_ip).  All
additional fields (status, bed_temp, etc.) are initialised with
sensible defaults and updated at runtime.
"""

from dataclasses import dataclass, field
from typing import Optional
from .constants import BED_TEMP_THRESHOLD
from controller import deur_openen, deur_dicht, schuif_aansturen

@dataclass
class Printer:
    name: str
    ip: str
    serial: str
    access_code: str
    esp_ip: str
    status: str = "Onbekend"
    bed_temp: float = 0.0
    print_klaar: bool = False
    finished_cooling_down: bool = False
    vorige_status: Optional[str] = None
    heeft_geprint: bool = False
    schuif_bezig: bool = False
    schuif_vastgelopen: bool = False
    schuif_commando_verstuurd: bool = False
    mc_percent: int = 0
    mqtt_client_instance: Optional[object] = None

    def open_door(self) -> bool:
        return deur_openen(self.esp_ip)

    def close_door(self) -> bool:
        return deur_dicht(self.esp_ip)

    def activate_slide(self) -> bool:
        return schuif_aansturen(self.esp_ip)

    @property
    def serial_str(self) -> str:
        return str(self.serial)