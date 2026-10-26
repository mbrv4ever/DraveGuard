# -*- coding: utf-8 -*-
"""DraveGuard - veilige opschoner.

Filosofie: NOOIT stilletjes verwijderen. We SCANNEN eerst, tonen wat er weg kan
met de vrij te maken ruimte, en verwijderen pas na bevestiging. Waar mogelijk gaat
alles naar de prullenbak (send2trash) zodat het terug te halen is.

Alleen veilige categorieen: tijdelijke bestanden, caches, oude logs, prullenbak,
installer-restanten. GEEN documenten, GEEN persoonlijke mappen, GEEN registry.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

try:
    from send2trash import send2trash
    HAVE_TRASH = True
except Exception:
    HAVE_TRASH = False


# ---------------------------------------------------------------- categorieen

@dataclass
class CleanCategory:
    key: str
    naam_nl: str
    naam_en: str
    paths: list                    # mappen om leeg te maken
    patterns: tuple = ()           # alleen bestanden die hierop eindigen (leeg = alles)
    recursive: bool = True
    min_age_days: int = 0          # alleen bestanden ouder dan X dagen
    enabled: bool = True
    # resultaat na scan:
    files: list = field(default_factory=list)
    bytes: int = 0


def _u(*p):
    return os.path.join(os.path.expanduser("~"), *p)


def build_categories():
    temp = os.environ.get("TEMP", _u("AppData", "Local", "Temp"))
    la = _u("AppData", "Local")
    cats = [
        CleanCategory("user_temp", "Tijdelijke bestanden (gebruiker)",
                      "User temp files", [temp, _u("AppData", "Local", "Temp")]),
        CleanCategory("win_temp", "Windows tijdelijke bestanden",
                      "Windows temp files", [r"C:\Windows\Temp"]),
        CleanCategory("prefetch", "Windows Prefetch (ouder dan 30 dagen)",
                      "Windows Prefetch (30+ days)", [r"C:\Windows\Prefetch"],
                      patterns=(".pf",), min_age_days=30),
        CleanCategory("crashdumps", "Crash-dumps",
                      "Crash dumps", [_u("AppData", "Local", "CrashDumps"),
                                      r"C:\Windows\Minidump"]),
        CleanCategory("thumbs", "Miniatuur-cache",
                      "Thumbnail cache",
                      [_u("AppData", "Local", "Microsoft", "Windows", "Explorer")],
                      patterns=("thumbcache_", "iconcache_"), recursive=False),
        CleanCategory("chrome", "Chrome cache",
                      "Chrome cache",
                      [os.path.join(la, "Google", "Chrome", "User Data", "Default", "Cache")]),
        CleanCategory("edge", "Edge cache",
                      "Edge cache",
                      [os.path.join(la, "Microsoft", "Edge", "User Data", "Default", "Cache")]),
        CleanCategory("firefox", "Firefox cache",
                      "Firefox cache",
                      [os.path.join(la, "Mozilla", "Firefox", "Profiles")],
                      patterns=("cache2",)),
        CleanCategory("nvidia", "NVIDIA shader-cache",
                      "NVIDIA shader cache",
                      [os.path.join(la, "NVIDIA", "DXCache"),
                       os.path.join(la, "D3DSCache")]),
        CleanCategory("installer", "Installer-restanten (%TEMP%\\*.tmp/.msi)",
                      "Installer leftovers", [temp], patterns=(".msi", ".tmp", ".old")),
        CleanCategory("win_update", "Windows Update-cache (oud)",
                      "Windows Update cache",
                      [r"C:\Windows\SoftwareDistribution\Download"], min_age_days=7),
        CleanCategory("logs", "Oude logbestanden (ouder dan 30 dagen)",
                      "Old log files (30+ days)",
                      [r"C:\Windows\Logs", _u("AppData", "Local", "Temp")],
                      patterns=(".log",), min_age_days=30),
    ]
    return cats


# ---------------------------------------------------------------- scannen

def _too_young(path: str, min_age_days: int) -> bool:
    if min_age_days <= 0:
        return False
    try:
        age = (time.time() - os.path.getmtime(path)) / 86400.0
        return age < min_age_days
    except Exception:
        return True


def scan_category(cat: CleanCategory, is_cancelled=None):
    """Vult cat.files en cat.bytes met wat er (veilig) weg kan."""
    cat.files = []
    cat.bytes = 0
    for base in cat.paths:
        if not base or not os.path.isdir(base):
            continue
        if cat.recursive:
            walker = os.walk(base)
        else:
            try:
                walker = [(base, [], os.listdir(base))]
            except Exception:
                continue
        for dirpath, _dirs, filenames in walker:
            if is_cancelled and is_cancelled():
                return
            for fn in filenames:
                low = fn.lower()
                if cat.patterns and not any(low.endswith(p) or low.startswith(p)
                                            for p in cat.patterns):
                    continue
                fp = os.path.join(dirpath, fn)
                if _too_young(fp, cat.min_age_days):
                    continue
                try:
                    sz = os.path.getsize(fp)
                except Exception:
                    continue
                cat.files.append(fp)
                cat.bytes += sz


def scan_all(cats, on_progress=None, is_cancelled=None):
    total = 0
    for i, c in enumerate(cats):
        if is_cancelled and is_cancelled():
            break
        if not c.enabled:
            c.files, c.bytes = [], 0
            continue
        if on_progress:
            on_progress(i + 1, len(cats), c.naam_nl)
        scan_category(c, is_cancelled)
        total += c.bytes
    return total


# ---------------------------------------------------------------- opschonen

def clean_category(cat: CleanCategory, use_trash=True, on_file=None):
    """Verwijdert de eerder gevonden bestanden. Geeft (aantal, bytes, fouten) terug."""
    done = 0
    freed = 0
    errors = 0
    for fp in cat.files:
        try:
            sz = os.path.getsize(fp)
        except Exception:
            sz = 0
        try:
            if use_trash and HAVE_TRASH:
                send2trash(fp)
            else:
                os.remove(fp)
            done += 1
            freed += sz
            if on_file:
                on_file(fp)
        except Exception:
            errors += 1
    return done, freed, errors


def prune_empty_dirs(cat: CleanCategory):
    """Ruimt lege submappen op die na het wissen zijn achtergebleven.
    Alleen voor echte tijdelijke mappen - nooit de basismap zelf verwijderen."""
    if cat.key not in ("user_temp", "win_temp", "win_update"):
        return
    for base in cat.paths:
        if not base or not os.path.isdir(base):
            continue
        base_abs = os.path.abspath(base)
        for dirpath, _dirs, _files in os.walk(base, topdown=False):
            if os.path.abspath(dirpath) == base_abs:
                continue
            try:
                if not os.listdir(dirpath):
                    os.rmdir(dirpath)
            except Exception:
                pass


def empty_recycle_bin():
    """Leegt de prullenbak (Windows). Geeft (ok, bericht)."""
    try:
        import ctypes
        SHERB_NOCONFIRMATION = 0x1
        SHERB_NOPROGRESSUI = 0x2
        SHERB_NOSOUND = 0x4
        res = ctypes.windll.shell32.SHEmptyRecycleBinW(
            None, None, SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND)
        # 0 = ok, -2147418113 = al leeg
        if res == 0 or res == -2147418113:
            return True, "prullenbak geleegd"
        return False, "code %s" % res
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------- uitgebreid zoeken

import hashlib
from dataclasses import dataclass as _dc


def _walk(roots, min_size=0, skip=("windows", "program files", "programdata",
                                   "$recycle.bin", "appdata\\local\\temp")):
    """Loopt door mappen; slaat systeemmappen over."""
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for dirpath, dirs, files in os.walk(root):
            low = dirpath.lower()
            if any(s in low for s in skip):
                dirs[:] = []
                continue
            for fn in files:
                p = os.path.join(dirpath, fn)
                try:
                    sz = os.path.getsize(p)
                except Exception:
                    continue
                if sz >= min_size:
                    yield p, sz


def user_roots():
    """Standaard: je eigen mappen. Nooit Windows of Program Files."""
    up = os.path.expanduser("~")
    kand = [os.path.join(up, m) for m in
            ("Downloads", "Documents", "Desktop", "Pictures", "Videos", "Music")]
    return [k for k in kand if os.path.isdir(k)]


def _quick_hash(path: str, chunk=65536) -> str:
    """Snelle vingerafdruk: grootte + eerste en laatste blok. Genoeg om te ziften."""
    h = hashlib.md5()
    sz = os.path.getsize(path)
    h.update(str(sz).encode())
    with open(path, "rb") as f:
        h.update(f.read(chunk))
        if sz > chunk * 2:
            f.seek(-chunk, os.SEEK_END)
            h.update(f.read(chunk))
    return h.hexdigest()


def _full_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def find_duplicates(roots=None, min_size=1024 * 1024, on_progress=None,
                    is_cancelled=None):
    """Zoekt echte dubbele bestanden (>1 MB). Geeft groepen terug: [[pad, pad, ...], ...]

    Drietrapsraket: eerst op grootte, dan snelle hash, dan volledige hash.
    Zo hoeven we maar heel weinig bestanden echt helemaal te lezen.
    """
    roots = roots or user_roots()
    op_grootte = {}
    for i, (p, sz) in enumerate(_walk(roots, min_size=min_size)):
        if is_cancelled and is_cancelled():
            return []
        if on_progress and i % 200 == 0:
            on_progress(len(op_grootte))
        op_grootte.setdefault(sz, []).append(p)

    kandidaten = [v for v in op_grootte.values() if len(v) > 1]

    op_quick = {}
    for groep in kandidaten:
        for p in groep:
            if is_cancelled and is_cancelled():
                return []
            try:
                op_quick.setdefault(_quick_hash(p), []).append(p)
            except Exception:
                continue

    groepen = []
    for groep in [v for v in op_quick.values() if len(v) > 1]:
        op_vol = {}
        for p in groep:
            if is_cancelled and is_cancelled():
                return []
            try:
                op_vol.setdefault(_full_hash(p), []).append(p)
            except Exception:
                continue
        for v in op_vol.values():
            if len(v) > 1:
                groepen.append(sorted(v))

    # grootste verspilling bovenaan
    groepen.sort(key=lambda g: os.path.getsize(g[0]) * (len(g) - 1), reverse=True)
    return groepen


def duplicate_waste(groepen) -> int:
    """Hoeveel ruimte je zou winnen door per groep één exemplaar te houden."""
    tot = 0
    for g in groepen:
        try:
            tot += os.path.getsize(g[0]) * (len(g) - 1)
        except Exception:
            pass
    return tot


def find_large_files(roots=None, top=60, min_size=25 * 1024 * 1024,
                     is_cancelled=None):
    """De grootste bestanden (standaard >25 MB).

    Zonder `roots` kijken we in je eigen gebruikersmappen. Geef je zelf een map op
    (bv. een hele schijf), dan zoeken we daar - handig als je grote spullen niet
    in Downloads/Documenten staan.
    """
    roots = roots or user_roots()
    out = []
    for p, sz in _walk(roots, min_size=min_size):
        if is_cancelled and is_cancelled():
            break
        out.append((p, sz))
    out.sort(key=lambda x: x[1], reverse=True)
    return out[:top]


INSTALLER_EXT = (".exe", ".msi", ".iso", ".zip", ".rar", ".7z")


def find_old_downloads(days=180, is_cancelled=None):
    """Installers en archieven in Downloads die al maanden ongebruikt zijn."""
    dl = os.path.join(os.path.expanduser("~"), "Downloads")
    if not os.path.isdir(dl):
        return []
    out = []
    grens = time.time() - days * 86400
    for p, sz in _walk([dl]):
        if is_cancelled and is_cancelled():
            break
        if not p.lower().endswith(INSTALLER_EXT):
            continue
        try:
            if os.path.getmtime(p) < grens:
                out.append((p, sz, int((time.time() - os.path.getmtime(p)) / 86400)))
        except Exception:
            continue
    out.sort(key=lambda x: x[1], reverse=True)
    return out


def delete_files(paden, use_trash=True):
    """Verwijdert een lijst bestanden. Geeft (aantal, bytes, fouten)."""
    done = freed = errors = 0
    for p in paden:
        try:
            sz = os.path.getsize(p)
        except Exception:
            sz = 0
        try:
            if use_trash and HAVE_TRASH:
                send2trash(p)
            else:
                os.remove(p)
            done += 1
            freed += sz
        except Exception:
            errors += 1
    return done, freed, errors


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return "%.1f %s" % (n, unit)
        n /= 1024.0
    return "%.1f TB" % n
