# -*- coding: utf-8 -*-
"""
Streetview_qgis_cej - QGIS plugin (Full)
- Login จาก Google Sheet (users_public CSV; password เป็น SHA-256)
- Remember last username + Remember me (token)
- นับคลิกแยก Map / Street View (ผ่าน JS + QWebChannel)
- Inactivity auto-logout 30 นาที
- ปุ่ม Logout ใน Dock (ยืนยันครั้งเดียว + beep) และจากเมนู Plugins
- ล้างค่า/แคช/marker และสลับเมาส์เป็น Pan Map หลัง Logout
- แสดงสถานะผู้ใช้/ตัวนับ/กล้อง บน Dock
"""
import os
import csv
import hashlib
from io import StringIO


def api_request(url, payload: dict, timeout=12):
    if "action" not in payload:
        payload["action"] = "login"
    try:
        import requests
        r = requests.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        try:
            import urllib.parse, urllib.request, json as _json
            qs = urllib.parse.urlencode(payload)
            with urllib.request.urlopen(f"{url}?{qs}", timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", "ignore")
            try:
                return _json.loads(raw)
            except Exception:
                return {"ok": raw.strip().lower().startswith("ok"), "message": raw.strip()}
        except Exception as e:
            return {"ok": False, "message": f"{e}"}
SCRIPT_URL = "https://script.google.com/macros/s/AKfycbwMmoPEMNXy26cdAfwRCmcB8mUs_yvEYuLrgItwaoRHJFAbzj5P9T7KqecQi3gESGaDtw/exec"

from datetime import datetime, timezone


from qgis.PyQt import QtWidgets, QtWebEngineWidgets, QtCore
from qgis.PyQt.QtCore import Qt
from qgis.gui import QgsMapToolEmitPoint, QgsMapToolPan
from qgis.core import (
    QgsProject, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsMessageLog, Qgis, QgsPointXY, QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsSingleSymbolRenderer, QgsMarkerSymbol, QgsProperty,
    QgsSvgMarkerSymbolLayer, QgsSymbolLayer
)
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtCore import QObject, pyqtSlot, QSettings, pyqtSignal, QTimer

# ---------- optional HTTP backends ----------
try:
    import requests
    _HAS_REQUESTS = True
except Exception:
    _HAS_REQUESTS = False
    import urllib.request

# ------------------ Helpers ------------------
def log(msg, level=Qgis.Info):
    QgsMessageLog.logMessage(str(msg), "StreetView", level)

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def load_users_from_sheet(sheet_csv_url: str):
    """
    โหลดผู้ใช้จาก Google Sheet (CSV -> users_public)
    โครงหัวตารางต้องมี: username,password,role,active
    - password: ค่า SHA-256 (hex) ไม่ใช่ plain text
    - active: TRUE/true/1 หมายถึงใช้งานได้
    return: dict[username] = {"pwdhash": "...", "role": "...", "active": bool}
    """
    users = {}
    try:
        if _HAS_REQUESTS:
            resp = requests.get(sheet_csv_url, timeout=12)
            resp.raise_for_status()
            text = resp.content.decode("utf-8", errors="replace")
        else:
            with urllib.request.urlopen(sheet_csv_url, timeout=15) as r:
                text = r.read().decode("utf-8", errors="replace")

        reader = csv.DictReader(StringIO(text))
        for row in reader:
            uname = (row.get("username") or "").strip()
            pwdhash = (row.get("password") or "").strip().lower()
            role = (row.get("role") or "").strip()
            active_raw = (row.get("active") or "").strip().lower()
            active = active_raw in ("1", "true", "yes", "y")

            if not uname or not pwdhash:
                continue

            users[uname] = {"pwdhash": pwdhash, "role": role, "active": active}
    except Exception as e:
        log(f"Load users error: {e}", Qgis.Warning)
    return users

# ------------------ Login Dialog ------------------
class LoginDialog(QtWidgets.QDialog):
    ORG = "StreetViewQGIS"
    APP = "StreetViewPlugin"

    # 🔗 ใส่ลิงก์ CSV ของแท็บ users_public (Publish to web → CSV)


    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Login to Street View")
        self.setModal(True)
        self.resize(400, 200)

        form = QtWidgets.QFormLayout()
        self.userEdit = QtWidgets.QLineEdit()
        self.passEdit = QtWidgets.QLineEdit()
        self.passEdit.setEchoMode(QtWidgets.QLineEdit.Password)
        self.rememberChk = QtWidgets.QCheckBox("จำฉันไว้ (Remember me)")
        self.msgLbl = QtWidgets.QLabel("")
        self.msgLbl.setStyleSheet("color:#c00;")

        form.addRow("Username:", self.userEdit)
        form.addRow("Password:", self.passEdit)
        form.addRow("", self.rememberChk)
        form.addRow("", self.msgLbl)

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btns.accepted.connect(self.try_login)
        btns.rejected.connect(self.reject)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(btns)

        self.settings = QSettings(self.ORG, self.APP)

        # โหลดฐานผู้ใช้จาก Google Sheet
        self.USER_DB = {}

        # Prefill last user / remember
        last_user = self.settings.value("last_user", "", type=str)
        if last_user:
            self.userEdit.setText(last_user)
        self.rememberChk.setChecked(self.settings.value("remember", False, type=bool))

        # Auto-login ถ้ามี token ถูกต้อง
        saved_user = self.settings.value("user", "", type=str)
        saved_token = self.settings.value("token", "", type=str)
        if saved_user and saved_token and self._validate_token(saved_user, saved_token):
            self._username = saved_user
            self._remember = True
            self.accept()
    def try_login(self):
        user = self.userEdit.text().strip()
        pwd = self.passEdit.text()
        if not user and not pwd:
            self.msgLbl.setText("กรุณากรอกชื่อผู้ใช้และรหัสผ่านให้ครบ")
            return
        if not user:
            self.msgLbl.setText("กรุณากรอกชื่อผู้ใช้ให้ครบ")
            return
        if not pwd:
            self.msgLbl.setText("กรุณากรอกรหัสผ่านให้ครบ")
            return

        prog = QtWidgets.QProgressDialog("กำลังตรวจสอบสิทธิ์การใช้งาน...", None, 0, 0, self)
        prog.setWindowTitle("กำลังล็อกอิน")
        prog.setWindowModality(Qt.WindowModal)
        prog.setAutoClose(True)
        prog.show()
        QtWidgets.QApplication.processEvents()
        try:
            data = api_request(SCRIPT_URL, {"action": "login", "username": user, "password": pwd}) or {}
        finally:
            prog.close()
        self._last_api_result = data

        ok = bool(data.get("ok"))
        # codes come back uppercase from Apps Script; we'll lower-case for matching
        code = (data.get("code") or data.get("error") or data.get("reason") or "").lower()
        msg  = (data.get("message") or "").lower()
        active = data.get("active")
        if active is None:
            active = data.get("is_active")
        exp = data.get("expires_at") or data.get("expire_at") or data.get("expires") or data.get("expiry") or data.get("expiresAt")

        if not ok:
            # Strong mappings first
            if code in ("invalid_password", "wrong_password") or ("invalid password" in msg):
                self.msgLbl.setText("รหัสผ่านไม่ถูกต้อง")
                return
            if code in ("user_not_found", "not_found") or ("user not found" in msg):
                self.msgLbl.setText("ไม่พบบัญชีผู้ใช้งานนี้ในระบบ")
                return
            if code in ("user_inactive", "inactive"):
                self.msgLbl.setText("ผู้ใช้นี้ถูกระงับการใช้งาน")
                return
            if code in ("user_expired", "expired"):
                self.msgLbl.setText("บัญชีนี้หมดอายุการใช้งานแล้ว")
                return
            if code in ("missing_credentials",):
                self.msgLbl.setText("กรุณากรอกชื่อผู้ใช้และรหัสผ่านให้ครบ")
                return
            # Backend/setup issues: show concise Thai
            if code in ("sheet_not_found", "no_users", "invalid_headers", "empty_request", "unknown_action", "server_error"):
                self.msgLbl.setText("ล็อกอินไม่สำเร็จ (เซิร์ฟเวอร์) — โปรดลองใหม่หรือติดต่อผู้ดูแลระบบ")
                return
            # Fallback
            self.msgLbl.setText("ล็อกอินไม่สำเร็จ")
            return

        # ok = True but still guard flags if present
        if active is False:
            self.msgLbl.setText("ผู้ใช้นี้ถูกระงับการใช้งาน")
            return
        if exp:
            try:
                s = str(exp).strip().replace("Z", "+00:00")
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > dt:
                    self.msgLbl.setText("บัญชีนี้หมดอายุการใช้งานแล้ว")
                    return
            except Exception:
                pass

        # Success
        self.settings.setValue("last_user", user)
        self._username = user
        self._remember = self.rememberChk.isChecked()
        self.settings.setValue("remember", bool(self._remember))
        token = (data.get("token") or data.get("authToken") or data.get("session") or "")
        if self._remember and token:
            self.settings.setValue("user", user)
            self.settings.setValue("token", token)
        else:
            self.settings.remove("user")
            self.settings.remove("token")
        self.msgLbl.setText("เข้าสู่ระบบสำเร็จ")
        self.accept()
    def _check_user(self, user: str, pwd_plain: str) -> bool:
        data = api_request(SCRIPT_URL, {"action": "login", "username": user, "password": pwd_plain})
        self._last_api_result = data
        return bool(data and data.get("ok") and data.get("active", True))
    def _validate_token(self, user: str, token: str) -> bool:
        data = api_request(SCRIPT_URL, {"action": "validate", "username": user, "token": token})
        self._last_api_result = data
        return bool(data and data.get("ok"))


    def username(self) -> str:
        return getattr(self, "_username", "")

    def remembered(self) -> bool:
        return getattr(self, "_remember", False)

# ------------------ Web Bridge ------------------
class StreetViewBridge(QObject):
    def __init__(self, plugin_ref):
        super().__init__()
        self.plugin_ref = plugin_ref

    @pyqtSlot(float, float)
    def updatePosition(self, lat, lon):
        try:
            self.plugin_ref.update_marker_position_from_wgs(lat, lon)
            self.plugin_ref.touch_activity()
        except Exception as e:
            log(f"updatePosition error: {e}", Qgis.Warning)

    @pyqtSlot(float, float, float)
    def updateCamera(self, heading, pitch, zoom):
        try:
            self.plugin_ref.update_marker_heading(heading, pitch, zoom)
            self.plugin_ref.touch_activity()
        except Exception as e:
            log(f"updateCamera error: {e}", Qgis.Warning)

    @pyqtSlot()
    def webClick(self):
        try:
            self.plugin_ref.on_web_clicked()
            self.plugin_ref.touch_activity()
        except Exception as e:
            log(f"webClick error: {e}", Qgis.Warning)

# ------------------ Dock Widget ------------------
class StreetViewDockWidget(QtWidgets.QDockWidget):
    requestLogout = pyqtSignal()

    def __init__(self, iface, api_key, login_user: str):
        super().__init__(f"Street View (Interactive) • {login_user}")
        self.iface = iface
        self.api_key = api_key
        self.login_user = login_user

        # state
        self.heading = 0.0
        self.pitch = 0.0
        self.zoom = 1.0
        self.map_click_count = 0
        self.sv_click_count = 0

        # UI
        wrap = QtWidgets.QWidget()
        self.setWidget(wrap)
        v = QtWidgets.QVBoxLayout(wrap)

        bar = QtWidgets.QHBoxLayout()
        self.pickBtn = QtWidgets.QPushButton("Pick on map")
        self.followChk = QtWidgets.QCheckBox("Follow camera (rotate)")
        self.followChk.setChecked(True)
        self.logoutBtn = QtWidgets.QPushButton("Logout")
        bar.addWidget(self.pickBtn)
        bar.addWidget(self.followChk)
        bar.addStretch(1)
        bar.addWidget(self.logoutBtn)
        v.addLayout(bar)

        self.webview = QtWebEngineWidgets.QWebEngineView()
        self.webview.loadFinished.connect(self.on_page_loaded)
        v.addWidget(self.webview, 1)

        self.statusLbl = QtWidgets.QLabel("")
        v.addWidget(self.statusLbl)

        self.webview.setHtml(
            "<html><body style='text-align:center;background:#f5f5f5'><h3>คลิกแผนที่เพื่อเริ่ม Street View</h3></body></html>"
        )

        # WebChannel
        self.channel = QWebChannel()
        self.bridge = StreetViewBridge(self)
        self.channel.registerObject("bridge", self.bridge)
        self.webview.page().setWebChannel(self.channel)

        # Map tools
        self.map_tool = QgsMapToolEmitPoint(iface.mapCanvas())
        self.map_tool.canvasClicked.connect(self.on_canvas_clicked)
        self.pickBtn.clicked.connect(self.activate_map_tool)
        self.logoutBtn.clicked.connect(self.on_logout_clicked)

        self.pan_tool = QgsMapToolPan(iface.mapCanvas())  # หลัง logout

        # Marker layer
        self.point_layer = None
        self.point_fid = None
        self.ensure_point_layer()

        # Session timer 30 นาที
        self.SESSION_MS = 30 * 60 * 1000
        self.session_timer = QTimer(self)
        self.session_timer.setSingleShot(True)
        self.session_timer.timeout.connect(self.on_session_timeout)
        self.touch_activity()

        iface.addDockWidget(QtCore.Qt.RightDockWidgetArea, self)
        self.update_status()

    # Inject JS (นับคลิกในหน้าเว็บ)
    def on_page_loaded(self, ok: bool):
        if not ok:
            return
        js = r"""
(function(){
  try {
    if (!window._qwc_inited) {
      window._qwc_inited = true;
      try {
        if (!window.bridge && window.qt && qt.webChannelTransport) {
          new QWebChannel(qt.webChannelTransport, function(channel){
            window.bridge = channel.objects.bridge;
          });
        }
      } catch(e){}
    }
    if (!window.__sv_click_bound) {
      window.__sv_click_bound = true;
      document.addEventListener('mousedown', function(){
        try { window.bridge && window.bridge.webClick && window.bridge.webClick(); } catch(e){}
      }, true);
    }
  } catch(e) {}
})();
"""
        try:
            self.webview.page().runJavaScript(js)
        except Exception as e:
            log(f"inject JS error: {e}", Qgis.Warning)

    # Session / Activity
    def touch_activity(self):
        try:
            self.session_timer.start(self.SESSION_MS)
        except Exception as e:
            log(f"touch_activity error: {e}", Qgis.Warning)

    def on_session_timeout(self):
        try:
            QtWidgets.QApplication.beep()
            QtWidgets.QMessageBox.information(
                self, "Session expired",
                "เซสชันหมดอายุ (ไม่มีการใช้งาน Street View เกิน 30 นาที)\nกำลังออกจากระบบอัตโนมัติ"
            )
        except Exception:
            pass
        self.reset_state()
        self.requestLogout.emit()

    # Reset state
    def reset_state(self):
        try:
            self.session_timer.stop()
        except Exception:
            pass

        try:
            if self.point_layer:
                QgsProject.instance().removeMapLayer(self.point_layer.id())
        except Exception:
            pass
        self.point_layer = None
        self.point_fid = None

        self.heading = 0.0
        self.pitch = 0.0
        self.zoom = 1.0
        self.map_click_count = 0
        self.sv_click_count = 0

        try:
            self.webview.setHtml("<html><body style='background:#fafafa'></body></html>")
            page = self.webview.page()
            prof = page.profile()
            try: prof.clearHttpCache()
            except Exception: pass
            try: prof.cookieStore().deleteAllCookies()
            except Exception: pass
            page.triggerAction(QtWebEngineWidgets.QWebEnginePage.Stop)
        except Exception as e:
            log(f"webview reset error: {e}", Qgis.Warning)

        try:
            self.iface.mapCanvas().setMapTool(self.pan_tool)
        except Exception as e:
            log(f"set pan tool error: {e}", Qgis.Warning)

        self.update_status()

    # Status
    def update_status(self):
        total = self.map_click_count + self.sv_click_count
        txt = (f"User: {self.login_user} • Clicks — Map: {self.map_click_count} • SV: {self.sv_click_count} "
               f"(Total: {total}) • Camera: heading {self.heading:.1f}°, pitch {self.pitch:.1f}°, zoom {self.zoom:.1f}")
        self.statusLbl.setText(txt)

    # Marker layer
    def ensure_point_layer(self):
        canvas_crs = self.iface.mapCanvas().mapSettings().destinationCrs().authid()
        vl_def = f"Point?crs={canvas_crs}&field=heading:double&field=pitch:double&field=zoom:double"
        self.point_layer = QgsVectorLayer(vl_def, "SV Marker (temp)", "memory")

        svg_path = os.path.join(os.path.dirname(__file__), "arrow.svg")
        svg_layer = QgsSvgMarkerSymbolLayer(svg_path, 8.0, 0.0)
        svg_layer.setDataDefinedProperty(QgsSymbolLayer.PropertyAngle, QgsProperty.fromExpression('"heading"'))
        svg_layer.setDataDefinedProperty(QgsSymbolLayer.PropertySize, QgsProperty.fromExpression('8 + 3 * "zoom"'))
        symbol = QgsMarkerSymbol()
        symbol.changeSymbolLayer(0, svg_layer)
        self.point_layer.setRenderer(QgsSingleSymbolRenderer(symbol))

        QgsProject.instance().addMapLayer(self.point_layer, addToLegend=True)

        feat = QgsFeature(self.point_layer.fields())
        feat.setGeometry(QgsGeometry())
        feat['heading'] = 0.0
        feat['pitch'] = 0.0
        feat['zoom'] = 1.0
        self.point_layer.dataProvider().addFeatures([feat])
        self.point_layer.updateExtents()

        try:
            lt = QgsProject.instance().layerTreeRoot()
            node = lt.findLayer(self.point_layer.id())
            if node:
                lt.insertChildNode(0, node.clone())
                lt.removeChildNode(node)
        except Exception:
            pass

        self.point_fid = next(self.point_layer.getFeatures()).id()

    def set_marker_canvas_point(self, point_canvas):
        if not self.point_layer or self.point_fid is None:
            return
        pr = self.point_layer.dataProvider()
        pr.changeGeometryValues({self.point_fid: QgsGeometry.fromPointXY(point_canvas)})

    def set_marker_heading_pitch_zoom(self, heading, pitch, zoom):
        if not self.point_layer or self.point_fid is None:
            return
        pr = self.point_layer.dataProvider()
        pr.changeAttributeValues({
            self.point_fid: {
                self.point_layer.fields().indexOf('heading'): float(heading),
                self.point_layer.fields().indexOf('pitch'): float(pitch),
                self.point_layer.fields().indexOf('zoom'): float(zoom),
            }
        })
        self.point_layer.triggerRepaint()

    # Map interactions
    def activate_map_tool(self):
        self.iface.mapCanvas().setMapTool(self.map_tool)
        self.touch_activity()
        self.update_status()

    def on_canvas_clicked(self, point, button):
        self.map_click_count += 1
        self.touch_activity()

        canvas = self.iface.mapCanvas()
        crs_src = canvas.mapSettings().destinationCrs()
        crs_wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        to_wgs84 = QgsCoordinateTransform(crs_src, crs_wgs84, QgsProject.instance())

        wgs_point = to_wgs84.transform(point)
        lat, lon = wgs_point.y(), wgs_point.x()

        self.set_marker_canvas_point(point)
        self.load_street_view_html(lat, lon, self.heading)
        self.update_status()
        log(f"Click #{self.map_click_count} (map) • Lat: {lat}, Lon: {lon}", Qgis.Info)

    # Web interactions
    def on_web_clicked(self):
        self.sv_click_count += 1
        self.touch_activity()
        self.update_status()
        log(f"Click #{self.sv_click_count} (streetview web)", Qgis.Info)

    # JS ↔ Python helpers
    def load_street_view_html(self, lat, lon, heading_deg):
        tpl_path = os.path.join(os.path.dirname(__file__), "streetview_template.html")
        with open(tpl_path, "r", encoding="utf-8") as f:
            html = f.read()
        html = (html.replace("{lat}", str(lat))
                    .replace("{lon}", str(lon))
                    .replace("{heading}", str(float(heading_deg)))
                    .replace("{api_key}", self.api_key))
        self.webview.setHtml(html)
        self.touch_activity()

    def update_marker_position_from_wgs(self, lat, lon):
        canvas = self.iface.mapCanvas()
        crs_dst = canvas.mapSettings().destinationCrs()
        tr = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"), crs_dst, QgsProject.instance())
        pt_canvas = tr.transform(QgsPointXY(lon, lat))
        self.set_marker_canvas_point(pt_canvas)
        self.touch_activity()

    def update_marker_heading(self, heading, pitch, zoom):
        self.heading = float(heading)
        self.pitch = float(pitch)
        self.zoom = float(zoom)
        self.set_marker_heading_pitch_zoom(self.heading, self.pitch, self.zoom)
        self.update_status()
        self.touch_activity()

    # Logout in Dock
    def on_logout_clicked(self):
        QtWidgets.QApplication.beep()
        reply = QtWidgets.QMessageBox.warning(
            self, "Confirm Logout",
            "⚠️ คุณต้องการออกจากระบบและล้างค่าทั้งหมดหรือไม่?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        if reply == QtWidgets.QMessageBox.Yes:
            self.reset_state()
            self.requestLogout.emit()
        else:
            log("Logout cancelled by user", Qgis.Info)

# ------------------ Plugin Entry ------------------
class StreetViewQGISCej:
    def __init__(self, iface):
        self.iface = iface
        self.widget = None
        self.action = None
        self.logout_action = None
        self.login_user = ""

    def initGui(self):
        self.action = QtWidgets.QAction("OpenStreetView", self.iface.mainWindow())
        self.action.triggered.connect(self.open_street_view)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&Street View Plugin", self.action)

        self.logout_action = QtWidgets.QAction("Logout StreetView", self.iface.mainWindow())
        self.logout_action.triggered.connect(lambda: self.logout(skip_confirm=False))
        self.iface.addPluginToMenu("&Street View Plugin", self.logout_action)

    def unload(self):
        if self.action:
            self.iface.removePluginMenu("&Street View Plugin", self.action)
            self.iface.removeToolBarIcon(self.action)
        if self.logout_action:
            self.iface.removePluginMenu("&Street View Plugin", self.logout_action)
        if self.widget:
            self.iface.removeDockWidget(self.widget)
            self.widget = None

    # Login gate
    def ensure_login(self) -> bool:
        if self.login_user:
            return True
        dlg = LoginDialog(self.iface.mainWindow())
        res = dlg.exec_()
        if res == QtWidgets.QDialog.Accepted:
            self.login_user = dlg.username() or "user"
            log(f"Login success: {self.login_user}", Qgis.Info)
            return True
        else:
            log("Login cancelled/failed", Qgis.Warning)
            return False

    def open_street_view(self):
        if not self.ensure_login():
            QtWidgets.QMessageBox.information(
                self.iface.mainWindow(), "Street View", "ต้องล็อกอินก่อนใช้งานปลั๊กอิน"
            )
            return

        if not self.widget:
            api_key = 'AIzaSyB3CBkQPkDRSbSRZEw4yozTvtDnusVyIJM'  # ★ ใส่ Google Maps JS API key ของคุณ
            self.widget = StreetViewDockWidget(self.iface, api_key, self.login_user)
            self.widget.requestLogout.connect(lambda: self.logout(skip_confirm=True))

        self.widget.show()
        self.widget.activate_map_tool()

    # Central logout
    def logout(self, skip_confirm: bool = False):
        if not skip_confirm:
            QtWidgets.QApplication.beep()
            reply = QtWidgets.QMessageBox.warning(
                self.iface.mainWindow(), "Confirm Logout",
                "⚠️ คุณต้องการออกจากระบบและล้างค่าทั้งหมดหรือไม่?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No
            )
            if reply != QtWidgets.QMessageBox.Yes:
                return

        # ลบ token/remember แต่คง last_user
        settings = QSettings(LoginDialog.ORG, LoginDialog.APP)
        settings.remove("user")
        settings.remove("token")
        settings.setValue("remember", False)

        if self.widget:
            try:
                self.widget.reset_state()
            except Exception:
                pass
            self.iface.removeDockWidget(self.widget)
            self.widget = None

        self.login_user = ""
        QtWidgets.QMessageBox.information(
            self.iface.mainWindow(), "Street View",
            "ออกจากระบบและล้างค่าเรียบร้อยแล้ว"
        )