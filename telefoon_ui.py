# -*- coding: utf-8 -*-
"""DraveGuard - tabblad 'Telefoon' (DraveCare, pc-kant via adb).

Eerst kijken, dan pas na jouw klik iets doen. Bestanden gaan naar D: (zelf te kiezen).
Dravenlock (Roger & Claudio).
"""
from __future__ import annotations

import os
import time

from PyQt6.QtCore import Qt, QUrl, QTimer
from PyQt6.QtGui import QDesktopServices, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QLineEdit, QTextEdit,
    QCheckBox, QFileDialog, QMessageBox, QTableWidgetItem, QHeaderView, QGridLayout)

import telefoon as TF
from onderhoud_ui import Klus, _tabel

NL = True
GOED, LETOP, SLECHT, ACC2 = "#57d98a", "#ffd166", "#ff6b6b", "#b59cff"
KL = {"goed": GOED, "letop": LETOP, "slecht": SLECHT}


def L(nl, en):
    return nl if NL else en


def _std_doel():
    for d in ("D:\\", "F:\\", "E:\\"):
        if os.path.isdir(d):
            return os.path.join(d, "DraveCare", "Telefoon")
    return os.path.join(os.path.expanduser("~"), "DraveCare", "Telefoon")


class TelefoonTab(QWidget):
    def __init__(self, g):
        super().__init__()
        self.g = g
        self.klussen = []
        self._stop = False
        db = g.db
        self.adb = TF.Adb(db.get_meta("tel_adb", ""), db.get_meta("tel_adres", ""))
        self.doel = db.get_meta("tel_doel", "") or _std_doel()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)
        t = QLabel("📱  " + L("Telefoon — DraveCare", "Phone — DraveCare"))
        t.setObjectName("h2")
        lay.addWidget(t)
        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("font-size:18px;")
        lay.addWidget(self.lbl_status)

        self.sub = QTabWidget()
        self.sub.addTab(self._p_verbind(), L("1 · Verbinden", "1 · Connect"))
        self.sub.addTab(self._p_bestanden(), L("2 · Bestanden naar pc", "2 · Files to PC"))
        self.sub.addTab(self._p_opruimen(), L("3 · Opruimen", "3 · Clean up"))
        self.sub.addTab(self._p_batterij(), L("4 · Batterij", "4 · Battery"))
        self.sub.addTab(self._p_apps(), L("5 · Apps", "5 · Apps"))
        self.sub.addTab(self._p_controle(), L("6 · Volledige controle", "6 · Full check"))
        lay.addWidget(self.sub, 1)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(170)
        self.log.setStyleSheet("font-size:16px;")
        lay.addWidget(self.log)
        self.lbl_status.setText(L('Telefoon zoeken…', 'Looking for phone…'))
        QTimer.singleShot(1200, self._auto)

    # ------------------------------------------------ hulp
    def say(self, s):
        self.log.append(s)

    def _auto(self):
        """Bij het openen: stil verbinden met het laatst gebruikte adres (in de achtergrond)."""
        def werk(say):
            if self.adb.adres and not self.adb.verbonden():
                self.adb.verbind(self.adb.adres)
            return None
        self.klus(werk, lambda r: self._status())

    def klus(self, fn, klaar=None):
        k = Klus(fn)
        k.regel.connect(self.say)
        if klaar:
            k.klaar.connect(klaar)
        k.klaar.connect(lambda _r, k=k: self.klussen.remove(k) if k in self.klussen else None)
        self.klussen.append(k)
        k.start()

    def _fout(self, r):
        if isinstance(r, Exception):
            self.say("⚠ " + str(r))
            return True
        return False

    def _status(self):
        try:
            ok = self.adb.verbonden()
        except Exception as e:
            ok = False
            self.lbl_status.setText("⚠ " + str(e))
            self.lbl_status.setStyleSheet("font-size:18px; color:%s;" % SLECHT)
            return
        if ok:
            self.lbl_status.setText(L("✔ Telefoon verbonden: ", "✔ Phone connected: ") + self.adb.adres)
            self.lbl_status.setStyleSheet("font-size:18px; color:%s;" % GOED)
        else:
            self.lbl_status.setText(L("✖ Geen telefoon verbonden — ga naar ‘1 · Verbinden’.",
                                      "✖ No phone connected — go to ‘1 · Connect’."))
            self.lbl_status.setStyleSheet("font-size:18px; color:%s;" % LETOP)

    def _uitleg(self, lay, tekst):
        u = QLabel(tekst)
        u.setWordWrap(True)
        u.setStyleSheet("font-size:16px;")
        lay.addWidget(u)

    # ------------------------------------------------ 1 verbinden
    def _p_verbind(self):
        w = QWidget(); lay = QVBoxLayout(w)
        self._uitleg(lay, L(
            "Zet op je telefoon aan: Instellingen → Systeem → Ontwikkelaarsopties → Draadloze foutopsporing. "
            "Daar staat ‘IP-adres en poort’, bijvoorbeeld 192.168.2.4:39231. Na een herstart van de telefoon "
            "verandert de poort — dan vul je hem hier opnieuw in.\n"
            "Eerste keer? Tik daar op ‘Apparaat koppelen met koppelingscode’ en vul hieronder het koppel-adres "
            "en de code in.",
            "On your phone: Settings → System → Developer options → Wireless debugging. Use the 'IP address & "
            "port' shown there. First time? Use 'Pair device with pairing code' and fill in below."))
        r = QHBoxLayout()
        r.addWidget(QLabel(L("Adres:poort", "Address:port")))
        self.ed_adres = QLineEdit(self.adb.adres)
        self.ed_adres.setPlaceholderText("192.168.2.4:39231")
        self.ed_adres.setMinimumHeight(44)
        r.addWidget(self.ed_adres, 1)
        r.addWidget(self.g._btn("🔗  " + L("Verbinden", "Connect"), self.verbind))
        lay.addLayout(r)
        r2 = QHBoxLayout()
        r2.addWidget(QLabel(L("Koppel-adres", "Pair address")))
        self.ed_paar = QLineEdit(); self.ed_paar.setMinimumHeight(44)
        self.ed_paar.setPlaceholderText("192.168.2.4:37011")
        r2.addWidget(self.ed_paar, 1)
        r2.addWidget(QLabel(L("Code", "Code")))
        self.ed_code = QLineEdit(); self.ed_code.setMaximumWidth(140); self.ed_code.setMinimumHeight(44)
        r2.addWidget(self.ed_code)
        r2.addWidget(self.g._btn(L("Koppelen", "Pair"), self.koppel, ghost=True))
        lay.addLayout(r2)
        r3 = QHBoxLayout()
        self.lbl_adb = QLabel("adb: " + (self.adb.pad or L("niet gevonden", "not found")))
        self.lbl_adb.setStyleSheet("color:%s; font-size:15px;" % ACC2)
        r3.addWidget(self.lbl_adb, 1)
        r3.addWidget(self.g._btn(L("adb.exe kiezen…", "Choose adb.exe…"), self.kies_adb, ghost=True))
        lay.addLayout(r3)
        self.lbl_toestel = QLabel("")
        self.lbl_toestel.setStyleSheet("font-size:18px;")
        self.lbl_toestel.setWordWrap(True)
        lay.addWidget(self.lbl_toestel)
        lay.addStretch()
        return w

    def kies_adb(self):
        f, _ = QFileDialog.getOpenFileName(self, "adb.exe", "", "adb.exe (adb.exe)")
        if f:
            self.g.db.set_meta("tel_adb", f)
            self.adb.pad = f
            self.lbl_adb.setText("adb: " + f)

    def _w_verbind(self, say):
        say(self.adb.verbind(self.ed_adres.text()))
        time.sleep(1)
        if not self.adb.verbonden():
            return None
        return self.adb.info()

    def verbind(self):
        if not self.ed_adres.text().strip():
            return
        self.say(L("Verbinden met ", "Connecting to ") + self.ed_adres.text().strip() + " …")
        def klaar(r):
            if self._fout(r):
                return
            self._status()
            if r:
                self.g.db.set_meta("tel_adres", self.adb.adres)
                self.lbl_toestel.setText("📱 %s %s · Android %s · %s %s" % (
                    r["merk"], r["model"], r["android"], L("beveiligingsupdate", "security patch"), r["patch"]))
        self.klus(self._w_verbind, klaar)

    def koppel(self):
        a, c = self.ed_paar.text().strip(), self.ed_code.text().strip()
        if a and c:
            self.klus(lambda say: say(self.adb.koppel(a, c)))

    # ------------------------------------------------ 2 bestanden
    def _p_bestanden(self):
        w = QWidget(); lay = QVBoxLayout(w)
        self._uitleg(lay, L(
            "Vink aan welke mappen je naar de pc wilt halen. Alleen NIEUWE bestanden worden gekopieerd; "
            "wat er al staat wordt overgeslagen. Er wordt NIETS van je telefoon verwijderd.",
            "Tick the folders to copy to the PC. Only NEW files are copied. Nothing is removed from your phone."))
        self.vinkjes = []
        grid = QGridLayout()
        for i, (naam, pad) in enumerate(TF.MAPPEN):
            cb = QCheckBox(naam)
            cb.setStyleSheet("font-size:17px; padding:4px;")
            cb.setToolTip(pad)
            cb.setChecked(pad in ("/sdcard/DCIM/Camera", "/sdcard/Pictures/Screenshots"))
            grid.addWidget(cb, i // 2, i % 2)
            self.vinkjes.append((cb, naam, pad))
        lay.addLayout(grid)
        r = QHBoxLayout()
        self.lbl_doel = QLabel(L("Naar: ", "To: ") + self.doel)
        self.lbl_doel.setStyleSheet("font-size:17px;")
        r.addWidget(self.lbl_doel, 1)
        r.addWidget(self.g._btn(L("Andere map…", "Other folder…"), self.kies_doel, ghost=True))
        r.addWidget(self.g._btn(L("Map openen", "Open folder"), lambda: self._open(self.doel), ghost=True))
        lay.addLayout(r)
        r2 = QHBoxLayout()
        r2.addWidget(self.g._btn("📏  " + L("Groottes bekijken", "Show sizes"), self.groottes, ghost=True))
        r2.addWidget(self.g._btn("⬇  " + L("Ophalen naar pc", "Copy to PC"), self.ophalen))
        r2.addWidget(self.g._btn(L("Stop", "Stop"), self.stop, ghost=True))
        lay.addLayout(r2)
        lay.addStretch()
        return w

    def kies_doel(self):
        d = QFileDialog.getExistingDirectory(self, L("Kies de map", "Choose folder"), self.doel)
        if d:
            if d[:2].upper() == "C:":
                QMessageBox.information(self, "DraveGuard", L(
                    "Liever niet op C: — kies een map op D: of een andere schijf.",
                    "Better not on C: — choose a folder on another drive."))
                return
            self.doel = d
            self.g.db.set_meta("tel_doel", d)
            self.lbl_doel.setText(L("Naar: ", "To: ") + d)

    def _open(self, pad):
        os.makedirs(pad, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(pad))

    def stop(self):
        self._stop = True

    def _gekozen(self):
        return [(n, p) for cb, n, p in self.vinkjes if cb.isChecked()]

    def groottes(self):
        keuze = [(n, p) for cb, n, p in self.vinkjes]
        def werk(say):
            for n, p in keuze:
                g = self.adb.map_grootte(p)
                say("  %-28s %s" % (n, TF.mooi(g) if g >= 0 else L("(bestaat niet)", "(missing)")))
        self.say(L("Groottes op de telefoon:", "Sizes on the phone:"))
        self.klus(werk, lambda r: self._fout(r))

    def ophalen(self):
        keuze = self._gekozen()
        if not keuze:
            return
        self._stop = False
        doel = self.doel
        def werk(say):
            tn = to = tb = 0
            for n, p in keuze:
                say("▶ " + n)
                dm = os.path.join(doel, n.split(" (")[0])
                a, b, c = self.adb.ophalen(p, dm, say, lambda: self._stop)
                say("  %d nieuw, %d stonden er al (%s)" % (a, b, TF.mooi(c)))
                tn, to, tb = tn + a, to + b, tb + c
                if self._stop:
                    break
            say(L("✔ Klaar: %d nieuwe bestanden (%s) in %s", "✔ Done: %d new files (%s) in %s") %
                (tn, TF.mooi(tb), doel))
        self.klus(werk, lambda r: self._fout(r))

    # ------------------------------------------------ 3 opruimen
    def _p_opruimen(self):
        w = QWidget(); lay = QVBoxLayout(w)
        self._uitleg(lay, L(
            "Caches zijn tijdelijke bestanden die apps zelf weer aanmaken. Opruimen is veilig: je verliest geen "
            "foto's, berichten of instellingen. Apps kunnen de eerste keer daarna iets trager starten.",
            "Caches are temporary files apps recreate. Clearing is safe: no photos, messages or settings are lost."))
        self.lbl_opslag = QLabel("")
        self.lbl_opslag.setStyleSheet("font-size:19px;")
        lay.addWidget(self.lbl_opslag)
        r = QHBoxLayout()
        r.addWidget(self.g._btn("📊  " + L("Opslag bekijken", "Show storage"), self.opslag, ghost=True))
        r.addWidget(self.g._btn("🧹  " + L("Alle caches opruimen", "Clear all caches"), self.caches))
        r.addWidget(self.g._btn("🔎  " + L("Grote bestanden zoeken", "Find large files"), self.groot, ghost=True))
        lay.addLayout(r)
        self.tb_groot = _tabel([L("Bestand op telefoon", "File on phone"), L("Grootte", "Size")])
        self.tb_groot.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.tb_groot, 1)
        return w

    def opslag(self):
        def klaar(r):
            if self._fout(r):
                return
            tot, geb = r
            if tot:
                pct = 100 * geb / tot
                k = SLECHT if pct > 90 else LETOP if pct > 75 else GOED
                self.lbl_opslag.setText(L("Opslag: %d%% vol — %s gebruikt van %s, %s vrij",
                                          "Storage: %d%% full — %s of %s used, %s free") %
                                        (pct, TF.mooi(geb), TF.mooi(tot), TF.mooi(tot - geb)))
                self.lbl_opslag.setStyleSheet("font-size:19px; color:%s;" % k)
        self.klus(lambda say: self.adb.opslag(), klaar)

    def caches(self):
        if QMessageBox.question(self, "DraveGuard", L("Alle app-caches op de telefoon opruimen?",
                                                      "Clear all app caches on the phone?")) \
                != QMessageBox.StandardButton.Yes:
            return
        self.klus(lambda say: self.adb.caches_opruimen(say), lambda r: (self._fout(r), self.opslag()))

    def groot(self):
        self.say(L("Grote bestanden zoeken (groter dan 50 MB)…", "Searching large files (>50 MB)…"))
        def klaar(r):
            if self._fout(r):
                return
            self.tb_groot.setRowCount(0)
            for n, g in r:
                i = self.tb_groot.rowCount(); self.tb_groot.insertRow(i)
                self.tb_groot.setItem(i, 0, QTableWidgetItem(n))
                self.tb_groot.setItem(i, 1, QTableWidgetItem(TF.mooi(g)))
            self.say(L("%d grote bestanden gevonden. Ophalen kan bij ‘2 · Bestanden’.",
                       "%d large files found.") % len(r))
        self.klus(lambda say: self.adb.grote_bestanden(50), klaar)

    # ------------------------------------------------ 4 batterij
    def _p_batterij(self):
        w = QWidget(); lay = QVBoxLayout(w)
        self.lbl_bat = QLabel(L("Klik op ‘Batterij bekijken’.", "Click ‘Show battery’."))
        self.lbl_bat.setStyleSheet("font-size:20px;")
        self.lbl_bat.setWordWrap(True)
        lay.addWidget(self.lbl_bat)
        lay.addWidget(self.g._btn("🔋  " + L("Batterij bekijken", "Show battery"), self.batterij))
        self._uitleg(lay, L("Stroomverbruik per app sinds de laatste keer volledig opladen (in mAh):",
                            "Power use per app since last full charge (mAh):"))
        self.tb_stroom = _tabel([L("App", "App"), "mAh"])
        self.tb_stroom.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.tb_stroom, 1)
        return w

    def batterij(self):
        def werk(say):
            return self.adb.batterij(), self.adb.stroomvreters(15)
        def klaar(r):
            if self._fout(r):
                return
            b, s = r
            t = L("Batterij %s%% · gezondheid: %s", "Battery %s%% · health: %s") % (b["niveau"], b["gezondheid"])
            if b["temp"] is not None:
                t += " · %.1f °C" % b["temp"]
            t += L(" · aan de lader" if b["laadt"] else " · niet aan de lader",
                   " · charging" if b["laadt"] else " · not charging")
            self.lbl_bat.setText(t)
            self.lbl_bat.setStyleSheet("font-size:20px; color:%s;" % (GOED if b["gezondheid"] == "goed" else LETOP))
            self.tb_stroom.setRowCount(0)
            for n, m in s:
                i = self.tb_stroom.rowCount(); self.tb_stroom.insertRow(i)
                self.tb_stroom.setItem(i, 0, QTableWidgetItem(n))
                self.tb_stroom.setItem(i, 1, QTableWidgetItem("%.0f" % m))
        self.klus(werk, klaar)

    # ------------------------------------------------ 5 apps
    def _p_apps(self):
        w = QWidget(); lay = QVBoxLayout(w)
        self._uitleg(lay, L(
            "Jouw eigen geïnstalleerde apps. Vink aan wat weg mag en klik op ‘Verwijderen’. Er wordt eerst een "
            "reservekopie (apk) op de pc gemaakt. Je app-gegevens gaan wél verloren.",
            "Your own installed apps. Tick what may go and click ‘Remove’. A backup (apk) is made on the PC first."))
        r = QHBoxLayout()
        r.addWidget(self.g._btn("📋  " + L("Apps ophalen", "Load apps"), self.apps, ghost=True))
        r.addWidget(self.g._btn("🗑  " + L("Aangevinkte verwijderen", "Remove ticked"), self.verwijder))
        lay.addLayout(r)
        self.tb_apps = _tabel(["", L("App (pakket)", "App (package)"), L("Grootte", "Size"),
                               L("Laatst gebruikt", "Last used")])
        self.tb_apps.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.tb_apps, 1)
        return w

    def apps(self):
        self.say(L("Apps ophalen (even geduld)…", "Loading apps…"))
        def werk(say):
            return self.adb.gebruikers_apps(), self.adb.app_groottes(), self.adb.laatst_gebruikt()
        def klaar(r):
            if self._fout(r):
                return
            lijst, gr, lg = r
            nu = time.time()
            rijen = []
            for p in lijst:
                a, d, c = gr.get(p, (0, 0, 0))
                t = lg.get(p, 0)
                rijen.append((p, a + d + c, t))
            rijen.sort(key=lambda x: x[2])          # langst niet gebruikt bovenaan
            self.tb_apps.setRowCount(0)
            for p, g, t in rijen:
                i = self.tb_apps.rowCount(); self.tb_apps.insertRow(i)
                vk = QTableWidgetItem(); vk.setFlags(vk.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                vk.setCheckState(Qt.CheckState.Unchecked)
                self.tb_apps.setItem(i, 0, vk)
                self.tb_apps.setItem(i, 1, QTableWidgetItem(p))
                self.tb_apps.setItem(i, 2, QTableWidgetItem(TF.mooi(g) if g else "?"))
                if t:
                    dagen = int((nu - t) / 86400)
                    it = QTableWidgetItem(time.strftime("%d-%m-%Y", time.localtime(t)) +
                                          L("  (%d dagen)", "  (%d days)") % dagen)
                    if dagen > 90:
                        it.setForeground(QColor(LETOP))
                else:
                    it = QTableWidgetItem(L("onbekend", "unknown"))
                self.tb_apps.setItem(i, 3, it)
            self.tb_apps.resizeColumnToContents(0)
            self.say(L("%d apps. Bovenaan: het langst niet gebruikt.", "%d apps. Top: unused longest.") % len(rijen))
        self.klus(werk, klaar)

    def verwijder(self):
        weg = [self.tb_apps.item(i, 1).text() for i in range(self.tb_apps.rowCount())
               if self.tb_apps.item(i, 0).checkState() == Qt.CheckState.Checked]
        if not weg:
            return
        if QMessageBox.question(self, "DraveGuard", L("Deze %d app(s) verwijderen?\n\n%s",
                                                      "Remove these %d app(s)?\n\n%s") % (len(weg), "\n".join(weg))) \
                != QMessageBox.StandardButton.Yes:
            return
        bmap = os.path.join(self.doel, "App-reservekopie")
        def werk(say):
            for p in weg:
                self.adb.verwijder_app(p, bmap, say)
            say(L("✔ Klaar. Reservekopieën staan in ", "✔ Done. Backups in ") + bmap)
        self.klus(werk, lambda r: (self._fout(r), self.apps()))

    # ------------------------------------------------ 6 controle
    def _p_controle(self):
        w = QWidget(); lay = QVBoxLayout(w)
        self._uitleg(lay, L(
            "Eén knop: opslag, batterij, beveiligingsupdate, apps die zelf apps mogen installeren, apps met "
            "camera/microfoon/locatie, grote bestanden en stroomverbruik. Je krijgt een rapport op de pc.",
            "One button: storage, battery, security patch, permissions, large files and power use. You get a report."))
        r = QHBoxLayout()
        r.addWidget(self.g._btn("🩺  " + L("Volledige controle starten", "Start full check"), self.controle))
        self.btn_rap = self.g._btn(L("Rapport openen", "Open report"), self.open_rapport, ghost=True)
        self.btn_rap.setEnabled(False)
        r.addWidget(self.btn_rap)
        lay.addLayout(r)
        self.lbl_ctl = QLabel("")
        self.lbl_ctl.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_ctl.setWordWrap(True)
        self.lbl_ctl.setStyleSheet("font-size:19px;")
        lay.addWidget(self.lbl_ctl)
        lay.addStretch()
        self._rapport = ""
        return w

    def controle(self):
        doel = self.doel
        def werk(say):
            r = self.adb.controle(say)
            pad = os.path.join(doel, "Rapporten", "DraveCare_rapport_%s.html" % time.strftime("%Y-%m-%d_%H%M"))
            TF.rapport_html(r, pad)
            return r, pad
        def klaar(res):
            if self._fout(res):
                return
            r, pad = res
            self._rapport = pad
            self.btn_rap.setEnabled(True)
            self.lbl_ctl.setText("<br>".join('<span style="color:%s">● %s</span>' % (KL[k], t)
                                             for k, t in TF.oordeel(r)))
            self.say(L("Rapport opgeslagen: ", "Report saved: ") + pad)
        self.klus(werk, klaar)

    def open_rapport(self):
        if self._rapport:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._rapport))
