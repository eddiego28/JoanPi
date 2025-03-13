# publisher/pubGUI.py
import sys, os, json, datetime, logging, asyncio, threading
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QPushButton, QSplitter,
    QGroupBox, QFormLayout, QMessageBox, QLineEdit, QFileDialog
)
from PyQt5.QtCore import Qt
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
from common.utils import log_to_file
from .pubEditor import PublisherEditorWidget

global_session = None
global_loop = None

# -------------------------------------------
# WAMP Publisher components
# -------------------------------------------
class JSONPublisher(ApplicationSession):
    def __init__(self, config, topic):
        super().__init__(config)
        self.topic = topic

    async def onJoin(self, details):
        global global_session, global_loop
        global_session = self
        global_loop = asyncio.get_event_loop()
        print(f"Conectado en el publicador (realm: {self.config.realm})")
        await asyncio.Future()

def start_publisher(url, realm, topic):
    """
    Inicia la sesión de publisher en un hilo aparte.
    """
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        runner = ApplicationRunner(url=url, realm=realm)
        runner.run(lambda config: JSONPublisher(config, topic))
    threading.Thread(target=run, daemon=True).start()

def send_message_now(router_url, realm, topic, message, delay=0):
    """
    Envía un mensaje con delay opcional a 'topic' en el realm especificado.
    """
    global global_session, global_loop
    if global_session is None or global_loop is None:
        print("No hay sesión activa. Inicia el publicador primero.")
        return

    async def _send():
        if delay > 0:
            await asyncio.sleep(delay)
        # Publicamos
        global_session.publish(topic, **message)
        # Log
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message_json = json.dumps(message, indent=2, ensure_ascii=False)
        log_to_file(timestamp, topic, realm, message_json)
        logging.info(f"Publicado: {timestamp} | Topic: {topic} | Realm: {realm}")
        print(f"Mensaje enviado en '{topic}' para realm '{realm}': {message}")

    asyncio.run_coroutine_threadsafe(_send(), global_loop)

# -------------------------------------------
# Visualizador de Mensajes
# -------------------------------------------
class PublisherMessageViewer(QWidget):
    """
    Muestra en una tabla los mensajes enviados (con su timestamp, topic, realms).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pubMessages = []
        self.initUI()
        
    def initUI(self):
        layout = QHBoxLayout(self)
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Hora", "Topic", "Realms"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table)
        self.setLayout(layout)
        self.setFixedHeight(200)

    def add_message(self, realms, topic, timestamp, details):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(timestamp))
        self.table.setItem(row, 1, QTableWidgetItem(topic))
        self.table.setItem(row, 2, QTableWidgetItem(", ".join(realms)))
        self.pubMessages.append(details)

# -------------------------------------------
# Main Publisher Tab
# -------------------------------------------
class PublisherTab(QWidget):
    """
    Tab principal para manejar la lógica de múltiples mensajes (MessageConfigWidget).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.msgWidgets = []
        self.next_id = 1
        self.realms_topics = {}  # realm -> { router_url, topics[] }
        self.initUI()
        self.loadGlobalRealmTopicConfig()

    def initUI(self):
        
        mainLayout = QVBoxLayout(self)

        # Barra de herramientas
        toolbar = QHBoxLayout()
        btnAddMsg = QPushButton("Agregar Mensaje")
        btnAddMsg.clicked.connect(self.addMessage)
        toolbar.addWidget(btnAddMsg)

        btnDelMsg = QPushButton("Eliminar Último Mensaje")
        btnDelMsg.clicked.connect(self.removeLastMessage)
        toolbar.addWidget(btnDelMsg)

        btnSendAll = QPushButton("Publicar Todos")
        btnSendAll.clicked.connect(self.publishAll)
        toolbar.addWidget(btnSendAll)

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

        # Vista de los mensajes enviados
        self.viewer = PublisherMessageViewer(self)
        splitter.addWidget(self.viewer)
        splitter.setSizes([500, 200])
        mainLayout.addWidget(splitter)

        # Botón para iniciar global
        globalPubLayout = QHBoxLayout()
        globalPubLayout.addWidget(QLabel("Publicador Global:"))
        self.btnStartGlobal = QPushButton("Iniciar Publicador Global")
        self.btnStartGlobal.clicked.connect(self.startGlobalPublisher)
        globalPubLayout.addWidget(self.btnStartGlobal)
        mainLayout.addLayout(globalPubLayout)

        self.setLayout(mainLayout)

    def addMessage(self):
        widget = MessageConfigWidget(self.next_id, parent=self)
        # Cargar realms/topics globales
        widget.updateRealmsTopics(self.realms_topics)
        self.msgLayout.addWidget(widget)
        self.msgWidgets.append(widget)
        self.next_id += 1

    def removeLastMessage(self):
        if self.msgWidgets:
            widget = self.msgWidgets.pop()
            self.msgLayout.removeWidget(widget)
            widget.deleteLater()
            self.next_id -= 1

    def publishAll(self):
        """
        Publica en todos los MessageConfigWidget agregados.
        """
        for widget in self.msgWidgets:
            cfg = widget.getConfig()
            realms = cfg.get("realms", [])
            topics = cfg.get("topics", [])
            msgContent = cfg["content"]
            delay = 0
            # Si usas tiempo de retardo
            try:
                h, m, s = map(int, cfg.get("time", "00:00:00").split(":"))
                delay = h*3600 + m*60 + s
            except ValueError:
                delay = 0
            # Publicar en cada realm/topic
            for realm in realms:
                router_url = self.realms_topics[realm]["router_url"]
                for topic in topics:
                    start_publisher(router_url, realm, topic)
                    send_message_now(router_url, realm, topic, msgContent, delay=delay)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.viewer.add_message(realms, ", ".join(topics), timestamp, json.dumps(msgContent, indent=2, ensure_ascii=False))

    def loadGlobalRealmTopicConfig(self):
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "realm_topic_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.realms_topics = data.get("realms", {})
                print("Configuración global (publisher) cargada.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error al cargar realm_topic_config.json:\n{e}")
        else:
            QMessageBox.warning(self, "Advertencia", "No se encontró realm_topic_config.json.")

    def startGlobalPublisher(self):
        """
        Inicia el publisher con la configuración del primer realm y topic, si lo deseas.
        O simplemente prepara la sesión global.
        """
        # (Opcional) Lógica para iniciar un publisher 'global'.
        # Por ejemplo, si quieres que haya un publisher corriendo siempre:
        # start_publisher(default_url, default_realm, default_topic)
        pass

    def addPublisherLog(self, realms, topic, timestamp, details):
        """
        Añade la entrada en la tabla de mensajes enviados (PublisherMessageViewer).
        """
        if isinstance(realms, list) and not isinstance(topic, list):
            self.viewer.add_message(realms, topic, timestamp, details)
        elif isinstance(realms, list) and isinstance(topic, list):
            # Manejo de listas
            self.viewer.add_message(realms, ", ".join(topic), timestamp, details)

# -------------------------------------------
# Configuración de cada Mensaje
# -------------------------------------------
class MessageConfigWidget(QGroupBox):
    """
    Representa la configuración de un mensaje en el Publicador.
    """
    def __init__(self, msg_id, parent=None):
        super().__init__(parent)
        self.msg_id = msg_id
        self.realms_topics = {}
        self.setTitle(f"Mensaje #{self.msg_id}")
        self.setCheckable(True)
        self.setChecked(True)

        self.initUI()

    def initUI(self):
       # Layout principal en horizontal
        mainLayout = QHBoxLayout(self)

        # ----------------------------------------------------------------
        # Lado Izquierdo (vertical): Realms y Topics
        # ----------------------------------------------------------------
        leftLayout = QVBoxLayout()

        # ---------- Tabla de Realms ----------
        lblRealms = QLabel("Realms + Router URL:")
        leftLayout.addWidget(lblRealms)

        self.realmTable = QTableWidget(0, 2)
        self.realmTable.setHorizontalHeaderLabels(["Realm", "Router URL"])
        self.realmTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        # Al hacer clic en un Realm -> actualizar Topics
        self.realmTable.cellClicked.connect(self.updateTopicsFromSelectedRealm)
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

        # ---------- Tabla de Topics ----------
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
        self.btnAddTopic = QPushButton("Agregar Topic")
        self.btnAddTopic.clicked.connect(self.addTopicRow)
        self.btnDelTopic = QPushButton("Borrar Topic")
        self.btnDelTopic.clicked.connect(self.deleteTopicRow)
        topicBtnLayout.addWidget(self.newTopicEdit)
        topicBtnLayout.addWidget(self.btnAddTopic)
        topicBtnLayout.addWidget(self.btnDelTopic)
        leftLayout.addLayout(topicBtnLayout)

        # Añadir el layout izquierdo al mainLayout
        mainLayout.addLayout(leftLayout, stretch=1)

        # ----------------------------------------------------------------
        # Lado Derecho (vertical): Editor JSON + Botón Enviar
        # ----------------------------------------------------------------
        rightLayout = QVBoxLayout()

        # Editor JSON (publisherEditorWidget): con vista JSON y árbol
        self.editorWidget = PublisherEditorWidget(parent=self)
        rightLayout.addWidget(self.editorWidget)

        # Botón de Enviar este mensaje
        self.btnSend = QPushButton("Enviar este Mensaje")
        self.btnSend.clicked.connect(self.sendMessage)
        rightLayout.addWidget(self.btnSend)

        # Añadir el layout derecho al mainLayout
        mainLayout.addLayout(rightLayout, stretch=1)

        self.setLayout(mainLayout)

    # -------------------------------------------
    # Lógica para Realms
    # -------------------------------------------
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

    def updateTopicsFromSelectedRealm(self, row, column):
        # Al hacer clic en la tabla de realms, se actualiza la tabla de topics
        realm_item = self.realmTable.item(row, 0)
        if not realm_item:
            return
        realm = realm_item.text().strip()
        self.topicTable.setRowCount(0)
        # Buscar en self.realms_topics
        if realm in self.realms_topics and "topics" in self.realms_topics[realm]:
            for topic in self.realms_topics[realm]["topics"]:
                row_pos = self.topicTable.rowCount()
                self.topicTable.insertRow(row_pos)
                t_item = QTableWidgetItem(topic)
                t_item.setFlags(t_item.flags() | Qt.ItemIsUserCheckable)
                t_item.setCheckState(Qt.Checked)
                self.topicTable.setItem(row_pos, 0, t_item)
        else:
            # No hay topics, poner default
            self.topicTable.insertRow(0)
            self.topicTable.setItem(0, 0, QTableWidgetItem("default"))

    # -------------------------------------------
    # Lógica para Topics
    # -------------------------------------------
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
            item = self.topicTable.item(row, 0)
            if item.checkState() != Qt.Checked:
                rows_to_delete.append(row)
        for row in reversed(rows_to_delete):
            self.topicTable.removeRow(row)

    # -------------------------------------------
    # Actualiza la tabla de realms con la config global
    # -------------------------------------------
    def updateRealmsTopics(self, realms_topics):
        self.realms_topics = realms_topics
        self.realmTable.setRowCount(0)
        for realm, info in sorted(realms_topics.items()):
            row = self.realmTable.rowCount()
            self.realmTable.insertRow(row)
            realm_item = QTableWidgetItem(realm)
            realm_item.setFlags(realm_item.flags() | Qt.ItemIsUserCheckable)
            realm_item.setCheckState(Qt.Checked)
            self.realmTable.setItem(row, 0, realm_item)
            # Router URL editable
            router_url = info.get("router_url", "ws://127.0.0.1:60001")
            self.realmTable.setItem(row, 1, QTableWidgetItem(router_url))
        # Si hay al menos un realm, actualizar los topics del primero
        if self.realmTable.rowCount() > 0:
            self.updateTopicsFromSelectedRealm(0, 0)

    # -------------------------------------------
    # Obtiene config de este widget
    # -------------------------------------------
    def getConfig(self):
        # Realms seleccionados
        realms = []
        for row in range(self.realmTable.rowCount()):
            item = self.realmTable.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                realms.append(item.text())
        # Topics seleccionados
        topics = []
        for row in range(self.topicTable.rowCount()):
            t_item = self.topicTable.item(row, 0)
            if t_item and t_item.checkState() == Qt.Checked:
                topics.append(t_item.text())
        # Mensaje JSON
        content_str = self.editorWidget.jsonPreview.toPlainText()
        try:
            content = json.loads(content_str)
        except:
            content = {}
        # Tiempo, modo, etc.
        time_val = self.editorWidget.commonTimeEdit.text().strip()
        mode_val = "On demand"  # o lo que tu editor maneje
        return {
            "realms": realms,
            "topics": topics,
            "content": content,
            "time": time_val,
            "mode": mode_val
        }

    # -------------------------------------------
    # Envía este mensaje (botón \"Enviar\")
    # -------------------------------------------
    def sendMessage(self):
        cfg = self.getConfig()
        realms = cfg["realms"]
        topics = cfg["topics"]
        content = cfg["content"]

        # Delay opcional
        delay = 0
        try:
            h, m, s = map(int, cfg.get("time", "00:00:00").split(":")) 
            delay = h*3600 + m*60 + s
        except:
            delay = 0

        if not realms or not topics:
            QMessageBox.warning(self, "Error", "Selecciona al menos un realm y un topic")
            return
        for realm in realms:
            router_url = self.realms_topics[realm].get("router_url", "ws://127.0.0.1:60001")
            for topic in topics:
                start_publisher(router_url, realm, topic)
                send_message_now(router_url, realm, topic, content, delay)

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Añadir log local si lo deseas
        if hasattr(self.parent(), "viewer") and self.parent().viewer:
            self.parent().viewer.add_message(realms, ",".join(topics), timestamp, json.dumps(content, indent=2, ensure_ascii=False))

    # -------------------------------------------
    # Toggle de la QGroupBox (mostrar/ocultar el widget)
    # -------------------------------------------
    def toggleContent(self, checked):
        pass  # si quieres ocultar self.contentWidget
