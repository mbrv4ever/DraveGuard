# -*- coding: utf-8 -*-
"""DraveGuard - realtime wacht + geplande scans.

Twee dingen, allebei zonder extra pakketten (puur stdlib + de eigen scanmotor):

  * FolderWatch  - houdt mappen (Downloads, Temp) in de gaten door te pollen.
                   Nieuw of gewijzigd bestand -> meteen door de scanner.
                   Geen 'watchdog'-afhankelijkheid: gewoon elke X seconden kijken
                   welke bestanden nieuw zijn t.o.v. de vorige ronde.

  * Schedule     - houdt bij wanneer de volgende geplande scan moet draaien
                   (bv. elke zondag om 10:00) en of dat moment gepasseerd is.

Beide zijn 'domme' klassen: ze doen zelf geen UI en geen threads. main.py roept
ze aan vanuit een QTimer en handelt de meldingen af.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

import engine


# ---------------------------------------------------------------- realtime wacht

# Bestandstypes die we uberhaupt de moeite waard vinden om live te scannen.
WATCH_EXT = {".exe", ".dll", ".scr", ".com", ".pif", ".bat", ".cmd", ".vbs", ".vbe",
             ".js", ".jse", ".ps1", ".jar", ".hta", ".msi", ".lnk", ".wsf", ".reg",
             ".zip", ".rar", ".7z", ".iso", ".docm", ".xlsm", ".pptm", ".pdf"}

MAX_WATCH_SIZE = 200 * 1024 * 1024        # boven 200 MB niet live scannen


def watch_folders():
    """Mappen die we standaard in de gaten houden."""
    up = os.path.expanduser("~")
    kand = [
        os.path.join(up, "Downloads"),
        os.path.join(up, "Desktop"),
        os.environ.get("TEMP", ""),
    ]
    return [k for k in kand if k and os.path.isdir(k)]


@dataclass
class FolderWatch:
    """Polling-wacht. Onthoudt per bestand de mtime; nieuw/gewijzigd = scannen."""
    folders: list = field(default_factory=watch_folders)
    seen: dict = field(default_factory=dict)      # pad -> mtime
    primed: bool = False                          # eerste ronde = alleen inlezen

    def _snapshot(self):
        nu = {}
        for folder in self.folders:
            if not os.path.isdir(folder):
                continue
            try:
                for dirpath, _dirs, files in os.walk(folder):
                    # niet te diep graven in Temp - dat is een moeras
                    if dirpath.count(os.sep) - folder.count(os.sep) > 2:
                        continue
                    for fn in files:
                        ext = os.path.splitext(fn)[1].lower()
                        if ext not in WATCH_EXT:
                            continue
                        p = os.path.join(dirpath, fn)
                        try:
                            st = os.stat(p)
                        except OSError:
                            continue
                        if st.st_size > MAX_WATCH_SIZE:
                            continue
                        nu[p] = st.st_mtime
            except Exception:
                continue
        return nu

    def poll(self):
        """Geeft de lijst met NIEUWE of GEWIJZIGDE bestanden sinds de vorige ronde."""
        nu = self._snapshot()
        if not self.primed:
            # eerste keer: alleen onthouden wat er al stond (niet alles alarmeren)
            self.seen = nu
            self.primed = True
            return []
        nieuw = [p for p, m in nu.items()
                 if p not in self.seen or self.seen[p] != m]
        self.seen = nu
        return nieuw

    def reset(self):
        self.seen = {}
        self.primed = False


def scan_paths(scanner: engine.Scanner, paden):
    """Scant losse bestanden; geeft alleen de echte bedreigingen terug."""
    treffers = []
    for p in paden:
        try:
            for f in scanner.scan_file(p):
                if f.is_threat:
                    treffers.append(f)
        except Exception:
            continue
    return treffers


# ---------------------------------------------------------------- geplande scan

DAGEN_NL = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag",
            "zaterdag", "zondag"]
DAGEN_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday"]


@dataclass
class Schedule:
    """Eenvoudige planner: wekelijks op dag N om uur:minuut, of dagelijks.

    Instellingen komen uit de DB (meta-tabel), zodat ze bewaard blijven:
      sched_on    "1"/"0"
      sched_mode  "week" | "dag"
      sched_day   "0".."6"   (0 = maandag)  - alleen bij week
      sched_hour  "0".."23"
      sched_min   "0".."59"
      sched_last  laatste keer gedraaid (unix-tijd)
    """
    db: object = None

    # -- lezen/schrijven
    def get(self, k, default=""):
        return self.db.get_meta(k, default) if self.db else default

    def set(self, k, v):
        if self.db:
            self.db.set_meta(k, str(v))

    @property
    def on(self) -> bool:
        return self.get("sched_on", "0") == "1"

    @property
    def mode(self) -> str:
        return self.get("sched_mode", "week")

    @property
    def day(self) -> int:
        try:
            return max(0, min(6, int(self.get("sched_day", "6"))))   # zondag
        except Exception:
            return 6

    @property
    def hour(self) -> int:
        try:
            return max(0, min(23, int(self.get("sched_hour", "10"))))
        except Exception:
            return 10

    @property
    def minute(self) -> int:
        try:
            return max(0, min(59, int(self.get("sched_min", "0"))))
        except Exception:
            return 0

    @property
    def last(self) -> float:
        try:
            return float(self.get("sched_last", "0") or 0)
        except Exception:
            return 0.0

    def mark_done(self):
        self.set("sched_last", "%.0f" % time.time())

    # -- de kern
    def due(self, nu: float = None) -> bool:
        """Is het geplande moment gepasseerd en hebben we het nog niet gedraaid?"""
        if not self.on:
            return False
        nu = nu or time.time()
        t = time.localtime(nu)

        # het geplande moment van VANDAAG
        vandaag = time.mktime((t.tm_year, t.tm_mon, t.tm_mday,
                               self.hour, self.minute, 0, 0, 0, -1))

        if self.mode == "week" and t.tm_wday != self.day:
            return False
        if nu < vandaag:
            return False                       # moment nog niet aangebroken
        if self.last >= vandaag:
            return False                       # vandaag al gedaan
        return True

    def beschrijving(self, nl=True) -> str:
        if not self.on:
            return "uit" if nl else "off"
        tijd = "%02d:%02d" % (self.hour, self.minute)
        if self.mode == "dag":
            return ("elke dag om %s" % tijd) if nl else ("every day at %s" % tijd)
        dag = (DAGEN_NL if nl else DAGEN_EN)[self.day]
        return ("elke %s om %s" % (dag, tijd)) if nl else ("every %s at %s" % (dag, tijd))
