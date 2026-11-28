# -*- coding: utf-8 -*-
"""DraveGuard - tabblad 'Wachter' (27-11-2026, idee van pa).

Kijkt na een Windows-update of je privacy-instellingen nog kloppen, wat er nieuw meestart
en welke programma's nu met internet praten. ALLEEN LEZEN: er verandert niets aan je pc.
Dravenlock (Roger & Claudio). GNU GPL v3.0.
"""
from __future__ import annotations

import os
import time

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
                             QTableWidgetItem, QAbstractItemView, QHeaderView, QTabWidget)

import wachter as W

NL = True
GOED_K, LETOP_K, SLECHT_K, ONB_K = "#57d98a", "#ffd166", "#ff6b6b", "#b59cff"
KLEUR = {W.GOED: GOED_K, W.LET_OP: LETOP_K, W.SLECHT: SLECHT_K, W.ONBEKEND: ONB_K}
TEKEN = {W.GOED: "✅", W.LET_OP: "⚠️", W.SLECHT: "❌", W.ONBEKEND: "❔"}


def L(nl, en):
    return nl if NL else en


class _Klus(QThread):
    klaar = pyqtSignal(object)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            res = self.fn()
        except Exception as e:          # nooit het venster laten crashen
            res = e
        self.klaar.emit(res)


def _tabel(koppen):
    t = QTableWidget(0, len(koppen))
    t.setHorizontalHeaderLabels(koppen)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    t.setWordWrap(True)
    t.setStyleSheet("font-size:16px;")
    h = t.horizontalHeader()
    for i in range(len(koppen)):
        h.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch if i >= 2 else QHeaderView.ResizeMode.ResizeToContents)
    return t


def _cel(tekst, kleur=None):
    it = QTableWidgetItem(tekst)
    it.setToolTip(tekst)
    if kleur:
        it.setForeground(QColor(kleur))
    return it


class WachterTab(QWidget):
    def __init__(self, g, cache_map):
        super().__init__()
        self.g = g
        self.map = cache_map
        self.klus = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)
        kop = QLabel("🛡️  " + L("Wachter — is je pc nog van jou?", "Guard — is your pc still yours?"))
        kop.setObjectName("h2")
        lay.addWidget(kop)
        uitleg = QLabel(L("Windows zet na een update soms stiekem dingen weer aan. De Wachter kijkt of je instellingen "
                          "nog kloppen, wat er nieuw meestart en wie er met internet praat. Hij kijkt alleen: "
                          "er verandert niets aan je pc.",
                          "After an update Windows sometimes quietly switches things back on. The Guard checks your "
                          "settings, what new starts with Windows and who talks to the internet. It only looks: "
                          "nothing on your pc is changed."))
        uitleg.setWordWrap(True)
        uitleg.setStyleSheet("font-size:17px;")
        lay.addWidget(uitleg)

        rij = QHBoxLayout()
        self.knop = QPushButton("🔍  " + L("Nu controleren", "Check now"))
        self.knop.setMinimumHeight(52)
        self.knop.setStyleSheet("font-size:20px;font-weight:bold;padding:8px 22px;")
        self.knop.clicked.connect(self.controleer)
        rij.addWidget(self.knop)
        rij.addStretch(1)
        lay.addLayout(rij)

        self.banner = QLabel("")
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet("font-size:19px;font-weight:bold;padding:10px;border-radius:8px;")
        lay.addWidget(self.banner)

        self.sub = QTabWidget()
        self.t_priv = _tabel(["", L("Onderdeel", "Item"), L("Wat is het", "What is it"), L("Zo zet je het uit", "How to switch off")])
        self.t_start = _tabel(["", L("Soort", "Type"), L("Naam", "Name"), L("Wat start er", "What starts")])
        self.t_net = _tabel(["", L("Programma", "Program"), L("Verbindingen", "Connections"), L("Advies", "Advice")])
        self.sub.addTab(self.t_priv, "🔒 " + L("Privacy", "Privacy"))
        self.sub.addTab(self.t_start, "🚀 " + L("Nieuw bij opstarten", "New at startup"))
        self.sub.addTab(self.t_net, "🌐 " + L("Wie praat met internet", "Who talks to the internet"))
        lay.addWidget(self.sub, 1)
        self._zet_banner(L("Klik op 'Nu controleren'. Het duurt een paar seconden.",
                           "Click 'Check now'. It takes a few seconds."), ONB_K)

    def _zet_banner(self, tekst, kleur):
        self.banner.setText(tekst)
        self.banner.setStyleSheet("font-size:19px;font-weight:bold;padding:10px;border-radius:8px;"
                                  "border:2px solid %s;color:%s;" % (kleur, kleur))

    def controleer(self):
        if self.klus and self.klus.isRunning():
            return
        self.knop.setEnabled(False)
        self._zet_banner(L("Even kijken...", "Checking..."), ONB_K)
        taal = "nl" if NL else "en"

        def werk():
            priv, veranderd, eerste, vorige = W.privacy_veranderd(self.map, taal)
            opstart = W.kijk_opstart_nieuw(self.map, taal)
            net = W.naar_buiten(taal)
            return priv, veranderd, eerste, vorige, opstart, net

        self.klus = _Klus(werk)
        self.klus.klaar.connect(self._klaar)
        self.klus.start()

    def _klaar(self, res):
        self.knop.setEnabled(True)
        if isinstance(res, Exception):
            self._zet_banner(L("Het controleren lukte niet: %s", "The check failed: %s") % res, SLECHT_K)
            return
        priv, veranderd, eerste, vorige, opstart, net = res
        # privacy
        self.t_priv.setRowCount(0)
        for b in sorted(priv, key=lambda x: {W.SLECHT: 0, W.LET_OP: 1, W.ONBEKEND: 2, W.GOED: 3}[x["status"]]):
            r = self.t_priv.rowCount()
            self.t_priv.insertRow(r)
            k = KLEUR[b["status"]]
            self.t_priv.setItem(r, 0, _cel(TEKEN[b["status"]]))
            self.t_priv.setItem(r, 1, _cel(b["titel"], k))
            self.t_priv.setItem(r, 2, _cel(b["uitleg"]))
            self.t_priv.setItem(r, 3, _cel(b["advies"] or L("Niets te doen.", "Nothing to do.")))
        self.t_priv.resizeRowsToContents()
        # opstart
        self.t_start.setRowCount(0)
        o = opstart[0]
        for v in o["extra"].get("nieuw", []):
            r = self.t_start.rowCount()
            self.t_start.insertRow(r)
            self.t_start.setItem(r, 0, _cel("🆕"))
            self.t_start.setItem(r, 1, _cel(L(*W.SOORT_NAAM.get(v["soort"], (v["soort"], v["soort"])))))
            self.t_start.setItem(r, 2, _cel(v["naam"], LETOP_K))
            self.t_start.setItem(r, 3, _cel(v["wat"]))
        for v in o["extra"].get("weg", []):
            r = self.t_start.rowCount()
            self.t_start.insertRow(r)
            self.t_start.setItem(r, 0, _cel("➖"))
            self.t_start.setItem(r, 1, _cel(L(*W.SOORT_NAAM.get(v["soort"], (v["soort"], v["soort"])))))
            self.t_start.setItem(r, 2, _cel(v["naam"] + L("  (weg)", "  (gone)")))
            self.t_start.setItem(r, 3, _cel(v["wat"]))
        if self.t_start.rowCount() == 0:
            self.t_start.insertRow(0)
            self.t_start.setItem(0, 0, _cel(TEKEN[o["status"]]))
            self.t_start.setItem(0, 1, _cel(""))
            self.t_start.setItem(0, 2, _cel(o["titel"], KLEUR[o["status"]]))
            self.t_start.setItem(0, 3, _cel(o["uitleg"]))
        self.t_start.resizeRowsToContents()
        # internet
        self.t_net.setRowCount(0)
        for b in net:
            r = self.t_net.rowCount()
            self.t_net.insertRow(r)
            k = KLEUR[b["status"]]
            self.t_net.setItem(r, 0, _cel(TEKEN[b["status"]]))
            self.t_net.setItem(r, 1, _cel(b["titel"], k))
            c = _cel(b["uitleg"])
            c.setToolTip("\n".join(b["extra"].get("adressen", [])))
            self.t_net.setItem(r, 2, c)
            self.t_net.setItem(r, 3, _cel(b["advies"] or L("Bekend programma.", "Known program.")))
        self.t_net.resizeRowsToContents()
        # samenvatting bovenaan
        n_let = sum(1 for b in priv if b["status"] in (W.LET_OP, W.SLECHT))
        delen = []
        if veranderd:
            delen.append(L("⚠️ Sinds de vorige keer (%s) staat er weer iets AAN: %s.",
                           "⚠️ Since last time (%s) something is ON again: %s.")
                         % (vorige, ", ".join(b["titel"] for b in veranderd)))
        elif eerste:
            delen.append(L("Eerste keer: ik heb de stand opgeschreven. Volgende keer zie je wat Windows heeft veranderd.",
                           "First time: I noted the current state. Next time you'll see what Windows changed."))
        else:
            delen.append(L("Sinds de vorige keer (%s) is er niets teruggezet. 👍", "Nothing was switched back since last time (%s). 👍") % vorige)
        delen.append(L("Privacy: %d van de %d onderdelen staan nog aan." % (n_let, len(priv)),
                       "Privacy: %d of %d are still on." % (n_let, len(priv))) if n_let else L("Privacy: alles staat uit. ✅", "Privacy: everything is off. ✅"))
        delen.append(o["titel"] + ".")
        verdacht = [b["titel"] for b in net if b["status"] == W.SLECHT]
        if verdacht:
            delen.append(L("❌ Let op: verbinding vanuit een rare plek: %s", "❌ Careful: connection from an odd place: %s") % ", ".join(verdacht))
        kleur = SLECHT_K if (veranderd or verdacht) else (LETOP_K if (n_let or o["status"] != W.GOED) else GOED_K)
        self._zet_banner("\n".join(delen) + "\n" + L("Gecontroleerd om %s.", "Checked at %s.") % time.strftime("%H:%M"), kleur)
