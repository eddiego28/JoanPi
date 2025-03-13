# subscriber/subGUI.py
import os, json, datetime, asyncio, threading
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QLineEdit, QFileDialog
)
from PyQt5.QtCore import Qt, pyqtSlot
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
from common.utils import log_to_file, JsonDetailDialog

global_session_sub = None

# -----------------------------------------------------------
# Clase MultiTopicSubscriber: sesión WAMP para suscripción
# -----------------------------------------------------------
class MultiTopicSubscriber(ApplicationSession):
    def __init__(self, config):
        # El constructor recibe solo 'config' (como requiere Autobahn)
        super().__init__(config)
        self.topics = []  # Se inyectan mediante la factoría
        self.on_message_callback = None

    async def onJoin(self, details):
        realm_name = self.config.realm  # Se obtiene del config de la sesión
        print(f"Suscriptor conectado en realm: {realm_name}")
        # Suscribirse a cada topic que tengamos en self.topics
        for t in self.topics:
            await self.subscribe(
                lambda *args, **kwargs: self.on_event(realm_name, t, *args, **kwargs),
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

# -----------------------------------------------------------
# Función start_subscriber: inicia la sesión en un hilo separado.
# -----------------------------------------------------------
def start_subscriber(url, realm, topics, on_message_callback):
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        runner = ApplicationRunner(url=url, realm=realm)
        runner.run(MultiTopicSubscriber.factory(topics, on_message_callback))
    threading.Thread(target=run, daemon=True).start()

# -----------------------------------------------------------
# Clase SubscriberMessageViewer: muestra los mensajes recibidos en una tabla.
# -----------------------------------------------------------
class SubscriberMessageViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.messages = []  # Almacena el JSON completo de cada mensaje recibido
        self.initUI()
        
    def initUI(self):
        layout = QVBoxLayout(self)
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        # Orden: Hora, Realm, Topic
        self.table.setHorizontalHeaderLabels(["Hora", "Realm", "Topic"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        # Conectar doble clic para ver el detalle
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
            if isinstance(data, dict):
                data = json.dumps(data, indent=2, ensure_ascii=False)
            dlg = JsonDetailDialog(data, self)
            dlg.exec_()

# -----------------------------------------------------------
# Clase SubscriberTab: interfaz principal del suscriptor.
# -----------------------------------------------------------
class SubscriberTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.realms_topics = {}  # Se cargará desde config/realm_topic_config.json
        self.selected_topics_by_realm = {}  # Para guardar la selección persistente de topics por realm
        self.current_realm = None
        self.initUI()
        self.loadGlobalRealmTopicConfig()

    def initUI(self):
        mainLayout = QHBoxLayout(self)
        
        # Lado izquierdo: Panel de Realms y Topics
        leftLayout = QVBoxLayout()
        
        lblRealms = QLabel("Realms (checkbox) + Router URL:")
        leftLayout.addWidget(lblRealms)
        self.realmTable = QTableWidget(0, 2)
        self.realmTable.setHorizontalHeaderLabels(["Realm", "Router URL"])
        self.realmTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.realmTable.cellClicked.connect(self.onRealmClicked)
        leftLayout.addWidget(self.realmTable)
        
        # Botones para Realms
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
        # Conectar para guardar cambios en la selección de topics
        self.topicTable.itemChanged.connect(self.onTopicItemChanged)
        leftLayout.addWidget(self.topicTable)
        
        # Botones para Topics
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
        
        # Botones de control: Suscribirse y Reset Log
        ctrlLayout = QHBoxLayout()
        self.btnSubscribe = QPushButton("Suscribirse")
        self.btnSubscribe.clicked.connect(self.startSubscription)
        ctrlLayout.addWidget(self.btnSubscribe)
        self.btnReset = QPushButton("Reset Log")
        self.btnReset.clicked.connect(self.resetLog)
        ctrlLayout.addWidget(self.btnReset)
        leftLayout.addLayout(ctrlLayout)
        
        mainLayout.addLayout(leftLayout, stretch=1)
        
        # Lado derecho: Viewer de mensajes
        self.viewer = SubscriberMessageViewer(self)
        mainLayout.addWidget(self.viewer, stretch=2)
        
        self.setLayout(mainLayout)

    def loadGlobalRealmTopicConfig(self):
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "realm_topic_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Si el JSON es una lista, convertirlo a diccionario
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
        self.realmTable.setRowCount(0)
        for realm, info in sorted(self.realms_topics.items()):
            row = self.realmTable.rowCount()
            self.realmTable.insertRow(row)
            itemRealm = QTableWidgetItem(realm)
            itemRealm.setFlags(itemRealm.flags() | Qt.ItemIsUserCheckable)
            itemRealm.setCheckState(Qt.Unchecked)
            self.realmTable.setItem(row, 0, itemRealm)
            router_url = info.get("router_url", "ws://127.0.0.1:60001/ws")
            self.realmTable.setItem(row, 1, QTableWidgetItem(router_url))
        # Inicialmente, si hay alguna fila, seleccionar la primera para cargar topics
        if self.realmTable.rowCount() > 0:
            self.realmTable.selectRow(0)
            self.onRealmClicked(0, 0)

    def onRealmClicked(self, row, col):
        realm_item = self.realmTable.item(row, 0)
        if realm_item:
            realm = realm_item.text().strip()
            self.current_realm = realm
            # Al cambiar de realm, si ya hay una selección guardada, usarla; si no, marcar todos por defecto.
            if realm not in self.selected_topics_by_realm:
                # Por defecto, se marcan todos los topics asociados
                topics = set(self.realms_topics.get(realm, {}).get("topics", []))
                self.selected_topics_by_realm[realm] = topics
            self.populateTopicTable(realm)

    def populateTopicTable(self, realm):
        self.topicTable.blockSignals(True)
        self.topicTable.setRowCount(0)
        topics = self.realms_topics.get(realm, {}).get("topics", [])
        # Obtener la selección guardada para este realm, si existe; sino, marcar todos por defecto.
        selected = self.selected_topics_by_realm.get(realm, set(topics))
        for t in topics:
            row = self.topicTable.rowCount()
            self.topicTable.insertRow(row)
            t_item = QTableWidgetItem(t)
            t_item.setFlags(t_item.flags() | Qt.ItemIsUserCheckable)
            if t in selected:
                t_item.setCheckState(Qt.Checked)
            else:
                t_item.setCheckState(Qt.Unchecked)
            self.topicTable.setItem(row, 0, t_item)
        self.topicTable.blockSignals(False)

    def onTopicItemChanged(self, item):
        # Actualiza la selección para el realm actual
        if not hasattr(self, "current_realm"):
            return
        realm = self.current_realm
        if realm not in self.selected_topics_by_realm:
            self.selected_topics_by_realm[realm] = set()
        topic = item.text().strip()
        if item.checkState() == Qt.Checked:
            self.selected_topics_by_realm[realm].add(topic)
        else:
            if topic in self.selected_topics_by_realm[realm]:
                self.selected_topics_by_realm[realm].remove(topic)

    def addRealmRow(self):
        new_realm = self.newRealmEdit.text().strip()
        if new_realm:
            row = self.realmTable.rowCount()
            self.realmTable.insertRow(row)
            itemRealm = QTableWidgetItem(new_realm)
            itemRealm.setFlags(itemRealm.flags() | Qt.ItemIsUserCheckable)
            itemRealm.setCheckState(Qt.Checked)
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
            t_item.setCheckState(Qt.Checked)
            self.topicTable.setItem(row, 0, t_item)
            # Actualizar la selección para el realm actual
            if hasattr(self, "current_realm"):
                self.selected_topics_by_realm.setdefault(self.current_realm, set()).add(new_topic)
            self.newTopicEdit.clear()

    def deleteTopicRow(self):
        rows_to_delete = []
        for row in range(self.topicTable.rowCount()):
            t_item = self.topicTable.item(row, 0)
            if t_item and t_item.checkState() != Qt.Checked:
                rows_to_delete.append(row)
        for row in reversed(rows_to_delete):
            # Si el topic estaba marcado en la selección, lo quitamos
            t_item = self.topicTable.item(row, 0)
            if t_item and hasattr(self, "current_realm"):
                if t_item.text().strip() in self.selected_topics_by_realm.get(self.current_realm, set()):
                    self.selected_topics_by_realm[self.current_realm].remove(t_item.text().strip())
            self.topicTable.removeRow(row)

    def startSubscription(self):
        # Para cada realm marcado, recoge los topics marcados y suscríbete.
        for row in range(self.realmTable.rowCount()):
            realm_item = self.realmTable.item(row, 0)
            url_item = self.realmTable.item(row, 1)
            if realm_item and realm_item.checkState() == Qt.Checked:
                realm = realm_item.text().strip()
                router_url = url_item.text().strip() if url_item else "ws://127.0.0.1:60001/ws"
                selected_topics = []
                for t_row in range(self.topicTable.rowCount()):
                    t_item = self.topicTable.item(t_row, 0)
                    if t_item and t_item.checkState() == Qt.Checked:
                        selected_topics.append(t_item.text().strip())
                if selected_topics:
                    start_subscriber(router_url, realm, selected_topics, self.onMessageArrived)
                    print(f"Suscrito a realm '{realm}' con topics {selected_topics}")
                else:
                    QMessageBox.warning(self, "Advertencia", f"No hay topics seleccionados para realm {realm}.")

    @pyqtSlot(str, str, dict)
    def onMessageArrived(self, realm, topic, content):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        details = json.dumps(content, indent=2, ensure_ascii=False)
        self.viewer.add_message(realm, topic, timestamp, details)
        print(f"Mensaje recibido en realm '{realm}', topic '{topic}' a las {timestamp}")

    def resetLog(self):
        self.viewer.table.setRowCount(0)
        self.viewer.messages = []

    def loadProjectFromConfig(self, sub_config):
        # Aquí puedes implementar la carga de un proyecto si lo deseas.
        pass

    # Conectar el cambio de estado en la tabla de topics para persistir la selección
    def showEvent(self, event):
        # Conectar itemChanged de topicTable para actualizar la selección
        self.topicTable.itemChanged.connect(self.onTopicItemChanged)
        super().showEvent(event)

    def hideEvent(self, event):
        # Desconectar para evitar múltiples conexiones
        self.topicTable.itemChanged.disconnect(self.onTopicItemChanged)
        super().hideEvent(event)

# Fin de SubscriberTab
