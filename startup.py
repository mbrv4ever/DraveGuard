# -*- coding: utf-8 -*-
"""DraveGuard - opstartitems beheren (volledig omkeerbaar).

Toont wat er met Windows meestart en laat je items UITZETTEN - maar nooit
onherstelbaar. Alles wat we uitzetten wordt eerst opgeslagen in
`cache/startup_backup.json` (registry) of verplaatst naar
`cache/startup_disabled/` (snelkoppelingen), zodat je het altijd terug kunt zetten.

Veiligheid:
  * Items die je beter kunt laten staan (antivirus, geluid, cloud-sync, drivers)
    worden gemarkeerd met een waarschuwing. DraveGuard zet ze niet stiekem uit.
  * HKLM (systeembreed) vereist administrator-rechten; dat melden we netjes.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass

try:
    import winreg
    HAVE_REG = True
except Exception:
    HAVE_REG = False

import engine   # voor CACHE-pad (portable)

BACKUP = os.path.join(engine.CACHE, "startup_backup.json")
DISABLED_DIR = os.path.join(engine.CACHE, "startup_disabled")
os.makedirs(DISABLED_DIR, exist_ok=True)


# ---------------------------------------------------------------- locaties

RUN_KEYS = [
    ("HKCU", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", "Gebruiker"),
    ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", "Systeem"),
    ("HKLM", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run",
     "Systeem (32-bit)"),
]

STARTUP_DIRS = [
    (os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Microsoft",
                  "Windows", "Start Menu", "Programs", "Startup"),
     "Opstartmap (gebruiker)"),
    (os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "Microsoft",
                  "Windows", "Start Menu", "Programs", "StartUp"),
     "Opstartmap (systeem)"),
]

_HIVES = {"HKCU": getattr(winreg, "HKEY_CURRENT_USER", None),
          "HKLM": getattr(winreg, "HKEY_LOCAL_MACHINE", None)} if HAVE_REG else {}


# Dingen die je beter kunt laten staan. Puur een waarschuwing - jij beslist.
KEEP_HINTS = [
    ("defender", "Beveiliging"), ("msmpeng", "Beveiliging"),
    ("securityhealth", "Beveiliging"), ("avast", "Beveiliging"),
    ("avg", "Beveiliging"), ("kaspersky", "Beveiliging"), ("bitdefender", "Beveiliging"),
    ("norton", "Beveiliging"), ("eset", "Beveiliging"), ("malwarebytes", "Beveiliging"),
    ("realtek", "Geluid/driver"), ("audio", "Geluid/driver"),
    ("nvidia", "Grafische driver"), ("igfx", "Grafische driver"),
    ("amd", "Grafische driver"), ("radeon", "Grafische driver"),
    ("synaptics", "Touchpad"), ("elan", "Touchpad"),
    ("onedrive", "Cloud-synchronisatie"), ("dropbox", "Cloud-synchronisatie"),
    ("google drive", "Cloud-synchronisatie"), ("nextcloud", "Cloud-synchronisatie"),
    ("bluetooth", "Bluetooth"), ("intel", "Driver"),
]


def _keep_reason(naam: str, waarde: str):
    tekst = ("%s %s" % (naam, waarde)).lower()
    for sleutel, reden in KEEP_HINTS:
        if sleutel in tekst:
            return reden
    return ""


@dataclass
class StartupItem:
    naam: str
    waarde: str                 # commando of pad
    bron: str                   # "HKCU" / "HKLM" / "HKLM32" / "map"
    scope: str                  # leesbare omschrijving
    pad: str = ""               # bij snelkoppelingen: bestandspad
    subkey: str = ""            # bij registry: de sleutel
    uit: bool = False           # staat hij nu uit (door ons)?
    keep: str = ""              # niet-lege string = waarschuwing

    @property
    def id(self) -> str:
        return "%s|%s|%s" % (self.bron, self.subkey, self.naam)


# ---------------------------------------------------------------- backup-bestand

def _load_backup() -> dict:
    try:
        with open(BACKUP, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_backup(d: dict) -> None:
    try:
        with open(BACKUP, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ---------------------------------------------------------------- lezen

def list_items():
    """Alle opstartitems: actieve én door ons uitgezette."""
    items = []
    backup = _load_backup()

    # 1. registry
    if HAVE_REG:
        for hive_naam, subkey, scope in RUN_KEYS:
            hive = _HIVES.get(hive_naam)
            if hive is None:
                continue
            bron = hive_naam + ("32" if "WOW6432" in subkey else "")
            try:
                with winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ) as k:
                    i = 0
                    while True:
                        try:
                            naam, waarde, _t = winreg.EnumValue(k, i)
                        except OSError:
                            break
                        i += 1
                        it = StartupItem(naam, str(waarde), bron, scope, subkey=subkey)
                        it.keep = _keep_reason(naam, str(waarde))
                        items.append(it)
            except FileNotFoundError:
                continue
            except PermissionError:
                continue

    # 2. opstartmappen
    for folder, scope in STARTUP_DIRS:
        if not os.path.isdir(folder):
            continue
        for fn in os.listdir(folder):
            if fn.lower() in ("desktop.ini",):
                continue
            p = os.path.join(folder, fn)
            it = StartupItem(fn, p, "map", scope, pad=p)
            it.keep = _keep_reason(fn, p)
            items.append(it)

    # 3. door ons uitgezette items er weer bij (zodat je ze terug kunt zetten)
    for _id, rec in backup.items():
        it = StartupItem(rec.get("naam", "?"), rec.get("waarde", ""),
                         rec.get("bron", ""), rec.get("scope", ""),
                         pad=rec.get("pad", ""), subkey=rec.get("subkey", ""),
                         uit=True)
        it.keep = _keep_reason(it.naam, it.waarde)
        items.append(it)

    items.sort(key=lambda x: (x.uit, x.naam.lower()))
    return items


# ---------------------------------------------------------------- uitzetten

def disable(item: StartupItem):
    """Zet een opstartitem uit. Volledig omkeerbaar."""
    backup = _load_backup()
    try:
        if item.bron == "map":
            if not os.path.isfile(item.pad):
                return False, "bestand niet gevonden"
            doel = os.path.join(DISABLED_DIR, os.path.basename(item.pad))
            if os.path.exists(doel):
                doel = os.path.join(DISABLED_DIR, "%d_%s" % (
                    int(time.time()), os.path.basename(item.pad)))
            shutil.move(item.pad, doel)
            backup[item.id] = {"naam": item.naam, "waarde": item.waarde,
                               "bron": "map", "scope": item.scope,
                               "pad": item.pad, "opslag": doel}
        else:
            if not HAVE_REG:
                return False, "registry niet beschikbaar"
            hive_naam = "HKCU" if item.bron == "HKCU" else "HKLM"
            hive = _HIVES[hive_naam]
            with winreg.OpenKey(hive, item.subkey, 0,
                                winreg.KEY_READ | winreg.KEY_WRITE) as k:
                naam, waarde, _t = item.naam, item.waarde, None
                winreg.DeleteValue(k, naam)
            backup[item.id] = {"naam": item.naam, "waarde": item.waarde,
                               "bron": item.bron, "scope": item.scope,
                               "subkey": item.subkey}
        _save_backup(backup)
        engine.log("opstart uitgezet: %s" % item.naam)
        return True, "uitgezet"
    except PermissionError:
        return False, "geen rechten - start DraveGuard als administrator"
    except FileNotFoundError:
        return False, "item bestaat niet meer"
    except Exception as e:
        return False, str(e)


def enable(item: StartupItem):
    """Zet een eerder uitgezet item weer aan."""
    backup = _load_backup()
    rec = backup.get(item.id)
    if not rec:
        return False, "geen backup gevonden"
    try:
        if rec.get("bron") == "map":
            opslag = rec.get("opslag", "")
            terug = rec.get("pad", "")
            if not os.path.isfile(opslag):
                return False, "opgeslagen bestand is weg"
            os.makedirs(os.path.dirname(terug), exist_ok=True)
            shutil.move(opslag, terug)
        else:
            if not HAVE_REG:
                return False, "registry niet beschikbaar"
            hive_naam = "HKCU" if rec.get("bron") == "HKCU" else "HKLM"
            hive = _HIVES[hive_naam]
            with winreg.OpenKey(hive, rec["subkey"], 0,
                                winreg.KEY_READ | winreg.KEY_WRITE) as k:
                winreg.SetValueEx(k, rec["naam"], 0, winreg.REG_SZ, rec["waarde"])
        backup.pop(item.id, None)
        _save_backup(backup)
        engine.log("opstart teruggezet: %s" % item.naam)
        return True, "teruggezet"
    except PermissionError:
        return False, "geen rechten - start DraveGuard als administrator"
    except Exception as e:
        return False, str(e)


def count_disabled() -> int:
    return len(_load_backup())
