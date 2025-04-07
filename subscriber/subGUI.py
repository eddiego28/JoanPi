import os, json, datetime, asyncio, threading, sys
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

# Función auxiliar para extraer el contenido si el mensaje está envuelto solo en args/kwargs
def extract_message(data):
    if isinstance(data, dict):
        keys = set(data.keys())
        if keys.issubset({"args", "kwargs"}):
            if "args" in data and data["args"]:
                if len(data["args"]) == 1:
                    return data["args"][0]
                else:
                    return data["args"]
            elif "kwargs" in data and data["kwargs"]:
                return data["kwargs"]
            else:
                return data
        else:
            return data
    else:
        return data

###############################################################################
# Diccionario global para almacenar las sesiones activas (una por realm)
###############################################################################
global_sub_sessions = {}  # key: realm, value: session object

###############################################################################
# MultiTopicSubscriber: sesión WAMP para suscripción
###############################################################################
class MultiTopicSubscriber(ApplicationSession):
    def __init__(self, config):
        super().__init__(config)
        self.topics = []  # Se asignan antes de iniciar la sesión
        self.on_message_callback = None
        self.logged = False  # Flag para registrar un solo mensaje por intento

    async def onJoin(self, details):
        realm_name = self.config.realm
        global global_sub_sessions
        global_sub_sessions[realm_name] = self
        print(f"Suscriptor connected to realm: {realm_name}")
        errors = []
        for t in self.topics:
            try:
                await self.subscribe(
                    lambda *args, topic=t, **kwargs: self.on_event(realm_name, topic, *args, **kwargs),
                    t
                )
            except Exception as e:
                errors.append(f"Topic {t}: {str(e)}")
        if not self.logged:
            if errors:
                self.logged = True
                if self.on_message_callback:
                    self.on_message_callback(realm_name, "Subscription", {"error": "No se pudo subscribir: " + ", ".join(errors)})
            else:
                self.logged = True
                if self.on_message_callback:
                    self.on_message_callback(realm_name, "Subscription", {"success": "Subscribed successfully"})

    async def onDisconnect(self):
        realm_name = self.config.realm
        if not self.logged:
            if self.on_message_callback:
                self.on_message_callback(realm_name, "Connection", {"error": "Conexión rechazada o perdida"})
            self.logged = True
        print(f"Disconnected from realm: {realm_name}")

    def on_event(self, realm, topic, *args, **kwargs):
        message_data = {"args": args, "kwargs": kwargs}
        if self.on_message_callback:
            self.on_message_callback(realm, topic, message_data)

    @classmethod
    def factory(cls, topics, on_message_callback):
        def create_session(config):
            session = cls(config)
            session.topics = topics
            session.on_message_callback = on_message_callback
            return session
        return create_session

###############################################################################
# start_subscriber: inicia una sesión para cada realm suscrito
###############################################################################
def start_subscriber(url, realm, topics, on_message_callback):
    global global_sub_sessions
    if realm in global_sub_sessions:
        try:
            global_sub_sessions[realm].leave("Re-subscribing with new topics")
            print(f"Previous session for realm '{realm}' closed.")
        except Exception as e:
            print("Error closing previous session:", e)
        del global_sub_sessions[realm]

    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        runner = ApplicationRunner(url=url, realm=realm)
        try:
            runner.run(MultiTopicSubscriber.factory(topics, on_message_callback))
        except Exception as e:
            on_message_callback(realm, "Connection", {"error": f"Connection failed: {str(e)}"})
    threading.Thread(target=run, daemon=True).start()

###############################################################################
# JsonDetailTabsDialog: muestra el JSON en dos pestañas (Raw y Tree) con botón para copiar
###############################################################################
class JsonDetailTabsDialog(QDialog):
    def __init__(self, data, parent=None):
        super().__init__(parent)
        # Si data es una cadena, se intenta cargar como JSON
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                pass
        # Guardamos el JSON formateado en self.raw_json_str para copiar
        self.raw_json_str = json.dumps(data, indent=2, ensure_ascii=False)
        self.setWindowTitle("JSON Details")
        self.resize(600, 400)
        mainLayout = QVBoxLayout(self)
        # Botón para copiar JSON al portapapeles
        copyButton = QPushButton("Copy JSON")
        copyButton.clicked.connect(self.copyJson)
        mainLayout.addWidget(copyButton)
        # Tab widget para mostrar el JSON en raw y en forma de árbol
        tab_widget = QTabWidget(self)
        
        # Pestaña Raw JSON
        raw_tab = QWidget()
        raw_layout = QVBoxLayout(raw_tab)
        raw_text = QTextEdit()
        raw_text.setReadOnly(True)
        raw_text.setPlainText(self.raw_json_str)
        raw_layout.addWidget(raw_text)
        tab_widget.addTab(raw_tab, "Raw JSON")
        
        # Pestaña Tree View
        tree_tab = QWidget()
        tree_layout = QVBoxLayout(tree_tab)
        tree = QTreeWidget()
        tree.setColumnCount(1)
        tree.header().hide()  # Ocultar cabecera
        self.buildTree(data, tree.invisibleRootItem())
        tree.expandAll()
        tree_layout.addWidget(tree)
        tab_widget.addTab(tree_tab, "Tree View")
        
        mainLayout.addWidget(tab_widget)
        self.setLayout(mainLayout)
    
    def buildTree(self, data, parent):
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    item = QTreeWidgetItem([f"{key}:"])
                    parent.addChild(item)
                    self.buildTree(value, item)
                else:
                    item = QTreeWidgetItem([f"{key}: {value}"])
                    parent.addChild(item)
        elif isinstance(data, list):
            for index, value in enumerate(data):
                if isinstance(value, (dict, list)):
                    item = QTreeWidgetItem([f"[{index}]:"])
                    parent.addChild(item)
                    self.buildTree(value, item)
                else:
                    item = QTreeWidgetItem([f"[{index}]: {value}"])
                    parent.addChild(item)
        else:
            item = QTreeWidgetItem([str(data)])
            parent.addChild(item)
    
    def copyJson(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.raw_json_str)
        QMessageBox.information(self, "Copied", "JSON copied to clipboard.")

###############################################################################
# SubscriberMessageViewer: visor de mensajes recibidos (QTable) y detalles (ventanas independientes)
###############################################################################
class SubscriberMessageViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.messages = []       # Datos parseados de los mensajes (dict)
        self.openDialogs = []    # Ventanas de detalle abiertas
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Time", "Realm", "Topic"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.itemDoubleClicked.connect(self.showDetails)
        layout.addWidget(self.table)
        self.setLayout(layout)

    def add_message(self, realm, topic, timestamp, raw_details, error=False):
        if isinstance(raw_details, str):
            try:
                data = json.loads(raw_details)
            except Exception:
                data = {"mensaje": raw_details}
        elif isinstance(raw_details, dict):
            data = raw_details
        else:
            data = {"mensaje": str(raw_details)}
        row = self.table.rowCount()
        self.table.insertRow(row)
        time_item = QTableWidgetItem(timestamp)
        realm_item = QTableWidgetItem(realm)
        topic_item = QTableWidgetItem(topic)
        if error:
            time_item.setForeground(QColor("red"))
            realm_item.setForeground(QColor("red"))
            topic_item.setForeground(QColor("red"))
        self.table.setItem(row, 0, time_item)
        self.table.setItem(row, 1, realm_item)
        self.table.setItem(row, 2, topic_item)
        self.messages.append(data)

    def showDetails(self, item):
        row = item.row()
        if row < len(self.messages):
            data = self.messages[row]
            dlg = JsonDetailTabsDialog(data)
            dlg.setWindowModality(Qt.WindowModal)
            dlg.show()
            self.openDialogs.append(dlg)
            dlg.finished.connect(lambda result, dlg=dlg: self.openDialogs.remove(dlg))

###############################################################################
# SubscriberTab: interfaz principal del suscriptor
###############################################################################
class SubscriberTab(QWidget):
    messageReceived = pyqtSignal(str, str, str, object)  # (realm, topic, timestamp, data_dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.realms_topics = {}          # Se carga desde el archivo de configuración
        self.selected_topics_by_realm = {}
        self.current_realm = None

        self.checkAllRealms = QCheckBox("All Realms")
        self.checkAllRealms.stateChanged.connect(self.toggleAllRealms)
        self.checkAllTopics = QCheckBox("All Topics")
        self.checkAllTopics.stateChanged.connect(self.toggleAllTopics)

        self.messageReceived.connect(self.onMessageReceived)
        self.initUI()
        self.loadGlobalRealmTopicConfig()

    def initUI(self):
        mainLayout = QHBoxLayout(self)

        # Panel izquierdo: Realms y Topics
        leftLayout = QVBoxLayout()
        topCtrlLayoutRealms = QHBoxLayout()
        topCtrlLayoutRealms.addWidget(self.checkAllRealms)
        leftLayout.addLayout(topCtrlLayoutRealms)

        lblRealms = QLabel("Realms (checkbox) + Router URL:")
        leftLayout.addWidget(lblRealms)
        self.realmTable = QTableWidget(0, 2)
        self.realmTable.setHorizontalHeaderLabels(["Realm", "Router URL"])
        self.realmTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.realmTable.cellClicked.connect(self.onRealmClicked)
        self.realmTable.itemChanged.connect(self.onRealmItemChanged)
        leftLayout.addWidget(self.realmTable)

        realmBtnsLayout = QHBoxLayout()
        self.newRealmEdit = QLineEdit()
        self.newRealmEdit.setPlaceholderText("New Realm")
        self.btnAddRealm = QPushButton("Add Realm")
        self.btnAddRealm.clicked.connect(self.addRealmRow)
        self.btnDelRealm = QPushButton("Remove Realm")
        self.btnDelRealm.clicked.connect(self.deleteRealmRow)
        realmBtnsLayout.addWidget(self.newRealmEdit)
        realmBtnsLayout.addWidget(self.btnAddRealm)
        realmBtnsLayout.addWidget(self.btnDelRealm)
        leftLayout.addLayout(realmBtnsLayout)

        topCtrlLayoutTopics = QHBoxLayout()
        topCtrlLayoutTopics.addWidget(self.checkAllTopics)
        leftLayout.addLayout(topCtrlLayoutTopics)

        lblTopics = QLabel("Topics (checkbox):")
        leftLayout.addWidget(lblTopics)
        self.topicTable = QTableWidget(0, 1)
        self.topicTable.setHorizontalHeaderLabels(["Topic"])
        self.topicTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.topicTable.itemChanged.connect(self.onTopicChanged)
        leftLayout.addWidget(self.topicTable)

        topicBtnsLayout = QHBoxLayout()
        self.newTopicEdit = QLineEdit()
        self.newTopicEdit.setPlaceholderText("New Topic")
        self.btnAddTopic = QPushButton("Add Topic")
        self.btnAddTopic.clicked.connect(self.addTopicRow)
        self.btnDelTopic = QPushButton("Remove Topic")
        self.btnDelTopic.clicked.connect(self.deleteTopicRow)
        topicBtnsLayout.addWidget(self.newTopicEdit)
        topicBtnsLayout.addWidget(self.btnAddTopic)
        topicBtnsLayout.addWidget(self.btnDelTopic)
        leftLayout.addLayout(topicBtnsLayout)

        ctrlLayout = QHBoxLayout()
        self.btnSubscribe = QPushButton("Subscribe")
        self.btnSubscribe.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
            }
        """)
        self.btnSubscribe.clicked.connect(self.confirmAndStartSubscription)
        ctrlLayout.addWidget(self.btnSubscribe)

        self.btnStop = QPushButton("Stop Subscription")
        self.btnStop.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                font-weight: bold;
            }
        """)
        self.btnStop.clicked.connect(self.stopSubscription)
        ctrlLayout.addWidget(self.btnStop)

        self.btnReset = QPushButton("Reset Log")
        self.btnReset.setStyleSheet("""
            QPushButton {
                background-color: #fd7e14;
                color: white;
                font-weight: bold;
            }
        """)
        self.btnReset.clicked.connect(self.resetLog)
        ctrlLayout.addWidget(self.btnReset)

        leftLayout.addLayout(ctrlLayout)
        mainLayout.addLayout(leftLayout, stretch=1)

        self.viewer = SubscriberMessageViewer(self)
        mainLayout.addWidget(self.viewer, stretch=2)
        self.setLayout(mainLayout)

    def confirmAndStartSubscription(self):
        global global_sub_sessions
        if global_sub_sessions:
            reply = QMessageBox.question(self, "Confirm",
                                         "An active subscription already exists. Would you like to stop it and start a new one?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.stopSubscription()
            else:
                return
        self.startSubscription()

    def toggleAllRealms(self, state):
        for row in range(self.realmTable.rowCount()):
            item = self.realmTable.item(row, 0)
            if item:
                item.setCheckState(Qt.Checked if state == Qt.Checked else Qt.Unchecked)
        for realm, info in self.realms_topics.items():
            if state == Qt.Checked:
                self.selected_topics_by_realm[realm] = set(info.get("topics", []))
            else:
                self.selected_topics_by_realm[realm] = set()

    def toggleAllTopics(self, state):
        if not self.current_realm:
            return
        for row in range(self.topicTable.rowCount()):
            item = self.topicTable.item(row, 0)
            if item:
                item.setCheckState(Qt.Checked if state == Qt.Checked else Qt.Unchecked)
        if self.current_realm in self.realms_topics:
            if state == Qt.Checked:
                self.selected_topics_by_realm[self.current_realm] = set(self.realms_topics[self.current_realm].get("topics", []))
            else:
                self.selected_topics_by_realm[self.current_realm] = set()

    def get_config_path(self, filename):
        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_path, "config", filename)

    def loadGlobalRealmTopicConfig(self):
        config_path = self.get_config_path("realm_topic_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data.get("realms"), list):
                    new_dict = {}
                    for item in data["realms"]:
                        realm = item.get("realm", "default")
                        new_dict[realm] = {
                            "router_url": item.get("router_url", "ws://127.0.0.1:60001"),
                            "topics": item.get("topics", [])
                        }
                    self.realms_topics = new_dict
                else:
                    self.realms_topics = data.get("realms", {})
                print("Global realms/topics configuration loaded (subscriber).")
                self.populateRealmTable()
            except Exception as e:
                QMessageBox.critical(self, "Error", f" The file realm_topic_config.json could not be loaded:\n{e}")
        else:
            QMessageBox.warning(self, "Warning", " File realm_topic_config.json not found.")

    def populateRealmTable(self):
        self.realmTable.blockSignals(True)
        self.realmTable.setRowCount(0)
        for realm, info in sorted(self.realms_topics.items()):
            row = self.realmTable.rowCount()
            self.realmTable.insertRow(row)
            itemRealm = QTableWidgetItem(realm)
            itemRealm.setFlags(itemRealm.flags() | Qt.ItemIsUserCheckable)
            itemRealm.setCheckState(Qt.Unchecked)
            self.realmTable.setItem(row, 0, itemRealm)
            router_url = info.get("router_url", "ws://127.0.0.1:60001")
            self.realmTable.setItem(row, 1, QTableWidgetItem(router_url))
        self.realmTable.blockSignals(False)
        if self.realmTable.rowCount() > 0:
            self.realmTable.selectRow(0)
            self.onRealmClicked(0, 0)

    def onRealmClicked(self, row, col):
        realm_item = self.realmTable.item(row, 0)
        if realm_item:
            realm = realm_item.text().strip()
            self.current_realm = realm
            topics = self.realms_topics.get(realm, {}).get("topics", [])
            self.topicTable.blockSignals(True)
            self.topicTable.setRowCount(0)
            if realm not in self.selected_topics_by_realm:
                self.selected_topics_by_realm[realm] = set()
            for t in topics:
                row_idx = self.topicTable.rowCount()
                self.topicTable.insertRow(row_idx)
                t_item = QTableWidgetItem(t)
                t_item.setFlags(t_item.flags() | Qt.ItemIsUserCheckable)
                t_item.setCheckState(Qt.Checked if t in self.selected_topics_by_realm[realm] else Qt.Unchecked)
                self.topicTable.setItem(row_idx, 0, t_item)
            self.topicTable.blockSignals(False)

    def onRealmItemChanged(self, item):
        pass

    def onTopicChanged(self, item):
        if not self.current_realm:
            return
        realm = self.current_realm
        selected = set()
        for row in range(self.topicTable.rowCount()):
            t_item = self.topicTable.item(row, 0)
            if t_item and t_item.checkState() == Qt.Checked:
                selected.add(t_item.text().strip())
        self.selected_topics_by_realm[realm] = selected

    def addRealmRow(self):
        new_realm = self.newRealmEdit.text().strip()
        if new_realm:
            row = self.realmTable.rowCount()
            self.realmTable.insertRow(row)
            itemRealm = QTableWidgetItem(new_realm)
            itemRealm.setFlags(itemRealm.flags() | Qt.ItemIsUserCheckable)
            itemRealm.setCheckState(Qt.Unchecked)
            self.realmTable.setItem(row, 0, itemRealm)
            self.realmTable.setItem(row, 1, QTableWidgetItem("ws://127.0.0.1:60001"))
            self.newRealmEdit.clear()

    def deleteRealmRow(self):
        rows_to_delete = []
        for row in range(self.realmTable.rowCount()):
            item = self.realmTable.item(row, 0)
            if item and item.checkState() != Qt.Checked:
                rows_to_delete.append(row)
        for row in reversed(rows_to_delete):
            self.realmTable.removeRow(row)

    def addTopicRow(self):
        new_topic = self.newTopicEdit.text().strip()
        if new_topic:
            row = self.topicTable.rowCount()
            self.topicTable.insertRow(row)
            t_item = QTableWidgetItem(new_topic)
            t_item.setFlags(t_item.flags() | Qt.ItemIsUserCheckable)
            t_item.setCheckState(Qt.Unchecked)
            self.topicTable.setItem(row, 0, t_item)
            self.newTopicEdit.clear()

    def deleteTopicRow(self):
        rows_to_delete = []
        for row in range(self.topicTable.rowCount()):
            t_item = self.topicTable.item(row, 0)
            if t_item and t_item.checkState() != Qt.Checked:
                rows_to_delete.append(row)
        for row in reversed(rows_to_delete):
            self.topicTable.removeRow(row)

    def startSubscription(self):
        for row in range(self.realmTable.rowCount()):
            realm_item = self.realmTable.item(row, 0)
            url_item = self.realmTable.item(row, 1)
            if realm_item and realm_item.checkState() == Qt.Checked:
                realm = realm_item.text().strip()
                router_url = url_item.text().strip() if url_item else "ws://127.0.0.1:60001"
                selected = self.selected_topics_by_realm.get(realm, set())
                if not selected:
                    realm_info = self.realms_topics.get(realm, {})
                    default_topics = realm_info.get("topics", [])
                    selected = set(default_topics)
                    self.selected_topics_by_realm[realm] = selected
                selected_topics = list(selected)
                if selected_topics:
                    start_subscriber(router_url, realm, selected_topics, self.handleMessage)
                    print(f"Attempting to subscribe to Realm '{realm}' with topics {selected_topics}")
                    sys.stdout.flush()
                else:
                    QMessageBox.warning(self, "Warning", f"There are no topics selected for the realm '{realm}'.")
    
    def confirmAndStartSubscription(self):
        global global_sub_sessions
        if global_sub_sessions:
            reply = QMessageBox.question(self, "Confirm",
                                         "An active subscription already exists. Would you like to stop it and start a new one?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.stopSubscription()
            else:
                return
        self.startSubscription()

    def stopSubscription(self):
        global global_sub_sessions
        if not global_sub_sessions:
            QMessageBox.warning(self, "Warning", "There are no active subscriptions to stop.")
            return
        for realm, session_obj in list(global_sub_sessions.items()):
            try:
                session_obj.leave("Stop subscription requested")
                print(f"Subscription stopped for realm '{realm}'.")
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.viewer.add_message(realm, "Stopped", timestamp, "Subscription stopped successfully.")
            except Exception as e:
                print("Error stopping subscription:", e)
            del global_sub_sessions[realm]

    def handleMessage(self, realm, topic, content):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        error_flag = False
        if isinstance(content, dict) and "error" in content:
            error_flag = True
        filtered = extract_message(content)
        details_str = json.dumps(filtered, indent=2, ensure_ascii=False)
        self.messageReceived.emit(realm, topic, timestamp, filtered)
        log_to_file(timestamp, realm, topic, details_str)
        print(f"Message received in '{realm}', topic '{topic}' at {timestamp}")
        sys.stdout.flush()

    @pyqtSlot(str, str, str, object)
    def onMessageReceived(self, realm, topic, timestamp, data_dict):
        filtered = extract_message(data_dict)
        details_str = json.dumps(filtered, indent=2, ensure_ascii=False)
        error_flag = False
        if isinstance(filtered, dict) and "error" in filtered:
            error_flag = True
        self.viewer.add_message(realm, topic, timestamp, details_str, error=error_flag)

    def resetLog(self):
        self.viewer.table.setRowCount(0)
        self.viewer.messages = []

    def loadProjectFromConfig(self, sub_config):
        pass


