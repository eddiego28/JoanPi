# publisher/pubGUI.py
import sys, os, json, datetime, logging, asyncio, threading
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, 
    QTableWidgetItem, QHeaderView, QAbstractItemView, QScrollArea, QGroupBox,
    QMessageBox, QLineEdit, QFileDialog, QSplitter, QComboBox
)
from PyQt5.QtCore import Qt
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
from common.utils import log_to_file, JsonDetailDialog
from .pubEditor import PublisherEditorWidget  # Este widget debe tener 'jsonPreview', 'commonTimeEdit', etc.

global_session = None
global_loop = None

# -------------------------------
# WAMP Publicador
# -------------------------------
class JSONPublisher(ApplicationSession):
    def __init__(self, config, topic):
        super().__init__(config)
        self.topic = topic

    async def onJoin(self, details):
        global global_session, global_loop
        global_session = self
        global_loop = asyncio.get_event_loop()
        print(f"Conexión establecida en el publicador (realm: {self.config.realm})")
        await asyncio.Future()  # Mantiene la sesión activa

def start_publisher(url, realm, topic):
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        runner = ApplicationRunner(url=url, realm=realm)
        runner.run(lambda config: JSONPublisher(config, topic))
    threading.Thread(target=run, daemon=True).start()

def send_message_now(router_url, realm, topic, message, delay=0):
    global global_session, global_loop
    if global_session is None or global_loop is None:
        print("No hay sesión activa. Inicia el publicador primero.")
        return
    async def _send():
        if delay > 0:
            await asyncio.sleep(delay)
        global_session.publish(topic, **message)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg_str = json.dumps(message, indent=2, ensure_ascii=False)
        log_to_file(timestamp, topic, realm, msg_str)
        logging.info(f"Publicado: {timestamp} | Topic: {topic} | Realm: {realm}")
        print(f"Mensaje enviado en topic '{topic}' para realm '{realm}': {message}")
    asyncio.run_coroutine_threadsafe(_send(), global_loop)

# -------------------------------
# Vista de Mensajes Publicados
# -------------------------------
class PublisherMessageViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pubMessages = []
        self.initUI()
        
    def initUI(self):
        layout = QVBoxLayout(self)
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Hora", "Topic", "Realms"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemDoubleClicked.connect(self.showDetails)
        layout.addWidget(self.table)
        self.setLayout(layout)
        self.setFixedHeight(200)
        
    def add_message(self, realms, topic, timestamp, details):
        # Para la visualización quitamos saltos de línea; pero almacenamos el JSON completo.
        display_details = details.replace("\n", " ") if isinstance(details, str) else str(details)
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(timestamp))
        self.table.setItem(row, 1, QTableWidgetItem(topic))
        self.table.setItem(row, 2, QTableWidgetItem(", ".join(realms)))
        self.pubMessages.append(details)
        
    def showDetails(self, item):
        row = item.row()
        if row < len(self.pubMessages):
            data = self.pubMessages[row]
            if isinstance(data, dict):
                data = json.dumps(data, indent=2, ensure_ascii=False)
            dlg = JsonDetailDialog(data, self)
            dlg.exec_()

# -------------------------------
# Widget de Configuración de Mensaje (Publisher)
# -------------------------------
class MessageConfigWidget(QGroupBox):
    """
    Configuración individual de un mensaje.
    A la izquierda se ubican las tablas de Realms y Topics;
    a la derecha el editor JSON, el modo y el tiempo.
    """
    def __init__(self, msg_id, parent=None):
        super().__init__(parent)
        self.msg_id = msg_id
        self.realms_topics = {}  # Se actualizará desde PublisherTab
        self.setTitle(f"Mensaje #{self.msg_id}")
        self.setCheckable(True)
        self.setChecked(True)
        self.initUI()

    def initUI(self):
        mainLayout = QHBoxLayout(self)

        # Lado Izquierdo: Realms y Topics
        leftLayout = QVBoxLayout()
        lblRealms = QLabel("Realms + Router URL:")
        leftLayout.addWidget(lblRealms)
        self.realmTable = QTableWidget(0, 2)
        self.realmTable.setHorizontalHeaderLabels(["Realm", "Router URL"])
        self.realmTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.realmTable.cellClicked.connect(self.updateTopicsFromSelectedRealm)
        leftLayout.addWidget(self.realmTable)
        # Botones para Realms
        realmBtnLayout = QHBoxLayout()
        self.newRealmEdit = QLineEdit()
        self.newRealmEdit.setPlaceholderText("Nuevo Realm")
        btnAddRealm = QPushButton("Agregar Realm")
        btnAddRealm.clicked.connect(self.addRealmRow)
        btnDelRealm = QPushButton("Borrar Realm")
        btnDelRealm.clicked.connect(self.deleteRealmRow)
        realmBtnLayout.addWidget(self.newRealmEdit)
        realmBtnLayout.addWidget(btnAddRealm)
        realmBtnLayout.addWidget(btnDelRealm)
        leftLayout.addLayout(realmBtnLayout)
        # Tabla de Topics
        lblTopics = QLabel("Topics:")
        leftLayout.addWidget(lblTopics)
        self.topicTable = QTableWidget(0, 1)
        self.topicTable.setHorizontalHeaderLabels(["Topic"])
        self.topicTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        leftLayout.addWidget(self.topicTable)
        # Botones para Topics
        topicBtnLayout = QHBoxLayout()
        self.newTopicEdit = QLineEdit()
        self.newTopicEdit.setPlaceholderText("Nuevo Topic")
        btnAddTopic = QPushButton("Agregar Topic")
        btnAddTopic.clicked.connect(self.addTopicRow)
        btnDelTopic = QPushButton("Borrar Topic")
        btnDelTopic.clicked.connect(self.deleteTopicRow)
        topicBtnLayout.addWidget(self.newTopicEdit)
        topicBtnLayout.addWidget(btnAddTopic)
        topicBtnLayout.addWidget(btnDelTopic)
        leftLayout.addLayout(topicBtnLayout)

        mainLayout.addLayout(leftLayout, stretch=1)

        # Lado Derecho: Editor JSON, modo y tiempo
        rightLayout = QVBoxLayout()
        modeLayout = QHBoxLayout()
        lblMode = QLabel("Modo:")
        self.modeCombo = QComboBox()
        self.modeCombo.addItems(["Programado", "Hora de sistema", "On demand"])
        modeLayout.addWidget(lblMode)
        modeLayout.addWidget(self.modeCombo)
        lblTime = QLabel("Tiempo (HH:MM:SS):")
        self.timeEdit = QLineEdit("00:00:00")
        modeLayout.addWidget(lblTime)
        modeLayout.addWidget(self.timeEdit)
        rightLayout.addLayout(modeLayout)

        self.editorWidget = PublisherEditorWidget(parent=self)
        rightLayout.addWidget(self.editorWidget)

        btnSend = QPushButton("Enviar este Mensaje")
        btnSend.clicked.connect(self.sendMessage)
        rightLayout.addWidget(btnSend)

        mainLayout.addLayout(rightLayout, stretch=1)
        self.setLayout(mainLayout)

    # Métodos para Realms y Topics
    def addRealmRow(self):
        new_realm = self.newRealmEdit.text().strip()
        if new_realm:
            row = self.realmTable.rowCount()
            self.realmTable.insertRow(row)
            realm_item = QTableWidgetItem(new_realm)
            realm_item.setFlags(realm_item.flags() | Qt.ItemIsUserCheckable)
            realm_item.setCheckState(Qt.Checked)
            self.realmTable.setItem(row, 0, realm_item)
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
            self.newTopicEdit.clear()

    def deleteTopicRow(self):
        rows_to_delete = []
        for row in range(self.topicTable.rowCount()):
            t_item = self.topicTable.item(row, 0)
            if t_item and t_item.checkState() != Qt.Checked:
                rows_to_delete.append(row)
        for row in reversed(rows_to_delete):
            self.topicTable.removeRow(row)

    def updateRealmsTopics(self, realms_topics):
        self.realms_topics = realms_topics
        self.realmTable.setRowCount(0)
        for realm, info in sorted(realms_topics.items()):
            row = self.realmTable.rowCount()
            self.realmTable.insertRow(row)
            r_item = QTableWidgetItem(realm)
            r_item.setFlags(r_item.flags() | Qt.ItemIsUserCheckable)
            r_item.setCheckState(Qt.Checked)
            self.realmTable.setItem(row, 0, r_item)
            router_url = info.get("router_url", "ws://127.0.0.1:60001/ws")
            self.realmTable.setItem(row, 1, QTableWidgetItem(router_url))
        if self.realmTable.rowCount() > 0:
            self.updateTopicsFromSelectedRealm(0, 0)

    def updateTopicsFromSelectedRealm(self, row, column):
        realm_item = self.realmTable.item(row, 0)
        if not realm_item:
            return
        realm = realm_item.text().strip()
        self.topicTable.setRowCount(0)
        if realm in self.realms_topics and "topics" in self.realms_topics[realm]:
            for topic in self.realms_topics[realm]["topics"]:
                r = self.topicTable.rowCount()
                self.topicTable.insertRow(r)
                t_item = QTableWidgetItem(topic)
                t_item.setFlags(t_item.flags() | Qt.ItemIsUserCheckable)
                t_item.setCheckState(Qt.Checked)
                self.topicTable.setItem(r, 0, t_item)
        else:
            self.topicTable.insertRow(0)
            self.topicTable.setItem(0, 0, QTableWidgetItem("default"))

    def getRouterURL(self):
        # Por defecto, devuelve el Router URL del primer realm en el widget
        if self.realmTable.rowCount() > 0:
            url_item = self.realmTable.item(0, 1)
            if url_item:
                return url_item.text().strip()
        return "ws://127.0.0.1:60001/ws"

    def getConfig(self):
        realms = []
        for row in range(self.realmTable.rowCount()):
            item = self.realmTable.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                realms.append(item.text().strip())
        topics = []
        for row in range(self.topicTable.rowCount()):
            t_item = self.topicTable.item(row, 0)
            if t_item and t_item.checkState() == Qt.Checked:
                topics.append(t_item.text().strip())
        try:
            content = json.loads(self.editorWidget.jsonPreview.toPlainText())
        except:
            content = {}
        time_val = self.timeEdit.text().strip()
        mode_val = self.modeCombo.currentText()
        return {
            "realms": realms,
            "topics": topics,
            "content": content,
            "time": time_val,
            "mode": mode_val
        }

    def sendMessage(self):
        cfg = self.getConfig()
        realms = cfg["realms"]
        topics = cfg["topics"]
        content = cfg["content"]
        mode = cfg["mode"]
        time_str = cfg["time"]
        delay = 0
        if mode == "Programado":
            try:
                h, m, s = map(int, time_str.split(":"))
                delay = h*3600 + m*60 + s
            except:
                delay = 0
        elif mode == "Hora de sistema":
            now = datetime.datetime.now()
            try:
                h, m, s = map(int, time_str.split(":"))
                target = now.replace(hour=h, minute=m, second=s)
                if target < now:
                    target += datetime.timedelta(days=1)
                delay = (target - now).total_seconds()
            except:
                delay = 0
        else:
            delay = 0

        if not realms or not topics:
            QMessageBox.warning(self, "Error", "Selecciona al menos un realm y un topic.")
            return

        for r in realms:
            router_url = self.realms_topics.get(r, {}).get("router_url", "ws://127.0.0.1:60001/ws")
            for t in topics:
                from .pubGUI import start_publisher, send_message_now
                start_publisher(router_url, r, t)
                send_message_now(router_url, r, t, content, delay)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.parent().addPublisherLog(realms, ", ".join(topics), timestamp, json.dumps(content, indent=2, ensure_ascii=False))

    def toggleContent(self, checked):
        # Opcional: Ocultar o mostrar el contenido del widget
        pass

# Fin de MessageConfigWidget
