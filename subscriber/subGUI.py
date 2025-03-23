import os, json, datetime, asyncio, threading, sys
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QLineEdit, QFileDialog,
    QDialog, QTreeWidget, QComboBox, QSplitter, QGroupBox, QPushButton, QTreeWidgetItem
)
from PyQt5.QtCore import Qt, pyqtSlot, pyqtSignal
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
from common.utils import log_to_file, JsonDetailDialog
from PyQt5.QtWidgets import QTreeWidgetItem

global_session_sub = None

# --------------------------------------------------------------------
# MultiTopicSubscriber: sesión WAMP para suscripción
# --------------------------------------------------------------------
class MultiTopicSubscriber(ApplicationSession):
    def __init__(self, config):
        super().__init__(config)
        self.topics = []  # Se asigna mediante la factoría
        self.on_message_callback = None

    async def onJoin(self, details):
        global global_session_sub
        realm_name = self.config.realm
        print(f"Suscriptor conectado en realm: {realm_name}")
        global_session_sub = self
        for t in self.topics:
            await self.subscribe(
                lambda *args, topic=t, **kwargs: self.on_event(realm_name, topic, *args, **kwargs),
                t
            )

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

# --------------------------------------------------------------------
# start_subscriber: inicia la suscripción en un hilo separado.
# --------------------------------------------------------------------
def start_subscriber(url, realm, topics, on_message_callback):
    global global_session_sub
    if global_session_sub is not None:
        try:
            global_session_sub.leave()
            print("Sesión previa cerrada.")
        except Exception as e:
            print("Error al cerrar la sesión previa:", e)
        global_session_sub = None
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        runner = ApplicationRunner(url=url, realm=realm)
        runner.run(MultiTopicSubscriber.factory(topics, on_message_callback))
    threading.Thread(target=run, daemon=True).start()

# --------------------------------------------------------------------
# JsonTreeDialog: muestra el JSON en formato de árbol (una columna)
# --------------------------------------------------------------------
class JsonTreeDialog(QDialog):
    def __init__(self, json_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Detalle JSON - Árbol")
        self.resize(600, 400)
        layout = QVBoxLayout(self)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(1)
        self.tree.setHeaderLabels(["JSON"])
        self.tree.header().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.tree)
        self.setLayout(layout)
        self.buildTree(json_data, self.tree.invisibleRootItem())
        self.tree.expandAll()

    def buildTree(self, data, parent):
        if isinstance(data, dict):
            for key, value in data.items():
                text = f"{key}: {value}" if not isinstance(value, (dict, list)) else f"{key}:"
                item = QTreeWidgetItem([text])
                parent.addChild(item)
                self.buildTree(value, item)
        elif isinstance(data, list):
            for index, value in enumerate(data):
                text = f"[{index}]: {value}" if not isinstance(value, (dict, list)) else f"[{index}]:"
                item = QTreeWidgetItem([text])
                parent.addChild(item)
                self.buildTree(value, item)
        else:
            item = QTreeWidgetItem([str(data)])
            parent.addChild(item)

# --------------------------------------------------------------------
# SubscriberMessageViewer: visor de mensajes recibidos (una fila por mensaje)
# (Sin fijar altura para mantener tamaño por defecto)
# --------------------------------------------------------------------
class SubscriberMessageViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.messages = []
        self.initUI()
        
    def initUI(self):
        layout = QVBoxLayout(self)
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Hora", "Realm", "Topic"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.itemDoubleClicked.connect(self.showDetails)
        layout.addWidget(self.table)
        self.setLayout(layout)

    def add_message(self, realm, topic, timestamp, details):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(timestamp))
        self.table.setItem(row, 1, QTableWidgetItem(realm))
        self.table.setItem(row, 2, QTableWidgetItem(topic))
        self.messages.append(details)

    def showDetails(self, item):
        row = item.row()
        if row < len(self.messages):
            data = self.messages[row]
            dlg = JsonTreeDialog(data, self)
            dlg.exec_()

# --------------------------------------------------------------------
# SubscriberTab: interfaz principal del suscriptor.
# – Panel izquierdo: tablas de realms (con router URL) y topics.
# – Se conserva el estado de los checkboxes para cada realm.
# – Al pulsar "Suscribirse" se suscribe solo a los realms y topics marcados.
# --------------------------------------------------------------------
class SubscriberTab(QWidget):
    messageReceived = pyqtSignal(str, str, str, str)  # (realm, topic, timestamp, details)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.realms_topics = {}  # Se carga desde el JSON de configuración
        self.selected_topics_by_realm = {}
        self.current_realm = None
        self.messageReceived.connect(self.onMessageReceived)
        self.initUI()
        self.loadGlobalRealmTopicConfig()

    def initUI(self):
        mainLayout = QHBoxLayout(self)
        # Panel izquierdo: Realms y Topics
        leftLayout = QVBoxLayout()
        lblRealms = QLabel("Realms (checkbox) + Router URL:")
        leftLayout.addWidget(lblRealms)
        self.realmTable = QTableWidget(0, 2)
        self.realmTable.setHorizontalHeaderLabels(["Realm", "Router URL"])
        self.realmTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.realmTable.cellClicked.connect(self.onRealmClicked)
        self.realmTable.itemChanged.connect(self.onRealmItemChanged)
        leftLayout.addWidget(self.realmTable)
        btnRealmLayout = QHBoxLayout()
        self.newRealmEdit = QLineEdit()
        self.newRealmEdit.setPlaceholderText("Nuevo Realm")
        self.btnAddRealm = QPushButton("Agregar Realm")
        self.btnAddRealm.clicked.connect(self.addRealmRow)
        self.btnDelRealm = QPushButton("Borrar Realm")
        self.btnDelRealm.clicked.connect(self.deleteRealmRow)
        btnRealmLayout.addWidget(self.newRealmEdit)
        btnRealmLayout.addWidget(self.btnAddRealm)
        btnRealmLayout.addWidget(self.btnDelRealm)
        leftLayout.addLayout(btnRealmLayout)
        lblTopics = QLabel("Topics (checkbox):")
        leftLayout.addWidget(lblTopics)
        self.topicTable = QTableWidget(0, 1)
        self.topicTable.setHorizontalHeaderLabels(["Topic"])
        self.topicTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.topicTable.itemChanged.connect(self.onTopicChanged)
        leftLayout.addWidget(self.topicTable)
        btnTopicLayout = QHBoxLayout()
        self.newTopicEdit = QLineEdit()
        self.newTopicEdit.setPlaceholderText("Nuevo Topic")
        self.btnAddTopic = QPushButton("Agregar Topic")
        self.btnAddTopic.clicked.connect(self.addTopicRow)
        self.btnDelTopic = QPushButton("Borrar Topic")
        self.btnDelTopic.clicked.connect(self.deleteTopicRow)
        btnTopicLayout.addWidget(self.newTopicEdit)
        btnTopicLayout.addWidget(self.btnAddTopic)
        btnTopicLayout.addWidget(self.btnDelTopic)
        leftLayout.addLayout(btnTopicLayout)
        ctrlLayout = QHBoxLayout()
        self.btnSubscribe = QPushButton("Suscribirse")
        self.btnSubscribe.setStyleSheet("""
            QPushButton {
                background-color: green;
                color: white;
                font-weight: bold;
            }
        """)
        self.btnSubscribe.clicked.connect(self.startSubscription)
        ctrlLayout.addWidget(self.btnSubscribe)
        self.btnReset = QPushButton("Reset Log")
        self.btnReset.clicked.connect(self.resetLog)
        ctrlLayout.addWidget(self.btnReset)
        leftLayout.addLayout(ctrlLayout)
        mainLayout.addLayout(leftLayout, stretch=1)
        self.btnStopSubscription = QPushButton("Detener Suscripción")
        self.btnStopSubscription.setStyleSheet("""
            QPushButton {
                background-color: red;
                color: white;
                font-weight: bold;
            }
        """)
        self.btnStopSubscription.clicked.connect(self.stopSubscription)
        ctrlLayout.addWidget(self.btnStopSubscription)
        # Panel derecho: Viewer de mensajes
        self.viewer = SubscriberMessageViewer(self)
        mainLayout.addWidget(self.viewer, stretch=2)
        self.setLayout(mainLayout)
        
        

    def loadGlobalRealmTopicConfig(self):
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "realm_topic_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    realms_dict = {}
                    for item in data:
                        realm = item.get("realm")
                        if realm:
                            realms_dict[realm] = {
                                "router_url": item.get("router_url", "ws://127.0.0.1:60001/ws"),
                                "topics": item.get("topics", [])
                            }
                    data = {"realms": realms_dict}
                self.realms_topics = data.get("realms", {})
                print("Configuración global de realms/topics cargada (suscriptor).")
                self.populateRealmTable()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo cargar realm_topic_config.json:\n{e}")
        else:
            QMessageBox.warning(self, "Advertencia", "No se encontró realm_topic_config.json.")
            
    def stopSubscription(self):
        global global_session_sub
        if global_session_sub is not None:
            try:
                global_session_sub.leave("Stop subscription requested")
                print("Suscripción detenida.")
                # Create a log entry that the subscription has been stopped
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.viewer.add_message("Subscription", "Stopped", timestamp, "Subscription stopped successfully.")
            except Exception as e:
                print("Error al detener suscripción:", e)
            global_session_sub = None
        else:
            QMessageBox.warning(self, "Advertencia", "No hay suscripción activa que detener.")

    def populateRealmTable(self):
        self.realmTable.blockSignals(True)
        self.realmTable.setRowCount(0)
        for realm, info in sorted(self.realms_topics.items()):
            row = self.realmTable.rowCount()
            self.realmTable.insertRow(row)
            itemRealm = QTableWidgetItem(realm)
            itemRealm.setFlags(itemRealm.flags() | Qt.ItemIsUserCheckable)
            itemRealm.setCheckState(Qt.Unchecked)  # Inicia desmarcado
            self.realmTable.setItem(row, 0, itemRealm)
            router_url = info.get("router_url", "ws://127.0.0.1:60001/ws")
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
                # Por defecto, se inician desmarcados para que el usuario elija
                self.selected_topics_by_realm[realm] = set()
            for t in topics:
                row_idx = self.topicTable.rowCount()
                self.topicTable.insertRow(row_idx)
                t_item = QTableWidgetItem(t)
                t_item.setFlags(t_item.flags() | Qt.ItemIsUserCheckable)
                if t in self.selected_topics_by_realm[realm]:
                    t_item.setCheckState(Qt.Checked)
                else:
                    t_item.setCheckState(Qt.Unchecked)
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
            self.realmTable.setItem(row, 1, QTableWidgetItem("ws://127.0.0.1:60001/ws"))
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
        # Se recorre la tabla de realms y se suscribe solo a los que estén marcados, usando la selección de topics guardada.
        for row in range(self.realmTable.rowCount()):
            realm_item = self.realmTable.item(row, 0)
            url_item = self.realmTable.item(row, 1)
            if realm_item and realm_item.checkState() == Qt.Checked:
                realm = realm_item.text().strip()
                router_url = url_item.text().strip() if url_item else "ws://127.0.0.1:60001/ws"
                selected_topics = list(self.selected_topics_by_realm.get(realm, []))
                if selected_topics:
                    start_subscriber(router_url, realm, selected_topics, self.handleMessage)
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    sub_info = {
                        "action": "subscribe",
                        "realm": realm,
                        "router_url": router_url,
                        "topics": selected_topics
                    }
                    details = json.dumps(sub_info, indent=2, ensure_ascii=False)
                    self.viewer.add_message(realm, ", ".join(selected_topics), timestamp, details)
                    print(f"Suscrito a realm '{realm}' con topics {selected_topics}")
                    sys.stdout.flush()
                else:
                    QMessageBox.warning(self, "Advertencia", f"No hay topics seleccionados para realm {realm}.")

    def handleMessage(self, realm, topic, content):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        details = json.dumps(content, indent=2, ensure_ascii=False)
        self.messageReceived.emit(realm, topic, timestamp, details)
        log_to_file(timestamp, realm, topic, details)
        print(f"Mensaje recibido en realm '{realm}', topic '{topic}' a las {timestamp}")
        sys.stdout.flush()

    @pyqtSlot(str, str, str, str)
    def onMessageReceived(self, realm, topic, timestamp, details):
        self.viewer.add_message(realm, topic, timestamp, details)

    def resetLog(self):
        self.viewer.table.setRowCount(0)
        self.viewer.messages = []

    def loadProjectFromConfig(self, sub_config):
        # Implementar según necesidades
        pass

# --------------------------------------------------------------------
# Fin de SubscriberTab