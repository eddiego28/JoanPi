import sys
import os
import json
import datetime
import asyncio
import threading

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QLineEdit, QFileDialog,
    QDialog, QTreeWidget, QComboBox, QSplitter, QGroupBox, QCheckBox,
    QTabWidget, QTextEdit, QApplication
)
from PyQt5.QtCore import Qt, pyqtSlot, pyqtSignal
from PyQt5.QtGui import QColor
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
from common.utils import log_to_file, JsonDetailDialog
from PyQt5.QtWidgets import QTreeWidgetItem

# -----------------------------------------------------------------------------
# Utilidad para asegurarse de que un directorio exista
# -----------------------------------------------------------------------------
def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

# -----------------------------------------------------------------------------
# Función auxiliar para extraer el contenido real de un mensaje WAMP
# -----------------------------------------------------------------------------
def extract_message(data):
    """
    Si data es dict con solo 'args' o 'kwargs', devuelve el valor directamente.
    Por ejemplo: {'args':[msg]} → msg, o {'kwargs':{...}} → {...}
    """
    if isinstance(data, dict):
        keys = set(data.keys())
        if keys.issubset({"args", "kwargs"}):
            if "args" in data and data["args"]:
                return data["args"][0] if len(data["args"]) == 1 else data["args"]
            if "kwargs" in data and data["kwargs"]:
                return data["kwargs"]
        return data
    else:
        return data

# -----------------------------------------------------------------------------
# MultiTopicSubscriber: clase de sesión WAMP para suscripción
# -----------------------------------------------------------------------------
class MultiTopicSubscriber(ApplicationSession):
    def __init__(self, config):
        super().__init__(config)
        self.topics = []                  # Lista de topics a suscribir
        self.on_message_callback = None   # Callback para entregar mensajes
        self.logged = False               # Para notificar solo una vez

    async def onJoin(self, details):
        """
        Al unirse al realm, suscribe a todos los topics y envía un
        único mensaje de éxito o error a través de on_message_callback.
        """
        realm_name = self.config.realm
        global global_sub_sessions
        global_sub_sessions[realm_name] = self

        errors = []
        for t in self.topics:
            try:
                await self.subscribe(
                    lambda *args, topic=t: self.on_event(realm_name, topic, *args),
                    t
                )
            except Exception as e:
                errors.append(f"{t}: {e}")

        if not self.logged:
            self.logged = True
            if errors:
                self.on_message_callback(realm_name, "Subscription", {
                    "error": "No se pudo subscribir: " + ", ".join(errors)
                })
            else:
                self.on_message_callback(realm_name, "Subscription", {
                    "success": "Subscribed successfully"
                })

    async def onDisconnect(self):
        """
        Notifica si la desconexión ocurre antes de que se haya
        logueado un mensaje de conexión.
        """
        realm_name = self.config.realm
        if not self.logged and self.on_message_callback:
            self.on_message_callback(realm_name, "Connection", {
                "error": "Conexión rechazada o perdida"
            })
            self.logged = True

    def on_event(self, realm, topic, *args):
        """
        Callback interno de autobahn al recibir un evento;
        delega en on_message_callback.
        """
        message_data = {"args": args}
        if self.on_message_callback:
            self.on_message_callback(realm, topic, message_data)

    @classmethod
    def factory(cls, topics, on_message_callback):
        """
        Devuelve una función para crear sesiones con los topics
        y callback ya preconfigurados.
        """
        def create_session(config):
            session = cls(config)
            session.topics = topics
            session.on_message_callback = on_message_callback
            return session
        return create_session

# -----------------------------------------------------------------------------
# Inicia/reinicia una sesión WAMP de suscripción para un realm
# -----------------------------------------------------------------------------
def start_subscriber(url, realm, topics, on_message_callback):
    global global_sub_sessions
    # Si ya existe una sesión para este realm, la cierra
    if realm in global_sub_sessions:
        try:
            global_sub_sessions[realm].leave("Re-subscribing")
        except Exception:
            pass
        del global_sub_sessions[realm]

    # Arranca la nueva sesión en hilo separado
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        runner = ApplicationRunner(url=url, realm=realm)
        try:
            runner.run(MultiTopicSubscriber.factory(topics, on_message_callback))
        except Exception as e:
            on_message_callback(realm, "Connection", {"error": str(e)})

    threading.Thread(target=run, daemon=True).start()

# -----------------------------------------------------------------------------
# Diálogo para mostrar un JSON en pestañas Raw y Tree, con botón Copiar
# -----------------------------------------------------------------------------
class JsonDetailTabsDialog(QDialog):
    def __init__(self, data, parent=None):
        super().__init__(parent)
        # Si viene como string, intentamos parsear
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                pass
        self.raw_json_str = json.dumps(data, indent=2, ensure_ascii=False)

        self.setWindowTitle("JSON Details")
        self.resize(600, 400)
        layout = QVBoxLayout(self)

        copyBtn = QPushButton("Copy JSON")
        copyBtn.clicked.connect(self.copyJson)
        layout.addWidget(copyBtn)

        tabs = QTabWidget()
        # Pestaña Raw JSON
        rawTab = QWidget()
        rawLayout = QVBoxLayout(rawTab)
        rawText = QTextEdit()
        rawText.setReadOnly(True)
        rawText.setPlainText(self.raw_json_str)
        rawLayout.addWidget(rawText)
        tabs.addTab(rawTab, "Raw JSON")

        # Pestaña Tree View
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
        """
        Construye recursivamente nodos QTreeWidgetItem para dicts/listas.
        """
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
        """
        Copia el JSON formateado al portapapeles.
        """
        QApplication.clipboard().setText(self.raw_json_str)
        QMessageBox.information(self, "Copied", "JSON copied to clipboard.")

# -----------------------------------------------------------------------------
# Widget para mostrar en tabla los mensajes recibidos
# -----------------------------------------------------------------------------
class SubscriberMessageViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.messages = []
        self.openDialogs = []

        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Time", "Realm", "Topic"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.itemDoubleClicked.connect(self.showDetails)
        layout.addWidget(self.table)

    def add_message(self, realm, topic, timestamp, raw_details, error=False):
        """
        Añade una fila al log con la info básica; almacena el detalle en self.messages.
        """
        # Intentamos parsear a dict
        try:
            data = json.loads(raw_details) if isinstance(raw_details, str) else raw_details
        except:
            data = {"message": raw_details}

        row = self.table.rowCount()
        self.table.insertRow(row)
        for col, text in enumerate([timestamp, realm, topic]):
            item = QTableWidgetItem(text)
            if error:
                item.setForeground(QColor("red"))
            self.table.setItem(row, col, item)

        self.messages.append(data)

    def showDetails(self, item):
        """
        Al hacer doble clic, abre el JsonDetailTabsDialog con el JSON correspondiente.
        """
        data = self.messages[item.row()]
        dlg = JsonDetailTabsDialog(data)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.show()
        self.openDialogs.append(dlg)
        dlg.finished.connect(lambda: self.openDialogs.remove(dlg))

# -----------------------------------------------------------------------------
# SubscriberTab: toda la lógica de la pestaña de Subscriber
# -----------------------------------------------------------------------------
class SubscriberTab(QWidget):
    messageReceived = pyqtSignal(str, str, str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.realms_topics = {}              # { realm: {router_url, topics} }
        self.selected_topics_by_realm = {}   # { realm: set(topics) }
        self.current_realm = None

        # Checkboxes "All Realms" / "All Topics"
        self.checkAllRealms = QCheckBox("All Realms")
        self.checkAllRealms.stateChanged.connect(self.toggleAllRealms)
        self.checkAllTopics = QCheckBox("All Topics")
        self.checkAllTopics.stateChanged.connect(self.toggleAllTopics)

        self.messageReceived.connect(self.onMessageReceived)

        self.initUI()
        self.loadGlobalRealmTopicConfig()

    def initUI(self):
        """
        Construye toda la interfaz: tablas, botones, layout principal.
        """
        mainLayout = QHBoxLayout(self)

        # Panel izquierdo: realms y topics
        leftLayout = QVBoxLayout()
        leftLayout.addWidget(self.checkAllRealms)
        leftLayout.addWidget(QLabel("Realms (checkbox) + Router URL:"))

        self.realmTable = QTableWidget(0, 2)
        self.realmTable.setHorizontalHeaderLabels(["Realm", "Router URL"])
        self.realmTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.realmTable.cellClicked.connect(self.onRealmClicked)
        leftLayout.addWidget(self.realmTable)

        realmBtns = QHBoxLayout()
        self.newRealmEdit = QLineEdit()
        self.newRealmEdit.setPlaceholderText("New Realm")
        realmBtns.addWidget(self.newRealmEdit)
        realmBtns.addWidget(QPushButton("Add Realm", clicked=self.addRealmRow))
        realmBtns.addWidget(QPushButton("Remove Realm", clicked=self.deleteRealmRow))
        leftLayout.addLayout(realmBtns)

        leftLayout.addWidget(self.checkAllTopics)
        leftLayout.addWidget(QLabel("Topics (checkbox):"))
        self.topicTable = QTableWidget(0, 1)
        self.topicTable.setHorizontalHeaderLabels(["Topic"])
        self.topicTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.topicTable.itemChanged.connect(self.onTopicChanged)
        leftLayout.addWidget(self.topicTable)

        topicBtns = QHBoxLayout()
        self.newTopicEdit = QLineEdit()
        self.newTopicEdit.setPlaceholderText("New Topic")
        topicBtns.addWidget(self.newTopicEdit)
        topicBtns.addWidget(QPushButton("Add Topic", clicked=self.addTopicRow))
        topicBtns.addWidget(QPushButton("Remove Topic", clicked=self.deleteTopicRow))
        leftLayout.addLayout(topicBtns)

        ctrlLayout = QHBoxLayout()
        ctrlLayout.addWidget(QPushButton("Subscribe", clicked=self.confirmAndStartSubscription))
        ctrlLayout.addWidget(QPushButton("Stop Subscription", clicked=self.stopSubscription))
        ctrlLayout.addWidget(QPushButton("Reset Log", clicked=self.resetLog))
        leftLayout.addLayout(ctrlLayout)

        mainLayout.addLayout(leftLayout, 1)

        # Panel derecho: visor de mensajes
        self.viewer = SubscriberMessageViewer(self)
        mainLayout.addWidget(self.viewer, 2)

    def get_config_path(self):
        """
        Devuelve la ruta absoluta a <root>/projects/subscriber
        partiendo de este fichero.
        """
        if getattr(sys, 'frozen', False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, 'projects', 'subscriber')

    def loadGlobalRealmTopicConfig(self):
        """
        Carga realm_topic_config.json para inicializar self.realms_topics.
        Luego llama a populateRealmTable().
        """
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'realm_topic_config.json')
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # Admite lista o dict
                if isinstance(data.get("realms"), list):
                    tmp = {}
                    for it in data["realms"]:
                        realm = it.get("realm")
                        tmp[realm] = {
                            'router_url': it.get("router_url", ""),
                            'topics': it.get("topics", [])
                        }
                    self.realms_topics = tmp
                else:
                    self.realms_topics = data.get("realms", {})
                self.populateRealmTable()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error loading config:\n{e}")
        else:
            QMessageBox.warning(self, "Warning", "realm_topic_config.json not found.")

    def populateRealmTable(self):
        """
        Rellena la tabla de Realms usando self.realms_topics.
        Todos los checkboxes a unchecked por defecto.
        """
        self.realmTable.blockSignals(True)
        self.realmTable.setRowCount(0)
        for realm, info in sorted(self.realms_topics.items()):
            r = self.realmTable.rowCount()
            self.realmTable.insertRow(r)
            item = QTableWidgetItem(realm)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.realmTable.setItem(r, 0, item)
            self.realmTable.setItem(r, 1, QTableWidgetItem(info.get('router_url', '')))
        self.realmTable.blockSignals(False)
        if self.realmTable.rowCount() > 0:
            self.onRealmClicked(0, 0)

    def onRealmClicked(self, row, col):
        """
        Cuando se hace click en un realm, recarga la lista de topics
        para ese realm en self.topicTable.
        """
        realm_item = self.realmTable.item(row, 0)
        if not realm_item:
            return
        realm = realm_item.text()
        self.current_realm = realm
        topics = self.realms_topics.get(realm, {}).get('topics', [])
        self.topicTable.blockSignals(True)
        self.topicTable.setRowCount(0)
        sel = self.selected_topics_by_realm.get(realm, set())
        for t in topics:
            i = self.topicTable.rowCount()
            self.topicTable.insertRow(i)
            it = QTableWidgetItem(t)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if t in sel else Qt.Unchecked)
            self.topicTable.setItem(i, 0, it)
        self.topicTable.blockSignals(False)

    def onTopicChanged(self, item):
        """
        Actualiza self.selected_topics_by_realm[current_realm] según
        los checkboxes en la tabla de topics.
        """
        if not self.current_realm:
            return
        sel = set()
        for i in range(self.topicTable.rowCount()):
            it = self.topicTable.item(i, 0)
            if it and it.checkState() == Qt.Checked:
                sel.add(it.text())
        self.selected_topics_by_realm[self.current_realm] = sel

    def addRealmRow(self):
        """Añade una fila vacía para un nuevo realm."""
        realm = self.newRealmEdit.text().strip()
        if not realm:
            return
        r = self.realmTable.rowCount()
        self.realmTable.insertRow(r)
        it = QTableWidgetItem(realm)
        it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
        it.setCheckState(Qt.Unchecked)
        self.realmTable.setItem(r, 0, it)
        self.realmTable.setItem(r, 1, QTableWidgetItem("ws://127.0.0.1:60001"))
        self.newRealmEdit.clear()

    def deleteRealmRow(self):
        """Elimina las filas de realm cuyo checkbox NO esté marcado."""
        to_del = []
        for i in range(self.realmTable.rowCount()):
            it = self.realmTable.item(i, 0)
            if it and it.checkState() != Qt.Checked:
                to_del.append(i)
        for i in reversed(to_del):
            self.realmTable.removeRow(i)

    def addTopicRow(self):
        """Añade una fila vacía para un nuevo topic en el realm actual."""
        topic = self.newTopicEdit.text().strip()
        if not topic:
            return
        i = self.topicTable.rowCount()
        self.topicTable.insertRow(i)
        it = QTableWidgetItem(topic)
        it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
        it.setCheckState(Qt.Unchecked)
        self.topicTable.setItem(i, 0, it)
        self.newTopicEdit.clear()

    def deleteTopicRow(self):
        """Elimina los topics cuyo checkbox NO esté marcado."""
        to_del = []
        for i in range(self.topicTable.rowCount()):
            it = self.topicTable.item(i, 0)
            if it and it.checkState() != Qt.Checked:
                to_del.append(i)
        for i in reversed(to_del):
            self.topicTable.removeRow(i)

    def toggleAllRealms(self, state):
        """Marca o desmarca todos los realms en la tabla."""
        for i in range(self.realmTable.rowCount()):
            it = self.realmTable.item(i, 0)
            it.setCheckState(Qt.Checked if state == Qt.Checked else Qt.Unchecked)
        if state == Qt.Checked:
            self.selected_topics_by_realm = {
                realm: set(info.get('topics', []))
                for realm, info in self.realms_topics.items()
            }
        else:
            self.selected_topics_by_realm = {
                realm: set() for realm in self.realms_topics
            }

    def toggleAllTopics(self, state):
        """Marca o desmarca todos los topics del realm actual."""
        if not self.current_realm:
            return
        for i in range(self.topicTable.rowCount()):
            it = self.topicTable.item(i, 0)
            it.setCheckState(Qt.Checked if state == Qt.Checked else Qt.Unchecked)
        if state == Qt.Checked:
            self.selected_topics_by_realm[self.current_realm] = set(
                self.realms_topics[self.current_realm].get('topics', [])
            )
        else:
            self.selected_topics_by_realm[self.current_realm] = set()

    def confirmAndStartSubscription(self):
        """
        Pregunta antes de detener una suscripción activa
        y comenzar una nueva.
        """
        global global_sub_sessions
        if global_sub_sessions:
            reply = QMessageBox.question(
                self, "Confirm",
                "An active subscription exists. Stop it and start a new one?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
            self.stopSubscription()
        self.startSubscription()

    def startSubscription(self):
        """
        Itera por todos los realms marcados, obtiene sus topics
        y llama a start_subscriber() para cada uno.
        """
        for i in range(self.realmTable.rowCount()):
            realm_it = self.realmTable.item(i, 0)
            url_it   = self.realmTable.item(i, 1)
            if realm_it.checkState() == Qt.Checked:
                realm = realm_it.text()
                url   = url_it.text() if url_it else ""
                topics = list(self.selected_topics_by_realm.get(realm, []))
                if not topics:
                    QMessageBox.warning(
                        self, "Warning",
                        f"No topics selected for realm '{realm}'."
                    )
                    continue
                start_subscriber(url, realm, topics, self.handleMessage)

    def stopSubscription(self):
        """Detiene todas las sesiones activas."""
        global global_sub_sessions
        if not global_sub_sessions:
            QMessageBox.warning(self, "Warning", "No active subscriptions.")
            return
        for realm, session in list(global_sub_sessions.items()):
            try:
                session.leave("Stop requested")
            except:
                pass
            del global_sub_sessions[realm]
        QMessageBox.information(self, "Subscriber", "Subscriptions stopped.")

    def handleMessage(self, realm, topic, content):
        """
        Callback que recibe MultiTopicSubscriber; emite señal
        para la UI y registra en archivo.
        """
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        filtered = extract_message(content)
        details = json.dumps(filtered, indent=2, ensure_ascii=False)
        error_flag = isinstance(filtered, dict) and "error" in filtered

        # Emite señal para que onMessageReceived lo añada al viewer
        self.messageReceived.emit(realm, topic, timestamp, details)
        # También guarda en log de disco
        log_to_file(timestamp, realm, topic, details)

    @pyqtSlot(str, str, str, object)
    def onMessageReceived(self, realm, topic, timestamp, details_str):
        """
        Slot conectado a messageReceived: añade la fila al viewer.
        """
        error_flag = "error" in details_str
        self.viewer.add_message(realm, topic, timestamp, details_str, error_flag)

    def resetLog(self):
        """Limpia la tabla de mensajes recibidos."""
        self.viewer.table.setRowCount(0)
        self.viewer.messages.clear()

    def getProjectConfig(self):
        """
        Devuelve un dict listo para serializar con la configuración actual:
        { "realms": [ {realm, router_url, topics}, ... ] }
        """
        realms = []
        for realm, info in self.realms_topics.items():
            realms.append({
                'realm': realm,
                'router_url': info.get('router_url', ''),
                'topics': info.get('topics', [])
            })
        return {'realms': realms}

    def saveProject(self):
        """
        Abre diálogo en <root>/projects/subscriber para guardar JSON
        con getProjectConfig().
        """
        base_dir = self.get_config_path()
        ensure_dir(base_dir)
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Subscriber Config", base_dir, "JSON Files (*.json)"
        )
        if not filepath:
            return
        try:
            config = self.getProjectConfig()
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Subscriber", "Configuration saved.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save:\n{e}")

    def loadProject(self):
        """
        Abre diálogo en <root>/projects/subscriber para cargar JSON.
        Luego delega en loadProjectFromConfig().
        """
        base_dir = self.get_config_path()
        ensure_dir(base_dir)
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Load Subscriber Config", base_dir, "JSON Files (*.json)"
        )
        if not filepath:
            return
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                config = json.load(f)
            self.loadProjectFromConfig(config)
            QMessageBox.information(self, "Subscriber", "Configuration loaded.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load:\n{e}")

    def loadProjectFromConfig(self, config):
        """
        Toma un dict con clave 'realms' o directamente el dict,
        y actualiza self.realms_topics, self.selected_topics_by_realm
        y la UI (populateRealmTable).
        """
        data = config.get('realms', config)
        new_realms = {}
        if isinstance(data, list):
            for item in data:
                realm = item.get('realm')
                if not realm:
                    continue
                new_realms[realm] = {
                    'router_url': item.get('router_url', ''),
                    'topics': item.get('topics', [])
                }
        elif isinstance(data, dict):
            new_realms = data

        self.realms_topics = new_realms
        self.selected_topics_by_realm = {
            realm: set(info.get('topics', []))
            for realm, info in new_realms.items()
        }
        self.populateRealmTable()
