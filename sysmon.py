# -*- coding: utf-8 -*-
"""DraveGuard - systeemwacht (geheugen, processen, stuurprogramma's).

Eerlijke uitgangspunten:
  * Wij "boosten" geen RAM. Ongebruikt geheugen is cache, geen verspilling.
    Wat we WEL doen: laten zien wat je geheugen opvreet, waarschuwen als een
    proces wegloopt (geheugenlek), en jou zelf laten afsluiten wat je niet wil.
  * Wij installeren GEEN drivers. Dat is een beruchte manier om een pc te slopen.
    Wij inventariseren, markeren wat oud of stuk is, en wijzen naar de officiele bron.

Alles read-only behalve het afsluiten van een proces - en dat vraagt bevestiging
in de interface. Kritieke Windows-processen worden geweigerd.
"""
from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field

NO_WIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)

try:
    import psutil
    HAVE_PSUTIL = True
except Exception:
    HAVE_PSUTIL = False


# ---------------------------------------------------------------- geheugen / cpu

@dataclass
class MemStats:
    total: int = 0
    used: int = 0
    available: int = 0
    percent: float = 0.0
    swap_percent: float = 0.0


def mem_stats() -> MemStats:
    if not HAVE_PSUTIL:
        return MemStats()
    vm = psutil.virtual_memory()
    try:
        sw = psutil.swap_memory().percent
    except Exception:
        sw = 0.0
    return MemStats(vm.total, vm.total - vm.available, vm.available, vm.percent, sw)


def cpu_percent() -> float:
    if not HAVE_PSUTIL:
        return 0.0
    return psutil.cpu_percent(interval=None)


def disk_percent(path: str = "C:\\") -> float:
    if not HAVE_PSUTIL:
        return 0.0
    try:
        return psutil.disk_usage(path).percent
    except Exception:
        return 0.0


# ---------------------------------------------------------------- processen

# Deze raken we NOOIT aan - Windows valt om als je ze afsluit.
PROTECTED = {
    "system", "system idle process", "registry", "smss.exe", "csrss.exe",
    "wininit.exe", "winlogon.exe", "services.exe", "lsass.exe", "lsaiso.exe",
    "svchost.exe", "fontdrvhost.exe", "dwm.exe", "memory compression",
    "sihost.exe", "ctfmon.exe", "explorer.exe", "msmpeng.exe",
}


UNKNOWN = "(systeemproces - naam afgeschermd)"


@dataclass
class Proc:
    pid: int
    name: str
    mem: int = 0            # bytes (RSS)
    mem_pct: float = 0.0
    cpu: float = 0.0
    user: str = ""
    unknown: bool = False   # naam niet uitleesbaar (Windows schermt 'm af)

    @property
    def protected(self) -> bool:
        # Kennen we de naam niet, dan raken we 'm NIET aan. Onbekend = beschermd.
        if self.unknown:
            return True
        return self.name.lower() in PROTECTED


def _proc_name(p) -> tuple:
    """Probeer een bruikbare naam te vinden. Geeft (naam, onbekend?) terug."""
    try:
        n = p.info.get("name")
        if n:
            return n, False
    except Exception:
        pass
    # tweede kans: rechtstreeks opvragen
    try:
        n = p.name()
        if n:
            return n, False
    except Exception:
        pass
    # derde kans: het uitvoerbare bestand
    try:
        exe = p.exe()
        if exe:
            return os.path.basename(exe), False
    except Exception:
        pass
    return UNKNOWN, True


def top_processes(n: int = 20):
    """Grootste geheugenvreters, gesorteerd."""
    if not HAVE_PSUTIL:
        return []
    out = []
    for p in psutil.process_iter(["pid", "name", "memory_info", "memory_percent",
                                  "cpu_percent", "username"]):
        try:
            i = p.info
            mi = i.get("memory_info")
            if not mi:
                continue
            naam, onbekend = _proc_name(p)
            out.append(Proc(
                pid=i["pid"],
                name=naam,
                mem=mi.rss,
                mem_pct=i.get("memory_percent") or 0.0,
                cpu=i.get("cpu_percent") or 0.0,
                user=(i.get("username") or "").split("\\")[-1],
                unknown=onbekend,
            ))
        except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
            continue
    out.sort(key=lambda x: x.mem, reverse=True)
    return out[:n]


def kill_process(pid: int):
    """Sluit een proces netjes af (terminate, daarna kill). Weigert kritieke processen."""
    if not HAVE_PSUTIL:
        return False, "psutil ontbreekt"
    try:
        p = psutil.Process(pid)
        naam = (p.name() or "").lower()
        if naam in PROTECTED:
            return False, "geweigerd: '%s' is een kritiek Windows-proces" % naam
        p.terminate()
        try:
            p.wait(timeout=4)
        except psutil.TimeoutExpired:
            p.kill()
        return True, "afgesloten"
    except psutil.NoSuchProcess:
        return True, "was al gestopt"
    except psutil.AccessDenied:
        return False, "geen rechten (start DraveGuard als administrator)"
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------- lek-detectie

@dataclass
class MemoryWatch:
    """Volgt geheugengebruik per proces over de tijd en herkent weglopers.

    Een 'leak' is hier: een proces dat over meerdere metingen structureel groeit
    en boven een drempel uitkomt. Geen magie - gewoon een trendlijn.
    """
    interval_s: int = 60
    min_mb: int = 300            # onder deze grens boeit het niet
    grow_mb: int = 150           # zoveel moet het gegroeid zijn over het venster
    samples: int = 5             # aantal metingen in het venster
    history: dict = field(default_factory=dict)   # pid -> [(t, rss), ...]
    last_check: float = 0.0

    def sample(self):
        """Neemt een meting. Geeft lijst met (Proc, gegroeid_mb) terug voor weglopers."""
        if not HAVE_PSUTIL:
            return []
        now = time.time()
        self.last_check = now
        alerts = []
        seen = set()
        for p in top_processes(40):
            seen.add(p.pid)
            hist = self.history.setdefault(p.pid, [])
            hist.append((now, p.mem))
            if len(hist) > self.samples:
                hist.pop(0)
            if len(hist) >= self.samples:
                eerste = hist[0][1]
                groei_mb = (p.mem - eerste) / (1024 * 1024)
                if p.mem >= self.min_mb * 1024 * 1024 and groei_mb >= self.grow_mb:
                    alerts.append((p, groei_mb))
        # opgeruimde processen vergeten
        for pid in [k for k in self.history if k not in seen]:
            self.history.pop(pid, None)
        return alerts

    def reset(self):
        self.history.clear()


# ---------------------------------------------------------------- stuurprogramma's

def _ps(cmd: str, timeout=40) -> str:
    try:
        p = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=timeout, creationflags=NO_WIN)
        return p.stdout or ""
    except Exception:
        return ""


@dataclass
class Driver:
    device: str
    version: str = ""
    date: str = ""          # jjjj-mm-dd
    vendor: str = ""
    age_days: int = -1

    @property
    def old(self) -> bool:
        return self.age_days > 365 * 3        # ouder dan 3 jaar


def list_drivers():
    """Inventariseert (read-only) de gesigneerde stuurprogramma's."""
    cmd = ("Get-CimInstance Win32_PnPSignedDriver | "
           "Where-Object { $_.DeviceName -ne $null } | "
           "Select-Object DeviceName,DriverVersion,DriverDate,Manufacturer | "
           "ConvertTo-Csv -NoTypeInformation")
    raw = _ps(cmd)
    out = []
    import csv, io
    try:
        rows = list(csv.DictReader(io.StringIO(raw)))
    except Exception:
        return out
    now = time.time()
    for r in rows:
        naam = (r.get("DeviceName") or "").strip()
        if not naam:
            continue
        datum = (r.get("DriverDate") or "").strip()
        mooi, leeftijd = "", -1
        # CIM-datum: 20230512000000.000000+000  of ISO
        try:
            kern = datum.split(".")[0][:8]
            if len(kern) == 8 and kern.isdigit():
                jjjj, mm, dd = kern[:4], kern[4:6], kern[6:8]
                mooi = "%s-%s-%s" % (jjjj, mm, dd)
                t = time.mktime((int(jjjj), int(mm), int(dd), 0, 0, 0, 0, 0, -1))
                leeftijd = int((now - t) / 86400)
        except Exception:
            mooi = datum[:10]
        out.append(Driver(
            device=naam,
            version=(r.get("DriverVersion") or "").strip(),
            date=mooi,
            vendor=(r.get("Manufacturer") or "").strip(),
            age_days=leeftijd,
        ))
    # oudste bovenaan
    out.sort(key=lambda d: d.age_days, reverse=True)
    return out


def problem_devices():
    """Apparaten met een fout in Apparaatbeheer (read-only)."""
    cmd = ("Get-PnpDevice | Where-Object { $_.Status -ne 'OK' -and $_.Status -ne 'Unknown' } | "
           "Select-Object FriendlyName,Status,Class | ConvertTo-Csv -NoTypeInformation")
    raw = _ps(cmd)
    out = []
    import csv, io
    try:
        for r in csv.DictReader(io.StringIO(raw)):
            naam = (r.get("FriendlyName") or "").strip()
            if naam:
                out.append((naam, (r.get("Status") or "").strip(),
                            (r.get("Class") or "").strip()))
    except Exception:
        pass
    return out


# Officiele, veilige bronnen - DraveGuard installeert zelf NOOIT drivers.
DRIVER_SOURCES = [
    ("Windows Update (aanbevolen)", "ms-settings:windowsupdate"),
    ("NVIDIA", "https://www.nvidia.com/download/index.aspx"),
    ("AMD", "https://www.amd.com/en/support"),
    ("Intel", "https://www.intel.com/content/www/us/en/download-center/home.html"),
    ("Apparaatbeheer openen", "devmgmt.msc"),
]


# ---------------------------------------------------------------- hardware herkennen

@dataclass
class Gpu:
    name: str
    vendor: str = ""          # genormaliseerd: nvidia / amd / intel / ""
    version: str = ""
    date: str = ""


@dataclass
class Hardware:
    gpus: list = field(default_factory=list)
    cpu: str = ""
    cpu_vendor: str = ""      # intel / amd
    board: str = ""           # moederbord (fabrikant + model)
    board_vendor: str = ""
    system: str = ""          # kant-en-klare pc/laptop (fabrikant + model)
    system_vendor: str = ""


def _norm_vendor(s: str) -> str:
    low = (s or "").lower()
    if "nvidia" in low:
        return "nvidia"
    if "advanced micro" in low or low.startswith("amd") or "authenticamd" in low \
            or " ati " in low or low == "ati":
        return "amd"
    if "intel" in low or "genuineintel" in low:
        return "intel"
    for merk in ("dell", "hp", "hewlett", "lenovo", "asus", "acer", "msi",
                 "gigabyte", "asrock", "medion", "microsoft"):
        if merk in low:
            return "hp" if merk == "hewlett" else merk
    return ""


# Officiele support-pagina's per merk. Nooit automatisch downloaden - alleen openen.
VENDOR_URLS = {
    "nvidia":    ("NVIDIA - stuurprogramma's", "https://www.nvidia.com/download/index.aspx"),
    "amd":       ("AMD - support & drivers", "https://www.amd.com/en/support"),
    "intel":     ("Intel - Download Center",
                  "https://www.intel.com/content/www/us/en/download-center/home.html"),
    "dell":      ("Dell - support", "https://www.dell.com/support/home"),
    "hp":        ("HP - support", "https://support.hp.com/us-en/drivers"),
    "lenovo":    ("Lenovo - support", "https://support.lenovo.com/"),
    "asus":      ("ASUS - support", "https://www.asus.com/support/"),
    "acer":      ("Acer - support", "https://www.acer.com/us-en/support"),
    "msi":       ("MSI - support", "https://www.msi.com/support"),
    "gigabyte":  ("Gigabyte - support", "https://www.gigabyte.com/Support"),
    "asrock":    ("ASRock - support", "https://www.asrock.com/support/"),
    "medion":    ("Medion - support", "https://www.medion.com/nl/service/"),
    "microsoft": ("Microsoft Surface - support",
                  "https://support.microsoft.com/surface"),
}


def detect_hardware() -> Hardware:
    """Herkent (read-only) videokaart(en), processor, moederbord en pc-merk."""
    hw = Hardware()
    import csv, io

    # videokaart(en)
    raw = _ps("Get-CimInstance Win32_VideoController | "
              "Select-Object Name,AdapterCompatibility,DriverVersion,DriverDate | "
              "ConvertTo-Csv -NoTypeInformation")
    try:
        for r in csv.DictReader(io.StringIO(raw)):
            naam = (r.get("Name") or "").strip()
            if not naam:
                continue
            merk = (r.get("AdapterCompatibility") or "").strip()
            datum = (r.get("DriverDate") or "").strip()
            mooi = ""
            try:
                kern = datum.split(".")[0][:8]
                if len(kern) == 8 and kern.isdigit():
                    mooi = "%s-%s-%s" % (kern[:4], kern[4:6], kern[6:8])
            except Exception:
                pass
            hw.gpus.append(Gpu(naam, _norm_vendor(merk or naam),
                               (r.get("DriverVersion") or "").strip(), mooi))
    except Exception:
        pass

    # processor
    raw = _ps("Get-CimInstance Win32_Processor | Select-Object Name,Manufacturer | "
              "ConvertTo-Csv -NoTypeInformation")
    try:
        for r in csv.DictReader(io.StringIO(raw)):
            hw.cpu = (r.get("Name") or "").strip()
            hw.cpu_vendor = _norm_vendor(r.get("Manufacturer") or hw.cpu)
            break
    except Exception:
        pass

    # moederbord
    raw = _ps("Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer,Product | "
              "ConvertTo-Csv -NoTypeInformation")
    try:
        for r in csv.DictReader(io.StringIO(raw)):
            fab = (r.get("Manufacturer") or "").strip()
            prod = (r.get("Product") or "").strip()
            hw.board = (" ".join(x for x in (fab, prod) if x)).strip()
            hw.board_vendor = _norm_vendor(fab)
            break
    except Exception:
        pass

    # kant-en-klare pc / laptop
    raw = _ps("Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer,Model | "
              "ConvertTo-Csv -NoTypeInformation")
    try:
        for r in csv.DictReader(io.StringIO(raw)):
            fab = (r.get("Manufacturer") or "").strip()
            mod = (r.get("Model") or "").strip()
            hw.system = (" ".join(x for x in (fab, mod) if x)).strip()
            hw.system_vendor = _norm_vendor(fab)
            break
    except Exception:
        pass

    return hw


def relevant_sources(hw: Hardware):
    """Alleen de bronnen die bij DEZE pc horen. Windows Update altijd eerst."""
    out = [("Windows Update (aanbevolen)", "ms-settings:windowsupdate")]
    gezien = set()
    for v in ([g.vendor for g in hw.gpus] + [hw.cpu_vendor,
                                             hw.system_vendor, hw.board_vendor]):
        if v and v in VENDOR_URLS and v not in gezien:
            gezien.add(v)
            out.append(VENDOR_URLS[v])
    out.append(("Apparaatbeheer openen", "devmgmt.msc"))
    return out


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return "%.1f %s" % (n, unit)
        n /= 1024.0
    return "%.1f TB" % n
