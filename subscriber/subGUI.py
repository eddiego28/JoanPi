import os, json, datetime, threading, sys, time
from twisted.internet.defer import inlineCallbacks
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QLineEdit, QFileDialog,
    QDialog, QTreeWidget, QComboBox, QSplitter, QGroupBox, QCheckBox, QTreeWidgetItem
)
from PyQt5.QtCore import Qt, pyqtSlot, pyqtSignal
from autobahn.wamp import types
# Importamos desde twisted:
from autobahn.twisted.wamp import ApplicationSession
from autobahn.twisted.websocket import WebSocketClientFactory, connectWS
from common.utils import log_to_file, JsonDetailDialog

# Si estás en Python 3.8+ y Autobahn 0.10.2, puede que necesites monkey-patch:
if not hasattr(time, "clock"):
    time.clock = time.perf_counter

###############################################################################
# Diccionario global para almacenar las sesiones activas (una por realm)
###############################################################################
global_sub_sessions = {}  # key: realm, value: session object

###############################################################################
# MultiTopicSubscriber: sesión WAMP para suscripción (adaptada para Autobahn 0.10.x)
###############################################################################
class MultiTopicSubscriber(ApplicationSession):
    def __init__(self, config=None):
        """
        En Autobahn 0.10.2 se espera un objeto de configuración (ComponentConfig).
        """
        super(MultiTopicSubscriber, self).__init__(config)
        self.topics = []  # Se asignan antes de iniciar la sesión
        self.on_message_callback = None

    @inlineCallbacks
    def onJoin(self, details):
        realm_name = self.config.realm
        global global_sub_sessions
        global_sub_sessions[realm_name] = self
        print("Suscriptor connected to realm: {}".format(realm_name))
        for t in self.topics:
            try:
                yield self.subscribe(
                    lambda *args, topic=t, **kwargs: self.on_event(realm_name, topic, *args, **kwargs),
                    t
                )
                print("Subscribed to topic: {}".format(t))
            except Exception as e:
                print("Error subscribing to topic {}: {}".format(t, e))

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
# start_subscriber_ws: conecta usando WebSocketClientFactory y connectWS
###############################################################################
def start_subscriber_ws(url, realm, topics, on_message_callback):
    """
    Crea una session factory que genera una instancia de MultiTopicSubscriber
    y conecta al router vía WebSocket usando WebSocketClientFactory y connectWS.
    Se fuerza la negociación para usar el subprotocolo "wamp.2.json" (sin batched).
    """
    # Función que crea la sesión
    def session_factory():
        from autobahn.twisted.wamp import ComponentConfig
        config = ComponentConfig(realm=realm, extra={})
        session = MultiTopicSubscriber(config)
        session.topics = topics
        session.on_message_callback = on_message_callback
        return session

    # Creamos la factoría de WebSocket
    factory = WebSocketClientFactory(url)
    # Asignamos la función que construye el protocolo (nuestra sesión)
    factory.buildProtocol = lambda addr: session_factory()
    # Forzamos la negociación para usar "wamp.2.json"
    factory.protocols = [u"wamp.2.json"]
    print("Conectando al router en {} para realm '{}'...".format(url, realm))
    connectWS(factory)

###############################################################################
# JsonTreeDialog: muestra el JSON en formato de árbol expandido
###############################################################################
class JsonTreeDialog(QDialog):
    def __init__(self, data, parent=None):
        super(JsonTreeDialog, self).__init__(parent)
        self.setWindowTitle("JSON detail - Tree View")
        self.resize(600, 400)
        layout = QVBoxLayout(self)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(1)
        self.tree.setHeaderLabels(["JSON"])
        self.tree.header().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.tree)
        self.setLayout(layout)
        self.buildTree(data, self.tree.invisibleRootItem())
        self.tree.expandAll()

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

###############################################################################
# SubscriberMessageViewer: visor de mensajes recibidos (QTable)
###############################################################################
class SubscriberMessageViewer(QWidget):
    def __init__(self, parent=None):
        super(SubscriberMessageViewer, self).__init__(parent)
        self.messages = []
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

    def add_message(self, realm, topic, timestamp, raw_details):
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
        self.table.setItem(row, 0, QTableWidgetItem(timestamp))
        self.table.setItem(row, 1, QTableWidgetItem(realm))
        self.table.setItem(row, 2, QTableWidgetItem(topic))
        self.messages.append(data)

    def showDetails(self, item):
        row = item.row()
        if row < len(self.messages):
            data = self.messages[row]
            dlg = JsonTreeDialog(data, self)
            dlg.exec_()

###############################################################################
# SubscriberTab: interfaz principal del suscriptor
###############################################################################
class SubscriberTab(QWidget):
    messageReceived = pyqtSignal(str, str, str, object)

    def __init__(self, parent=None):
        super(SubscriberTab, self).__init__(parent)
        self.realms_topics = {}
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
                    # Aquí usamos la nueva función start_subscriber_ws:
                    start_subscriber_ws(router_url, realm, selected_topics, self.handleMessage)
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    sub_info = {
                        "action": "subscribe",
                        "realm": realm,
                        "router_url": router_url,
                        "topics": selected_topics
                    }
                    details = json.dumps(sub_info, indent=2, ensure_ascii=False)
                    self.viewer.add_message(realm, ", ".join(selected_topics), timestamp, details)
                    print("Subscribed to Realm '{}' with topics {}".format(realm, selected_topics))
                    sys.stdout.flush()
                else:
                    QMessageBox.warning(self, "Warning", "There are no topics selected for the realm '{}'.".format(realm))

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
                print("Subscription stopped for realm '{}'.".format(realm))
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.viewer.add_message(realm, "Stopped", timestamp, "Subscription stopped successfully.")
            except Exception as e:
                print("Error stopping subscription:", e)
            del global_sub_sessions[realm]

    def handleMessage(self, realm, topic, content):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.messageReceived.emit(realm, topic, timestamp, content)
        log_to_file(timestamp, realm, topic, json.dumps(content, indent=2, ensure_ascii=False))
        print("Message received in '{}', topic '{}' at {}".format(realm, topic, timestamp))
        sys.stdout.flush()

    @pyqtSlot(str, str, str, object)
    def onMessageReceived(self, realm, topic, timestamp, data_dict):
        details_str = json.dumps(data_dict, indent=2, ensure_ascii=False)
        self.viewer.add_message(realm, topic, timestamp, details_str)

    def resetLog(self):
        self.viewer.table.setRowCount(0)
        self.viewer.messages = []

    def loadProjectFromConfig(self, sub_config):
        # Implementar si se requiere cargar configuración
        pass

###############################################################################
# Nueva función: start_subscriber_ws usando autobahn.twisted.websocket
###############################################################################
def start_subscriber_ws(url, realm, topics, on_message_callback):
    """
    Conecta al router mediante WebSocketClientFactory y connectWS,
    forzando el subprotocolo "wamp.2.json" (sin batched) para mayor compatibilidad.
    """
    from autobahn.twisted.websocket import WebSocketClientFactory, connectWS
    from autobahn.twisted.wamp import ComponentConfig

    def session_factory():
        config = ComponentConfig(realm=realm, extra={})
        session = MultiTopicSubscriber(config)
        session.topics = topics
        session.on_message_callback = on_message_callback
        return session

    factory = WebSocketClientFactory(url)
    # Configuramos la función buildProtocol para que devuelva nuestra sesión
    factory.buildProtocol = lambda addr: session_factory()
    # Forzamos subprotocolos sin "batched"
    factory.protocols = [u"wamp.2.json"]
    print("Conectando al router en {} para realm '{}'...".format(url, realm))
    connectWS(factory)
