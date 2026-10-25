# -*- coding: utf-8 -*-
"""DraveGuard - tabblad 'Onderhoud' en het venster 'Totaal onderhoud'.

Alles kijkt eerst. Pas na jouw vinkje en klik op 'Uitvoeren' verandert er iets.
Dravenlock (Roger & Claudio).
"""
from __future__ import annotations

import os
import time

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QTextEdit, QDialog, QTreeWidget,
    QTreeWidgetItem, QProgressBar, QMessageBox, QHeaderView, QStackedWidget,
    QCheckBox)

import onderhoud as O
import engine
import cleaner
import security

NL = True
GOED, LETOP, SLECHT, ACC2 = "#57d98a", "#ffd166", "#ff6b6b", "#b59cff"
KLEUR = {O.INFO: None, O.LET_OP: LETOP, O.VERDACHT: SLECHT}
ERNST_TXT = {O.INFO: ("Info", "Info"), O.LET_OP: ("Let op", "Check"), O.VERDACHT: ("Verdacht", "Suspicious")}
SOORT_TXT = {
    "programma": ("Programma", "Program"), "taak": ("Geplande taak", "Scheduled task"),
    "dienst": ("Dienst", "Service"), "opstart": ("Opstartitem", "Startup item"),
    "extensie": ("Extensie", "Extension"), "browser": ("Browser", "Browser"),
    "beleid": ("Browser-beleid", "Browser policy"), "proxy": ("Proxy", "Proxy"),
    "hosts": ("Hosts-bestand", "Hosts file"), "schijf": ("Schijf", "Disk"),
    "update": ("Update", "Update"),
}


def L(nl, en):
    return nl if NL else en


def soort(s):
    return L(*SOORT_TXT.get(s, (s, s)))


# ---------------------------------------------------------------- werk-thread

class Klus(QThread):
    """Voert fn(say) uit in de achtergrond. say(tekst) stuurt een regel naar het venster."""
    regel = pyqtSignal(str)
    klaar = pyqtSignal(object)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            res = self.fn(lambda s: self.regel.emit(str(s)))
        except Exception as e:      # nooit het venster laten crashen
            res = e
        self.klaar.emit(res)


def _tabel(koppen):
    t = QTableWidget(0, len(koppen))
    t.setHorizontalHeaderLabels(koppen)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    t.setWordWrap(False)
    return t


def _cel(tekst, kleur=None, vink=None, tip=""):
    it = QTableWidgetItem(tekst)
    it.setToolTip(tip or tekst)
    if kleur:
        it.setForeground(QColor(kleur))
    if vink is not None:
        it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        it.setCheckState(Qt.CheckState.Checked if vink else Qt.CheckState.Unchecked)
    return it


def _fit(t):
    t.resizeColumnsToContents()
    h = t.horizontalHeader()
    for c in range(t.columnCount()):
        h.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
    h.setSectionResizeMode(t.columnCount() - 1, QHeaderView.ResizeMode.Stretch)


def _vondst_tabel(t, vondsten, vink_bij=O.VERDACHT):
    t.setRowCount(0)
    for v in vondsten:
        r = t.rowCount()
        t.insertRow(r)
        k = KLEUR.get(v.ernst)
        t.setItem(r, 0, _cel(L(*ERNST_TXT[v.ernst]), k, vink=(v.ernst >= vink_bij) if v.actie else None))
        t.setItem(r, 1, _cel(soort(v.soort)))
        t.setItem(r, 2, _cel(v.naam, tip="%s\n\n%s" % (v.naam, v.detail)))
        t.setItem(r, 3, _cel(v.reden + (("  →  " + v.actie) if v.actie else ""), k,
                             tip="%s\n\n%s\n\n%s" % (v.reden, v.detail, v.actie)))
    _fit(t)


def _aangevinkt(t, vondsten):
    uit = []
    for r in range(t.rowCount()):
        it = t.item(r, 0)
        if it and it.flags() & Qt.ItemFlag.ItemIsUserCheckable and it.checkState() == Qt.CheckState.Checked:
            if r < len(vondsten):
                uit.append(vondsten[r])
    return uit


# ---------------------------------------------------------------- het tabblad

class OnderhoudTab(QWidget):
    def __init__(self, g):
        super().__init__()
        self.g = g                     # het hoofdvenster (DraveGuard)
        self.klussen = []
        self.adw, self.brw, self.alle_ext, self.upd = [], [], [], []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)

        kop = QHBoxLayout()
        t = QLabel(L("Totaal onderhoud", "Full maintenance"))
        t.setObjectName("h2")
        kop.addWidget(t)
        kop.addStretch()
        self.btn_totaal = g._btn("🧰  " + L("Totaal onderhoud starten", "Start full maintenance"),
                                 self.start_totaal,
                                 tip=L("Maakt een herstelpunt, scant alles en laat je dan kiezen wat er gebeurt.",
                                       "Creates a restore point, checks everything, then lets you choose."))
        self.btn_totaal.setMinimumHeight(60)
        kop.addWidget(self.btn_totaal)
        lay.addLayout(kop)

        uitleg = QLabel(L("Eén knop voor alles: virussen, rommel, adware, browser, schijf en updates. "
                          "Eerst wordt er alleen gekeken; jij vinkt aan wat er moet gebeuren.",
                          "One button for everything: viruses, junk, adware, browser, disk and updates. "
                          "It only looks first; you tick what should happen."))
        uitleg.setWordWrap(True)
        uitleg.setStyleSheet("font-size:16px;")
        lay.addWidget(uitleg)

        self.admin_rij = QHBoxLayout()
        self.lbl_admin = QLabel("")
        self.lbl_admin.setWordWrap(True)
        self.admin_rij.addWidget(self.lbl_admin, 1)
        self.btn_admin = g._btn(L("Herstart als beheerder", "Restart as administrator"), self._admin, ghost=True)
        self.admin_rij.addWidget(self.btn_admin)
        lay.addLayout(self.admin_rij)
        self._admin_tekst()

        self.sub = QTabWidget()
        self.sub.addTab(self._tab_adware(), L("Adware", "Adware"))
        self.sub.addTab(self._tab_browser(), L("Browser", "Browser"))
        self.sub.addTab(self._tab_herstel(), L("Herstel en schijf", "Repair and disk"))
        self.sub.addTab(self._tab_updates(), L("Programma-updates", "Program updates"))
        lay.addWidget(self.sub, 1)

    # ---------- hulp
    def _admin_tekst(self):
        if O.is_admin():
            self.lbl_admin.setText("✅  " + L("DraveGuard draait als beheerder: alles kan.",
                                              "DraveGuard runs as administrator: everything works."))
            self.lbl_admin.setStyleSheet("color:%s; font-size:15px;" % GOED)
            self.btn_admin.setVisible(False)
        else:
            self.lbl_admin.setText("⚠  " + L("Niet als beheerder: herstelpunt, sfc/DISM, Windows.old en diensten "
                                             "lukken pas na 'Herstart als beheerder'.",
                                             "Not administrator: restore point, sfc/DISM, Windows.old and services "
                                             "need 'Restart as administrator'."))
            self.lbl_admin.setStyleSheet("color:%s; font-size:15px;" % LETOP)
            self.btn_admin.setVisible(O.WINDOWS)

    def _admin(self):
        if O.herstart_als_beheerder():
            self.g._real_quit() if hasattr(self.g, "_real_quit") else self.g.close()

    def _start(self, fn, klaar, log=None):
        k = Klus(fn)
        if log is not None:
            k.regel.connect(lambda s: log.append(s))
        k.klaar.connect(klaar)
        k.finished.connect(lambda: self.klussen.remove(k) if k in self.klussen else None)
        self.klussen.append(k)
        k.start()
        return k

    def _knoppen(self, *paren):
        rij = QHBoxLayout()
        uit = []
        for tekst, slot, ghost in paren:
            b = self.g._btn(tekst, slot, ghost=ghost)
            rij.addWidget(b)
            uit.append(b)
        rij.addStretch()
        return rij, uit

    # ---------- adware
    def _tab_adware(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        info = QLabel(L("Zoekt adware en mogelijk ongewenste programma's in je programma's, de taakplanner, "
                        "diensten en opstartitems.",
                        "Looks for adware and potentially unwanted programs in programs, scheduled tasks, "
                        "services and startup items."))
        info.setWordWrap(True)
        lay.addWidget(info)
        rij, (self.b_adw_zoek, self.b_adw_fix) = self._knoppen(
            (L("Zoeken", "Scan"), self.adware_zoeken, False),
            (L("Aangevinkte oplossen", "Fix ticked"), self.adware_oplossen, False))
        self.b_adw_fix.setEnabled(False)
        lay.addLayout(rij)
        self.lbl_adw = QLabel("")
        lay.addWidget(self.lbl_adw)
        self.t_adw = _tabel([L("Oordeel", "Verdict"), L("Soort", "Type"), L("Naam", "Name"), L("Waarom", "Why")])
        lay.addWidget(self.t_adw, 1)
        return w

    def adware_zoeken(self):
        self.b_adw_zoek.setEnabled(False)
        self.lbl_adw.setText(L("Bezig met zoeken…", "Scanning…"))
        self._start(lambda say: O.scan_adware(say), self._adware_klaar)

    def _adware_klaar(self, res):
        self.b_adw_zoek.setEnabled(True)
        if isinstance(res, Exception):
            self.lbl_adw.setText(str(res))
            return
        self.adw = res
        _vondst_tabel(self.t_adw, res)
        self.b_adw_fix.setEnabled(bool(res))
        self.lbl_adw.setText(("✅  " + L("Geen adware of ongewenste programma's gevonden.",
                                         "No adware or unwanted programs found.")) if not res else
                             L("%d gevonden. Vink aan wat weg mag en klik op 'Aangevinkte oplossen'.",
                               "%d found. Tick what may go and click 'Fix ticked'.") % len(res))

    def adware_oplossen(self):
        keus = _aangevinkt(self.t_adw, self.adw)
        if not keus or not self._ok(len(keus)):
            return
        uit = []
        for v in keus:
            ok, msg = O.doe_adware(v)
            uit.append(("✅ " if ok else "❌ ") + "%s: %s" % (v.naam, msg))
        QMessageBox.information(self, "DraveGuard", "\n".join(uit))
        self.adware_zoeken()

    def _ok(self, n):
        return QMessageBox.question(self, "DraveGuard",
                                    L("%d onderdeel/onderdelen aanpakken?", "Handle %d item(s)?") % n) == \
            QMessageBox.StandardButton.Yes

    # ---------- browser
    def _tab_browser(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        info = QLabel(L("Controleert extensies in Chrome, Edge, Brave, Vivaldi, Firefox en LibreWolf, een gekaapte "
                        "startpagina of zoekmachine, afgedwongen browser-beleid, de proxy en het hosts-bestand.",
                        "Checks extensions in Chrome, Edge, Brave, Vivaldi, Firefox and LibreWolf, a hijacked "
                        "home page or search engine, forced browser policies, the proxy and the hosts file."))
        info.setWordWrap(True)
        lay.addWidget(info)
        rij, (self.b_brw_zoek, self.b_brw_fix) = self._knoppen(
            (L("Controleren", "Check"), self.browser_zoeken, False),
            (L("Aangevinkte oplossen", "Fix ticked"), self.browser_oplossen, False))
        self.b_brw_fix.setEnabled(False)
        self.chk_alle = QCheckBox(L("Toon ook alle extensies", "Also show all extensions"))
        self.chk_alle.toggled.connect(lambda _: self._browser_toon())
        rij.insertWidget(2, self.chk_alle)
        lay.addLayout(rij)
        self.lbl_brw = QLabel("")
        self.lbl_brw.setWordWrap(True)
        lay.addWidget(self.lbl_brw)
        self.t_brw = _tabel([L("Oordeel", "Verdict"), L("Soort", "Type"), L("Naam", "Name"), L("Waarom", "Why")])
        lay.addWidget(self.t_brw, 1)
        return w

    def browser_zoeken(self):
        self.b_brw_zoek.setEnabled(False)
        self.lbl_brw.setText(L("Bezig met controleren…", "Checking…"))
        self._start(lambda say: O.scan_browsers(say), self._browser_klaar)

    def _browser_klaar(self, res):
        self.b_brw_zoek.setEnabled(True)
        if isinstance(res, Exception):
            self.lbl_brw.setText(str(res))
            return
        self.brw, self.alle_ext = res
        self._browser_toon()

    def _browser_toon(self):
        lijst = list(self.brw)
        if self.chk_alle.isChecked():
            bekend = {v.data.get("id") for v in self.brw if v.soort == "extensie"}
            for e in sorted(self.alle_ext, key=lambda x: (x["browser"], x["naam"].lower())):
                if e["id"] in bekend:
                    continue
                lijst.append(O.Vondst("extensie", "%s  (%s, %s)" % (e["naam"], e["browser"], e["profiel"]),
                                      e["id"], O.INFO,
                                      (L("Aan", "On") if e["aan"] else L("Uit", "Off")) + " · " +
                                      (L("uit de winkel", "from the store") if e["winkel"] else L("niet uit de winkel", "not from store")) +
                                      (" · " + L("mag alle sites lezen", "can read all sites") if e["breed"] else ""),
                                      L("Extensiepagina openen", "Open extensions page"), e))
        self.brw_toon = lijst
        _vondst_tabel(self.t_brw, lijst)
        self.b_brw_fix.setEnabled(bool(lijst))
        n_ext = len(self.alle_ext)
        if not self.brw:
            self.lbl_brw.setText("✅  " + L("Niets verdachts gevonden. %d extensies gecontroleerd, startpagina, zoekmachine, "
                                            "beleid, proxy en hosts-bestand zijn in orde.",
                                            "Nothing suspicious. %d extensions checked; home page, search engine, "
                                            "policies, proxy and hosts file are fine.") % n_ext)
        else:
            self.lbl_brw.setText(L("%d punt(en) om naar te kijken (van %d extensies).",
                                   "%d item(s) to look at (of %d extensions).") % (len(self.brw), n_ext))

    def browser_oplossen(self):
        keus = _aangevinkt(self.t_brw, getattr(self, "brw_toon", self.brw))
        if not keus or not self._ok(len(keus)):
            return
        uit, geopend = [], set()
        for v in keus:
            if v.soort in ("extensie", "browser"):
                sl = (v.data.get("exe"), v.data.get("pagina"))
                if sl in geopend:
                    continue
                geopend.add(sl)
            ok, msg = O.doe_browser(v)
            uit.append(("✅ " if ok else "❌ ") + "%s: %s" % (v.naam, msg))
        QMessageBox.information(self, "DraveGuard", "\n".join(uit))

    # ---------- herstel en schijf
    def _tab_herstel(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        rij1, (self.b_punt, self.b_sfc, self.b_dism) = self._knoppen(
            ("🛟  " + L("Herstelpunt maken", "Create restore point"), self.herstelpunt, False),
            (L("Windows-bestanden controleren (sfc)", "Check Windows files (sfc)"), lambda: self._lang(O.doe_sfc, "sfc"), True),
            (L("Windows repareren (DISM)", "Repair Windows (DISM)"), lambda: self._lang(O.doe_dism, "DISM"), True))
        lay.addLayout(rij1)
        rij2, (self.b_sxs, self.b_old, self.b_disk) = self._knoppen(
            (L("Onderdelen-opslag opruimen (WinSxS)", "Clean component store (WinSxS)"), lambda: self._lang(O.doe_winsxs, "WinSxS"), True),
            (L("Windows.old verwijderen", "Remove Windows.old"), self.windows_old, True),
            (L("Schijven controleren", "Check disks"), self.schijf_zoeken, True))
        lay.addLayout(rij2)
        tip = QLabel(L("Tip: sfc en DISM duren elk 10 tot 30 minuten. Je kunt intussen gewoon doorwerken.",
                       "Tip: sfc and DISM each take 10 to 30 minutes. You can keep working."))
        tip.setStyleSheet("color:%s; font-size:15px;" % ACC2)
        lay.addWidget(tip)
        self.t_disk = _tabel([L("Oordeel", "Verdict"), L("Soort", "Type"), L("Schijf", "Disk"), L("Uitleg", "Details")])
        self.t_disk.setMaximumHeight(170)
        lay.addWidget(self.t_disk)
        self.log_h = QTextEdit()
        self.log_h.setReadOnly(True)
        self.log_h.setPlaceholderText(L("Hier zie je wat er gebeurt.", "Progress appears here."))
        lay.addWidget(self.log_h, 1)
        return w

    def _knoppen_herstel(self, aan):
        for b in (self.b_punt, self.b_sfc, self.b_dism, self.b_sxs, self.b_old):
            b.setEnabled(aan)

    def herstelpunt(self):
        self._knoppen_herstel(False)
        self.log_h.append(L("Herstelpunt maken…", "Creating restore point…"))
        self._start(lambda say: O.herstelpunt_maken(), self._herstel_klaar)

    def _lang(self, fn, naam):
        if not O.is_admin():
            QMessageBox.information(self, "DraveGuard", L("Hiervoor moet DraveGuard als beheerder draaien.",
                                                          "This needs DraveGuard to run as administrator."))
            return
        self._knoppen_herstel(False)
        self.log_h.append("— %s —" % naam)
        self._start(lambda say: fn(say), self._herstel_klaar, log=self.log_h)

    def windows_old(self):
        p, g = O.windows_old()
        if not g:
            QMessageBox.information(self, "DraveGuard", L("Er is geen Windows.old op deze pc.", "There is no Windows.old."))
            return
        if QMessageBox.question(self, "DraveGuard", L(
                "Windows.old is %s groot. Hierin staat je vorige Windows-versie. Na verwijderen kun je niet meer "
                "terug naar die versie. Verwijderen?",
                "Windows.old is %s. It holds your previous Windows version; after removal you cannot go back. Remove?")
                % O.human(g)) != QMessageBox.StandardButton.Yes:
            return
        self._lang(O.doe_windows_old, "Windows.old")

    def _herstel_klaar(self, res):
        self._knoppen_herstel(True)
        if isinstance(res, Exception):
            self.log_h.append("❌ %s" % res)
            return
        ok, msg = res
        self.log_h.append(("✅ " if ok else "❌ ") + msg)

    def schijf_zoeken(self):
        self.b_disk.setEnabled(False)
        self._start(lambda say: O.scan_schijf(), self._schijf_klaar)

    def _schijf_klaar(self, res):
        self.b_disk.setEnabled(True)
        if isinstance(res, Exception):
            self.log_h.append(str(res))
            return
        self.t_disk.setRowCount(0)
        for v in res:
            r = self.t_disk.rowCount()
            self.t_disk.insertRow(r)
            k = KLEUR.get(v.ernst) or GOED
            self.t_disk.setItem(r, 0, _cel(L("Gezond", "Healthy") if v.ernst == O.INFO else L(*ERNST_TXT[v.ernst]), k))
            self.t_disk.setItem(r, 1, _cel(v.detail))
            self.t_disk.setItem(r, 2, _cel(v.naam))
            self.t_disk.setItem(r, 3, _cel(v.reden, k))
        _fit(self.t_disk)

    # ---------- updates
    def _tab_updates(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        info = QLabel(L("Zoekt via winget (van Microsoft) welke programma's een nieuwere versie hebben.",
                        "Uses winget (by Microsoft) to find programs with a newer version."))
        info.setWordWrap(True)
        lay.addWidget(info)
        rij, (self.b_upd_zoek, self.b_upd_doe) = self._knoppen(
            (L("Updates zoeken", "Find updates"), self.updates_zoeken, False),
            (L("Aangevinkte bijwerken", "Update ticked"), self.updates_doen, False))
        self.b_upd_doe.setEnabled(False)
        lay.addLayout(rij)
        self.lbl_upd = QLabel("")
        lay.addWidget(self.lbl_upd)
        self.t_upd = _tabel(["", L("Programma", "Program"), L("Nu", "Now"), L("Nieuw", "New")])
        lay.addWidget(self.t_upd, 1)
        self.log_u = QTextEdit()
        self.log_u.setReadOnly(True)
        self.log_u.setMaximumHeight(120)
        lay.addWidget(self.log_u)
        return w

    def updates_zoeken(self):
        self.b_upd_zoek.setEnabled(False)
        self.lbl_upd.setText(L("Bezig met zoeken (kan een halve minuut duren)…", "Searching (may take half a minute)…"))
        self._start(lambda say: O.updates_zoeken(), self._updates_klaar)

    def _updates_klaar(self, res):
        self.b_upd_zoek.setEnabled(True)
        if isinstance(res, Exception):
            self.lbl_upd.setText(str(res))
            return
        self.upd, msg = res
        self.lbl_upd.setText(msg)
        self.t_upd.setRowCount(0)
        for u in self.upd:
            r = self.t_upd.rowCount()
            self.t_upd.insertRow(r)
            self.t_upd.setItem(r, 0, _cel("", vink=True))
            self.t_upd.setItem(r, 1, _cel(u["naam"], tip="%s\n%s" % (u["naam"], u["id"])))
            self.t_upd.setItem(r, 2, _cel(u["versie"]))
            self.t_upd.setItem(r, 3, _cel(u["nieuw"], GOED))
        _fit(self.t_upd)
        self.t_upd.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.t_upd.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.b_upd_doe.setEnabled(bool(self.upd))

    def updates_doen(self):
        keus = [self.upd[r] for r in range(self.t_upd.rowCount())
                if self.t_upd.item(r, 0).checkState() == Qt.CheckState.Checked and r < len(self.upd)]
        if not keus or not self._ok(len(keus)):
            return
        self.b_upd_doe.setEnabled(False)

        def werk(say):
            uit = []
            for i, u in enumerate(keus, 1):
                say("(%d/%d) %s …" % (i, len(keus), u["naam"]))
                ok, msg = O.update_een(u["id"])
                uit.append((u, ok))
                say(("✅ " if ok else "❌ ") + u["naam"])
            return uit
        self._start(werk, lambda r: (self.log_u.append(L("Klaar.", "Done.")), self.updates_zoeken()), log=self.log_u)

    # ---------- totaal
    def start_totaal(self):
        TotaalDialoog(self.g, self).exec()


# ---------------------------------------------------------------- Totaal onderhoud

STAPPEN = [
    ("punt", ("Herstelpunt maken", "Create restore point")),
    ("virus", ("Virussen en malware zoeken", "Scan for viruses and malware")),
    ("rommel", ("Rommel zoeken", "Find junk")),
    ("adware", ("Adware en ongewenste programma's", "Adware and unwanted programs")),
    ("browser", ("Browser-controle", "Browser check")),
    ("veilig", ("Beveiliging van Windows", "Windows security")),
    ("schijf", ("Schijfgezondheid", "Disk health")),
    ("updates", ("Programma-updates", "Program updates")),
]


class TotaalDialoog(QDialog):
    def __init__(self, g, tab):
        super().__init__(g)
        self.g, self.tab = g, tab
        self.setWindowTitle(L("DraveGuard - Totaal onderhoud", "DraveGuard - Full maintenance"))
        self.resize(980, 760)
        self.res = {}
        self.klus = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        self.titel = QLabel(L("Totaal onderhoud", "Full maintenance"))
        self.titel.setObjectName("h2")
        lay.addWidget(self.titel)
        self.uitleg = QLabel(L("Stap 1: DraveGuard kijkt overal. Er wordt nog niets veranderd (alleen een herstelpunt gemaakt).",
                               "Step 1: DraveGuard checks everything. Nothing is changed yet (only a restore point)."))
        self.uitleg.setWordWrap(True)
        lay.addWidget(self.uitleg)
        self.balk = QProgressBar()
        self.balk.setRange(0, len(STAPPEN))
        lay.addWidget(self.balk)

        self.stack = QStackedWidget()
        # pagina 1: stappen
        p1 = QWidget()
        l1 = QVBoxLayout(p1)
        self.stap_lbl = {}
        for k, (nl, en) in STAPPEN:
            q = QLabel("○  " + L(nl, en))
            q.setStyleSheet("font-size:19px; padding:4px;")
            l1.addWidget(q)
            self.stap_lbl[k] = q
        self.lbl_nu = QLabel("")
        self.lbl_nu.setStyleSheet("color:%s; font-size:15px;" % ACC2)
        self.lbl_nu.setWordWrap(True)
        l1.addWidget(self.lbl_nu)
        l1.addStretch()
        self.stack.addWidget(p1)
        # pagina 2: rapport
        self.boom = QTreeWidget()
        self.boom.setHeaderLabels([L("Wat", "What"), L("Uitleg", "Details")])
        self.boom.setColumnWidth(0, 470)
        self.boom.setStyleSheet("QTreeWidget { font-size:17px; } QTreeView::item { padding:4px; }")
        self.stack.addWidget(self.boom)
        # pagina 3: uitvoeren
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.stack.addWidget(self.log)
        lay.addWidget(self.stack, 1)

        rij = QHBoxLayout()
        rij.addStretch()
        self.b_doe = g._btn(L("Aangevinkte uitvoeren", "Run ticked"), self.uitvoeren)
        self.b_doe.setVisible(False)
        rij.addWidget(self.b_doe)
        self.b_rap = g._btn(L("Rapport openen", "Open report"), self._open_rapport, ghost=True)
        self.b_rap.setVisible(False)
        rij.addWidget(self.b_rap)
        self.b_sluit = g._btn(L("Sluiten", "Close"), self.close, ghost=True)
        rij.addWidget(self.b_sluit)
        lay.addLayout(rij)
        self.rapport_pad = ""
        self._scan()

    # ---------- stap 1: kijken
    def _stap(self, k, staat, extra=""):
        nl, en = dict(STAPPEN)[k]
        teken = {"bezig": "⏳", "ok": "✅", "let": "⚠", "fout": "❌", "over": "⏭"}[staat]
        kleur = {"bezig": ACC2, "ok": GOED, "let": LETOP, "fout": SLECHT, "over": "#8880a5"}[staat]
        self.stap_lbl[k].setText("%s  %s%s" % (teken, L(nl, en), ("   —  " + extra) if extra else ""))
        self.stap_lbl[k].setStyleSheet("font-size:19px; padding:4px; color:%s;" % kleur)

    def _scan(self):
        g = self.g
        db = g.db
        scanner = g._make_scanner()
        cats = cleaner.build_categories()
        for c in cats:
            cb = getattr(g, "clean_checks", {}).get(c.key)
            if cb is not None:
                c.enabled = cb.isChecked()
        self.cats = cats

        def werk(say):
            r = {}
            say("stap:punt")
            r["punt"] = O.herstelpunt_maken() if O.is_admin() else (None, L("Niet als beheerder: overgeslagen.",
                                                                          "Not administrator: skipped."))
            say("stap:virus")
            vond = []
            scanner.run(engine.quick_targets(), deep=True,
                        on_file=lambda i, n, p: say("info:%d / %d  %s" % (i, n, os.path.basename(p)[:60])) if i % 25 == 0 else None,
                        on_finding=lambda f: vond.append(f) if f.is_threat else None)
            r["virus"] = (vond, scanner.stats)
            say("stap:rommel")
            tot = cleaner.scan_all(cats, on_progress=lambda i, n, s: say("info:" + s))
            r["rommel"] = tot
            say("stap:adware")
            r["adware"] = O.scan_adware(lambda s: say("info:" + s))
            say("stap:browser")
            r["browser"] = O.scan_browsers(lambda s: say("info:" + s))
            say("stap:veilig")
            try:
                r["veilig"] = security.run_all_checks()
            except Exception:
                r["veilig"] = []
            say("stap:schijf")
            r["schijf"] = O.scan_schijf()
            say("stap:updates")
            r["updates"] = O.scan_updates()
            return r

        self.huidig = None
        self.klus = Klus(werk)
        self.klus.regel.connect(self._regel)
        self.klus.klaar.connect(self._scan_klaar)
        self.klus.start()

    def _regel(self, s):
        if s.startswith("stap:"):
            k = s[5:]
            if self.huidig:
                self._stap(self.huidig, "ok")
                self.balk.setValue(self.balk.value() + 1)
            self.huidig = k
            self._stap(k, "bezig")
        elif s.startswith("info:"):
            self.lbl_nu.setText(s[5:])

    def _scan_klaar(self, r):
        if isinstance(r, Exception):
            self.lbl_nu.setText("❌ %s" % r)
            return
        self.res = r
        self.balk.setValue(len(STAPPEN))
        # stappen samenvatten
        ok, msg = r["punt"]
        self._stap("punt", "ok" if ok else ("over" if ok is None else "fout"), msg)
        vond, st = r["virus"]
        self._stap("virus", "fout" if vond else "ok", L("%d bestanden, %d bedreiging(en)", "%d files, %d threat(s)") % (st.scanned, len(vond)))
        self._stap("rommel", "let" if r["rommel"] > 200 * 1024 ** 2 else "ok", O.human(r["rommel"]))
        self._stap("adware", "let" if r["adware"] else "ok", str(len(r["adware"])))
        self._stap("browser", "let" if r["browser"][0] else "ok",
                   L("%d punten, %d extensies", "%d items, %d extensions") % (len(r["browser"][0]), len(r["browser"][1])))
        slecht = [x for x in r["veilig"] if x[1] in (security.BAD, security.WARN)]
        self._stap("veilig", "let" if slecht else "ok", str(len(slecht)) if slecht else L("in orde", "fine"))
        dsl = [v for v in r["schijf"] if v.ernst > O.INFO]
        self._stap("schijf", "fout" if any(v.ernst == O.VERDACHT for v in dsl) else ("let" if dsl else "ok"),
                   L("%d schijf/schijven", "%d disk(s)") % len(r["schijf"]))
        self._stap("updates", "let" if r["updates"][0] else "ok", r["updates"][1])
        self.lbl_nu.setText("")
        self._rapport_bouwen()

    # ---------- stap 2: rapport met vinkjes
    def _groep(self, titel, n, kleur=None):
        it = QTreeWidgetItem([titel, ""])
        f = it.font(0)
        f.setBold(True)
        it.setFont(0, f)
        if kleur:
            it.setForeground(0, QColor(kleur))
        it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
        self.boom.addTopLevelItem(it)
        it.setExpanded(n <= 12)
        return it

    def _kind(self, ouder, tekst, uitleg, actie, vink=True, kleur=None, vinkbaar=True):
        it = QTreeWidgetItem([tekst, uitleg])
        it.setToolTip(0, tekst)
        it.setToolTip(1, uitleg)
        if kleur:
            it.setForeground(0, QColor(kleur))
            it.setForeground(1, QColor(kleur))
        if vinkbaar:
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(0, Qt.CheckState.Checked if vink else Qt.CheckState.Unchecked)
        it.setData(0, Qt.ItemDataRole.UserRole, actie)
        ouder.addChild(it)
        return it

    def _rapport_bouwen(self):
        r = self.res
        b = self.boom
        b.clear()
        vond, _ = r["virus"]
        if vond:
            gr = self._groep(L("🦠  Bedreigingen (%d) - naar quarantaine", "🦠  Threats (%d) - to quarantine") % len(vond), len(vond), SLECHT)
            for f in vond:
                self._kind(gr, os.path.basename(f.path), "%s  (%s)" % (f.detection, O._nep_pad(f.path)), ("virus", f), True, SLECHT)
        if r["rommel"] > 0:
            gr = self._groep(L("🧹  Rommel opruimen (%s)", "🧹  Clean junk (%s)") % O.human(r["rommel"]), 20)
            for c in self.cats:
                if c.enabled and c.bytes:
                    self._kind(gr, c.naam_nl if NL else c.naam_en, "%s  (%d)" % (O.human(c.bytes), len(c.files)), ("rommel", c), True)
        if r["adware"]:
            gr = self._groep(L("🧩  Adware en ongewenste programma's (%d)", "🧩  Adware and unwanted programs (%d)") % len(r["adware"]),
                             len(r["adware"]), LETOP)
            for v in r["adware"]:
                self._kind(gr, "%s: %s" % (soort(v.soort), v.naam), "%s  →  %s" % (v.reden, v.actie), ("adware", v),
                           v.ernst >= O.VERDACHT, KLEUR.get(v.ernst))
        bv, _alle = r["browser"]
        if bv:
            gr = self._groep(L("🌐  Browser (%d)", "🌐  Browser (%d)") % len(bv), len(bv), LETOP)
            for v in bv:
                self._kind(gr, "%s: %s" % (soort(v.soort), v.naam), "%s  →  %s" % (v.reden, v.actie), ("browser", v),
                           v.ernst >= O.VERDACHT and v.soort in ("beleid", "hosts"), KLEUR.get(v.ernst))
        if r["updates"][0]:
            gr = self._groep(L("⬆  Programma-updates (%d)", "⬆  Program updates (%d)") % len(r["updates"][0]), 6)
            for v in r["updates"][0]:
                self._kind(gr, v.naam, v.detail, ("update", v), True)
        # extra onderhoud
        gr = self._groep(L("🛠  Extra onderhoud (duurt langer)", "🛠  Extra maintenance (takes longer)"), 3)
        admin = O.is_admin()
        nb = "" if admin else L("  (beheerder nodig)", "  (administrator needed)")
        self._kind(gr, L("Windows-bestanden controleren en repareren (sfc)", "Check and repair Windows files (sfc)"),
                   L("10 tot 30 minuten", "10 to 30 minutes") + nb, ("sfc", None), False)
        self._kind(gr, L("Onderdelen-opslag opruimen (WinSxS)", "Clean component store (WinSxS)"),
                   L("Ruimt oude Windows-onderdelen op, 5 tot 15 minuten", "Removes old Windows components, 5-15 min") + nb,
                   ("winsxs", None), False)
        pold, gold = O.windows_old()
        if gold:
            self._kind(gr, L("Windows.old verwijderen", "Remove Windows.old"),
                       L("%s - je kunt daarna niet meer terug naar de vorige Windows", "%s - you cannot go back afterwards") % O.human(gold) + nb,
                       ("winold", None), False)
        # alleen ter info
        info = []
        for t_, st, u in r["veilig"]:
            if st in (security.BAD, security.WARN):
                info.append((t_, u, SLECHT if st == security.BAD else LETOP))
        for v in r["schijf"]:
            info.append((v.naam, "%s  %s" % (v.detail, v.reden), KLEUR.get(v.ernst) or GOED))
        if info:
            gr = QTreeWidgetItem([L("ℹ  Ter info (daar hoef je niets voor aan te vinken)", "ℹ  For your information"), ""])
            f = gr.font(0)
            f.setBold(True)
            gr.setFont(0, f)
            b.addTopLevelItem(gr)
            for t_, u, k in info:
                self._kind(gr, t_, u, None, kleur=k, vinkbaar=False)
            gr.setExpanded(True)
        ok, msg = r["punt"]
        n_vink = sum(1 for i in range(b.topLevelItemCount()) for j in range(b.topLevelItem(i).childCount())
                     if b.topLevelItem(i).child(j).data(0, Qt.ItemDataRole.UserRole))
        self.titel.setText(L("Rapport", "Report"))
        self.uitleg.setText(L("Stap 2: vink aan wat er moet gebeuren en klik op 'Aangevinkte uitvoeren'. "
                              "Bedreigingen, rommel en updates staan al aan; twijfelgevallen niet.",
                              "Step 2: tick what should happen and click 'Run ticked'. Threats, junk and updates "
                              "are ticked; doubtful items are not.") +
                            ("\n🛟 " + msg if msg else ""))
        self.stack.setCurrentIndex(1)
        self.b_doe.setVisible(n_vink > 0)
        self._bewaar_rapport([L("RESULTAAT VAN HET KIJKEN", "SCAN RESULT")] + self._rapport_regels())

    def _rapport_regels(self):
        uit = []
        b = self.boom
        for i in range(b.topLevelItemCount()):
            g = b.topLevelItem(i)
            uit.append("")
            uit.append(g.text(0))
            for j in range(g.childCount()):
                c = g.child(j)
                v = ""
                if c.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                    v = "[x] " if c.checkState(0) == Qt.CheckState.Checked else "[ ] "
                uit.append("   %s%s  -  %s" % (v, c.text(0), c.text(1)))
        return uit

    def _bewaar_rapport(self, regels):
        try:
            self.rapport_pad = O.rapport_opslaan(regels)
            self.b_rap.setVisible(True)
        except Exception:
            pass

    def _open_rapport(self):
        if self.rapport_pad:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.rapport_pad))

    # ---------- stap 3: uitvoeren
    def uitvoeren(self):
        acties = []
        b = self.boom
        for i in range(b.topLevelItemCount()):
            g = b.topLevelItem(i)
            for j in range(g.childCount()):
                c = g.child(j)
                a = c.data(0, Qt.ItemDataRole.UserRole)
                if a and c.flags() & Qt.ItemFlag.ItemIsUserCheckable and c.checkState(0) == Qt.CheckState.Checked:
                    acties.append((a, c.text(0)))
        if not acties:
            QMessageBox.information(self, "DraveGuard", L("Er is niets aangevinkt.", "Nothing is ticked."))
            return
        if QMessageBox.question(self, "DraveGuard", L("%d onderdelen uitvoeren?", "Run %d items?") % len(acties)) != \
                QMessageBox.StandardButton.Yes:
            return
        vooraf = self._rapport_regels()
        self.b_doe.setVisible(False)
        self.b_sluit.setEnabled(False)
        self.stack.setCurrentIndex(2)
        self.titel.setText(L("Bezig…", "Working…"))
        self.uitleg.setText(L("Stap 3: DraveGuard voert uit wat je aanvinkte. Je kunt meekijken.",
                              "Step 3: DraveGuard runs what you ticked."))
        self.balk.setRange(0, len(acties))
        self.balk.setValue(0)
        db = self.g.db
        use_trash = self.g._get_chk("use_trash", True)
        browser_open = set()

        def werk(say):
            uitslag = []
            gedaan_rommel = 0.0
            for n, ((soort_, obj), tekst) in enumerate(acties, 1):
                say("balk:%d" % (n - 1))
                say("▶ " + tekst)
                ok, msg = False, ""
                try:
                    if soort_ == "virus":
                        ok, msg = engine.quarantine(db, obj.path, obj.detection)
                        msg = L("in quarantaine", "quarantined") if ok else str(msg)
                    elif soort_ == "rommel":
                        d, vrij, err = cleaner.clean_category(obj, use_trash=use_trash)
                        cleaner.prune_empty_dirs(obj)
                        gedaan_rommel += vrij
                        ok, msg = True, "%s (%d %s%s)" % (O.human(vrij), d, L("bestanden", "files"),
                                                         (", %d %s" % (err, L("in gebruik", "in use"))) if err else "")
                    elif soort_ == "adware":
                        ok, msg = O.doe_adware(obj)
                    elif soort_ == "browser":
                        sl = (obj.data.get("exe"), obj.data.get("pagina"))
                        if obj.soort in ("extensie", "browser") and sl in browser_open:
                            ok, msg = True, L("pagina was al geopend", "page already open")
                        else:
                            browser_open.add(sl)
                            ok, msg = O.doe_browser(obj)
                    elif soort_ == "update":
                        ok, msg = O.update_een(obj.data["id"])
                    elif soort_ == "sfc":
                        ok, msg = O.doe_sfc(lambda s: say("   " + s))
                    elif soort_ == "winsxs":
                        ok, msg = O.doe_winsxs(lambda s: say("   " + s))
                    elif soort_ == "winold":
                        ok, msg = O.doe_windows_old(lambda s: say("   " + s))
                except Exception as e:
                    ok, msg = False, str(e)
                say(("   ✅ " if ok else "   ❌ ") + (msg or ""))
                uitslag.append((tekst, ok, msg))
            say("balk:%d" % len(acties))
            return uitslag

        self.klus = Klus(werk)
        self.klus.regel.connect(self._doe_regel)
        self.klus.klaar.connect(lambda u: self._doe_klaar(u, vooraf))
        self.klus.start()

    def _doe_regel(self, s):
        if s.startswith("balk:"):
            self.balk.setValue(int(s[5:]))
        else:
            self.log.append(s)

    def _doe_klaar(self, uitslag, vooraf):
        self.b_sluit.setEnabled(True)
        if isinstance(uitslag, Exception):
            self.log.append("❌ %s" % uitslag)
            return
        goed = sum(1 for _, ok, _m in uitslag if ok)
        self.titel.setText(L("Klaar!", "Done!"))
        self.uitleg.setText(L("%d van %d gelukt. Het rapport is bewaard.", "%d of %d succeeded. The report was saved.")
                            % (goed, len(uitslag)))
        regels = vooraf + ["", L("UITGEVOERD", "DONE")] + \
            ["   %s %s  -  %s" % ("OK " if ok else "MIS", t_, m) for t_, ok, m in uitslag]
        self._bewaar_rapport(regels)
        try:
            self.g._refresh_home()
        except Exception:
            pass

    def closeEvent(self, e):
        if self.klus and self.klus.isRunning():
            if QMessageBox.question(self, "DraveGuard", L("DraveGuard is nog bezig. Toch sluiten? (Het werk gaat op de "
                                                          "achtergrond door tot de huidige stap klaar is.)",
                                                          "Still working. Close anyway?")) != \
                    QMessageBox.StandardButton.Yes:
                e.ignore()
                return
            self.tab.klussen.append(self.klus)     # thread levend houden
        super().closeEvent(e)
