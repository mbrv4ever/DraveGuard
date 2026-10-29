# -*- coding: utf-8 -*-
"""DraveGuard - beveiliging & opschoner voor Windows (PyQt6).

Dravenlock-app: donker paars thema, grote fonts/knoppen (toegankelijk),
tweetalig NL/EN, portable (cache/ naast de app), donationware.

Tabs: Overzicht | Scannen | Opschonen | Beveiliging | Quarantaine | Instellingen.
Alle zware taken draaien in QThreads zodat het venster niet bevriest.
"""
from __future__ import annotations

import os
import sys
import locale
import subprocess

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer, QTime
from PyQt6.QtGui import QIcon, QFont, QColor, QAction
from PyQt6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QTabWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QListWidget, QListWidgetItem, QProgressBar,
    QCheckBox, QLineEdit, QFileDialog, QMessageBox, QFrame, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QSizePolicy,
    QSystemTrayIcon, QMenu, QGridLayout, QComboBox, QTimeEdit)

import engine
import cleaner
import security
import sysmon
import startup
import watcher
import onderhoud_ui   # onderhoud-1.1.0
import telefoon_ui   # telefoon-1.2.0 (DraveCare, pc-kant)

APP_NAME = "DraveGuard"
VERSION = "1.2.1"
DONATE = "https://paypal.me/roger076"
CONTACT = "service@dravenlock.nl"


# ---------------------------------------------------------------- taal (NL/EN)

def is_nl() -> bool:
    try:
        lang = (locale.getdefaultlocale()[0] or "").lower()
    except Exception:
        lang = ""
    if not lang:
        lang = (os.environ.get("LANG", "") or "").lower()
    return lang.startswith("nl")


NL = is_nl()

TX = {
    "title":      ("DraveGuard - Beveiliging & Opschoner", "DraveGuard - Security & Cleaner"),
    "tab_home":   ("Overzicht", "Overview"),
    "tab_scan":   ("Scannen", "Scan"),
    "tab_clean":  ("Opschonen", "Clean"),
    "tab_sec":    ("Beveiliging", "Security"),
    "tab_quar":   ("Quarantaine", "Quarantine"),
    "tab_set":    ("Instellingen", "Settings"),
    "tab_ond":    ("Onderhoud", "Maintenance"),
    "tt_ond":     ("Totaal onderhoud: adware, browser, herstelpunt, schijf en programma-updates.",
                   "Full maintenance: adware, browser, restore point, disk and program updates."),
    "totaal":     ("Totaal onderhoud", "Full maintenance"),

    "protect":    ("Beschermd", "Protected"),
    "attention":  ("Aandacht nodig", "Needs attention"),
    "sig_count":  ("Handtekeningen in database:", "Signatures in database:"),
    "last_upd":   ("Laatste update:", "Last update:"),
    "never":      ("nog nooit", "never"),
    "clam_found": ("ClamAV-motor gevonden", "ClamAV engine found"),
    "clam_none":  ("ClamAV niet gevonden (optioneel)", "ClamAV not found (optional)"),

    "quick":      ("Snelscan (rommelplekken)", "Quick scan (common spots)"),
    "full":       ("Volledige scan (kies map/schijf)", "Full scan (choose folder/drive)"),
    "choose":     ("Map kiezen...", "Choose folder..."),
    "stop":       ("Stoppen", "Stop"),
    "scanning":   ("Bezig met scannen...", "Scanning..."),
    "scan_done":  ("Scan klaar", "Scan complete"),
    "files":      ("bestanden", "files"),
    "threats":    ("bedreigingen", "threats"),
    "no_threats": ("Geen bedreigingen gevonden. Alles ziet er schoon uit!",
                   "No threats found. Everything looks clean!"),
    "quar_sel":   ("Geselecteerde in quarantaine plaatsen", "Quarantine selected"),
    "make_test":  ("Testbestand maken (veilig)", "Create test file (safe)"),

    "scan_clean": ("Rommel zoeken", "Find junk"),
    "clean_now":  ("Nu opschonen", "Clean now"),
    "empty_bin":  ("Prullenbak legen", "Empty recycle bin"),
    "freeable":   ("Vrij te maken:", "Freeable:"),
    "cleaned":    ("Opgeschoond:", "Cleaned:"),
    "confirm_clean": ("Weet je zeker dat je de gekozen categorieen wilt opschonen?",
                      "Are you sure you want to clean the selected categories?"),
    "cleaning":   ("Bezig met opschonen...", "Cleaning..."),
    "skipped_lock": ("%d overgeslagen (nu in gebruik door Windows).",
                     "%d skipped (currently in use by Windows)."),
    "trash_note": ("De bestanden staan nu in de prullenbak, dus de ruimte is nog niet "
                   "echt vrij. Wil je de prullenbak nu legen om de ruimte vrij te maken?",
                   "The files are now in the recycle bin, so the space isn't freed yet. "
                   "Empty the recycle bin now to actually free the space?"),
    "nothing_cleaned": ("Er is niets verwijderd - waarschijnlijk waren de bestanden in "
                        "gebruik. Sluit browsers/programma's en probeer opnieuw.",
                        "Nothing was removed - the files were likely in use. Close "
                        "browsers/programs and try again."),

    "sec_check":  ("Beveiliging controleren", "Check security"),
    "autoruns":   ("Opstartprogramma's", "Startup programs"),
    "advies_note": ("DraveGuard wijzigt zelf geen instellingen - dit is advies.",
                    "DraveGuard changes no settings itself - this is advice."),

    "restore":    ("Herstellen", "Restore"),
    "delete":     ("Definitief verwijderen", "Delete permanently"),
    "quar_empty": ("Quarantaine is leeg.", "Quarantine is empty."),

    "authkey":    ("MalwareBazaar auth-key (gratis via auth.abuse.ch):",
                   "MalwareBazaar auth-key (free at auth.abuse.ch):"),
    "upd_recent": ("Handtekeningen bijwerken (laatste 48u)",
                   "Update signatures (last 48h)"),
    "upd_full":   ("Volledige database ophalen (groot)", "Fetch full database (large)"),
    "use_yara":   ("YARA-patroondetectie gebruiken", "Use YARA pattern detection"),
    "use_clam":   ("ClamAV gebruiken indien aanwezig", "Use ClamAV if present"),
    "use_heur":   ("Heuristiek gebruiken", "Use heuristics"),
    "use_trash":  ("Naar prullenbak i.p.v. direct wissen", "Send to recycle bin instead of delete"),
    "donate":     ("Steun DraveGuard (doneren)", "Support DraveGuard (donate)"),
    "saved":      ("Opgeslagen.", "Saved."),
    "tip_yara":   ("YARA herkent malware aan gedragspatronen in plaats van aan een "
                   "exacte vingerafdruk. Vangt ook nieuwe varianten. Aanlaten.",
                   "YARA recognises malware by behaviour patterns instead of an exact "
                   "fingerprint. Also catches new variants. Keep this on."),
    "tip_clam":   ("Als je ClamAV op je pc hebt staan, gebruikt DraveGuard die er extra "
                   "bij. Heb je 'm niet, dan gebeurt er gewoon niets.",
                   "If ClamAV is installed, DraveGuard uses it as an extra engine. "
                   "If not, nothing happens."),
    "tip_heur":   ("Heuristiek let op verdachte kenmerken: dubbele extensies zoals "
                   "factuur.pdf.exe, programma's in tijdelijke mappen, verstopte namen.",
                   "Heuristics watch for suspicious traits: double extensions like "
                   "invoice.pdf.exe, programs in temp folders, hidden names."),
    "tip_trash":  ("Aan: verwijderde bestanden gaan naar de prullenbak en zijn terug te "
                   "halen (ruimte komt pas vrij na het legen). Uit: meteen weg, ruimte "
                   "direct vrij.",
                   "On: deleted files go to the recycle bin and can be restored (space "
                   "is freed only after emptying). Off: deleted immediately, space freed "
                   "right away."),

    # --- hover-tekst op de tabbladen
    "tt_home":    ("Overzicht: status, aantal handtekeningen en snelknoppen.",
                   "Overview: status, signature count and quick actions."),
    "tt_scan":    ("Scannen: snelscan of een map naar keuze doorzoeken op malware.",
                   "Scan: quick scan or search a folder of your choice for malware."),
    "tt_clean":   ("Opschonen: tijdelijke bestanden, caches en oude logs opruimen.",
                   "Clean: remove temp files, caches and old logs."),
    "tt_extra":   ("Uitgebreid: dubbele bestanden, grootste bestanden en oude downloads.",
                   "Extended: duplicate files, largest files and old downloads."),
    "tt_sys":     ("Systeem: live meters en de grootste geheugenvreters afsluiten.",
                   "System: live meters and closing the biggest memory users."),
    "tt_drv":     ("Stuurprogramma's: overzicht van je drivers + link naar de juiste bron.",
                   "Drivers: overview of your drivers + link to the right source."),
    "tt_sec":     ("Beveiliging: status van Defender/firewall + opstartitems beheren.",
                   "Security: Defender/firewall status + manage startup items."),
    "tt_quar":    ("Quarantaine: apart gezette bestanden herstellen of definitief wissen.",
                   "Quarantine: restore or permanently delete isolated files."),
    "tt_set":     ("Instellingen: scanmotoren, realtime wacht, geplande scan en updates.",
                   "Settings: scan engines, realtime watch, scheduled scan and updates."),

    "updating":   ("Bezig met bijwerken...", "Updating..."),
    "upd_ok":     ("Database bijgewerkt: +%d handtekeningen.", "Database updated: +%d signatures."),
    "upd_auth":   ("Auth-key ontbreekt of is ongeldig. Haal een gratis sleutel bij auth.abuse.ch.",
                   "Auth-key missing or invalid. Get a free key at auth.abuse.ch."),
    "upd_fail":   ("Bijwerken mislukt: %s", "Update failed: %s"),
    "admin_hint": ("Tip: sommige mappen vereisen dat je DraveGuard als administrator start.",
                   "Tip: some folders require running DraveGuard as administrator."),
    "info":       ("Info", "About"),

    # --- systeem / geheugen
    "tab_sys":    ("Systeem", "System"),
    "tab_drv":    ("Stuurprogramma's", "Drivers"),
    "ram":        ("Geheugen (RAM)", "Memory (RAM)"),
    "cpu":        ("Processor", "CPU"),
    "disk":       ("Schijf C:", "Disk C:"),
    "refresh":    ("Vernieuwen", "Refresh"),
    "hogs":       ("Grootste geheugenvreters", "Biggest memory users"),
    "kill":       ("Geselecteerd proces afsluiten", "Close selected process"),
    "kill_ask":   ("'%s' afsluiten? Sla eerst je werk op in dat programma.",
                   "Close '%s'? Save your work in that program first."),
    "watch_on":   ("Wacht: aan (elke minuut)", "Watch: on (every minute)"),
    "watch_off":  ("Wacht: uit", "Watch: off"),
    "leak":       ("Geheugenlek?", "Memory leak?"),
    "leak_msg":   ("'%s' groeide %.0f MB in korte tijd en gebruikt nu %s.\n"
                   "Mogelijk een geheugenlek. Sluiten en opnieuw starten helpt vaak.",
                   "'%s' grew %.0f MB in a short time and now uses %s.\n"
                   "Possibly a memory leak. Closing and restarting often helps."),
    "ram_note":   ("Let op: 'RAM opschonen' is een mythe. Ongebruikt geheugen is cache, "
                   "geen verspilling. Wat wél helpt: zien wat het opvreet en dat afsluiten.",
                   "Note: 'RAM cleaning' is a myth. Unused memory is cache, not waste. "
                   "What does help: seeing what eats it and closing that."),
    "protected":  ("Dit is een kritiek Windows-proces - dat sluit DraveGuard niet af.",
                   "This is a critical Windows process - DraveGuard will not close it."),
    "proc_unknown": ("Windows schermt de naam van dit proces af (meestal 'Memory "
                     "Compression' of 'Secure System'). Omdat DraveGuard niet kan "
                     "vaststellen wat het is, blijft het beschermd en wordt het niet "
                     "afgesloten. Dit is normaal en geen probleem.",
                     "Windows hides this process's name (usually 'Memory Compression' "
                     "or 'Secure System'). Because DraveGuard cannot verify what it is, "
                     "it stays protected and will not be closed. This is normal."),
    "proc_tip":   ("Selecteer de regel en klik 'Geselecteerd proces afsluiten' om dit "
                   "programma te stoppen. Sla eerst je werk erin op.",
                   "Select the row and click 'Close selected process' to stop this "
                   "program. Save your work in it first."),

    # --- drivers
    "drv_scan":   ("Stuurprogramma's inventariseren", "Inventory drivers"),
    "drv_note":   ("DraveGuard installeert NOOIT zelf drivers - dat is een beruchte manier "
                   "om een pc te slopen. Hij toont wat je hebt en wijst naar de officiële bron.",
                   "DraveGuard NEVER installs drivers itself - that's a notorious way to break "
                   "a PC. It shows what you have and points to the official source."),
    "drv_old":    ("Ouder dan 3 jaar", "Older than 3 years"),
    "drv_old_tip": ("Dit stuurprogramma is ouder dan 3 jaar. Dat hoeft geen probleem te "
                    "zijn — als het apparaat goed werkt, laat het gerust staan. Kijk "
                    "eventueel bij de officiële bron hieronder of er een nieuwere is.",
                    "This driver is older than 3 years. That's not necessarily a problem "
                    "— if the device works fine, leave it. Optionally check the official "
                    "source below for a newer one."),
    "drv_prob":   ("Apparaten met een probleem", "Devices with a problem"),
    "drv_none":   ("Geen problemen gevonden.", "No problems found."),
    "drv_src":    ("Officiële bronnen", "Official sources"),
    "hw_none":    ("Klik op 'Stuurprogramma's inventariseren' — dan herkent DraveGuard "
                   "je hardware en toont alleen de bronnen die bij jóuw pc horen.",
                   "Click 'Inventory drivers' — DraveGuard will detect your hardware and "
                   "show only the sources that match your PC."),
    "hw_found":   ("Herkende hardware", "Detected hardware"),
    "hw_gpu":     ("Videokaart", "Graphics card"),
    "hw_cpu":     ("Processor", "Processor"),
    "hw_board":   ("Moederbord", "Motherboard"),
    "hw_sys":     ("Systeem", "System"),

    # --- uitgebreid opschonen
    "tab_extra":  ("Uitgebreid", "Extended"),
    "extra_note": ("Zoekt in je eigen mappen (Downloads, Documenten, Bureaublad, "
                   "Afbeeldingen, Video's, Muziek). Nooit in Windows of Program Files. "
                   "Er gaat niks weg zonder jouw bevestiging.",
                   "Searches your own folders (Downloads, Documents, Desktop, Pictures, "
                   "Videos, Music). Never Windows or Program Files. Nothing is removed "
                   "without your confirmation."),
    "find_dup":   ("Dubbele bestanden zoeken", "Find duplicate files"),
    "find_big":   ("Grootste bestanden", "Largest files"),
    "find_old":   ("Oude downloads (6+ maanden)", "Old downloads (6+ months)"),
    "searching":  ("Bezig met zoeken...", "Searching..."),
    "dup_found":  ("%d groepen dubbele bestanden — %s te winnen",
                   "%d groups of duplicates — %s to reclaim"),
    "dup_keep":   ("origineel (houden)", "original (keep)"),
    "dup_copy":   ("dubbel (kan weg)", "duplicate (can go)"),
    "big_found":  ("%d grote bestanden gevonden", "%d large files found"),
    "old_found":  ("%d oude downloads gevonden", "%d old downloads found"),
    "days_old":   ("%d dagen oud", "%d days old"),
    "del_sel":    ("Geselecteerde verwijderen", "Delete selected"),
    "del_ask":    ("%d bestand(en) verwijderen?", "Delete %d file(s)?"),
    "open_folder": ("Map openen", "Open folder"),
    "extra_tip":  ("Selecteer wat je weg wilt hebben (meerdere kan met Ctrl of Shift) "
                   "en klik 'Geselecteerde verwijderen'. Er gaat niks weg zonder "
                   "bevestiging.",
                   "Select what you want gone (multiple with Ctrl or Shift) and click "
                   "'Delete selected'. Nothing is removed without confirmation."),
    "root_default": ("Zoekt nu in: je eigen mappen (Downloads, Documenten, Bureaublad, "
                     "Afbeeldingen, Video's, Muziek).",
                     "Searching in: your own folders (Downloads, Documents, Desktop, "
                     "Pictures, Videos, Music)."),
    "root_now":   ("Zoekt nu in: %s", "Searching in: %s"),
    "root_pick":  ("Andere map kiezen...", "Choose another folder..."),
    "root_reset": ("Terug naar eigen mappen", "Back to my folders"),
    "pick_row":   ("Selecteer eerst een regel in de lijst.",
                   "Select a row in the list first."),
    "gone":       ("Dit bestand bestaat niet meer:\n%s", "This file no longer exists:\n%s"),
    "tip_dup":    ("Zoekt bestanden die exact identiek zijn (zelfde inhoud, andere naam "
                   "of plek). Per groep hoef je er maar één te bewaren.",
                   "Finds files that are exactly identical (same content, different name "
                   "or place). You only need to keep one per group."),
    "tip_big":    ("Toont je grootste bestanden vanaf 25 MB. Staan je grote spullen op "
                   "een andere schijf? Kies dan eerst die map hieronder.",
                   "Shows your largest files from 25 MB up. Big stuff on another drive? "
                   "Pick that folder below first."),
    "tip_old":    ("Installers en archieven in Downloads die je al 6+ maanden niet hebt "
                   "aangeraakt. Die heb je meestal niet meer nodig.",
                   "Installers and archives in Downloads untouched for 6+ months. You "
                   "usually don't need those anymore."),
    "tip_root":   ("Kies zelf waar er gezocht wordt — bijvoorbeeld een hele schijf zoals "
                   "D:\\, als je grote bestanden daar staan.",
                   "Choose where to search — for example a whole drive like D:\\, if "
                   "your large files live there."),
    "tip_root_reset": ("Terug naar de standaard: je eigen gebruikersmappen.",
                       "Back to the default: your own user folders."),

    # --- realtime wacht + geplande scan
    "realtime":   ("Realtime wacht (Downloads, Bureaublad, Temp)",
                   "Realtime watch (Downloads, Desktop, Temp)"),
    "rt_note":    ("Nieuwe of gewijzigde bestanden worden meteen gescand. Je krijgt "
                   "een melding uit het systeemvak als er iets niet deugt.",
                   "New or changed files are scanned immediately. You get a tray "
                   "notification if something is wrong."),
    "rt_hit":     ("Verdacht bestand gevonden: %s\n%s",
                   "Suspicious file found: %s\n%s"),
    "sched_on":   ("Geplande scan aanzetten", "Enable scheduled scan"),
    "sched_when": ("Wanneer:", "When:"),
    "sched_daily": ("Elke dag", "Every day"),
    "sched_weekly": ("Wekelijks", "Weekly"),
    "sched_start": ("Geplande scan gestart...", "Scheduled scan started..."),
    "sched_now":  ("Nu ingesteld op: %s", "Currently set to: %s"),

    # --- opstartitems
    "start_note": ("Uitzetten is altijd terug te draaien: DraveGuard bewaart een kopie "
                   "en zet het item op jouw woord gewoon weer terug.",
                   "Disabling is always reversible: DraveGuard keeps a copy and restores "
                   "the item whenever you say so."),
    "start_off":  ("Uitzetten", "Disable"),
    "start_on":   ("Weer aanzetten", "Enable again"),
    "start_is_on":  ("staat aan", "enabled"),
    "start_is_off": ("staat UIT", "DISABLED"),
    "start_off_ask": ("'%s' niet meer met Windows laten meestarten?\n"
                      "Je kunt dit altijd terugdraaien.",
                      "Stop '%s' from starting with Windows?\nYou can always undo this."),
    "start_already_off": ("Dit item staat al uit.", "This item is already disabled."),
    "start_keep": ("Beter laten staan", "Better to keep"),
    "start_no_advice": ("Geen bijzonderheden — dit item mag je gerust uitzetten.",
                        "Nothing special — you can safely disable this item."),

    # --- systeemvak
    "tray_show":  ("Tonen", "Show"),
    "tray_scan":  ("Snelscan", "Quick scan"),
    "tray_quit":  ("Afsluiten", "Quit"),
    "tray_hint":  ("DraveGuard draait door in het systeemvak en houdt je geheugen in de gaten.",
                   "DraveGuard keeps running in the system tray and watches your memory."),
}


def T(key: str) -> str:
    v = TX.get(key, (key, key))
    return v[0] if NL else v[1]


# ---------------------------------------------------------------- thema (donker paars)

BG = "#16131f"
PANEL = "#211b30"
ACCENT = "#7F77DD"
ACCENT2 = "#b59cff"
BORDER = "#4a3d66"
TXTCOL = "#ece7ff"
GOOD = "#57d98a"
WARNC = "#ffd166"
BADC = "#ff6b6b"

STYLE = f"""
QWidget {{ background:{BG}; color:{TXTCOL};
           font-size:18px; font-family:'Segoe UI',Arial; }}
QTabWidget::pane {{ border:1px solid {BORDER}; border-radius:8px; background:{PANEL}; }}
QTabBar::tab {{ background:{PANEL}; color:{TXTCOL}; padding:10px 9px;
               font-size:16px; border:1px solid {BORDER}; border-bottom:none;
               border-top-left-radius:8px; border-top-right-radius:8px; margin-right:3px; }}
QTabBar::tab:selected {{ background:{ACCENT}; color:white; font-weight:bold; }}
QPushButton {{ background:{ACCENT}; color:white; border:none; border-radius:8px;
               padding:12px 18px; font-size:18px; font-weight:bold; }}
QPushButton:hover {{ background:{ACCENT2}; }}
QPushButton:disabled {{ background:#3a3350; color:#8880a5; }}
QPushButton#ghost {{ background:{PANEL}; color:{ACCENT2}; border:2px solid {BORDER}; }}
QPushButton#ghost:hover {{ border-color:{ACCENT2}; }}
QTextEdit, QListWidget, QTableWidget, QLineEdit {{
    background:#1b1626; border:1px solid {BORDER}; border-radius:8px;
    padding:8px; font-size:17px; selection-background-color:{ACCENT}; }}
QProgressBar {{ background:#1b1626; border:1px solid {BORDER}; border-radius:8px;
    height:26px; text-align:center; font-size:15px; color:{TXTCOL}; }}
QProgressBar::chunk {{ background:{ACCENT}; border-radius:7px; }}
QCheckBox {{ font-size:17px; spacing:10px; padding:4px; }}
QCheckBox::indicator {{ width:22px; height:22px; border:2px solid {ACCENT2};
    border-radius:5px; background:#1b1626; }}
QCheckBox::indicator:checked {{ background:{ACCENT}; image:none; }}
QHeaderView::section {{ background:{PANEL}; color:{ACCENT2}; padding:8px;
    border:1px solid {BORDER}; font-size:16px; font-weight:bold; }}
QLabel#h1 {{ font-size:30px; font-weight:bold; color:{ACCENT2}; }}
QLabel#h2 {{ font-size:22px; font-weight:bold; color:{ACCENT2}; }}
QLabel#big {{ font-size:40px; font-weight:bold; }}
QScrollBar:vertical {{ background:{PANEL}; width:16px; }}
QScrollBar::handle:vertical {{ background:{BORDER}; border-radius:8px; min-height:30px; }}
"""


def asset(name: str) -> str:
    base = engine.HERE
    for cand in (os.path.join(base, "assets", name),
                 os.path.join(getattr(sys, "_MEIPASS", base), "assets", name)):
        if os.path.isfile(cand):
            return cand
    return ""


# ---------------------------------------------------------------- werk-threads

class ScanThread(QThread):
    progress = pyqtSignal(int, int, str)
    found = pyqtSignal(object)
    done = pyqtSignal(object)

    def __init__(self, scanner: engine.Scanner, roots, deep=True):
        super().__init__()
        self.scanner = scanner
        self.roots = roots
        self.deep = deep

    def run(self):
        res = self.scanner.run(
            self.roots, deep=self.deep,
            on_file=lambda i, n, p: self.progress.emit(i, n, p),
            on_finding=lambda f: self.found.emit(f))
        self.done.emit(self.scanner.stats)


class CleanScanThread(QThread):
    progress = pyqtSignal(int, int, str)
    done = pyqtSignal(float)

    def __init__(self, cats):
        super().__init__()
        self.cats = cats
        self._cancel = False

    def run(self):
        total = cleaner.scan_all(
            self.cats, on_progress=lambda i, n, s: self.progress.emit(i, n, s),
            is_cancelled=lambda: self._cancel)
        self.done.emit(float(total))


class DoCleanThread(QThread):
    progress = pyqtSignal(int, int, str)
    done = pyqtSignal(int, float, int)          # bestanden, bytes, overgeslagen

    def __init__(self, cats, use_trash):
        super().__init__()
        self.cats = [c for c in cats if c.enabled and c.files]
        self.use_trash = use_trash

    def run(self):
        tf, tb, sk = 0, 0.0, 0
        n = max(1, len(self.cats))
        for i, c in enumerate(self.cats):
            self.progress.emit(i + 1, n, c.naam_nl if NL else c.naam_en)
            done, freed, err = cleaner.clean_category(c, use_trash=self.use_trash)
            tf += done
            tb += freed
            sk += err
            c.files, c.bytes = [], 0
            cleaner.prune_empty_dirs(c)
        self.done.emit(tf, float(tb), sk)


class UpdateThread(QThread):
    step = pyqtSignal(str)
    done = pyqtSignal(int, str)

    def __init__(self, db, key, full):
        super().__init__()
        self.db, self.key, self.full = db, key, full

    def run(self):
        new, msg = engine.update_signatures(
            self.db, self.key, full=self.full,
            progress=lambda s: self.step.emit(s))
        self.done.emit(new, msg)


class SecThread(QThread):
    done = pyqtSignal(object, object)

    def run(self):
        self.done.emit(security.run_all_checks(), security.list_autoruns())


class ExtraThread(QThread):
    """Zwaar zoekwerk (dubbele bestanden e.d.) in een thread."""
    progress = pyqtSignal(int)
    done = pyqtSignal(str, object)

    def __init__(self, mode, roots=None):
        super().__init__()
        self.mode = mode
        self.roots = roots          # None = eigen gebruikersmappen
        self._cancel = False

    def run(self):
        c = lambda: self._cancel
        if self.mode == "dup":
            res = cleaner.find_duplicates(
                roots=self.roots,
                on_progress=lambda n: self.progress.emit(n), is_cancelled=c)
        elif self.mode == "big":
            res = cleaner.find_large_files(roots=self.roots, is_cancelled=c)
        else:
            res = cleaner.find_old_downloads(is_cancelled=c)
        self.done.emit(self.mode, res)


class DriverThread(QThread):
    """PowerShell is traag - dus in een thread, anders bevriest het venster."""
    done = pyqtSignal(object, object, object)

    def run(self):
        self.done.emit(sysmon.list_drivers(), sysmon.problem_devices(),
                       sysmon.detect_hardware())


# ---------------------------------------------------------------- hoofdvenster

class DraveGuard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = engine.SignatureDB()
        self.scanner = None
        self.scan_thread = None
        self.clean_thread = None
        self.findings = []
        self.cats = cleaner.build_categories()

        self.setWindowTitle(T("title"))
        ico = asset("icon.ico")
        if ico:
            self.setWindowIcon(QIcon(ico))
        self.resize(1120, 820)
        self.setMinimumSize(QSize(860, 560))

        # deze moeten bestaan vóórdat de tabs worden opgebouwd (Instellingen leest ze)
        self._quitting = False
        self.watch = sysmon.MemoryWatch()
        self.fwatch = watcher.FolderWatch()
        self.sched = watcher.Schedule(self.db)
        self._bg_scanner = None

        tabs = QTabWidget()
        tabs.addTab(self._tab_home(), T("tab_home"))
        tabs.addTab(self._tab_scan(), T("tab_scan"))
        tabs.addTab(self._tab_clean(), T("tab_clean"))
        tabs.addTab(self._tab_extra(), T("tab_extra"))
        tabs.addTab(self._tab_system(), T("tab_sys"))
        tabs.addTab(self._tab_drivers(), T("tab_drv"))
        tabs.addTab(self._tab_security(), T("tab_sec"))
        tabs.addTab(self._tab_quar(), T("tab_quar"))
        tabs.addTab(self._tab_settings(), T("tab_set"))
        # onderhoud-1.1.0: Onderhoud vóór Instellingen (indexen 0-7 blijven gelijk)
        onderhoud_ui.NL = NL
        self.ond_tab = onderhoud_ui.OnderhoudTab(self)
        tabs.insertTab(8, self.ond_tab, T("tab_ond"))
        # schuiftabs-1.0.2: elk tabblad in een schuifvak, zodat het venster op elk scherm past
        for _i in range(tabs.count()):
            _pg = tabs.widget(_i); _txt = tabs.tabText(_i)
            tabs.removeTab(_i)
            _sc = QScrollArea(); _sc.setWidgetResizable(True)
            _sc.setFrameShape(QFrame.Shape.NoFrame); _sc.setWidget(_pg)
            tabs.insertTab(_i, _sc, _txt)
        # hover-tekst per tabblad (toegankelijkheid)
        for i, key in enumerate(("tt_home", "tt_scan", "tt_clean", "tt_extra", "tt_sys",
                                 "tt_drv", "tt_sec", "tt_quar", "tt_ond", "tt_set")):
            tabs.setTabToolTip(i, T(key))
        # telefoon-1.2.0: tabblad Telefoon (DraveCare) vóór Instellingen
        telefoon_ui.NL = NL
        self.tel_tab = telefoon_ui.TelefoonTab(self)
        _sc = QScrollArea(); _sc.setWidgetResizable(True)
        _sc.setFrameShape(QFrame.Shape.NoFrame); _sc.setWidget(self.tel_tab)
        tabs.insertTab(9, _sc, "📱 Telefoon" if NL else "📱 Phone")
        tabs.setTabToolTip(9, "Je telefoon onderhouden via de pc: bestanden ophalen, opruimen, batterij, apps en een volledige controle."
                           if NL else "Maintain your phone from the PC: files, clean-up, battery, apps and a full check.")

        tabs.currentChanged.connect(self._on_tab)
        self.tabs = tabs
        tabs.setCurrentIndex(0)   # altijd openen op Overzicht
        self.setCentralWidget(tabs)
        self._refresh_home()

        # --- systeemvak (draakje) + achtergrondwachten
        # (watch/fwatch/sched zijn hierboven al aangemaakt, vóór de tabs)
        self._setup_tray()

        self.live = QTimer(self)                 # meters, 2s
        self.live.timeout.connect(self._tick_live)
        self.live.start(2000)
        self.leaktimer = QTimer(self)            # geheugenlek-wacht, 60s
        self.leaktimer.timeout.connect(self._tick_watch)
        self.leaktimer.start(60000)
        self.rttimer = QTimer(self)              # realtime map-wacht, 15s
        self.rttimer.timeout.connect(self._tick_realtime)
        self.rttimer.start(15000)
        self.schedtimer = QTimer(self)           # geplande scan, elke minuut kijken
        self.schedtimer.timeout.connect(self._tick_schedule)
        self.schedtimer.start(60000)

    # ---------- realtime wacht (Downloads / Bureaublad / Temp)
    def _tick_realtime(self):
        if self.db.get_meta("realtime", "0") != "1":
            return
        nieuw = self.fwatch.poll()
        if not nieuw:
            return
        if self._bg_scanner is None:
            self._bg_scanner = self._make_scanner()
        treffers = watcher.scan_paths(self._bg_scanner, nieuw)
        for f in treffers:
            tekst = T("rt_hit") % (os.path.basename(f.path), f.detection)
            if self.tray:
                self.tray.showMessage("DraveGuard", tekst,
                                      QSystemTrayIcon.MessageIcon.Critical, 10000)
            self.findings.append(f)
            self._scan_found(f)
            break

    # ---------- geplande scan
    def _tick_schedule(self):
        if not self.sched.due():
            return
        self.sched.mark_done()
        if self.tray:
            self.tray.showMessage("DraveGuard", T("sched_start"),
                                  QSystemTrayIcon.MessageIcon.Information, 5000)
        self.tabs.setCurrentIndex(1)
        self._quick_scan()

    # ---------- helpers
    def _btn(self, text, slot, ghost=False, tip=""):
        b = QPushButton(text)
        if ghost:
            b.setObjectName("ghost")
        b.clicked.connect(slot)
        b.setMinimumHeight(52)
        # hover-tekst: toegankelijkheid (en EU-richtlijn). Geen tip? Dan de knoptekst.
        b.setToolTip(tip or text)
        b.setAccessibleName(text)
        b.setAccessibleDescription(tip or text)
        return b

    def _cel(self, tekst, tip="", kleur=None):
        """Tabelcel met hover-tekst (volledige inhoud, ook als de kolom te smal is)."""
        it = QTableWidgetItem(tekst)
        it.setToolTip(tip or tekst)
        if kleur:
            it.setForeground(QColor(kleur))
        return it

    def _fit(self, table):
        """Kolommen laten meegroeien met hun inhoud; eerste kolom rekt uit."""
        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, table.columnCount()):
            table.horizontalHeader().setSectionResizeMode(
                c, QHeaderView.ResizeMode.ResizeToContents)

    def _hr(self):
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet(f"color:{BORDER};")
        return f

    # ---------- tab: overzicht
    def _tab_home(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(26, 22, 26, 22)
        lay.setSpacing(14)

        top = QHBoxLayout()
        logo = asset("logo_t.png") or asset("logo.png")
        if logo:
            from PyQt6.QtGui import QPixmap
            l = QLabel()
            l.setPixmap(QPixmap(logo).scaledToHeight(84, Qt.TransformationMode.SmoothTransformation))
            top.addWidget(l)
        titel = QLabel("DraveGuard")
        titel.setObjectName("h1")
        top.addWidget(titel)
        top.addStretch()
        lay.addLayout(top)

        self.lbl_status = QLabel("...")
        self.lbl_status.setObjectName("big")
        lay.addWidget(self.lbl_status)

        self.lbl_home_info = QLabel("")
        self.lbl_home_info.setWordWrap(True)
        lay.addWidget(self.lbl_home_info)

        lay.addWidget(self._hr())

        row = QHBoxLayout()
        row.addWidget(self._btn("🛡  " + T("quick"), lambda: (self.tabs.setCurrentIndex(1),
                                                              self._quick_scan())))
        row.addWidget(self._btn("🧹  " + T("scan_clean"), lambda: (self.tabs.setCurrentIndex(2),
                                                                   self._clean_scan())))
        row.addWidget(self._btn("🔒  " + T("sec_check"), lambda: (self.tabs.setCurrentIndex(6),
                                                                  self._run_security())))
        lay.addLayout(row)
        _bt = self._btn("🧰  " + T("totaal"), lambda: self.ond_tab.start_totaal(),
                        tip=T("tt_ond"))
        _bt.setMinimumHeight(64)
        lay.addWidget(_bt)
        lay.addStretch()

        note = QLabel("♥  " + T("donate") + "   ·   " + CONTACT)
        note.setStyleSheet(f"color:{ACCENT2}; font-size:15px;")
        note.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        note.setOpenExternalLinks(False)
        note.mousePressEvent = lambda e: self._open(DONATE)
        note.setCursor(Qt.CursorShape.PointingHandCursor)
        lay.addWidget(note)
        return w

    def _refresh_home(self):
        n = self.db.count()
        clam = engine.find_clamscan()
        self.lbl_status.setText("🛡  " + T("protect"))
        self.lbl_status.setStyleSheet(f"color:{GOOD};")
        last = self.db.get_meta("last_update", "") or T("never")
        parts = [
            "%s %s" % (T("sig_count"), f"{n:,}".replace(",", ".")),
            "%s %s" % (T("last_upd"), last),
            T("clam_found") if clam else T("clam_none"),
        ]
        self.lbl_home_info.setText("\n".join(parts))

    # ---------- tab: scannen
    def _tab_scan(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)

        row = QHBoxLayout()
        row.addWidget(self._btn(T("quick"), self._quick_scan))
        row.addWidget(self._btn(T("choose"), self._choose_scan, ghost=True))
        self.btn_stop = self._btn(T("stop"), self._stop_scan, ghost=True)
        self.btn_stop.setEnabled(False)
        row.addWidget(self.btn_stop)
        lay.addLayout(row)

        self.scan_bar = QProgressBar()
        self.scan_bar.setValue(0)
        lay.addWidget(self.scan_bar)
        self.scan_lbl = QLabel("")
        self.scan_lbl.setStyleSheet("font-size:15px;")
        lay.addWidget(self.scan_lbl)

        self.result = QTableWidget(0, 4)
        self.result.setHorizontalHeaderLabels(
            ["Bestand" if NL else "File", "Detectie" if NL else "Detection",
             "Bron" if NL else "Source", "Ernst" if NL else "Severity"])
        self.result.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.result.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.result.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        lay.addWidget(self.result, 1)

        row2 = QHBoxLayout()
        row2.addWidget(self._btn(T("quar_sel"), self._quarantine_selected))
        row2.addWidget(self._btn(T("make_test"), self._make_test, ghost=True))
        row2.addStretch()
        lay.addLayout(row2)
        return w

    def _make_scanner(self):
        return engine.Scanner(self.db,
                              use_yara=self._get_chk("use_yara", True),
                              use_clam=self._get_chk("use_clam", True),
                              use_heur=self._get_chk("use_heur", True))

    def _quick_scan(self):
        roots = engine.quick_targets()
        if not roots:
            QMessageBox.information(self, APP_NAME, "Geen snelscan-mappen gevonden.")
            return
        self._start_scan(roots, deep=True)

    def _choose_scan(self):
        d = QFileDialog.getExistingDirectory(self, T("choose"), os.path.expanduser("~"))
        if d:
            self._start_scan([d], deep=True)

    def _start_scan(self, roots, deep=True):
        if self.scan_thread and self.scan_thread.isRunning():
            return
        self.result.setRowCount(0)
        self.findings = []
        self.scanner = self._make_scanner()
        self.scan_thread = ScanThread(self.scanner, roots, deep)
        self.scan_thread.progress.connect(self._scan_progress)
        self.scan_thread.found.connect(self._scan_found)
        self.scan_thread.done.connect(self._scan_finished)
        self.btn_stop.setEnabled(True)
        self.scan_lbl.setText(T("scanning"))
        self.scan_thread.start()

    def _scan_progress(self, i, n, path):
        self.scan_bar.setMaximum(max(1, n))
        self.scan_bar.setValue(i)
        self.scan_lbl.setText("%d / %d  ·  %s" % (i, n, os.path.basename(path)[:60]))

    def _scan_found(self, f: engine.Finding):
        if not f.is_threat:
            return
        self.findings.append(f)
        r = self.result.rowCount()
        self.result.insertRow(r)
        sev_txt = {engine.SEV_SUS: ("Verdacht" if NL else "Suspicious"),
                   engine.SEV_MAL: ("Kwaadaardig" if NL else "Malicious")}.get(
                       f.severity, "?")
        cells = [f.path, f.detection, f.source, sev_txt]
        for c, val in enumerate(cells):
            it = QTableWidgetItem(val)
            if c == 3:
                it.setForeground(QColor(BADC if f.severity >= engine.SEV_MAL else WARNC))
            self.result.setItem(r, c, it)

    def _scan_finished(self, stats: engine.ScanStats):
        self.btn_stop.setEnabled(False)
        self.scan_bar.setValue(self.scan_bar.maximum())
        msg = "%s  ·  %d %s, %d %s  (%.1fs)" % (
            T("scan_done"), stats.scanned, T("files"), stats.threats, T("threats"),
            stats.elapsed)
        self.scan_lbl.setText(msg)
        if stats.threats == 0:
            QMessageBox.information(self, APP_NAME, T("no_threats"))

    def _stop_scan(self):
        if self.scanner:
            self.scanner.cancel = True
        self.btn_stop.setEnabled(False)

    def _quarantine_selected(self):
        rows = sorted({i.row() for i in self.result.selectedIndexes()}, reverse=True)
        if not rows:
            QMessageBox.information(self, APP_NAME,
                                    "Selecteer eerst een of meer regels." if NL
                                    else "Select one or more rows first.")
            return
        ok = 0
        for r in rows:
            if r >= len(self.findings):
                continue
            f = self.findings[r]
            success, res = engine.quarantine(self.db, f.path, f.detection)
            if success:
                ok += 1
                self.result.removeRow(r)
                self.findings.pop(r)
            else:
                QMessageBox.warning(self, APP_NAME, "%s:\n%s" % (f.path, res))
        if ok:
            QMessageBox.information(self, APP_NAME,
                                    ("%d bestand(en) in quarantaine." if NL
                                     else "%d file(s) quarantined.") % ok)
            self._refresh_quar()

    def _make_test(self):
        d = QFileDialog.getExistingDirectory(self, T("make_test"), os.path.expanduser("~"))
        if not d:
            return
        p = engine.make_testfile(d)
        QMessageBox.information(
            self, APP_NAME,
            ("Onschadelijk testbestand gemaakt:\n%s\n\nScan deze map om te zien dat de "
             "scanner werkt." if NL else
             "Safe test file created:\n%s\n\nScan that folder to verify the scanner works.")
            % p)

    # ---------- tab: opschonen
    def _tab_clean(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)

        hdr = QLabel(T("tab_clean"))
        hdr.setObjectName("h2")
        lay.addWidget(hdr)

        self.clean_scroll = QScrollArea()
        self.clean_scroll.setWidgetResizable(True)
        inner = QWidget()
        self.clean_box = QVBoxLayout(inner)
        self.clean_box.setSpacing(6)
        self.clean_checks = {}
        for c in self.cats:
            cb = QCheckBox("%s" % (c.naam_nl if NL else c.naam_en))
            cb.setChecked(c.enabled)
            self.clean_checks[c.key] = cb
            self.clean_box.addWidget(cb)
        self.clean_box.addStretch()
        self.clean_scroll.setWidget(inner)
        lay.addWidget(self.clean_scroll, 1)

        self.clean_bar = QProgressBar()
        lay.addWidget(self.clean_bar)
        self.clean_lbl = QLabel("")
        lay.addWidget(self.clean_lbl)

        row = QHBoxLayout()
        row.addWidget(self._btn(T("scan_clean"), self._clean_scan))
        self.btn_clean = self._btn(T("clean_now"), self._do_clean)
        self.btn_clean.setEnabled(False)
        row.addWidget(self.btn_clean)
        row.addWidget(self._btn(T("empty_bin"), self._empty_bin, ghost=True))
        lay.addLayout(row)
        return w

    def _clean_scan(self):
        for c in self.cats:
            c.enabled = self.clean_checks[c.key].isChecked()
        self.clean_thread = CleanScanThread(self.cats)
        self.clean_thread.progress.connect(
            lambda i, n, s: (self.clean_bar.setMaximum(n), self.clean_bar.setValue(i),
                             self.clean_lbl.setText(s)))
        self.clean_thread.done.connect(self._clean_scan_done)
        self.clean_lbl.setText(T("scanning"))
        self.clean_thread.start()

    def _clean_scan_done(self, total):
        self.clean_bar.setValue(self.clean_bar.maximum())
        lines = []
        for c in self.cats:
            if c.enabled and c.bytes:
                lines.append("  • %s — %s (%d)" % (
                    c.naam_nl if NL else c.naam_en, cleaner.human(c.bytes), len(c.files)))
        self.clean_lbl.setText("%s %s\n%s" % (
            T("freeable"), cleaner.human(total), "\n".join(lines)))
        self.btn_clean.setEnabled(total > 0)

    def _do_clean(self):
        if not any(c.enabled and c.files for c in self.cats):
            QMessageBox.information(self, APP_NAME,
                                    T("scan_clean") + " ?")   # eerst scannen
            return
        if QMessageBox.question(self, APP_NAME, T("confirm_clean")) != \
                QMessageBox.StandardButton.Yes:
            return
        use_trash = self._get_chk("use_trash", True)
        self.btn_clean.setEnabled(False)
        self.clean_lbl.setText(T("cleaning"))
        self._clean_do = DoCleanThread(self.cats, use_trash)
        self._clean_do.progress.connect(
            lambda i, n, s: (self.clean_bar.setMaximum(n), self.clean_bar.setValue(i),
                             self.clean_lbl.setText("%s  (%s)" % (T("cleaning"), s))))
        self._clean_do.done.connect(
            lambda f, b, s: self._clean_finished(f, b, s, use_trash))
        self._clean_do.start()

    def _clean_finished(self, files, total_bytes, skipped, use_trash):
        self.clean_bar.setValue(self.clean_bar.maximum())
        txt = "%s %s (%d %s)" % (T("cleaned"), cleaner.human(total_bytes),
                                 files, T("files"))
        if skipped:
            txt += "  ·  " + (T("skipped_lock") % skipped)
        self.clean_lbl.setText(txt)

        if files == 0 and skipped > 0:
            QMessageBox.information(self, APP_NAME, T("nothing_cleaned"))
        elif use_trash and cleaner.HAVE_TRASH and total_bytes > 0:
            # ruimte komt pas vrij als de prullenbak geleegd wordt -> meteen aanbieden
            if QMessageBox.question(self, APP_NAME, txt + "\n\n" + T("trash_note")) == \
                    QMessageBox.StandardButton.Yes:
                ok, msg = cleaner.empty_recycle_bin()
                QMessageBox.information(self, APP_NAME, msg)
        else:
            QMessageBox.information(self, APP_NAME, txt)

    def _empty_bin(self):
        ok, msg = cleaner.empty_recycle_bin()
        QMessageBox.information(self, APP_NAME, msg)

    # ---------- tab: uitgebreid opschonen
    def _tab_extra(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)

        note = QLabel(T("extra_note"))
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{ACCENT2}; font-size:15px;")
        lay.addWidget(note)

        row = QHBoxLayout()
        row.addWidget(self._btn(T("find_dup"), lambda: self._extra_scan("dup"),
                                tip=T("tip_dup")))
        row.addWidget(self._btn(T("find_big"), lambda: self._extra_scan("big"),
                                ghost=True, tip=T("tip_big")))
        row.addWidget(self._btn(T("find_old"), lambda: self._extra_scan("old"),
                                ghost=True, tip=T("tip_old")))
        lay.addLayout(row)

        # waar wordt gezocht? standaard je eigen mappen, maar je mag zelf kiezen
        row0 = QHBoxLayout()
        self.root_lbl = QLabel(T("root_default"))
        self.root_lbl.setWordWrap(True)
        self.root_lbl.setStyleSheet(f"color:{ACCENT2}; font-size:15px;")
        row0.addWidget(self.root_lbl, 1)
        row0.addWidget(self._btn(T("root_pick"), self._extra_pick_root, ghost=True,
                                 tip=T("tip_root")))
        row0.addWidget(self._btn(T("root_reset"), self._extra_reset_root, ghost=True,
                                 tip=T("tip_root_reset")))
        lay.addLayout(row0)
        self._extra_root = None          # None = eigen gebruikersmappen

        self.extra_lbl = QLabel("")
        lay.addWidget(self.extra_lbl)

        self.extra_table = QTableWidget(0, 3)
        self.extra_table.setHorizontalHeaderLabels(
            ["Bestand" if NL else "File", "Grootte" if NL else "Size",
             "Info", ])
        self.extra_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.extra_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.extra_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.extra_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        lay.addWidget(self.extra_table, 1)

        row2 = QHBoxLayout()
        row2.addWidget(self._btn(T("del_sel"), self._extra_delete))
        row2.addWidget(self._btn(T("open_folder"), self._extra_open, ghost=True))
        row2.addStretch()
        lay.addLayout(row2)

        self._extra_rows = []       # lijst van paden per rij
        return w

    def _extra_pick_root(self):
        d = QFileDialog.getExistingDirectory(self, T("root_pick"), "C:\\")
        if d:
            self._extra_root = [d]
            self.root_lbl.setText(T("root_now") % d)

    def _extra_reset_root(self):
        self._extra_root = None
        self.root_lbl.setText(T("root_default"))

    def _extra_scan(self, mode):
        self.extra_table.setRowCount(0)
        self._extra_rows = []
        self.extra_lbl.setText(T("searching"))
        # oude downloads kijkt altijd in de Downloads-map, de rest volgt je keuze
        roots = None if mode == "old" else self._extra_root
        self._extra_thread = ExtraThread(mode, roots=roots)
        self._extra_thread.progress.connect(
            lambda n: self.extra_lbl.setText("%s (%d)" % (T("searching"), n)))
        self._extra_thread.done.connect(self._extra_done)
        self._extra_thread.start()

    def _extra_done(self, mode, res):
        self.extra_table.setRowCount(0)
        self._extra_rows = []

        if mode == "dup":
            verspild = cleaner.duplicate_waste(res)
            self.extra_lbl.setText(T("dup_found") % (len(res), cleaner.human(verspild)))
            for groep in res:
                for i, p in enumerate(groep):
                    try:
                        sz = os.path.getsize(p)
                    except Exception:
                        sz = 0
                    info = T("dup_keep") if i == 0 else T("dup_copy")
                    self._add_extra_row(p, sz, info,
                                        kleur=GOOD if i == 0 else WARNC)
        elif mode == "big":
            self.extra_lbl.setText(T("big_found") % len(res))
            for p, sz in res:
                self._add_extra_row(p, sz, "")
        else:
            self.extra_lbl.setText(T("old_found") % len(res))
            for p, sz, dagen in res:
                self._add_extra_row(p, sz, T("days_old") % dagen, kleur=WARNC)

    def _add_extra_row(self, pad, grootte, info, kleur=None):
        r = self.extra_table.rowCount()
        self.extra_table.insertRow(r)
        tip = "%s\n\n%s%s\n\n%s" % (
            pad, cleaner.human(grootte),
            ("  ·  " + info) if info else "", T("extra_tip"))
        self.extra_table.setItem(r, 0, self._cel(pad, tip))
        self.extra_table.setItem(r, 1, self._cel(cleaner.human(grootte), tip))
        self.extra_table.setItem(r, 2, self._cel(info, tip, kleur))
        self._extra_rows.append(pad)
        self._fit(self.extra_table)

    def _extra_selected(self):
        rijen = sorted({i.row() for i in self.extra_table.selectedIndexes()})
        return [self._extra_rows[r] for r in rijen if r < len(self._extra_rows)]

    def _extra_delete(self):
        paden = self._extra_selected()
        if not paden:
            return
        if QMessageBox.question(self, APP_NAME, T("del_ask") % len(paden)) != \
                QMessageBox.StandardButton.Yes:
            return
        use_trash = self._get_chk("use_trash", True)
        done, freed, errors = cleaner.delete_files(paden, use_trash=use_trash)
        msg = "%s %s (%d %s)" % (T("cleaned"), cleaner.human(freed), done, T("files"))
        if errors:
            msg += "  ·  " + (T("skipped_lock") % errors)
        QMessageBox.information(self, APP_NAME, msg)
        self.extra_lbl.setText(msg)

    def _extra_open(self):
        paden = self._extra_selected()
        if not paden:
            QMessageBox.information(self, APP_NAME, T("pick_row"))   # zeg het gewoon
            return
        pad = paden[0]
        try:
            if os.path.exists(pad):
                # Verkenner openen MET het bestand geselecteerd
                subprocess.Popen(['explorer', '/select,', os.path.normpath(pad)])
            else:
                map_ = os.path.dirname(pad)
                if os.path.isdir(map_):
                    os.startfile(map_)
                else:
                    QMessageBox.warning(self, APP_NAME, T("gone") % pad)
        except Exception as e:
            QMessageBox.warning(self, APP_NAME, str(e))

    # ---------- tab: systeem (geheugen / processen)
    def _tab_system(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)

        # meters
        self.bar_ram = QProgressBar()
        self.bar_cpu = QProgressBar()
        self.bar_disk = QProgressBar()
        for lbl, bar in ((T("ram"), self.bar_ram), (T("cpu"), self.bar_cpu),
                         (T("disk"), self.bar_disk)):
            row = QHBoxLayout()
            l = QLabel(lbl)
            l.setMinimumWidth(190)
            row.addWidget(l)
            row.addWidget(bar, 1)
            lay.addLayout(row)

        self.lbl_ram = QLabel("")
        self.lbl_ram.setStyleSheet("font-size:16px;")
        lay.addWidget(self.lbl_ram)

        note = QLabel("ℹ  " + T("ram_note"))
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{ACCENT2}; font-size:15px;")
        lay.addWidget(note)

        hdr = QLabel(T("hogs"))
        hdr.setObjectName("h2")
        lay.addWidget(hdr)

        self.proc_table = QTableWidget(0, 4)
        self.proc_table.setHorizontalHeaderLabels(
            ["Programma" if NL else "Program", "Geheugen" if NL else "Memory",
             "%", "PID"])
        self.proc_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.proc_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.proc_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        lay.addWidget(self.proc_table, 1)

        row = QHBoxLayout()
        row.addWidget(self._btn(T("refresh"), self._refresh_procs, ghost=True))
        row.addWidget(self._btn(T("kill"), self._kill_selected))
        self.btn_watch = self._btn(T("watch_on"), self._toggle_watch, ghost=True)
        row.addWidget(self.btn_watch)
        lay.addLayout(row)

        self._watch_on = True
        self._procs = []
        return w

    def _tick_live(self):
        if not sysmon.HAVE_PSUTIL:
            self.lbl_ram.setText("psutil ontbreekt - start via Start-DraveGuard.bat")
            return
        m = sysmon.mem_stats()
        self.bar_ram.setValue(int(m.percent))
        self.bar_cpu.setValue(int(sysmon.cpu_percent()))
        self.bar_disk.setValue(int(sysmon.disk_percent()))
        self.lbl_ram.setText("%s / %s  (%s vrij)" % (
            sysmon.human(m.used), sysmon.human(m.total), sysmon.human(m.available))
            if NL else "%s / %s  (%s free)" % (
            sysmon.human(m.used), sysmon.human(m.total), sysmon.human(m.available)))

    def _refresh_procs(self):
        self._procs = sysmon.top_processes(25)
        self.proc_table.setRowCount(0)
        for p in self._procs:
            r = self.proc_table.rowCount()
            self.proc_table.insertRow(r)
            naam = p.name + ("  🔒" if p.protected else "")
            if p.unknown:
                tip = T("proc_unknown")
            elif p.protected:
                tip = "%s\n\n%s" % (p.name, T("protected"))
            else:
                tip = "%s\n\nPID %d — %s (%.1f%%)\n%s" % (
                    p.name, p.pid, sysmon.human(p.mem), p.mem_pct, T("proc_tip"))
            kleur = "#8880a5" if p.protected else None
            self.proc_table.setItem(r, 0, self._cel(naam, tip, kleur))
            self.proc_table.setItem(r, 1, self._cel(sysmon.human(p.mem), tip, kleur))
            self.proc_table.setItem(r, 2, self._cel("%.1f" % p.mem_pct, tip, kleur))
            self.proc_table.setItem(r, 3, self._cel(str(p.pid), tip, kleur))
        self._fit(self.proc_table)

    def _kill_selected(self):
        sel = {i.row() for i in self.proc_table.selectedIndexes()}
        if not sel:
            return
        r = min(sel)
        if r >= len(self._procs):
            return
        p = self._procs[r]
        if p.protected:
            QMessageBox.information(self, APP_NAME, T("protected"))
            return
        if QMessageBox.question(self, APP_NAME, T("kill_ask") % p.name) != \
                QMessageBox.StandardButton.Yes:
            return
        ok, msg = sysmon.kill_process(p.pid)
        if not ok:
            QMessageBox.warning(self, APP_NAME, msg)
        self._refresh_procs()

    def _toggle_watch(self):
        self._watch_on = not self._watch_on
        self.btn_watch.setText(T("watch_on") if self._watch_on else T("watch_off"))
        if not self._watch_on:
            self.watch.reset()

    def _tick_watch(self):
        """Elke minuut: kijk of een proces structureel wegloopt (geheugenlek)."""
        if not self._watch_on or not sysmon.HAVE_PSUTIL:
            return
        for p, groei in self.watch.sample():
            tekst = T("leak_msg") % (p.name, groei, sysmon.human(p.mem))
            if self.tray and self.tray.isVisible():
                self.tray.showMessage("DraveGuard - " + T("leak"), tekst,
                                      QSystemTrayIcon.MessageIcon.Warning, 8000)
            else:
                QMessageBox.warning(self, T("leak"), tekst)
            break            # één melding per ronde is genoeg

    # ---------- tab: stuurprogramma's
    def _tab_drivers(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)

        note = QLabel("⚠  " + T("drv_note"))
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{WARNC}; font-size:15px;")
        lay.addWidget(note)

        lay.addWidget(self._btn(T("drv_scan"), self._scan_drivers))
        self.drv_lbl = QLabel("")
        lay.addWidget(self.drv_lbl)

        self.drv_table = QTableWidget(0, 4)
        self.drv_table.setHorizontalHeaderLabels(
            ["Apparaat" if NL else "Device", "Versie" if NL else "Version",
             "Datum" if NL else "Date", "Leverancier" if NL else "Vendor"])
        self.drv_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.drv_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        lay.addWidget(self.drv_table, 2)

        hdr = QLabel(T("drv_prob"))
        hdr.setObjectName("h2")
        lay.addWidget(hdr)
        self.drv_prob = QListWidget()
        lay.addWidget(self.drv_prob, 1)

        hdr2 = QLabel(T("drv_src"))
        hdr2.setObjectName("h2")
        lay.addWidget(hdr2)

        # herkende hardware + bronnen die daar echt bij horen
        self.hw_lbl = QLabel(T("hw_none"))
        self.hw_lbl.setWordWrap(True)
        self.hw_lbl.setStyleSheet(f"color:{ACCENT2}; font-size:16px;")
        lay.addWidget(self.hw_lbl)

        self.src_row = QGridLayout()                    # raster: tekst past altijd
        self.src_row.setHorizontalSpacing(10)
        self.src_row.setVerticalSpacing(8)
        self._build_sources(sysmon.DRIVER_SOURCES)      # voorlopig: algemeen
        lay.addLayout(self.src_row)
        return w

    def _build_sources(self, bronnen):
        """(Her)bouwt de bronnen als een RASTER, zodat de tekst nooit afgeknipt wordt."""
        while self.src_row.count():
            it = self.src_row.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        for i, (naam, url) in enumerate(bronnen):
            b = self._btn(naam, lambda _c=False, u=url: self._open_src(u), ghost=True)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            # knop mag nooit smaller worden dan zijn eigen tekst
            fm = b.fontMetrics()
            b.setMinimumWidth(fm.horizontalAdvance(naam) + 46)
            self.src_row.addWidget(b, i // 3, i % 3)      # 3 per rij

    def _open_src(self, url):
        try:
            if url.endswith(".msc") or url.startswith("ms-settings:"):
                os.startfile(url)
            else:
                self._open(url)
        except Exception as e:
            QMessageBox.warning(self, APP_NAME, str(e))

    def _scan_drivers(self):
        self.drv_lbl.setText(T("scanning"))
        self.drv_thread = DriverThread()
        self.drv_thread.done.connect(self._drivers_done)
        self.drv_thread.start()

    def _drivers_done(self, drivers, problems, hw):
        # --- herkende hardware -> alleen de bronnen die hierbij horen
        regels = []
        for g in hw.gpus:
            extra = []
            if g.version:
                extra.append(g.version)
            if g.date:
                extra.append(g.date)
            regels.append("🎮  %s: <b>%s</b>%s" % (
                T("hw_gpu"), g.name, ("  (%s)" % " · ".join(extra)) if extra else ""))
        if hw.cpu:
            regels.append("🧠  %s: <b>%s</b>" % (T("hw_cpu"), hw.cpu))
        if hw.board:
            regels.append("🔧  %s: <b>%s</b>" % (T("hw_board"), hw.board))
        if hw.system:
            regels.append("💻  %s: <b>%s</b>" % (T("hw_sys"), hw.system))
        if regels:
            self.hw_lbl.setText("<b>%s</b><br>%s" % (T("hw_found"), "<br>".join(regels)))
            self._build_sources(sysmon.relevant_sources(hw))
        else:
            self.hw_lbl.setText(T("hw_none"))
            self._build_sources(sysmon.DRIVER_SOURCES)

        self.drv_table.setRowCount(0)
        oud = 0
        for d in drivers:
            r = self.drv_table.rowCount()
            self.drv_table.insertRow(r)
            tip = "%s\n\n%s: %s\n%s: %s\n%s: %s" % (
                d.device,
                "Versie" if NL else "Version", d.version or "?",
                "Datum" if NL else "Date", d.date or "?",
                "Leverancier" if NL else "Vendor", d.vendor or "?")
            if d.old:
                tip += "\n\n⚠  " + T("drv_old_tip")
            kleur = WARNC if d.old else None
            for c, val in enumerate([d.device, d.version, d.date, d.vendor]):
                self.drv_table.setItem(r, c, self._cel(val, tip, kleur))
            if d.old:
                oud += 1
        self._fit(self.drv_table)
        self.drv_prob.clear()
        if problems:
            for naam, status, klasse in problems:
                self.drv_prob.addItem(QListWidgetItem("❌  %s  (%s, %s)" % (naam, status, klasse)))
        else:
            self.drv_prob.addItem(QListWidgetItem("✅  " + T("drv_none")))
        self.drv_lbl.setText("%d %s  ·  %d %s" % (
            len(drivers), "stuurprogramma's" if NL else "drivers",
            oud, T("drv_old").lower()))

    # ---------- systeemvak
    def _setup_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        ico = asset("icon.ico")
        self.tray = QSystemTrayIcon(QIcon(ico) if ico else self.windowIcon(), self)
        self.tray.setToolTip("DraveGuard")
        menu = QMenu()
        a_show = QAction(T("tray_show"), self)
        a_show.triggered.connect(self._tray_show)
        a_scan = QAction(T("tray_scan"), self)
        a_scan.triggered.connect(lambda: (self._tray_show(), self.tabs.setCurrentIndex(1),
                                          self._quick_scan()))
        a_quit = QAction(T("tray_quit"), self)
        a_quit.triggered.connect(self._real_quit)
        for a in (a_show, a_scan):
            menu.addAction(a)
        menu.addSeparator()
        menu.addAction(a_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self._tray_show()
            if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self.tray.show()

    def _tray_show(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _real_quit(self):
        self._quitting = True
        if self.tray:
            self.tray.hide()
        QApplication.quit()

    def closeEvent(self, e):
        """Venster sluiten = verbergen naar het systeemvak (niet afsluiten)."""
        if self._quitting or not self.tray:
            e.accept()
            return
        e.ignore()
        self.hide()
        self.tray.showMessage("DraveGuard", T("tray_hint"),
                              QSystemTrayIcon.MessageIcon.Information, 4000)

    # ---------- tab: beveiliging
    def _tab_security(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)
        lay.addWidget(self._btn(T("sec_check"), self._run_security))
        note = QLabel(T("advies_note"))
        note.setStyleSheet(f"color:{ACCENT2}; font-size:15px;")
        lay.addWidget(note)

        self.sec_list = QTextEdit()
        self.sec_list.setReadOnly(True)
        lay.addWidget(self.sec_list, 1)

        hdr = QLabel(T("autoruns"))
        hdr.setObjectName("h2")
        lay.addWidget(hdr)

        note2 = QLabel(T("start_note"))
        note2.setWordWrap(True)
        note2.setStyleSheet(f"color:{ACCENT2}; font-size:15px;")
        lay.addWidget(note2)

        self.start_table = QTableWidget(0, 4)
        self.start_table.setHorizontalHeaderLabels(
            ["Programma" if NL else "Program", "Status",
             "Waar" if NL else "Where", "Advies" if NL else "Advice"])
        self.start_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.start_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.start_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        lay.addWidget(self.start_table, 2)

        row = QHBoxLayout()
        row.addWidget(self._btn(T("refresh"), self._refresh_startup, ghost=True))
        row.addWidget(self._btn(T("start_off"), self._startup_disable))
        row.addWidget(self._btn(T("start_on"), self._startup_enable, ghost=True))
        lay.addLayout(row)

        self._start_items = []
        return w

    # ---------- opstartitems
    def _refresh_startup(self):
        self._start_items = startup.list_items()
        self.start_table.setRowCount(0)
        for it in self._start_items:
            r = self.start_table.rowCount()
            self.start_table.insertRow(r)
            status = T("start_is_off") if it.uit else T("start_is_on")
            advies = ("⚠  " + it.keep) if it.keep else "—"

            # hover-tekst per cel: het volledige verhaal, ook bij een smalle kolom
            tip_naam = "%s\n\n%s" % (it.naam, it.waarde)
            tip_status = (T("start_is_off") + " — " + T("start_on"))if it.uit else \
                         (T("start_is_on") + " — " + T("start_off"))
            tip_advies = ("%s: %s\n\n%s" % (T("start_keep"), it.keep, T("start_note"))
                          if it.keep else T("start_no_advice"))

            self.start_table.setItem(r, 0, self._cel(it.naam, tip_naam))
            self.start_table.setItem(r, 1, self._cel(
                status, tip_status, "#8880a5" if it.uit else GOOD))
            self.start_table.setItem(r, 2, self._cel(it.scope, it.scope))
            self.start_table.setItem(r, 3, self._cel(
                advies, tip_advies, WARNC if it.keep else None))
        self._fit(self.start_table)

    def _sel_startup(self):
        sel = {i.row() for i in self.start_table.selectedIndexes()}
        if not sel:
            return None
        r = min(sel)
        return self._start_items[r] if r < len(self._start_items) else None

    def _startup_disable(self):
        it = self._sel_startup()
        if not it:
            return
        if it.uit:
            QMessageBox.information(self, APP_NAME, T("start_already_off"))
            return
        vraag = T("start_off_ask") % it.naam
        if it.keep:
            vraag += "\n\n⚠  %s: %s" % (T("start_keep"), it.keep)
        if QMessageBox.question(self, APP_NAME, vraag) != QMessageBox.StandardButton.Yes:
            return
        ok, msg = startup.disable(it)
        if not ok:
            QMessageBox.warning(self, APP_NAME, msg)
        self._refresh_startup()

    def _startup_enable(self):
        it = self._sel_startup()
        if not it or not it.uit:
            return
        ok, msg = startup.enable(it)
        if not ok:
            QMessageBox.warning(self, APP_NAME, msg)
        self._refresh_startup()

    def _run_security(self):
        self.sec_list.setPlainText(T("scanning"))
        self.sec_thread = SecThread()
        self.sec_thread.done.connect(self._sec_done)
        self.sec_thread.start()

    def _sec_done(self, checks, autoruns):
        icon = {security.OK: "✅", security.WARN: "⚠️",
                security.BAD: "❌", security.UNK: "❔"}
        html = []
        for titel, status, uitleg in checks:
            col = {security.OK: GOOD, security.WARN: WARNC,
                   security.BAD: BADC, security.UNK: ACCENT2}[status]
            html.append(f"<p style='margin:6px 0'>{icon[status]} "
                        f"<b>{titel}</b><br><span style='color:{col}'>{uitleg}</span></p>")
        self.sec_list.setHtml("".join(html))
        # de opstartitems staan nu in hun eigen beheerbare tabel
        self._refresh_startup()

    # ---------- tab: quarantaine
    def _tab_quar(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)
        self.quar_table = QTableWidget(0, 4)
        self.quar_table.setHorizontalHeaderLabels(
            ["Origineel pad" if NL else "Original path", "Detectie" if NL else "Detection",
             "Wanneer" if NL else "When", "Grootte" if NL else "Size"])
        self.quar_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.quar_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.quar_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        lay.addWidget(self.quar_table, 1)
        row = QHBoxLayout()
        row.addWidget(self._btn(T("restore"), self._restore_quar, ghost=True))
        row.addWidget(self._btn(T("delete"), self._delete_quar))
        lay.addLayout(row)
        self._quar_ids = []
        return w

    def _refresh_quar(self):
        rows = self.db.quar_list()
        self._quar_ids = [r[0] for r in rows]
        self.quar_table.setRowCount(0)
        for qid, orig, stored, sha, det, ts, size in rows:
            r = self.quar_table.rowCount()
            self.quar_table.insertRow(r)
            for c, val in enumerate([orig, det, ts, cleaner.human(size or 0)]):
                self.quar_table.setItem(r, c, QTableWidgetItem(str(val)))
        if not rows:
            self.quar_table.setRowCount(1)
            self.quar_table.setItem(0, 0, QTableWidgetItem(T("quar_empty")))

    def _sel_quar_id(self):
        sel = {i.row() for i in self.quar_table.selectedIndexes()}
        r = min(sel) if sel else -1
        if 0 <= r < len(self._quar_ids):
            return self._quar_ids[r]
        return None

    def _restore_quar(self):
        qid = self._sel_quar_id()
        if qid is None:
            return
        ok, msg = engine.restore(self.db, qid)
        QMessageBox.information(self, APP_NAME, msg)
        self._refresh_quar()

    def _delete_quar(self):
        qid = self._sel_quar_id()
        if qid is None:
            return
        if QMessageBox.question(self, APP_NAME,
                                "Definitief verwijderen?" if NL else "Delete permanently?") \
                == QMessageBox.StandardButton.Yes:
            engine.delete_quarantined(self.db, qid)
            self._refresh_quar()

    # ---------- tab: instellingen
    def _tab_settings(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)

        lay.addWidget(QLabel(T("authkey")))
        self.key_edit = QLineEdit(self.db.get_meta("auth_key", ""))
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        lay.addWidget(self.key_edit)

        row = QHBoxLayout()
        row.addWidget(self._btn(T("upd_recent"), lambda: self._update_sigs(False)))
        row.addWidget(self._btn(T("upd_full"), lambda: self._update_sigs(True), ghost=True))
        lay.addLayout(row)
        self.upd_lbl = QLabel("")
        lay.addWidget(self.upd_lbl)

        lay.addWidget(self._hr())
        self.chk = {}
        TIPS = {
            "use_yara": T("tip_yara"), "use_clam": T("tip_clam"),
            "use_heur": T("tip_heur"), "use_trash": T("tip_trash"),
        }
        for key, default in (("use_yara", True), ("use_clam", True),
                             ("use_heur", True), ("use_trash", True)):
            cb = QCheckBox(T(key))
            cb.setChecked(self.db.get_meta(key, "1") == "1")
            cb.stateChanged.connect(lambda _s, k=key: self._save_chk(k))
            cb.setToolTip(TIPS.get(key, ""))
            cb.setAccessibleDescription(TIPS.get(key, ""))
            self.chk[key] = cb
            lay.addWidget(cb)

        # --- realtime wacht
        lay.addWidget(self._hr())
        self.cb_rt = QCheckBox(T("realtime"))
        self.cb_rt.setChecked(self.db.get_meta("realtime", "0") == "1")
        self.cb_rt.stateChanged.connect(self._save_realtime)
        lay.addWidget(self.cb_rt)
        rtn = QLabel(T("rt_note"))
        rtn.setWordWrap(True)
        rtn.setStyleSheet(f"color:{ACCENT2}; font-size:15px;")
        lay.addWidget(rtn)

        # --- geplande scan
        lay.addWidget(self._hr())
        self.cb_sched = QCheckBox(T("sched_on"))
        self.cb_sched.setChecked(self.sched.on)
        self.cb_sched.stateChanged.connect(self._save_sched)
        lay.addWidget(self.cb_sched)

        srow = QHBoxLayout()
        srow.addWidget(QLabel(T("sched_when")))
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems([T("sched_weekly"), T("sched_daily")])
        self.cmb_mode.setCurrentIndex(0 if self.sched.mode == "week" else 1)
        self.cmb_day = QComboBox()
        self.cmb_day.addItems(watcher.DAGEN_NL if NL else watcher.DAGEN_EN)
        self.cmb_day.setCurrentIndex(self.sched.day)
        self.tijd = QTimeEdit()
        self.tijd.setDisplayFormat("HH:mm")
        self.tijd.setTime(QTime(self.sched.hour, self.sched.minute))
        for w2 in (self.cmb_mode, self.cmb_day, self.tijd):
            w2.setMinimumHeight(46)
            srow.addWidget(w2)
        srow.addStretch()
        lay.addLayout(srow)
        self.cmb_mode.currentIndexChanged.connect(self._save_sched)
        self.cmb_day.currentIndexChanged.connect(self._save_sched)
        self.tijd.timeChanged.connect(self._save_sched)

        self.sched_lbl = QLabel("")
        self.sched_lbl.setStyleSheet(f"color:{ACCENT2}; font-size:15px;")
        lay.addWidget(self.sched_lbl)
        self._update_sched_lbl()

        lay.addWidget(self._hr())
        lay.addWidget(self._btn("♥  " + T("donate"), lambda: self._open(DONATE)))
        info = QLabel("%s %s   ·   %s\n%s" % (APP_NAME, VERSION, CONTACT, T("admin_hint")))
        info.setStyleSheet("font-size:14px; color:#9c94c0;")
        info.setWordWrap(True)
        lay.addWidget(info)
        lay.addStretch()
        return w

    def _save_realtime(self):
        aan = self.cb_rt.isChecked()
        self.db.set_meta("realtime", "1" if aan else "0")
        if aan:
            self.fwatch.reset()          # eerste ronde = alleen inlezen, geen valse alarmen

    def _save_sched(self):
        self.sched.set("sched_on", "1" if self.cb_sched.isChecked() else "0")
        self.sched.set("sched_mode", "week" if self.cmb_mode.currentIndex() == 0 else "dag")
        self.sched.set("sched_day", self.cmb_day.currentIndex())
        t = self.tijd.time()
        self.sched.set("sched_hour", t.hour())
        self.sched.set("sched_min", t.minute())
        self._update_sched_lbl()

    def _update_sched_lbl(self):
        self.cmb_day.setVisible(self.cmb_mode.currentIndex() == 0)
        self.sched_lbl.setText(T("sched_now") % self.sched.beschrijving(NL))

    def _get_chk(self, key, default=True):
        cb = getattr(self, "chk", {}).get(key)
        if cb is not None:
            return cb.isChecked()
        return self.db.get_meta(key, "1" if default else "0") == "1"

    def _save_chk(self, key):
        self.db.set_meta(key, "1" if self.chk[key].isChecked() else "0")

    def _update_sigs(self, full):
        key = self.key_edit.text().strip()
        self.db.set_meta("auth_key", key)
        if not key:
            QMessageBox.information(self, APP_NAME, T("upd_auth"))
            return
        self.upd_lbl.setText(T("updating"))
        self.upd_thread = UpdateThread(self.db, key, full)
        self.upd_thread.step.connect(lambda s: self.upd_lbl.setText(T("updating") + " (%s)" % s))
        self.upd_thread.done.connect(self._update_done)
        self.upd_thread.start()

    def _update_done(self, new, msg):
        if msg == "ok":
            self.upd_lbl.setText(T("upd_ok") % new)
        elif msg == "auth":
            self.upd_lbl.setText(T("upd_auth"))
        else:
            self.upd_lbl.setText(T("upd_fail") % msg)
        self._refresh_home()

    # ---------- overig
    def _on_tab(self, idx):
        titel = self.tabs.tabText(idx)
        if titel == T("tab_quar"):
            self._refresh_quar()
        elif titel == T("tab_home"):
            self._refresh_home()
        elif titel == T("tab_sys"):
            self._refresh_procs()          # processen meteen inladen
        elif titel == T("tab_sec"):
            self._refresh_startup()        # opstartitems meteen inladen

    def _open(self, url):
        import webbrowser
        webbrowser.open(url)


def main():
    try:
        app = QApplication(sys.argv)
        app.setStyleSheet(STYLE)
        ico = asset("icon.ico")
        if ico:
            app.setWindowIcon(QIcon(ico))
        win = DraveGuard()
        win.show()
        try:  # Dravenlock: stille update-check (uit te zetten; Ctrl+Shift+U = met de hand)
            import drave_update
            drave_update.start(win, 'DraveGuard', VERSION)
        except Exception:
            pass
        sys.exit(app.exec())
    except Exception as e:
        try:
            with open(os.path.join(engine.CACHE, "error.log"), "a", encoding="utf-8") as f:
                import traceback
                f.write(traceback.format_exc())
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
