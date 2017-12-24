""" This module only for common constants """
from enum import Enum


class Type(Enum):
    """ Types of DVB transponders """
    Satellite = "s"
    Terestrial = "t"
    Cable = "c"


class FLAG(Enum):
    """ Service flags """
    KEEP = 1  # Do not automatically update the services parameters.
    HIDE = 2
    PIDS = 4  # Always use the cached instead of current pids.
    LOCK = 8
    NEW = 40  # Marked as new at the last scan

    @staticmethod
    def hide_values():
        return 2, 3, 6, 7, 10, 42, 43, 46, 47


POLARIZATION = {"0": "H", "1": "V", "2": "L", "3": "R"}

PLS_MODE = {"0": "Root", "1": "Gold", "2": "Combo"}

FEC = {"0": "Auto", "1": "1/2", "2": "2/3",
       "3": "3/4", "4": "5/6", "5": "7/8",
       "6": "8/9", "7": "3/5", "8": "4/5",
       "9": "9/10", "15": None}

SYSTEM = {"0": "DVB-S", "1": "DVB-S2"}

MODULATION = {"0": "Auto", "1": "QPSK", "2": "8PSK", "3": "16APSK", "5": "32APSK"}

SERVICE_TYPE = {"-2": "Unknown", "1": "TV", "2": "Radio", "3": "Data",
                "10": "Radio", "12": "Data", "22": "TV", "25": "TV (HD)",
                "136": "Data", "139": "Data"}

CAS = {"C:2600": "BISS", "C:0b00": "Conax", "C:0b01": "Conax", "C:0b02": "Conax", "C:0baa": "Conax", "C:0602": "Irdeto",
       "C:0604": "Irdeto", "C:0606": "Irdeto", "C:0608": "Irdeto", "C:0622": "Irdeto", "C:0626": "Irdeto",
       "C:0664": "Irdeto", "C:0614": "Irdeto", "C:0692": "Irdeto", "C:1801": "Nagravision", "C:0500": "Viaccess",
       "C:0E00": "PowerVu", "C:4ae0": "DRE-Crypt", "C:4ae1": "DRE-Crypt", "C:7be1": "DRE-Crypt"}
