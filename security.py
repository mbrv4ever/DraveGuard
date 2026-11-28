# -*- coding: utf-8 -*-
"""DraveGuard - beveiligingscheck (ALLEEN LEZEN).

Leest de status van Windows-beveiliging en toont autoruns/opstartitems, met advies.
Wijzigt NOOIT zelf een systeeminstelling - dat laat DraveGuard bewust aan de gebruiker.
"""
from __future__ import annotations

import os
import subprocess

NO_WIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)

OK, WARN, BAD, UNK = "ok", "warn", "bad", "onbekend"


def _ps(cmd: str, timeout=15):
    """Draait een PowerShell-commando (read-only) en geeft stdout terug."""
    try:
        p = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=timeout, creationflags=NO_WIN)
        return (p.stdout or "").strip()
    except Exception:
        return ""


def _reg(path: str, value: str, timeout=8):
    try:
        p = subprocess.run(["reg", "query", path, "/v", value],
                           capture_output=True, text=True, timeout=timeout,
                           creationflags=NO_WIN)
        return p.stdout or ""
    except Exception:
        return ""


# ---------------------------------------------------------------- checks

def check_defender():
    out = _ps("(Get-MpComputerStatus | Select-Object -ExpandProperty "
              "RealTimeProtectionEnabled)")
    if out.lower().startswith("true"):
        return OK, "Realtime-bescherming staat aan."
    if out.lower().startswith("false"):
        return BAD, "Realtime-bescherming staat UIT. Zet Windows Defender aan."
    return UNK, "Kon Defender-status niet lezen (mogelijk vervangen door andere AV)."


def check_defender_signatures():
    out = _ps("(Get-MpComputerStatus | Select-Object -ExpandProperty "
              "AntivirusSignatureAge)")
    try:
        age = int(out.split()[0])
        if age <= 3:
            return OK, "Virusdefinities zijn %d dag(en) oud." % age
        if age <= 14:
            return WARN, "Virusdefinities zijn %d dagen oud - werk ze bij." % age
        return BAD, "Virusdefinities zijn %d dagen oud - flink verouderd." % age
    except Exception:
        return UNK, "Kon de leeftijd van de definities niet lezen."


def check_firewall():
    out = _ps("(Get-NetFirewallProfile | Select-Object -ExpandProperty Enabled)")
    vals = [v.strip().lower() for v in out.splitlines() if v.strip()]
    if vals and all(v.startswith("true") for v in vals):
        return OK, "Firewall staat aan voor alle profielen."
    if vals and any(v.startswith("false") for v in vals):
        return BAD, "Firewall staat (deels) UIT."
    return UNK, "Kon firewall-status niet lezen."


def check_uac():
    out = _reg(r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System",
               "EnableLUA")
    if "0x1" in out:
        return OK, "Gebruikersaccountbeheer (UAC) staat aan."
    if "0x0" in out:
        return BAD, "UAC staat UIT - programma's kunnen ongevraagd rechten krijgen."
    return UNK, "Kon UAC-status niet lezen."


def check_smartscreen():
    out = _reg(r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer",
               "SmartScreenEnabled")
    low = out.lower()
    if "warn" in low or "requireadmin" in low or "prompt" in low or "on" in low:
        return OK, "SmartScreen is actief."
    if "off" in low:
        return WARN, "SmartScreen staat uit."
    return UNK, "Kon SmartScreen-status niet lezen."


def check_windows_update():
    out = _ps("(Get-Service -Name wuauserv).Status")
    low = out.lower()
    if "running" in low:
        return OK, "Windows Update-dienst draait."
    if "stopped" in low:
        return WARN, "Windows Update-dienst is gestopt (start soms vanzelf bij gebruik)."
    return UNK, "Kon de Update-dienst niet lezen."


def check_bitlocker():
    out = _ps("(Get-BitLockerVolume -MountPoint $env:SystemDrive)."
              "ProtectionStatus 2>$null")
    low = out.lower()
    if "on" in low or low.strip() == "1":
        return OK, "Systeemschijf is versleuteld (BitLocker aan)."
    if "off" in low or low.strip() == "0":
        return WARN, "Systeemschijf is niet versleuteld (optioneel)."
    return UNK, "BitLocker-status onbekend (niet elke Windows-editie heeft dit)."


def run_all_checks():
    """Geeft lijst van (titel, status, uitleg)."""
    return [
        ("Windows Defender (realtime)", *check_defender()),
        ("Virusdefinities", *check_defender_signatures()),
        ("Firewall", *check_firewall()),
        ("Gebruikersaccountbeheer (UAC)", *check_uac()),
        ("SmartScreen", *check_smartscreen()),
        ("Windows Update", *check_windows_update()),
        ("Schijfversleuteling (BitLocker)", *check_bitlocker()),
    ]


# ---------------------------------------------------------------- autoruns / opstart

RUN_KEYS = [
    (r"HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run", "Gebruiker"),
    (r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run", "Systeem"),
    (r"HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run", "Systeem (32-bit)"),
]


def list_autoruns():
    """Leest (read-only) de programma's die met Windows meestarten."""
    items = []
    for key, scope in RUN_KEYS:
        try:
            p = subprocess.run(["reg", "query", key], capture_output=True,
                               text=True, timeout=8, creationflags=NO_WIN)
        except Exception:
            continue
        for line in (p.stdout or "").splitlines():
            line = line.strip()
            if not line or line.startswith("HKEY") or "REG_" not in line:
                continue
            parts = line.split(None, 2)
            if len(parts) >= 3:
                naam, _typ, waarde = parts[0], parts[1], parts[2]
                items.append((scope, naam, waarde))

    # opstartmappen
    startups = [
        (os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Microsoft",
                      "Windows", "Start Menu", "Programs", "Startup"), "Opstartmap (gebruiker)"),
        (os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "Microsoft",
                      "Windows", "Start Menu", "Programs", "StartUp"), "Opstartmap (systeem)"),
    ]
    for folder, scope in startups:
        if os.path.isdir(folder):
            for fn in os.listdir(folder):
                if fn.lower() not in ("desktop.ini",):
                    items.append((scope, fn, os.path.join(folder, fn)))
    return items
