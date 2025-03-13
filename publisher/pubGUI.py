# publisher/pubGUI.py
import sys, os, json, datetime, logging, asyncio, threading
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QScrollArea, QGroupBox,
    QMessageBox, QLineEdit, QFileDialog, QSplitter, QComboBox
)
from PyQt5.QtCore import Qt
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
from common.utils import log_to_file
from .pubEditor import PublisherEditorWidget  # Debe contener jsonPreview, commonTimeEdit, etc.
from common.utils import log_to_file, JsonDetailDialog
global_session = None
global_loop = None

class JSONPublisher(ApplicationSession):
    def __init__(self, config, topic):
        super().__init__(config)
        self.topic = topic

    async def onJoin(self, details):
        global global_session, global_loop
        global_session = self
        global_loop = asyncio.get_event_loop()
        print(f"Conectado al realm '{self.config.realm}' en publicador.")
        await asyncio.Future()

def start_publisher(url, realm, topic):
    """
    Inicia la sesión WAMP en un hilo aparte para publicar.
    """
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        runner = ApplicationRunner(url=url, realm=realm)
        runner.run(lambda cfg: JSONPublisher(cfg, topic))
    threading.Thread(target=run, daemon=True).start()

def send_message_now(router_url, realm, topic, message, delay=0):
    """
    Envía un mensaje con 'delay' opcional.
    """
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
        print(f"Mensaje enviado a topic '{topic}' en realm '{realm}': {message}")

    asyncio.run_coroutine_threadsafe(_send(), global_loop)

# ------------------------------------------------------------------
# Vista de mensajes enviados con doble clic para ver detalle
# ------------------------------------------------------------------
class PublisherMessageViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pubMessages = []  # Guardar el JSON real
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Hora", "Topic", "Realms"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)

         # Doble clic
        self.table.itemDoubleClicked.connect(self.showDetails)
        layout.addWidget(self.table)
        self.setLayout(layout)
        self.setFixedHeight(200)

        layout.addWidget(self.table)
        self.setLayout(layout)
        self.setFixedHeight(200)

    def add_message(self, realms, topic, timestamp, details):
        # Quitar \n
        if isinstance(details, str):
            details = details.replace("\n", " ")
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(timestamp))
        self.table.setItem(row, 1, QTableWidgetItem(topic))
        self.table.setItem(row, 2, QTableWidgetItem(", ".join(realms)))
        # Guardar el JSON completo (sin quitar \n) en self.pubMessages
        # para ver al hacer doble clic:
        self.pubMessages.append(details)

  
    def showDetails(self, item):
        row = item.row()
        if row < len(self.pubMessages):
            data_str = self.pubMessages[row]
            # Si es dict, pásalo a str
            if isinstance(data_str, dict):
                data_str = json.dumps(data_str, indent=2, ensure_ascii=False)
            from common.utils import JsonDetailDialog
            dlg = JsonDetailDialog(data_str, self)
            dlg.exec_()
            
    def sendMessage(self):
        cfg = self.getConfig()  # realms, topics, content, etc.
        realms = cfg["realms"]
        topics = cfg["topics"]
        content = cfg["content"]
        # Calcular delay según modo = Programado/Hora de sistema/On demand
        delay = self.calcDelay(cfg["mode"], cfg["time"])

        for realm in realms:
            router_url = self.realms_topics[realm]["router_url"]
            for topic in topics:
                start_publisher(router_url, realm, topic)
                send_message_now(router_url, realm, topic, content, delay)

        # Agregar registro al log local (tabla en PublisherTab)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        details_str = json.dumps(content, indent=2, ensure_ascii=False)
        # "self.parent()" es tu PublisherTab. Llama a un método "addPublisherLog(...)" 
        self.parent().addPublisherLog(realms, ", ".join(topics), timestamp, details_str)

# ------------------------------------------------------------------
# Tab principal del publicador
# ------------------------------------------------------------------
class PublisherTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.realms_topics = {}
        self.msgWidgets = []
        self.next_id = 1
        self.initUI()
        self.loadGlobalRealmTopicConfig()

    def initUI(self):
        mainLayout = QVBoxLayout(self)

        # Barra de herramientas
        toolbar = QHBoxLayout()
        btnAddMsg = QPushButton("Agregar Mensaje")
        btnAddMsg.clicked.connect(self.addMessage)
        toolbar.addWidget(btnAddMsg)

        btnDelLast = QPushButton("Eliminar Último Mensaje")
        btnDelLast.clicked.connect(self.removeLastMessage)
        toolbar.addWidget(btnDelLast)

        btnPublishAll = QPushButton("Publicar Todos")
        btnPublishAll.clicked.connect(self.publishAll)
        toolbar.addWidget(btnPublishAll)
        
        # NUEVO: Botón para iniciar publicador (global)
        btnStartGlobal = QPushButton("Iniciar Publicador")
        btnStartGlobal.clicked.connect(self.startGlobalPublisher)
        toolbar.addWidget(btnStartGlobal)

        mainLayout.addLayout(toolbar)

        # Splitter
        splitter = QSplitter(Qt.Vertical)

        # Área de mensajes
        self.msgArea = QScrollArea()
        self.msgArea.setWidgetResizable(True)
        self.msgContainer = QWidget()
        self.msgLayout = QVBoxLayout(self.msgContainer)
        self.msgArea.setWidget(self.msgContainer)

        splitter.addWidget(self.msgArea)

        # Vista de mensajes
        self.viewer = PublisherMessageViewer(self)
        splitter.addWidget(self.viewer)
        splitter.setSizes([500, 200])
        mainLayout.addWidget(splitter)

        self.setLayout(mainLayout)
    
    # Dentro de PublisherTab (o dentro de MessageConfigWidget)
    def publishAll(self):
        # Obtiene la configuración de cada mensaje (realms, topics, contenido, etc.)
        for widget in self.msgWidgets:
            cfg = widget.getConfig()  # Esto devuelve un dict con "realms", "topics", etc.
            realms = cfg.get("realms", [])
            topics = cfg.get("topics", [])
            content = cfg.get("content", {})
            delay = 0  # Calcula el delay según el modo y tiempo, si aplica
            
            # Publica en cada combinación realm-topic que esté marcada:
            for realm in realms:
                # Se obtiene la URL del router del realm:
                router_url = self.realms_topics.get(realm, {}).get("router_url", "ws://127.0.0.1:60001/ws")
                for topic in topics:
                    start_publisher(router_url, realm, topic)
                    send_message_now(router_url, realm, topic, content, delay)
            
            # Registra el mensaje en el log:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.addPublisherLog(realms, ", ".join(topics), timestamp, json.dumps(content, indent=2, ensure_ascii=False))

        
    def startGlobalPublisher(self):
        """
        Inicia el publicador sin enviar mensaje inmediato, 
        simplemente corre la sesión en algún realm/topic por defecto 
        o hace lo que tú desees.
        """
        # Por ejemplo, escoges un realm y un topic cualquiera 
        # para que la sesión no esté 'vacía'.
        default_realm = "default"
        default_topic = "com.my.default"
        default_url = "ws://127.0.0.1:60001"
        from .pubGUI import start_publisher
        start_publisher(default_url, default_realm, default_topic)
        print(f"Sesión de publicador iniciada en realm '{default_realm}' con topic '{default_topic}'")

    def loadGlobalRealmTopicConfig(self):
        """
        Carga realm_topic_config.json con 'realm'->{'router_url', 'topics':[...] }
        """
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "realm_topic_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.realms_topics = data.get("realms", {})
                print("Configuración global (publisher) cargada.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error al cargar realm_topic_config.json: {e}")
        else:
            QMessageBox.warning(self, "Advertencia", "No se encontró realm_topic_config.json.")

    def addMessage(self):
        widget = MessageConfigWidget(self.next_id, parent=self)
        widget.updateRealmsTopics(self.realms_topics)
        self.msgLayout.addWidget(widget)
        self.msgWidgets.append(widget)
        self.next_id += 1

    def removeLastMessage(self):
        if self.msgWidgets:
            w = self.msgWidgets.pop()
            self.msgLayout.removeWidget(w)
            w.deleteLater()
            self.next_id -= 1

    def publishAll(self):
        for w in self.msgWidgets:
            cfg = w.getConfig()
            realms = cfg.get("realms", [])
            topics = cfg.get("topics", [])
            content = cfg.get("content", {})
            mode = cfg.get("mode", "On demand")
            time_str = cfg.get("time", "00:00:00")

            # Calcular delay según 'mode'
            delay = self.calcDelay(mode, time_str)

            for r in realms:
                url = self.realms_topics.get(r, {}).get("router_url", "ws://127.0.0.1:60001")
                for t in topics:
                    start_publisher(url, r, t)
                    send_message_now(url, r, t, content, delay)

            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.viewer.add_message(realms, ", ".join(topics), timestamp, json.dumps(content, indent=2, ensure_ascii=False))

    def calcDelay(self, mode, time_str):
        if mode == "Programado":
            # interpret time_str como HH:MM:SS (delay)
            try:
                h, m, s = map(int, time_str.split(":"))
                return h*3600 + m*60 + s
            except:
                return 0
        elif mode == "Hora de sistema":
            # interpret time_str como hora absoluta
            now = datetime.datetime.now()
            try:
                h, m, s = map(int, time_str.split(":"))
                target = now.replace(hour=h, minute=m, second=s)
                if target < now:
                    # si ya pasó, siguiente día
                    target += datetime.timedelta(days=1)
                return (target - now).total_seconds()
            except:
                return 0
        else:
            # On demand
            return 0

    def addPublisherLog(self, realms, topic, timestamp, details):
        # self.viewer es un PublisherMessageViewer
        if isinstance(realms, list):
            self.viewer.add_message(realms, topic, timestamp, details)
        else:
            self.viewer.add_message([realms], topic, timestamp, details)

# ------------------------------------------------------------------
# Configuración de cada mensaje (left: Realms+Topics, right: Editor)
# ------------------------------------------------------------------
class MessageConfigWidget(QGroupBox):
    def __init__(self, msg_id, parent=None):
        super().__init__(parent)
        self.msg_id = msg_id
        self.realms_topics = {}
        self.setTitle(f"Mensaje #{self.msg_id}")
        self.setCheckable(True)
        self.setChecked(True)
        self.initUI()

    def initUI(self):
        mainLayout = QHBoxLayout(self)

        # -----------------------------
        # Lado Izquierdo (vertical): Realms, Topics
        # -----------------------------
        leftLayout = QVBoxLayout()

        lblRealms = QLabel("Realms + Router URL:")
        leftLayout.addWidget(lblRealms)
        self.realmTable = QTableWidget(0, 2)
        self.realmTable.setHorizontalHeaderLabels(["Realm", "Router URL"])
        self.realmTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.realmTable.cellClicked.connect(self.updateTopicsFromSelectedRealm)
        leftLayout.addWidget(self.realmTable)

        # Botones Realms
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

        lblTopics = QLabel("Topics:")
        leftLayout.addWidget(lblTopics)
        self.topicTable = QTableWidget(0, 1)
        self.topicTable.setHorizontalHeaderLabels(["Topic"])
        self.topicTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        leftLayout.addWidget(self.topicTable)

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

        # -----------------------------
        # Lado Derecho (vertical): Editor JSON + Modo + Tiempo
        # -----------------------------
        rightLayout = QVBoxLayout()

        # Modo y Tiempo
        modeLayout = QHBoxLayout()
        lblMode = QLabel("Modo:")
        self.modeCombo = QComboBox()
        self.modeCombo.addItems(["Programado", "Hora de sistema", "On demand"])
        modeLayout.addWidget(lblMode)
        modeLayout.addWidget(self.modeCombo)

        lblTime = QLabel("Tiempo:")
        self.timeEdit = QLineEdit("00:00:00")
        modeLayout.addWidget(lblTime)
        modeLayout.addWidget(self.timeEdit)

        rightLayout.addLayout(modeLayout)

        # Editor JSON
        self.editorWidget = PublisherEditorWidget(parent=self)
        rightLayout.addWidget(self.editorWidget)

        btnSend = QPushButton("Enviar este Mensaje")
        btnSend.clicked.connect(self.sendMessage)
        rightLayout.addWidget(btnSend)

        mainLayout.addLayout(rightLayout, stretch=1)

        self.setLayout(mainLayout)

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
        realm = realm_item.text()
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

    def getConfig(self):
        # Realms
        realms = []
        for row in range(self.realmTable.rowCount()):
            item = self.realmTable.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                realms.append(item.text())
        # Topics
        topics = []
        for row in range(self.topicTable.rowCount()):
            t_item = self.topicTable.item(row, 0)
            if t_item and t_item.checkState() == Qt.Checked:
                topics.append(t_item.text())

        # JSON del editor
        msg_str = self.editorWidget.jsonPreview.toPlainText()
        try:
            content = json.loads(msg_str)
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
        """
        Envía este mensaje solamente.
        """
        cfg = self.getConfig()
        realms = cfg["realms"]
        topics = cfg["topics"]
        content = cfg["content"]
        mode = cfg["mode"]
        time_str = cfg["time"]

        # Calcular delay
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
                start_publisher(router_url, r, t)
                send_message_now(router_url, r, t, content, delay)

        # Log local en publisher
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if hasattr(self.parent(), "viewer"):
            details = json.dumps(content, indent=2, ensure_ascii=False)
            self.parent().viewer.add_message(realms, ", ".join(topics), timestamp, details)
