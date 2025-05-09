import sys
import os
import json
import datetime
import logging
import asyncio
import threading

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QPushButton, QSplitter,
    QGroupBox, QFormLayout, QMessageBox, QLineEdit, QFileDialog, QComboBox, QCheckBox, QDialog, QTextEdit, QTreeWidget, QTreeWidgetItem, QTabWidget
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor

from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
from common.utils import log_to_file, JsonDetailDialog

from .pubEditor import PublisherEditorWidget

# -----------------------------------------------------------------------------
# ensure_dir: crea un directorio si no existe
# -----------------------------------------------------------------------------
def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

# -----------------------------------------------------------------------------
# Carga la configuración de realms y topics para el publisher
# -----------------------------------------------------------------------------
REALMS_CONFIG = {}
def load_realm_topic_config():
    global REALMS_CONFIG
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(base, "..", "config", "realm_topic_config_pub.json")
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        # Admite lista de realms o dict
        if isinstance(cfg.get("realms"), list):
            tmp = {}
            for it in cfg["realms"]:
                realm = it.get("realm", "default")
                tmp[realm] = {
                    "router_url": it.get("router_url", "ws://127.0.0.1:60001"),
                    "topics": it.get("topics", [])
                }
            REALMS_CONFIG = tmp
        else:
            REALMS_CONFIG = cfg.get("realms", {})
    except Exception as e:
        # Config fallback
        REALMS_CONFIG = {
            "default": {"router_url": "ws://127.0.0.1:60001", "topics": []}
        }
        print("Error loading pub config:", e)

# Ejecuta la carga de configuración al importar
load_realm_topic_config()

# -----------------------------------------------------------------------------
# JSONPublisher: sesión WAMP para publicar mensajes JSON
# -----------------------------------------------------------------------------
class JSONPublisher(ApplicationSession):
    def __init__(self, config, topic, widget):
        super().__init__(config)
        self.topic = topic
        self.widget = widget  # referencia al MessageConfigWidget

    async def onJoin(self, details):
        """
        Una vez conectado, guarda la sesión y permanece esperando
        para publicar mensajes.
        """
        self.loop = asyncio.get_event_loop()
        self.widget.session = self
        self.widget.loop = self.loop
        global global_pub_sessions
        global_pub_sessions[self.config.realm] = self
        print(f"Publisher connected: realm={self.config.realm}, topic={self.topic}")
        await asyncio.Future()  # No cerrar nunca

# Diccionario global de sesiones activas
global_pub_sessions = {}

# -----------------------------------------------------------------------------
# start_publisher: inicia o reutiliza una sesión para un realm dado
# -----------------------------------------------------------------------------
def start_publisher(url, realm, topic, widget):
    global global_pub_sessions
    if realm in global_pub_sessions:
        # Reutilizamos la sesión existente
        widget.session = global_pub_sessions[realm]
        widget.loop = widget.session.loop
        print(f"Reusing publisher session for realm '{realm}'")
    else:
        # Creamos una nueva en un hilo
        def run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            runner = ApplicationRunner(url=url, realm=realm)
            def factory(cfg):
                return JSONPublisher(cfg, topic, widget)
            runner.run(factory)
        threading.Thread(target=run, daemon=True).start()

# -----------------------------------------------------------------------------
# send_message_now: publica inmediatamente o tras un delay
# -----------------------------------------------------------------------------
def send_message_now(session, loop, topic, message, delay=0):
    async def _send():
        if delay > 0:
            await asyncio.sleep(delay)
        # Publica con args o kwargs según tipo
        if isinstance(message, dict):
            session.publish(topic, **message)
        else:
            session.publish(topic, message)
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_to_file(ts, topic, session.config.realm, json.dumps(message, indent=2, ensure_ascii=False))
        print(f"Published on {topic}: {message}")
    if session and loop:
        asyncio.run_coroutine_threadsafe(_send(), loop)

# -----------------------------------------------------------------------------
# JsonDetailTabsDialog: muestra JSON en pestañas Raw y Tree
# -----------------------------------------------------------------------------
class JsonDetailTabsDialog(QDialog):
    def __init__(self, data, parent=None):
        super().__init__(parent)
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except:
                pass
        self.raw_json_str = json.dumps(data, indent=2, ensure_ascii=False)

        self.setWindowTitle("JSON Details")
        self.resize(600, 400)
        layout = QVBoxLayout(self)

        copyBtn = QPushButton("Copy JSON")
        copyBtn.clicked.connect(self.copyJson)
        layout.addWidget(copyBtn)

        tabs = QTabWidget()
        # Raw JSON
        rawTab = QWidget()
        rawLayout = QVBoxLayout(rawTab)
        rawText = QTextEdit()
        rawText.setReadOnly(True)
        rawText.setPlainText(self.raw_json_str)
        rawLayout.addWidget(rawText)
        tabs.addTab(rawTab, "Raw JSON")
        # Tree view
        treeTab = QWidget()
        treeLayout = QVBoxLayout(treeTab)
        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        self.buildTree(data, tree.invisibleRootItem())
        tree.expandAll()
        treeLayout.addWidget(tree)
        tabs.addTab(treeTab, "Tree View")

        layout.addWidget(tabs)

    def buildTree(self, data, parent):
        if isinstance(data, dict):
            for k, v in data.items():
                item = QTreeWidgetItem([str(k)])
                parent.addChild(item)
                self.buildTree(v, item)
        elif isinstance(data, list):
            for i, v in enumerate(data):
                item = QTreeWidgetItem([f"[{i}]"])
                parent.addChild(item)
                self.buildTree(v, item)
        else:
            QTreeWidgetItem(parent, [str(data)])

    def copyJson(self):
        QApplication.clipboard().setText(self.raw_json_str)
        QMessageBox.information(self, "Copied", "JSON copied to clipboard.")

# -----------------------------------------------------------------------------
# PublisherMessageViewer: tabla de logs de publicación
# -----------------------------------------------------------------------------
class PublisherMessageViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logs = []
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Time", "Realm", "Topic"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.itemDoubleClicked.connect(self.showDetails)
        layout.addWidget(self.table)

    def add_message(self, realm, topic, timestamp, details, error=False):
        row = self.table.rowCount()
        self.table.insertRow(row)
        for col, text in enumerate([timestamp, realm, topic]):
            item = QTableWidgetItem(text)
            if error:
                item.setForeground(QColor("red"))
            self.table.setItem(row, col, item)
        self.logs.append(details)

    def showDetails(self, item):
        dlg = JsonDetailTabsDialog(self.logs[item.row()])
        dlg.show()

# -----------------------------------------------------------------------------
# MessageConfigWidget: configura un solo mensaje (realm, topic, JSON, horario)
# -----------------------------------------------------------------------------
class MessageConfigWidget(QWidget):
    def __init__(self, msg_id, parent=None):
        super().__init__(parent)
        self.msg_id = msg_id
        self.session = None
        self.loop = None
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)

        # Header con checkbox (habilitar), etiqueta y botones
        hdr = QHBoxLayout()
        self.enableChk = QCheckBox()
        self.enableChk.setChecked(True)
        self.enableChk.stateChanged.connect(self.onEnableChanged)
        hdr.addWidget(self.enableChk)

        self.headerLabel = QLabel(f"Message #{self.msg_id}")
        hdr.addWidget(self.headerLabel)
        hdr.addStretch()

        self.minBtn = QPushButton("–")
        self.minBtn.setFixedSize(20, 20)
        self.minBtn.clicked.connect(self.toggleMinimize)
        hdr.addWidget(self.minBtn)

        self.delBtn = QPushButton("Delete")
        self.delBtn.setFixedSize(50, 20)
        self.delBtn.clicked.connect(self.deleteSelf)
        hdr.addWidget(self.delBtn)

        layout.addLayout(hdr)

        # Contenido: Connection Settings + Message Content
        self.content = QWidget()
        cl = QVBoxLayout(self.content)

        # Connection Settings
        connGroup = QGroupBox("Connection Settings")
        frm = QFormLayout()
        self.realmCombo = QComboBox()
        self.realmCombo.addItems(list(REALMS_CONFIG.keys()))
        self.realmCombo.currentTextChanged.connect(self.updateTopics)
        frm.addRow("Realm:", self.realmCombo)

        self.urlEdit = QLineEdit()
        frm.addRow("Router URL:", self.urlEdit)

        self.topicCombo = QComboBox()
        frm.addRow("Topic:", self.topicCombo)
        connGroup.setLayout(frm)
        cl.addWidget(connGroup)

        # Message Content
        contentGroup = QGroupBox("Message Content")
        cg = QVBoxLayout()
        self.editor = PublisherEditorWidget(self)
        cg.addWidget(self.editor)
        contentGroup.setLayout(cg)
        cl.addWidget(contentGroup)

        layout.addWidget(self.content)

        # Botón Send Now
        sendBtn = QPushButton("Send Now")
        sendBtn.clicked.connect(self.sendMessage)
        layout.addWidget(sendBtn)

        self.setLayout(layout)
        # Inicializa campos
        self.updateTopics(self.realmCombo.currentText())
        # Conecta radio toggles si los hubiera
        self.editor.onDemandRadio.toggled.connect(lambda c: self.editor.commonTimeEdit.setDisabled(c))

    def onEnableChanged(self, state):
        """Activa o desactiva todo el content según el checkbox."""
        self.content.setDisabled(state != Qt.Checked)

    def toggleMinimize(self):
        """Minimiza o expande el widget."""
        vis = not self.content.isVisible()
        self.content.setVisible(vis)
        self.minBtn.setText("+" if not vis else "–")

    def deleteSelf(self):
        """Elimina este widget de su contenedor."""
        parent = self.parentWidget()
        while parent and not hasattr(parent, "removeMessageWidget"):
            parent = parent.parentWidget()
        if parent:
            parent.removeMessageWidget(self)

    def updateTopics(self, realm):
        """Recarga la lista de topics cuando cambia el realm."""
        info = REALMS_CONFIG.get(realm, {})
        topics = info.get("topics", [])
        self.topicCombo.clear()
        self.topicCombo.addItems(topics)
        self.urlEdit.setText(info.get("router_url", ""))

    def sendMessage(self):
        """Publica inmediatamente el JSON configurado."""
        try:
            data = json.loads(self.editor.jsonPreview.toPlainText())
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Invalid JSON:\n{e}")
            return
        topic = self.topicCombo.currentText().strip()
        delay = 0  # on-demand
        if self.session and self.loop:
            send_message_now(self.session, self.loop, topic, data, delay)
        else:
            QMessageBox.warning(self, "Error", "No active publisher session.")
            return

    def getConfig(self):
        """Devuelve un dict con la configuración de este mensaje."""
        mode = "onDemand"
        if self.editor.programmedRadio.isChecked():
            mode = "programmed"
        elif self.editor.SystemRadioTime.isChecked():
            mode = "systemTime"
        return {
            "id": self.msg_id,
            "realm": self.realmCombo.currentText(),
            "router_url": self.urlEdit.text().strip(),
            "topic": self.topicCombo.currentText().strip(),
            "content": json.loads(self.editor.jsonPreview.toPlainText()),
            "mode": mode,
            "time": self.editor.commonTimeEdit.text().strip()
        }

# -----------------------------------------------------------------------------
# PublisherTab: pestaña principal de Publisher, agrupa todos los MessageConfigWidget
# -----------------------------------------------------------------------------
class PublisherTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.msgWidgets = []
        self.next_id = 1
        self.initUI()

    def initUI(self):
        """
        Estructura de dos columnas: 
        - Izquierda: log y botones Start/Stop
        - Derecha: lista de MessageConfigWidget + controles
        """
        splitter = QSplitter(Qt.Horizontal)

        # Izquierda: log
        left = QWidget()
        ll = QVBoxLayout(left)
        hl = QHBoxLayout()
        self.startBtn = QPushButton("Start Publisher")
        self.startBtn.setStyleSheet("background-color: green; color: white;")
        hl.addWidget(self.startBtn)
        self.stopBtn = QPushButton("Stop Publisher")
        self.stopBtn.setStyleSheet("background-color: red; color: white;")
        hl.addWidget(self.stopBtn)
        ll.addLayout(hl)
        self.viewer = PublisherMessageViewer(self)
        ll.addWidget(self.viewer)
        splitter.addWidget(left)

        # Derecha: mensajes
        right = QWidget()
        rl = QVBoxLayout(right)
        self.addMsgBtn = QPushButton("Add Message")
        rl.addWidget(self.addMsgBtn)
        self.msgArea = QScrollArea()
        self.msgArea.setWidgetResizable(True)
        self.msgContainer = QWidget()
        self.msgLayout = QVBoxLayout(self.msgContainer)
        self.msgArea.setWidget(self.msgContainer)
        rl.addWidget(self.msgArea)
        bl = QHBoxLayout()
        self.scenarioBtn = QPushButton("Start Scenario")
        bl.addWidget(self.scenarioBtn)
        self.instantBtn = QPushButton("Send Instant Message")
        bl.addWidget(self.instantBtn)
        rl.addLayout(bl)
        splitter.addWidget(right)

        main = QVBoxLayout(self)
        main.addWidget(splitter)

        # Conexiones
        self.addMsgBtn.clicked.connect(self.addMessage)
        self.startBtn.clicked.connect(self.confirmAndStartPublisher)
        self.stopBtn.clicked.connect(self.stopAllPublishers)
        self.scenarioBtn.clicked.connect(self.startScenario)
        self.instantBtn.clicked.connect(self.sendAllAsync)

    def removeMessageWidget(self, widget):
        """Elimina un MessageConfigWidget del layout."""
        if widget in self.msgWidgets:
            self.msgWidgets.remove(widget)
            widget.deleteLater()

    def addMessage(self):
        """Crea un nuevo MessageConfigWidget y lo añade."""
        w = MessageConfigWidget(self.next_id, parent=self)
        self.msgLayout.addWidget(w)
        self.msgWidgets.append(w)
        self.next_id += 1

    def confirmAndStartPublisher(self):
        """Confirma antes de detener cualquier sesión y iniciar otra."""
        global global_pub_sessions
        if global_pub_sessions:
            reply = QMessageBox.question(
                self, "Confirm",
                "A publisher session exists. Stop it and start a new one?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
            self.stopAllPublishers()
        self.startPublisher()

    def startPublisher(self):
        """Inicia una sesión por cada MessageConfigWidget."""
        for w in self.msgWidgets:
            cfg = w.getConfig()
            start_publisher(cfg["router_url"], cfg["realm"], cfg["topic"], w)
            QTimer.singleShot(500, lambda w=w, c=cfg: self.logPublisherStarted(w, c))

    def logPublisherStarted(self, widget, config):
        """Agrega un log indicando si se inició correctamente la sesión."""
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not widget.session:
            self.viewer.add_message(config["realm"], config["topic"], ts, "Failed to start", error=True)
        else:
            self.viewer.add_message(config["realm"], config["topic"], ts, "Publisher started")

    def stopAllPublishers(self):
        """Detiene todas las sesiones activas."""
        global global_pub_sessions
        for realm, session in list(global_pub_sessions.items()):
            try:
                session.leave("Requested stop")
            except:
                pass
            del global_pub_sessions[realm]
        QMessageBox.information(self, "Publisher", "All publishers stopped.")

    def sendAllAsync(self):
        """Envía inmediatamente todos los mensajes configurados."""
        for w in self.msgWidgets:
            cfg = w.getConfig()
            send_message_now(w.session, w.loop, cfg["topic"], cfg["content"], delay=0)
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.viewer.add_message(cfg["realm"], cfg["topic"], ts, json.dumps(cfg["content"], indent=2), error=False)

    def startScenario(self):
        """Programa cada mensaje según su modo (onDemand/programmed/systemTime)."""
        # Implementar lógica análoga a tu versión original
        pass

    def get_config_path(self, subfolder):
        """
        Devuelve la ruta <root>/projects/publisher/<subfolder>
        partiendo de este fichero.
        """
        if getattr(sys, 'frozen', False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, 'projects', 'publisher', subfolder)

    def getProjectConfig(self):
        """
        Recopila todos los escenarios en un dict serializable:
        { "scenarios": [ {...}, {...}, ... ] }
        """
        return {'scenarios': [w.getConfig() for w in self.msgWidgets]}

    def saveProject(self):
        """
        Guarda la configuración completa de Publisher en /projects/publisher.
        """
        base_dir = os.path.dirname(self.get_config_path(''))
        ensure_dir(base_dir)
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Publisher Config", base_dir, "JSON Files (*.json)"
        )
        if not filepath:
            return
        try:
            cfg = self.getProjectConfig()
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Publisher", "Configuration saved.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save:\n{e}")

    def loadProject(self):
        """
        Carga la configuración de Publisher desde /projects/publisher.
        """
        base_dir = os.path.dirname(self.get_config_path(''))
        ensure_dir(base_dir)
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Load Publisher Config", base_dir, "JSON Files (*.json)"
        )
        if not filepath:
            return
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            self.loadProjectFromConfig(cfg)
            QMessageBox.information(self, "Publisher", "Configuration loaded.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load:\n{e}")

    def loadProjectFromConfig(self, config):
        """
        Aplica un dict {'scenarios': [...]} a la UI,
        recreando los MessageConfigWidget.
        """
        scenarios = config.get('scenarios', [])
        # Limpia la UI
        for w in list(self.msgWidgets):
            w.deleteLater()
        self.msgWidgets.clear()
        self.next_id = 1

        # Crea widgets según cada escenario
        for sc in scenarios:
            w = MessageConfigWidget(self.next_id, parent=self)
            w.realmCombo.setCurrentText(sc.get('realm', ''))
            w.urlEdit.setText(sc.get('router_url', ''))
            w.topicCombo.setCurrentText(sc.get('topic', ''))
            w.editor.jsonPreview.setPlainText(
                json.dumps(sc.get('content', {}), indent=2, ensure_ascii=False)
            )
            w.editor.commonTimeEdit.setText(sc.get('time', '00:00:00'))
            mode = sc.get('mode', 'onDemand')
            if mode == 'programmed':
                w.editor.programmedRadio.setChecked(True)
            elif mode == 'systemTime':
                w.editor.SystemRadioTime.setChecked(True)
            else:
                w.editor.onDemandRadio.setChecked(True)
            self.msgLayout.addWidget(w)
            self.msgWidgets.append(w)
            self.next_id += 1
