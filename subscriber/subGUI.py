# subscriber/subGUI.py
import os, json, datetime, logging, asyncio, threading
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QLineEdit
)
from PyQt5.QtCore import Qt, pyqtSlot, QMetaObject, Q_ARG
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
from common.utils import log_to_file, JsonDetailDialog

global_session_sub = None
global_loop_sub = None

def start_subscriber(url, realm, topics, on_message_callback):
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        runner = ApplicationRunner(url=url, realm=realm)
        runner.run(lambda cfg: MultiTopicSubscriber(cfg, topics, on_message_callback))
    threading.Thread(target=run, daemon=True).start()

class MultiTopicSubscriber(ApplicationSession):
    def __init__(self, config, topics, on_message_callback):
        super().__init__(config)
        self.topics = topics
        self.on_message_callback = on_message_callback

    async def onJoin(self, details):
        print(f"Suscriptor conectado (realm={self.config.realm})")
        for t in self.topics:
            await self.subscribe(lambda *args, **kwargs: self.on_event(t, *args, **kwargs), t)

    def on_event(self, topic, *args, **kwargs):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message_data = {"args": args, "kwargs": kwargs}
        msg_str = json.dumps(message_data, indent=2, ensure_ascii=False)
        log_to_file(timestamp, topic, self.config.realm, msg_str)
        if self.on_message_callback:
            self.on_message_callback(topic, message_data)
    
    @classmethod
    def factory(cls, topics, callback):
        def create(config):
            session = cls(config)
            session.topics = topics
            session.on_message_callback = callback
            return session
        return create

class SubscriberMessageViewer(QWidget):
    """
    Muestra los mensajes recibidos en un QTableWidget
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.messages = []
        layout = QVBoxLayout(self)
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Hora", "Topic", "Realm"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)

        # Doble click para ver detalle
        self.table.itemDoubleClicked.connect(self.showDetail)

        layout.addWidget(self.table)
        self.setLayout(layout)

    def add_message(self, realm, topic, timestamp, details):
        """
        details => string JSON o dict
        """
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(timestamp))
        self.table.setItem(row, 1, QTableWidgetItem(topic))
        self.table.setItem(row, 2, QTableWidgetItem(realm))
        self.messages.append(details)

    def showDetail(self, item):
        row = item.row()
        if row < len(self.messages):
            data_str = self.messages[row]
            if isinstance(data_str, dict):
                data_str = json.dumps(data_str, indent=2, ensure_ascii=False)
            dlg = JsonDetailDialog(data_str, self)
            dlg.exec_()

class SubscriberTab(QWidget):
    """
    Suscriptor con Realms + Topics a la izquierda, y tabla de mensajes a la derecha.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.realms_topics = {}
        self.initUI()
        self.loadGlobalRealmTopicConfig()

    def initUI(self):
        mainLayout = QHBoxLayout(self)

        # Lado izquierdo (vertical): Realms, Topics
        leftLayout = QVBoxLayout()

        lblRealms = QLabel("Realms (checkbox) + Router URL:")
        leftLayout.addWidget(lblRealms)

        self.realmTable = QTableWidget(0, 2)
        self.realmTable.setHorizontalHeaderLabels(["Realm", "Router URL"])
        self.realmTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.realmTable.cellClicked.connect(self.onRealmClicked)
        leftLayout.addWidget(self.realmTable)

        # Botones Realms
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

        lblTopics = QLabel("Topics:")
        leftLayout.addWidget(lblTopics)
        self.topicTable = QTableWidget(0, 1)
        self.topicTable.setHorizontalHeaderLabels(["Topic"])
        self.topicTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        leftLayout.addWidget(self.topicTable)

        # Botones Topics
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

        # Botones Suscribirse / Reset
        subBtnLayout = QHBoxLayout()
        self.btnSubscribe = QPushButton("Suscribirse")
        self.btnSubscribe.clicked.connect(self.startSubscription)
        subBtnLayout.addWidget(self.btnSubscribe)
        self.btnReset = QPushButton("Reset Log")
        self.btnReset.clicked.connect(self.resetLog)
        subBtnLayout.addWidget(self.btnReset)
        leftLayout.addLayout(subBtnLayout)

        mainLayout.addLayout(leftLayout, stretch=1)

        # Lado derecho: viewer de mensajes
        self.viewer = SubscriberMessageViewer(self)
        mainLayout.addWidget(self.viewer, stretch=2)

        self.setLayout(mainLayout)

    def loadGlobalRealmTopicConfig(self):
        path = os.path.join(os.path.dirname(__file__), "..", "config", "realm_topic_config.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.realms_topics = data.get("realms", {})
                print("Configuración global de realms/topics cargada (suscriptor).")
                self.populateRealmTable()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo cargar realm_topic_config.json:{e}")
        else:
            QMessageBox.warning(self, "Advertencia", "No se encontró realm_topic_config.json.")

    def populateRealmTable(self):
        self.realmTable.setRowCount(0)
        for realm, info in sorted(self.realms_topics.items()):
            row = self.realmTable.rowCount()
            self.realmTable.insertRow(row)
            realm_item = QTableWidgetItem(realm)
            realm_item.setFlags(realm_item.flags() | Qt.ItemIsUserCheckable)
            realm_item.setCheckState(Qt.Unchecked)
            self.realmTable.setItem(row, 0, realm_item)

            router_url = info.get("router_url", "ws://127.0.0.1:60001")
            self.realmTable.setItem(row, 1, QTableWidgetItem(router_url))

    def onRealmClicked(self, row, col):
        realm_item = self.realmTable.item(row, 0)
        if not realm_item:
            return
        realm = realm_item.text()
        self.populateTopicTable(realm)

    def populateTopicTable(self, realm):
        self.topicTable.setRowCount(0)
        realm_info = self.realms_topics.get(realm, {})
        topics = realm_info.get("topics", [])
        for t in topics:
            r_pos = self.topicTable.rowCount()
            self.topicTable.insertRow(r_pos)
            t_item = QTableWidgetItem(t)
            t_item.setFlags(t_item.flags() | Qt.ItemIsUserCheckable)
            t_item.setCheckState(Qt.Unchecked)
            self.topicTable.setItem(r_pos, 0, t_item)

    def addRealmRow(self):
        new_realm = self.newRealmEdit.text().strip()
        if new_realm:
            row = self.realmTable.rowCount()
            self.realmTable.insertRow(row)
            realm_item = QTableWidgetItem(new_realm)
            realm_item.setFlags(realm_item.flags() | Qt.ItemIsUserCheckable)
            realm_item.setCheckState(Qt.Checked)
            self.realmTable.setItem(row, 0, realm_item)
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
    
    def startSubscription(self):
        # Recolecta realms chequeados de la tabla de realms
        for row in range(self.realmTable.rowCount()):
            realm_item = self.realmTable.item(row, 0)
            url_item = self.realmTable.item(row, 1)
            if realm_item and realm_item.checkState() == Qt.Checked:
                realm = realm_item.text().strip()
                router_url = url_item.text().strip() if url_item else "ws://127.0.0.1:60001/ws"
                selected_topics = []
                # Recolecta topics chequeados de la tabla de topics
                for t_row in range(self.topicTable.rowCount()):
                    t_item = self.topicTable.item(t_row, 0)
                    if t_item and t_item.checkState() == Qt.Checked:
                        selected_topics.append(t_item.text().strip())
                if selected_topics:
                    start_subscriber(router_url, realm, selected_topics, self.onMessageArrived)
                else:
                    QMessageBox.warning(self, "Advertencia", f"No hay topics seleccionados para realm {realm}.")


    def addTopicRow(self):
        new_topic = self.newTopicEdit.text().strip()
        if new_topic:
            row = self.topicTable.rowCount()
            self.topicTable.insertRow(row)
            topic_item = QTableWidgetItem(new_topic)
            topic_item.setFlags(topic_item.flags() | Qt.ItemIsUserCheckable)
            topic_item.setCheckState(Qt.Checked)
            self.topicTable.setItem(row, 0, topic_item)
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
        """
        Se suscribe a todos los realms y topics marcados.
        """
        for r in range(self.realmTable.rowCount()):
            realm_item = self.realmTable.item(r, 0)
            url_item = self.realmTable.item(r, 1)
            if realm_item and realm_item.checkState() == Qt.Checked:
                realm_name = realm_item.text()
                router_url = url_item.text().strip() if url_item else "ws://127.0.0.1:60001"
                selected_topics = []
                for t in range(self.topicTable.rowCount()):
                    t_item = self.topicTable.item(t, 0)
                    if t_item and t_item.checkState() == Qt.Checked:
                        selected_topics.append(t_item.text())
                if selected_topics:
                    start_subscriber(router_url, realm_name, selected_topics, self.onMessageArrived)
                else:
                    QMessageBox.warning(self, "Advertencia", f"No hay topics chequeados para realm {realm_name}.")

    @pyqtSlot(str, dict)
    def onMessageArrived(self, topic, content):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        realm = "(desconocido)"  # si no lo pasas en callback
        details = json.dumps(content, indent=2, ensure_ascii=False)
        self.viewer.add_message(realm, topic, timestamp, details)

    def resetLog(self):
        self.viewer.table.setRowCount(0)
        self.viewer.messages = []

    def loadProjectFromConfig(self, sub_config):
        """
        Si guardas un proyecto con realms y topics, podrías poblar aquí las tablas.
        """
        pass
