# -*- coding: utf-8 -*-
# DraveCare - Dravenlock (Roger & Claudio). Vrije software onder de GNU GPL v3.0.
"""droid.py - alles wat DraveCare aan Android vraagt (via pyjnius). Op de pc geeft het voorbeeldwaarden."""
import os
import time

ANDROID = "ANDROID_PRIVATE" in os.environ or "ANDROID_ARGUMENT" in os.environ
OPSLAG = "/storage/emulated/0" if ANDROID else os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_opslag")

_c = {}


def K(naam):
    if naam not in _c:
        from jnius import autoclass
        _c[naam] = autoclass(naam)
    return _c[naam]


def act():
    return K("org.kivy.android.PythonActivity").mActivity


def sdk():
    try:
        return K("android.os.Build$VERSION").SDK_INT
    except Exception:
        return 0


def _start(intent):
    try:
        intent.addFlags(0x10000000)          # FLAG_ACTIVITY_NEW_TASK
        act().startActivity(intent)
        return True
    except Exception:
        return False


def _intent(actie, uri=None):
    I = K("android.content.Intent")
    if uri is None:
        return I(actie)
    return I(actie, K("android.net.Uri").parse(uri))


# ------------------------------------------------------------------ toestemmingen
def alle_bestanden_ok():
    if not ANDROID:
        return True
    try:
        if sdk() >= 30:
            return bool(K("android.os.Environment").isExternalStorageManager())
        return True
    except Exception:
        return False


def vraag_alle_bestanden():
    pkg = act().getPackageName()
    if not _start(_intent("android.settings.MANAGE_APP_ALL_FILES_ACCESS_PERMISSION", "package:" + pkg)):
        _start(_intent("android.settings.MANAGE_ALL_FILES_ACCESS_PERMISSION"))


def gebruik_ok():
    if not ANDROID:
        return True
    try:
        a = act()
        ops = a.getSystemService("appops")
        uid = K("android.os.Process").myUid()
        f = ops.unsafeCheckOpNoThrow if sdk() >= 29 else ops.checkOpNoThrow
        return f("android:get_usage_stats", uid, a.getPackageName()) == 0
    except Exception:
        return False


def vraag_gebruik():
    pkg = act().getPackageName()
    if not _start(_intent("android.settings.USAGE_ACCESS_SETTINGS", "package:" + pkg)):
        _start(_intent("android.settings.USAGE_ACCESS_SETTINGS"))


# ------------------------------------------------------------------ opslag en batterij
def opslag():
    """(totaal, vrij) in bytes."""
    if not ANDROID:
        return 128 * 2 ** 30, 31 * 2 ** 30
    try:
        S = K("android.os.StatFs")(K("android.os.Environment").getDataDirectory().getPath())
        return int(S.getTotalBytes()), int(S.getAvailableBytes())
    except Exception:
        try:
            s = os.statvfs(OPSLAG)
            return s.f_blocks * s.f_frsize, s.f_bavail * s.f_frsize
        except Exception:
            return 0, 0


GEZOND = {1: "onbekend", 2: "goed", 3: "te warm", 4: "versleten", 5: "te hoge spanning", 6: "fout", 7: "te koud"}


def batterij():
    if not ANDROID:
        return {"niveau": 78, "gezondheid": "goed", "code": 2, "temp": 26.5, "spanning": 4.05, "laadt": False}
    try:
        f = K("android.content.IntentFilter")("android.intent.action.BATTERY_CHANGED")
        i = act().registerReceiver(None, f)
        lvl, sc = i.getIntExtra("level", -1), i.getIntExtra("scale", 100)
        code = i.getIntExtra("health", 1)
        return {"niveau": int(round(100.0 * lvl / max(1, sc))) if lvl >= 0 else -1,
                "gezondheid": GEZOND.get(code, "onbekend"), "code": code,
                "temp": i.getIntExtra("temperature", 0) / 10.0,
                "spanning": i.getIntExtra("voltage", 0) / 1000.0,
                "laadt": i.getIntExtra("plugged", 0) != 0}
    except Exception:
        return {"niveau": -1, "gezondheid": "onbekend", "code": 1, "temp": 0.0, "spanning": 0.0, "laadt": False}


# ------------------------------------------------------------------ apps
def apps():
    """Lijst van dicts voor jouw eigen (niet-systeem) apps."""
    if not ANDROID:
        nu = time.time()
        return [{"pkg": "com.voorbeeld.%d" % i, "naam": "Voorbeeld-app %d" % i, "grootte": (i + 1) * 30 * 2 ** 20,
                 "gebruikt": nu - i * 20 * 86400, "camera": i % 3 == 0, "micro": i % 4 == 0, "locatie": i % 2 == 0,
                 "installeert": i == 5, "sinds": nu - 400 * 86400} for i in range(12)]
    a = act()
    pm = a.getPackageManager()
    gebruikt, groot = {}, {}
    if gebruik_ok():
        try:
            usm = a.getSystemService("usagestats")
            nu = int(time.time() * 1000)
            m = usm.queryAndAggregateUsageStats(nu - 400 * 86400000, nu)
            for k in m.keySet().toArray():
                gebruikt[k] = m.get(k).getLastTimeUsed() / 1000.0
        except Exception:
            pass
    ssm = uuid = None
    try:
        ssm = a.getSystemService("storagestats")
        uuid = K("android.os.storage.StorageManager").UUID_DEFAULT
    except Exception:
        pass
    ops = None
    try:
        ops = a.getSystemService("appops")
    except Exception:
        pass
    lijst = pm.getInstalledPackages(4096)          # GET_PERMISSIONS
    uit = []
    eigen = a.getPackageName()
    for n in range(lijst.size()):
        p = lijst.get(n)
        ai = p.applicationInfo
        if ai is None or (ai.flags & 1 and not ai.flags & 128) or p.packageName == eigen:
            continue                                # systeem-app (niet bijgewerkt) of DraveCare zelf
        perms = list(p.requestedPermissions or [])
        flags = list(p.requestedPermissionsFlags or [])
        aan = {perms[i] for i in range(min(len(perms), len(flags))) if flags[i] & 2}
        inst = False
        if "android.permission.REQUEST_INSTALL_PACKAGES" in perms:
            inst = True
            try:
                f = ops.unsafeCheckOpNoThrow if sdk() >= 29 else ops.checkOpNoThrow
                inst = f("android:request_install_packages", ai.uid, p.packageName) == 0
            except Exception:
                pass
        gr = 0
        if ssm is not None and uuid is not None:
            try:
                st = ssm.queryStatsForUid(uuid, ai.uid)
                gr = st.getAppBytes() + st.getDataBytes() + st.getCacheBytes()
            except Exception:
                gr = 0
        try:
            naam = str(pm.getApplicationLabel(ai))
        except Exception:
            naam = p.packageName
        uit.append({"pkg": p.packageName, "naam": naam, "grootte": gr,
                    "gebruikt": gebruikt.get(p.packageName, 0), "sinds": p.firstInstallTime / 1000.0,
                    "camera": "android.permission.CAMERA" in aan,
                    "micro": "android.permission.RECORD_AUDIO" in aan,
                    "locatie": "android.permission.ACCESS_FINE_LOCATION" in aan
                    or "android.permission.ACCESS_COARSE_LOCATION" in aan,
                    "installeert": inst})
    return uit


def open_app(pkg):
    """De instellingenpagina van een app (rechten, opslag, verwijderen)."""
    I = K("android.content.Intent")
    U = K("android.net.Uri")
    return _start(I("android.settings.APPLICATION_DETAILS_SETTINGS", U.fromParts("package", pkg, None)))


def verwijder_app(pkg):
    """Android laat zelf het 'Verwijderen?'-venster zien."""
    return _start(_intent("android.intent.action.DELETE", "package:" + pkg))


def open_onbekende_bronnen(pkg):
    if not _start(_intent("android.settings.MANAGE_UNKNOWN_APP_SOURCES", "package:" + pkg)):
        open_app(pkg)


# ------------------------------------------------------------------ veiligheid
def veiligheid():
    if not ANDROID:
        return {"slot": True, "patch": "2022-09-01", "android": "11", "model": "voorbeeld", "ontw": True, "adb": True}
    r = {"slot": None, "patch": "", "android": "", "model": "", "ontw": False, "adb": False}
    try:
        r["slot"] = bool(act().getSystemService("keyguard").isDeviceSecure())
    except Exception:
        pass
    try:
        V = K("android.os.Build$VERSION")
        r["patch"], r["android"] = str(V.SECURITY_PATCH), str(V.RELEASE)
        B = K("android.os.Build")
        r["model"] = "%s %s" % (B.MANUFACTURER, B.MODEL)
    except Exception:
        pass
    try:
        G = K("android.provider.Settings$Global")
        cr = act().getContentResolver()
        r["ontw"] = G.getInt(cr, "development_settings_enabled", 0) == 1
        r["adb"] = G.getInt(cr, "adb_enabled", 0) == 1
    except Exception:
        pass
    return r


def open_schermslot():
    _start(_intent("android.app.action.SET_NEW_PASSWORD")) or _start(_intent("android.settings.SECURITY_SETTINGS"))


def open_updates():
    _start(_intent("android.settings.SYSTEM_UPDATE_SETTINGS")) or _start(_intent("android.settings.DEVICE_INFO_SETTINGS"))


def open_ontwikkelaar():
    _start(_intent("android.settings.APPLICATION_DEVELOPMENT_SETTINGS"))


# ------------------------------------------------------------------ mediabibliotheek
_wacht = []


def scan_media(paden):
    """Onthoudt welke bestanden verplaatst zijn; scan_flush() (op de hoofddraad) laat het de galerij weten."""
    if ANDROID and paden:
        _wacht.extend(paden)


def scan_flush():
    if not _wacht:
        return
    paden = list(_wacht)
    del _wacht[:]
    try:
        K("android.media.MediaScannerConnection").scanFile(act(), paden, None, None)
    except Exception:
        pass
