# -*- coding: utf-8 -*-
"""DraveGuard - scanmotor (defensief).

Onderdelen:
  * SignatureDB   - lokale SQLite met hashes van bekende malware (abuse.ch)
  * Updater       - haalt hash-lijsten op bij MalwareBazaar (auth-key nodig, gratis)
  * YaraRules     - eigen, defensieve patroonregels (heuristische detectie)
  * Heuristics    - verdachte locaties, dubbele extensies, hoge entropie, autoruns
  * ClamAV        - optioneel: gebruikt clamscan.exe als die op de pc staat
  * Quarantine    - verdachte bestanden veilig apart zetten (en herstellen)
  * Scanner       - loopt door mappen en combineert alle checks

BELANGRIJK: deze module downloadt NOOIT malware-samples. Alleen hashes (tekst).
Alles blijft portable in de map `cache/` naast de app (regel: niets in AppData/Temp).
"""
from __future__ import annotations

import csv
import hashlib
import io
import math
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
import urllib.error
import zipfile
from dataclasses import dataclass, field

# ---------------------------------------------------------------- paden (portable)

def app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


HERE = app_dir()
CACHE = os.path.join(HERE, "cache")
QUAR_DIR = os.path.join(CACHE, "quarantaine")
DB_PATH = os.path.join(CACHE, "signatures.db")
LOG_PATH = os.path.join(CACHE, "scan.log")

for _d in (CACHE, QUAR_DIR):
    os.makedirs(_d, exist_ok=True)


def log(msg: str) -> None:
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


# ---------------------------------------------------------------- resultaat-object

SEV_INFO = 0
SEV_LOW = 1
SEV_SUS = 2      # verdacht
SEV_MAL = 3      # kwaadaardig (hash-treffer / ClamAV / YARA-hit)


@dataclass
class Finding:
    path: str
    severity: int
    detection: str              # naam van de detectie
    source: str                 # "hash" | "yara" | "heuristiek" | "clamav"
    detail: str = ""
    sha256: str = ""
    size: int = 0

    @property
    def is_threat(self) -> bool:
        return self.severity >= SEV_SUS


# ---------------------------------------------------------------- hashes

def sha256_of(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def md5_of(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def entropy_of(data: bytes) -> float:
    """Shannon-entropie (0..8). >7.2 = waarschijnlijk gepakt/versleuteld."""
    if not data:
        return 0.0
    counts = [0] * 256
    for b in data:
        counts[b] += 1
    n = len(data)
    e = 0.0
    for c in counts:
        if c:
            p = c / n
            e -= p * math.log2(p)
    return e


# ---------------------------------------------------------------- signature-database

# EICAR = het officiële, ONSCHADELIJKE testbestand van antivirus-fabrikanten.
# Geen malware; puur om te controleren of een scanner werkt.
EICAR_SHA256 = "275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f"
EICAR_MD5 = "44d88612fea8a8f36de82e1278abb02f"

# Eigen, ongevaarlijk testbestand van DraveGuard (zie make_testfile()).
DG_TEST_TEXT = b"DRAVEGUARD-TESTBESTAND-GEEN-VIRUS-ALLEEN-OM-DE-SCANNER-TE-TESTEN\n"
DG_TEST_SHA256 = hashlib.sha256(DG_TEST_TEXT).hexdigest()


class SignatureDB:
    """Lokale hash-database. Alleen tekst (hashes), nooit samples."""

    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init()
        self._seed()

    def _init(self) -> None:
        c = self._conn
        c.execute("""CREATE TABLE IF NOT EXISTS sigs (
                        sha256 TEXT PRIMARY KEY,
                        md5    TEXT,
                        name   TEXT,
                        added  TEXT )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_md5 ON sigs(md5)")
        c.execute("""CREATE TABLE IF NOT EXISTS meta (
                        k TEXT PRIMARY KEY, v TEXT )""")
        c.execute("""CREATE TABLE IF NOT EXISTS quarantine (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        orig_path TEXT, stored TEXT, sha256 TEXT,
                        detection TEXT, ts TEXT, size INTEGER )""")
        c.commit()

    def _seed(self) -> None:
        """Een paar veilige testhandtekeningen zodat de scanner meteen te testen is."""
        self.add_many([
            (EICAR_SHA256, EICAR_MD5, "EICAR-Test-File (onschadelijk)"),
            (DG_TEST_SHA256, "", "DraveGuard-Testbestand (onschadelijk)"),
        ])

    # -- schrijven
    def add_many(self, rows) -> int:
        now = time.strftime("%Y-%m-%d")
        data = [(r[0].lower(), (r[1] or "").lower(), r[2] or "?", now) for r in rows if r and r[0]]
        if not data:
            return 0
        cur = self._conn.executemany(
            "INSERT OR IGNORE INTO sigs (sha256, md5, name, added) VALUES (?,?,?,?)", data)
        self._conn.commit()
        return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

    def set_meta(self, k: str, v: str) -> None:
        self._conn.execute("INSERT OR REPLACE INTO meta (k,v) VALUES (?,?)", (k, str(v)))
        self._conn.commit()

    def get_meta(self, k: str, default: str = "") -> str:
        r = self._conn.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return r[0] if r else default

    # -- lezen
    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM sigs").fetchone()[0]

    def lookup_sha256(self, h: str):
        r = self._conn.execute("SELECT name FROM sigs WHERE sha256=?", (h.lower(),)).fetchone()
        return r[0] if r else None

    def lookup_md5(self, h: str):
        r = self._conn.execute("SELECT name FROM sigs WHERE md5=?", (h.lower(),)).fetchone()
        return r[0] if r else None

    # -- quarantaine-boekhouding
    def quar_add(self, orig, stored, sha, det, size) -> None:
        self._conn.execute(
            "INSERT INTO quarantine (orig_path,stored,sha256,detection,ts,size) VALUES (?,?,?,?,?,?)",
            (orig, stored, sha, det, time.strftime("%Y-%m-%d %H:%M"), size))
        self._conn.commit()

    def quar_list(self):
        return self._conn.execute(
            "SELECT id,orig_path,stored,sha256,detection,ts,size FROM quarantine ORDER BY id DESC"
        ).fetchall()

    def quar_del(self, qid: int) -> None:
        self._conn.execute("DELETE FROM quarantine WHERE id=?", (qid,))
        self._conn.commit()

    def quar_get(self, qid: int):
        return self._conn.execute(
            "SELECT id,orig_path,stored,sha256,detection,ts,size FROM quarantine WHERE id=?",
            (qid,)).fetchone()


# ---------------------------------------------------------------- abuse.ch updater

MB_URLS_FULL = [
    "https://mb-api.abuse.ch/v2/files/exports/{key}/full.csv",
    "https://bazaar.abuse.ch/export/csv/full/?auth-key={key}",
]
MB_URLS_RECENT = [
    "https://mb-api.abuse.ch/v2/files/exports/{key}/recent.csv",
    "https://bazaar.abuse.ch/export/csv/recent/?auth-key={key}",
]


def _fetch(url: str, key: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": "DraveGuard/1.0 (defensive scanner)",
        "Auth-Key": key,
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _rows_from_csv_bytes(raw: bytes):
    """Geeft (sha256, md5, familie) terug uit een MalwareBazaar-CSV (evt. gezipt)."""
    if raw[:2] == b"PK":                       # zip -> pak de eerste csv eruit
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            name = next((n for n in z.namelist() if n.lower().endswith(".csv")), z.namelist()[0])
            raw = z.read(name)
    text = raw.decode("utf-8", "replace")
    out = []
    for row in csv.reader(io.StringIO(text), skipinitialspace=True):
        if not row or row[0].lstrip().startswith("#"):
            continue
        if len(row) < 3:
            continue
        # kolommen: first_seen, sha256, md5, sha1, reporter, file_name, ...
        sha, md5 = row[1].strip().strip('"'), row[2].strip().strip('"')
        if len(sha) != 64:
            continue
        fam = ""
        if len(row) > 8:
            fam = row[8].strip().strip('"')
        out.append((sha, md5, fam or "Malware (MalwareBazaar)"))
    return out


def update_signatures(db: SignatureDB, auth_key: str, full: bool = False, progress=None):
    """Haalt hashes op bij MalwareBazaar. Geeft (aantal_nieuw, bericht) terug."""
    if not auth_key.strip():
        return 0, "no-key"
    urls = MB_URLS_FULL if full else MB_URLS_RECENT
    last_err = ""
    for tpl in urls:
        url = tpl.format(key=auth_key.strip())
        try:
            if progress:
                progress("download")
            raw = _fetch(url, auth_key.strip())
            rows = _rows_from_csv_bytes(raw)
            if not rows:
                last_err = "leeg antwoord"
                continue
            if progress:
                progress("opslaan")
            before = db.count()
            db.add_many(rows)
            new = db.count() - before
            db.set_meta("last_update", time.strftime("%Y-%m-%d %H:%M"))
            db.set_meta("sig_count", str(db.count()))
            log("signatures bijgewerkt: +%d (totaal %d)" % (new, db.count()))
            return new, "ok"
        except urllib.error.HTTPError as e:
            last_err = "HTTP %s" % e.code
            if e.code in (401, 403):
                return 0, "auth"          # verkeerde/ontbrekende sleutel
        except Exception as e:               # netwerk/parse
            last_err = str(e)
    log("update mislukt: %s" % last_err)
    return 0, last_err or "mislukt"


# ---------------------------------------------------------------- YARA (defensief)

# Eigen regels: herkennen ALGEMENE kenmerken van kwaadaardige bestanden.
YARA_SRC = r'''
rule DG_Script_Obfuscatie {
    meta: naam = "Verdacht versluierd script"
    strings:
        $a = "FromBase64String" nocase
        $b = "IEX" nocase
        $c = "Invoke-Expression" nocase
        $d = "-enc " nocase
        $e = "powershell -w hidden" nocase
        $f = "eval(" nocase
        $g = "ActiveXObject" nocase
    condition: 2 of them
}

rule DG_Downloader_Gedrag {
    meta: naam = "Downloader-gedrag"
    strings:
        $a = "URLDownloadToFile" nocase
        $b = "WinHttpRequest" nocase
        $c = "certutil -urlcache" nocase
        $d = "bitsadmin /transfer" nocase
        $e = "DownloadString" nocase
        $f = "WebClient" nocase
    condition: any of them
}

rule DG_Persistentie {
    meta: naam = "Nestelt zich in het systeem"
    strings:
        $a = "CurrentVersion\\Run" nocase
        $b = "schtasks /create" nocase
        $c = "reg add HKCU" nocase
        $d = "sc create" nocase
        $e = "Startup\\" nocase
    condition: 2 of them
}

rule DG_Ransomware_Aanwijzing {
    meta: naam = "Mogelijke ransomware"
    strings:
        $a = "your files have been encrypted" nocase
        $b = "bitcoin" nocase
        $c = "decrypt" nocase
        $d = "vssadmin delete shadows" nocase
        $e = "wbadmin delete catalog" nocase
        $f = "cipher /w" nocase
        $g = "READ_ME" nocase
    condition: $d or $e or (2 of ($a,$b,$c,$f,$g))
}

rule DG_Info_Stealer {
    meta: naam = "Mogelijke wachtwoord-dief"
    strings:
        $a = "Login Data" nocase
        $b = "logins.json" nocase
        $c = "key3.db" nocase
        $d = "wallet.dat" nocase
        $e = "sqlite3" nocase
        $f = "cookies.sqlite" nocase
        $g = "Local State" nocase
    condition: 3 of them
}

rule DG_Spionage_Keylog {
    meta: naam = "Spyware / keylogger-kenmerken"
    strings:
        $a = "SetWindowsHookEx" nocase
        $b = "GetAsyncKeyState" nocase
        $c = "GetForegroundWindow" nocase
        $d = "keylog" nocase
        $e = "BitBlt" nocase
        $f = "GetClipboardData" nocase
    condition: 2 of them
}

rule DG_AV_Uitschakelen {
    meta: naam = "Probeert beveiliging uit te schakelen"
    strings:
        $a = "Set-MpPreference" nocase
        $b = "DisableRealtimeMonitoring" nocase
        $c = "netsh advfirewall set" nocase
        $d = "taskkill /f /im MsMpEng" nocase
        $e = "Add-MpPreference -ExclusionPath" nocase
    condition: any of them
}
'''

MAX_YARA_SIZE = 40 * 1024 * 1024        # boven 40 MB slaan we YARA over (traag)


class YaraRules:
    def __init__(self):
        self.rules = None
        self.error = ""
        try:
            import yara                       # type: ignore
            self.rules = yara.compile(source=YARA_SRC)
        except ImportError:
            self.error = "yara-python niet geinstalleerd"
        except Exception as e:                # regelfout
            self.error = str(e)
            log("YARA-compile fout: %s" % e)

    @property
    def ok(self) -> bool:
        return self.rules is not None

    def scan(self, path: str, size: int):
        """Geeft lijst met (regelnaam, mooie_naam) terug."""
        if not self.ok or size > MAX_YARA_SIZE:
            return []
        try:
            hits = self.rules.match(filepath=path, timeout=20)
        except Exception:
            return []
        out = []
        for h in hits:
            mooi = ""
            try:
                mooi = h.meta.get("naam", "")
            except Exception:
                pass
            out.append((h.rule, mooi or h.rule))
        return out


# ---------------------------------------------------------------- ClamAV (optioneel)

def find_clamscan():
    """Zoekt clamscan.exe; geeft pad of None."""
    cand = [
        r"C:\Program Files\ClamAV\clamscan.exe",
        r"C:\Program Files (x86)\ClamAV\clamscan.exe",
        shutil.which("clamscan") or "",
    ]
    for c in cand:
        if c and os.path.isfile(c):
            return c
    return None


def clamav_scan(clamscan: str, path: str):
    """Geeft detectienaam terug of None. Draait clamscan op 1 bestand."""
    try:
        p = subprocess.run([clamscan, "--no-summary", "--stdout", path],
                           capture_output=True, text=True, timeout=90,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        return None
    if p.returncode == 1:                 # 1 = virus gevonden
        for line in (p.stdout or "").splitlines():
            if line.strip().endswith("FOUND"):
                naam = line.rsplit(":", 1)[-1].replace("FOUND", "").strip()
                return naam or "ClamAV-detectie"
        return "ClamAV-detectie"
    return None


# ---------------------------------------------------------------- heuristiek

RISKY_EXT = {".exe", ".dll", ".scr", ".com", ".pif", ".bat", ".cmd", ".vbs", ".vbe",
             ".js", ".jse", ".ps1", ".jar", ".hta", ".msi", ".lnk", ".wsf", ".reg"}
DOC_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".jpg", ".jpeg", ".png",
           ".gif", ".mp3", ".mp4", ".zip", ".rar"}
ARCHIVE_EXT = {".zip", ".rar", ".7z", ".iso", ".cab"}

TEMP_MARKERS = ("\\temp\\", "\\tmp\\", "\\appdata\\local\\temp\\",
                "\\downloads\\", "\\windows\\temp\\")


_MEI = re.compile(r"\\_mei\d+(\\|$)", re.I)


def is_uitpakmap(path: str) -> bool:
    """Tijdelijke uitpakmap van een programma (PyInstaller: Temp\\_MEI12345). Hoort bij een programma dat
    nu draait of net draaide; de echte bestanden staan elders. Geen bedreiging, en vaak nog in gebruik."""
    return bool(_MEI.search(path))


def _in_temp(path: str) -> bool:
    p = path.lower()
    return any(m in p for m in TEMP_MARKERS)


def heuristics(path: str, size: int):
    """Geeft lijst (severity, naam, uitleg) terug. Puur op naam/locatie/inhoud."""
    out = []
    low = path.lower()
    base = os.path.basename(low)
    ext = os.path.splitext(base)[1]

    # 1. dubbele extensie: factuur.pdf.exe
    stam = os.path.splitext(base)[0]
    tweede = os.path.splitext(stam)[1]
    if ext in RISKY_EXT and tweede in DOC_EXT:
        out.append((SEV_MAL, "Dubbele extensie",
                    "Bestand doet zich voor als '%s' maar is een %s." % (tweede, ext)))

    # 2. uitvoerbaar bestand op een tijdelijke plek
    if ext in RISKY_EXT and _in_temp(low):
        out.append((SEV_SUS, "Uitvoerbaar bestand op tijdelijke plek",
                    "Uitvoerbare bestanden horen zelden in Temp/Downloads thuis."))

    # 3. verborgen + systeem-attribuut op een gebruikersbestand
    try:
        attrs = os.stat(path).st_file_attributes  # type: ignore[attr-defined]
        HIDDEN, SYSTEM = 0x2, 0x4
        if (attrs & HIDDEN) and (attrs & SYSTEM) and ext in RISKY_EXT:
            out.append((SEV_SUS, "Verborgen systeembestand",
                        "Verborgen én als systeembestand gemarkeerd - typisch verstopgedrag."))
    except Exception:
        pass

    # 4. naam probeert te misleiden (unicode omkering / heel veel spaties)
    if "‮" in base:                     # right-to-left override
        out.append((SEV_MAL, "Verborgen omgekeerde bestandsnaam",
                    "Gebruikt een RTL-teken om de echte extensie te verbergen."))
    if base.count(" ") > 12:
        out.append((SEV_SUS, "Misleidende bestandsnaam",
                    "Extreem veel spaties in de naam - verbergt vaak de echte extensie."))

    # 5. hoge entropie in een uitvoerbaar bestand (gepakt/versleuteld)
    if ext in (".exe", ".dll", ".scr") and 4096 < size < 64 * 1024 * 1024:
        try:
            with open(path, "rb") as f:
                f.seek(max(0, size // 2))
                blok = f.read(65536)
            e = entropy_of(blok)
            if e > 7.4:
                out.append((SEV_LOW, "Sterk gecomprimeerd/versleuteld",
                            "Entropie %.2f - vaak een packer. Kan legitiem zijn." % e))
        except Exception:
            pass

    # 6. script in een opstartmap
    if ext in RISKY_EXT and "\\start menu\\programs\\startup" in low:
        out.append((SEV_SUS, "Item in opstartmap",
                    "Dit bestand start automatisch mee met Windows."))

    return out


# ---------------------------------------------------------------- quarantaine

QUAR_KEY = 0x5A          # simpele XOR: maakt het bestand onuitvoerbaar in quarantaine


def _xor_copy(src: str, dst: str) -> None:
    with open(src, "rb") as fi, open(dst, "wb") as fo:
        while True:
            b = fi.read(1 << 20)
            if not b:
                break
            fo.write(bytes(x ^ QUAR_KEY for x in b))


def quarantine(db: SignatureDB, path: str, detection: str):
    """Verplaatst een bestand veilig naar quarantaine (XOR = kan niet meer draaien)."""
    try:
        size = os.path.getsize(path)
        sha = sha256_of(path)
        stem = re.sub(r"[^A-Za-z0-9_.-]", "_", os.path.basename(path))[:60]
        stored = os.path.join(QUAR_DIR, "%d_%s.quar" % (int(time.time()), stem))
        _xor_copy(path, stored)
        os.remove(path)                       # origineel weg (kopie staat veilig in quarantaine)
        db.quar_add(path, stored, sha, detection, size)
        log("quarantaine: %s (%s)" % (path, detection))
        return True, stored
    except PermissionError:
        return False, "geen rechten (draai als administrator)"
    except Exception as e:
        return False, str(e)


def restore(db: SignatureDB, qid: int):
    row = db.quar_get(qid)
    if not row:
        return False, "niet gevonden"
    _id, orig, stored, _sha, _det, _ts, _size = row
    try:
        os.makedirs(os.path.dirname(orig), exist_ok=True)
        _xor_copy(stored, orig)               # XOR is zijn eigen omgekeerde
        os.remove(stored)
        db.quar_del(qid)
        log("hersteld: %s" % orig)
        return True, orig
    except Exception as e:
        return False, str(e)


def delete_quarantined(db: SignatureDB, qid: int):
    row = db.quar_get(qid)
    if not row:
        return False, "niet gevonden"
    stored = row[2]
    try:
        if os.path.isfile(stored):
            os.remove(stored)
        db.quar_del(qid)
        return True, "verwijderd"
    except Exception as e:
        return False, str(e)


def make_testfile(folder: str) -> str:
    """Schrijft een ONSCHADELIJK testbestand waarvan de hash in de database staat.
    Zo kun je controleren of de scanner echt werkt (geen echte malware!)."""
    p = os.path.join(folder, "DraveGuard-TEST.txt")
    with open(p, "wb") as f:
        f.write(DG_TEST_TEXT)
    return p


# ---------------------------------------------------------------- scanner

SKIP_DIRS = {"$recycle.bin", "system volume information", "windows\\winsxs",
             "windowsapps", "node_modules"}
MAX_FILE = 300 * 1024 * 1024          # bestanden > 300 MB: alleen hash overslaan


@dataclass
class ScanStats:
    files: int = 0
    scanned: int = 0
    threats: int = 0
    skipped: int = 0
    uitpak: int = 0          # overgeslagen tijdelijke programma-uitpakmappen (_MEI...)
    started: float = field(default_factory=time.time)

    @property
    def elapsed(self) -> float:
        return time.time() - self.started


class Scanner:
    """Combineert hash-DB, YARA, heuristiek en (optioneel) ClamAV."""

    def __init__(self, db: SignatureDB, use_yara=True, use_clam=True, use_heur=True):
        self.db = db
        self.yara = YaraRules() if use_yara else None
        self.heur = use_heur
        self.clamscan = find_clamscan() if use_clam else None
        self.cancel = False
        self.stats = ScanStats()

    # -- bestandenlijst
    def collect(self, roots, deep=True):
        out = []
        for root in roots:
            if os.path.isfile(root):
                out.append(root)
                continue
            for dirpath, dirnames, filenames in os.walk(root, topdown=True):
                low = dirpath.lower()
                if any(s in low for s in SKIP_DIRS):
                    dirnames[:] = []
                    continue
                if is_uitpakmap(low):            # tijdelijke kopie van een draaiend programma: overslaan
                    self.stats.uitpak += 1
                    dirnames[:] = []
                    continue
                for fn in filenames:
                    out.append(os.path.join(dirpath, fn))
                if not deep:
                    dirnames[:] = []
        return out

    # -- 1 bestand
    def scan_file(self, path: str):
        findings = []
        try:
            size = os.path.getsize(path)
        except Exception:
            self.stats.skipped += 1
            return findings

        ext = os.path.splitext(path)[1].lower()

        # a) hash-database (het hardste bewijs)
        if size <= MAX_FILE:
            try:
                sha = sha256_of(path)
                naam = self.db.lookup_sha256(sha)
                if not naam:
                    naam = self.db.lookup_md5(md5_of(path))
                if naam:
                    findings.append(Finding(path, SEV_MAL, naam, "hash",
                                            "Exacte match met een bekende handtekening.",
                                            sha, size))
                    self.stats.scanned += 1
                    self.stats.threats += 1
                    return findings          # zeker: verder zoeken niet nodig
            except (PermissionError, OSError):
                self.stats.skipped += 1
                return findings

        # b) YARA (patronen) - alleen voor zinnige bestandstypes
        if self.yara and self.yara.ok and (ext in RISKY_EXT or ext in ("", ".txt", ".dat")):
            for _rule, mooi in self.yara.scan(path, size):
                findings.append(Finding(path, SEV_SUS, mooi, "yara",
                                        "Patroon uit de regels van DraveGuard.", "", size))

        # c) heuristiek (naam/locatie/entropie)
        if self.heur:
            for sev, naam, uitleg in heuristics(path, size):
                findings.append(Finding(path, sev, naam, "heuristiek", uitleg, "", size))

        # d) ClamAV (als aanwezig) - alleen bij risicovolle types
        if self.clamscan and ext in RISKY_EXT and size <= 100 * 1024 * 1024:
            det = clamav_scan(self.clamscan, path)
            if det:
                findings.append(Finding(path, SEV_MAL, det, "clamav",
                                        "Gevonden door de ClamAV-motor.", "", size))

        self.stats.scanned += 1
        if any(f.is_threat for f in findings):
            self.stats.threats += 1
        return findings

    # -- hele scan
    def run(self, roots, deep=True, on_file=None, on_finding=None):
        self.cancel = False
        self.stats = ScanStats()
        files = self.collect(roots, deep=deep)
        self.stats.files = len(files)
        alles = []
        for i, p in enumerate(files):
            if self.cancel:
                break
            if on_file:
                on_file(i + 1, len(files), p)
            for f in self.scan_file(p):
                alles.append(f)
                if on_finding:
                    on_finding(f)
        return alles


# ---------------------------------------------------------------- snelscan-locaties

def quick_targets():
    """Plekken waar rommel zich het vaakst nestelt."""
    up = os.path.expanduser("~")
    kand = [
        os.path.join(up, "Downloads"),
        os.path.join(up, "Desktop"),
        os.environ.get("TEMP", ""),
        os.path.join(up, "AppData", "Local", "Temp"),
        os.path.join(up, "AppData", "Roaming", "Microsoft", "Windows",
                     "Start Menu", "Programs", "Startup"),
        r"C:\Windows\Temp",
        os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"),
                     "Microsoft", "Windows", "Start Menu", "Programs", "StartUp"),
    ]
    return [k for k in kand if k and os.path.isdir(k)]
