# subscriber/subGUI.py
import os, json, datetime, asyncio, threading, sys
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QLineEdit, QFileDialog,
    QDialog, QTreeWidget
)
from PyQt5.QtCore import Qt, pyqtSlot, pyqtSignal
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
from common.utils import log_to_file, JsonDetailDialog
from PyQt5.QtWidgets import QTreeWidgetItem

global_session_sub = None

# --- Clase MultiTopicSubscriber ---
class MultiTopicSubscriber(ApplicationSession):
    def __init__(self, config):
        super().__init__(config)
        self.topics = []  # Se asigna mediante la factoría
        self.on_message_callback = None

    async def onJoin(self, details):
        realm_name = self.config.realm
        print(f"Suscriptor conectado en realm: {realm_name}")
        # Para cada topic, se suscribe usando lambda con parámetro por defecto para capturar el valor actual
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

# --- Función start_subscriber ---
def start_subscriber(url, realm, topics, on_message_callback):
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        runner = ApplicationRunner(url=url, realm=realm)
        runner.run(MultiTopicSubscriber.factory(topics, on_message_callback))
    threading.Thread(target=run, daemon=True).start()

# --- Clase JsonTreeDialog: detalle del JSON en una sola columna ---
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
        self.tree.expandAll()  # Expande todo el árbol para ver la estructura vertical

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

# --- Clase SubscriberMessageViewer: muestra una única fila por mensaje ---
class SubscriberMessageViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.messages = []  # Guarda el JSON completo de cada mensaje
        self.initUI()
        
    def initUI(self):
        layout = QVBoxLayout(self)
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        # Las columnas son: Hora, Realm, Topic
        self.table.setHorizontalHeaderLabels(["Hora", "Realm", "Topic"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.itemDoubleClicked.connect(self.showDetails)
        layout.addWidget(self.table)
        self.setLayout(layout)
        
    def add_message(self, realm, topic, timestamp, details):
        # Se añade UNA única fila por mensaje
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

# --- Clase SubscriberTab: interfaz principal del suscriptor ---
class SubscriberTab(QWidget):
    # Signal para actualizar la QTable; se conecta solo una vez en el constructor
    messageReceived = pyqtSignal(str, str, str, str)  # (realm, topic, timestamp, details)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.realms_topics = {}          # Se carga desde el JSON (p.ej., realm_topic_config.json)
        self.selected_topics_by_realm = {}  # Guarda la selección manual de topics por realm
        self.current_realm = None
        # Conexión única de la señal
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
        
        realmBtnLayout = QHBoxLayout()
        self.newRealmEdit = QLineEdit()
        self.newRealmEdit.setPlaceholderText("Nuevo Realm")
        self.btnAddRealm = QPushButton("Agregar Realm")
        self.btnAddRealm.clicked.connect(self.addRealmRow)
        self.btnDelRealm = QPushButton("Borrar Realm")
        self.btnDelRealm.clicked.connect(self.deleteRealmRow)
        realmBtnLayout.addWidget(self.newRealmEdit)
        realmBtnLayout.addWidget(self.btnAddRealm)
        realmBtnLayout.addWidget(self.btnDelRealm)
        leftLayout.addLayout(realmBtnLayout)
        
        lblTopics = QLabel("Topics (checkbox):")
        leftLayout.addWidget(lblTopics)
        self.topicTable = QTableWidget(0, 1)
        self.topicTable.setHorizontalHeaderLabels(["Topic"])
        self.topicTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.topicTable.itemChanged.connect(self.onTopicItemChanged)
        leftLayout.addWidget(self.topicTable)
        
        topicBtnLayout = QHBoxLayout()
        self.newTopicEdit = QLineEdit()
        self.newTopicEdit.setPlaceholderText("Nuevo Topic")
        self.btnAddTopic = QPushButton("Agregar Topic")
        self.btnAddTopic.clicked.connect(self.addTopicRow)
        self.btnDelTopic = QPushButton("Borrar Topic")
        self.btnDelTopic.clicked.connect(self.deleteTopicRow)
        topicBtnLayout.addWidget(self.newTopicEdit)
        topicBtnLayout.addWidget(self.btnAddTopic)
        topicBtnLayout.addWidget(self.btnDelTopic)
        leftLayout.addLayout(topicBtnLayout)
        
        ctrlLayout = QHBoxLayout()
        self.btnSubscribe = QPushButton("Suscribirse")
        self.btnSubscribe.clicked.connect(self.startSubscription)
        ctrlLayout.addWidget(self.btnSubscribe)
        self.btnReset = QPushButton("Reset Log")
        self.btnReset.clicked.connect(self.resetLog)
        ctrlLayout.addWidget(self.btnReset)
        leftLayout.addLayout(ctrlLayout)
        
        mainLayout.addLayout(leftLayout, stretch=1)
        
        # Panel derecho: Viewer de mensajes (logs)
        self.viewer = SubscriberMessageViewer(self)
        mainLayout.addWidget(self.viewer, stretch=2)
        
        self.setLayout(mainLayout)

    def loadGlobalRealmTopicConfig(self):
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "realm_topic_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Soporta formatos: dict o lista
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

    def populateRealmTable(self):
        self.realmTable.blockSignals(True)
        self.realmTable.setRowCount(0)
        for realm, info in sorted(self.realms_topics.items()):
            row = self.realmTable.rowCount()
            self.realmTable.insertRow(row)
            itemRealm = QTableWidgetItem(realm)
            itemRealm.setFlags(itemRealm.flags() | Qt.ItemIsUserCheckable)
            # Iniciar desmarcado
            itemRealm.setCheckState(Qt.Unchecked)
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
            # Si ya hubo selección para este realm, conservarla; si no, inicializar como conjunto vacío
            if realm not in self.selected_topics_by_realm:
                self.selected_topics_by_realm[realm] = set()
            self.populateTopicTable(realm)

    def onRealmItemChanged(self, item):
        if item.column() != 0:
            return
        realm = item.text().strip()
        if self.current_realm == realm:
            selected = set()
            for row in range(self.topicTable.rowCount()):
                t_item = self.topicTable.item(row, 0)
                if t_item and t_item.checkState() == Qt.Checked:
                    selected.add(t_item.text().strip())
            self.selected_topics_by_realm[realm] = selected

    def populateTopicTable(self, realm):
        self.topicTable.blockSignals(True)
        self.topicTable.setRowCount(0)
        topics = self.realms_topics.get(realm, {}).get("topics", [])
        selected = self.selected_topics_by_realm.get(realm, set())
        for t in topics:
            row = self.topicTable.rowCount()
            self.topicTable.insertRow(row)
            t_item = QTableWidgetItem(t)
            t_item.setFlags(t_item.flags() | Qt.ItemIsUserCheckable)
            # Se respeta la selección guardada (si el usuario la marcó, se mantiene; de lo contrario, desmarcado)
            t_item.setCheckState(Qt.Checked if t in selected else Qt.Unchecked)
            self.topicTable.setItem(row, 0, t_item)
        self.topicTable.blockSignals(False)

    def onTopicItemChanged(self, item):
        if not self.current_realm:
            return
        realm = self.current_realm
        topic = item.text().strip()
        if realm not in self.selected_topics_by_realm:
            self.selected_topics_by_realm[realm] = set()
        if item.checkState() == Qt.Checked:
            self.selected_topics_by_realm[realm].add(topic)
        else:
            self.selected_topics_by_realm[realm].discard(topic)

    def addRealmRow(self):
        new_realm = self.newRealmEdit.text().strip()
        if new_realm:
            row = self.realmTable.rowCount()
            self.realmTable.insertRow(row)
            itemRealm = QTableWidgetItem(new_realm)
            itemRealm.setFlags(itemRealm.flags() | Qt.ItemIsUserCheckable)
            # Iniciar desmarcado
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
            # Iniciar desmarcado
            t_item.setCheckState(Qt.Unchecked)
            self.topicTable.setItem(row, 0, t_item)
            if self.current_realm:
                self.selected_topics_by_realm.setdefault(self.current_realm, set()).add(new_topic)
            self.newTopicEdit.clear()

    def deleteTopicRow(self):
        rows_to_delete = []
        for row in range(self.topicTable.rowCount()):
            t_item = self.topicTable.item(row, 0)
            if t_item and t_item.checkState() != Qt.Checked:
                rows_to_delete.append(row)
        for row in reversed(rows_to_delete):
            t_item = self.topicTable.item(row, 0)
            if t_item and self.current_realm:
                self.selected_topics_by_realm[self.current_realm].discard(t_item.text().strip())
            self.topicTable.removeRow(row)

    def startSubscription(self):
        # Para cada realm marcado, usar la selección actual (manual) de topics
        for row in range(self.realmTable.rowCount()):
            realm_item = self.realmTable.item(row, 0)
            url_item = self.realmTable.item(row, 1)
            if realm_item and realm_item.checkState() == Qt.Checked:
                realm = realm_item.text().strip()
                router_url = url_item.text().strip() if url_item else "ws://127.0.0.1:60001/ws"
                # Se usa la selección manual guardada en selected_topics_by_realm
                selected_topics = list(self.selected_topics_by_realm.get(realm, set()))
                if selected_topics:
                    start_subscriber(router_url, realm, selected_topics, self.handleMessage)
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    subscription_info = {
                        "action": "subscribe",
                        "realm": realm,
                        "router_url": router_url,
                        "topics": selected_topics
                    }
                    details = json.dumps(subscription_info, indent=2, ensure_ascii=False)
                    self.viewer.add_message(realm, "Subscription", timestamp, details)
                    print(f"Suscrito a realm '{realm}' con topics {selected_topics}")
                    sys.stdout.flush()
                else:
                    QMessageBox.warning(self, "Advertencia", f"No hay topics seleccionados para realm {realm}.")

    def handleMessage(self, realm, topic, content):
        # Este método se llama desde el hilo del suscriptor.
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        details = json.dumps(content, indent=2, ensure_ascii=False)
        # Emitir la señal solo una vez
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
        pass

    # Eliminamos showEvent/hideEvent para evitar reconexiones duplicadas.
# Fin de SubscriberTab
