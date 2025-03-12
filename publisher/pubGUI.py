import sys, os, json, datetime, logging, asyncio, threading
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QPushButton, QSplitter,
    QGroupBox, QFormLayout, QMessageBox, QLineEdit, QFileDialog, QComboBox
)
from PyQt5.QtCore import Qt
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
from common.utils import log_to_file, JsonDetailDialog
from .pubEditor import PublisherEditorWidget

global_session = None
global_loop = None

# Componente WAMP para el publicador
class JSONPublisher(ApplicationSession):
    def __init__(self, config, topic):
        super().__init__(config)
        self.topic = topic

    async def onJoin(self, details):
        global global_session, global_loop
        global_session = self
        global_loop = asyncio.get_event_loop()
        print("Conexión establecida en el publicador (realm:", self.config.realm, ")")
        await asyncio.Future()

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
        message_json = json.dumps(message, indent=2, ensure_ascii=False)
        log_to_file(timestamp, topic, realm, message_json)
        logging.info(f"Publicado: {timestamp} | Topic: {topic} | Realm: {realm}")
        print("Mensaje enviado en", topic, "para realm", realm, ":", message)
    asyncio.run_coroutine_threadsafe(_send(), global_loop)

# Widget para visualizar mensajes enviados
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
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(timestamp))
        self.table.setItem(row, 1, QTableWidgetItem(topic))
        self.table.setItem(row, 2, QTableWidgetItem(", ".join(realms)))
        self.pubMessages.append(details)

    def showDetails(self, item):
        row = item.row()
        if row < len(self.pubMessages):
            dlg = JsonDetailDialog(self.pubMessages[row], self)
            dlg.exec_()

# Tab Publicador
class PublisherTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.msgWidgets = []
        self.next_id = 1
        self.realms_topics = {}    # Se cargará desde config/realm_topic_config.json
        self.realm_configs = {}    # Se cargará desde config/realm_topic_config.json
        self.initUI()
        self.loadGlobalRealmTopicConfig()

    def initUI(self):
        layout = QVBoxLayout()
        # Barra de herramientas (sin colores adicionales)
        toolbar = QHBoxLayout()
        groupMensajes = QHBoxLayout()
        btnAgregar = QPushButton("Agregar mensaje")
        btnAgregar.clicked.connect(self.addMessage)
        groupMensajes.addWidget(btnAgregar)
        btnEliminar = QPushButton("Eliminar mensaje")
        btnEliminar.clicked.connect(self.deleteSelectedMessage)
        groupMensajes.addWidget(btnEliminar)
        toolbar.addLayout(groupMensajes)
        groupCarga = QHBoxLayout()
        btnCargarProj = QPushButton("Cargar Proyecto")
        btnCargarProj.clicked.connect(self.loadProject)
        groupCarga.addWidget(btnCargarProj)
        btnRecargarRT = QPushButton("Recargar Realm/Topic")
        btnRecargarRT.clicked.connect(self.loadGlobalRealmTopicConfig)
        groupCarga.addWidget(btnRecargarRT)
        toolbar.addLayout(groupCarga)
        groupEnvio = QHBoxLayout()
        btnEnviar = QPushButton("Enviar Mensaje")
        btnEnviar.clicked.connect(self.sendAllAsync)
        groupEnvio.addWidget(btnEnviar)
        toolbar.addLayout(groupEnvio)
        layout.addLayout(toolbar)

        # Área de mensajes
        splitter = QSplitter(Qt.Vertical)
        self.msgArea = QScrollArea()
        self.msgArea.setWidgetResizable(True)
        self.msgContainer = QWidget()
        self.msgLayout = QVBoxLayout()
        self.msgContainer.setLayout(self.msgLayout)
        self.msgArea.setWidget(self.msgContainer)
        splitter.addWidget(self.msgArea)
        self.viewer = PublisherMessageViewer(self)
        splitter.addWidget(self.viewer)
        splitter.setSizes([500, 200])
        layout.addWidget(splitter)

        # Botón global para iniciar publicador
        connLayout = QHBoxLayout()
        connLayout.addWidget(QLabel("Publicador Global"))
        self.globalStartButton = QPushButton("Iniciar Publicador")
        self.globalStartButton.clicked.connect(self.startPublisher)
        connLayout.addWidget(self.globalStartButton)
        layout.addLayout(connLayout)

        layout.addWidget(QLabel("Resumen de mensajes enviados:"))
        layout.addWidget(self.viewer)
        self.setLayout(layout)

    def loadGlobalRealmTopicConfig(self):
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "realm_topic_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.realms_topics = data.get("realms", {})
                self.realm_configs = data.get("realm_configs", {})
                for widget in self.msgWidgets:
                    widget.updateRealmsTopics(self.realms_topics)
                print("Configuración global de realms/topics cargada (publicador).")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error al cargar la configuración global:\n{e}")
        else:
            QMessageBox.warning(self, "Advertencia", "No se encontró el archivo realm_topic_config.json.")

    def deleteSelectedMessage(self):
        if self.msgWidgets:
            self.removeMessage(self.msgWidgets[-1])

    def addMessage(self):
        from .pubEditor import PublisherEditorWidget
        widget = MessageConfigWidget(self.next_id, self)
        if self.realms_topics:
            widget.updateRealmsTopics(self.realms_topics)
        self.msgLayout.addWidget(widget)
        self.msgWidgets.append(widget)
        self.next_id += 1

    def removeMessage(self, widget):
        if widget in self.msgWidgets:
            self.msgWidgets.remove(widget)
            widget.setParent(None)
            widget.deleteLater()

    def addPublisherLog(self, realms, topic, timestamp, details):
        self.viewer.add_message(realms, topic, timestamp, details)

    def startPublisher(self):
        for widget in self.msgWidgets:
            config = widget.getConfig()
            realms = config.get("realms", [])
            topics = config.get("topics", [])
            try:
                h, m, s = map(int, config.get("time", "00:00:00").split(":"))
                delay = h * 3600 + m * 60 + s
            except:
                delay = 0
            for realm in realms:
                router_url = self.realm_configs.get(realm, widget.getRouterURL())
                for topic in topics:
                    start_publisher(router_url, realm, topic)
                    send_message_now(router_url, realm, topic, config.get("content", {}), delay)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.addPublisherLog(realms, ", ".join(topics), timestamp, f"Publicador iniciado: {config}")

    def sendAllAsync(self):
        for widget in self.msgWidgets:
            config = widget.getConfig()
            realms = config.get("realms", [])
            topics = config.get("topics", [])
            for realm in realms:
                router_url = self.realm_configs.get(realm, widget.getRouterURL())
                for topic in topics:
                    send_message_now(router_url, realm, topic, config.get("content", {}), delay=0)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sent_message = json.dumps(config.get("content", {}), indent=2, ensure_ascii=False)
            self.addPublisherLog(realms, ", ".join(topics), timestamp, sent_message)

    def getProjectConfig(self):
        scenarios = [widget.getConfig() for widget in self.msgWidgets]
        return {"scenarios": scenarios, "realm_configs": self.realm_configs}

    def loadProjectFromConfig(self, pub_config):
        scenarios = pub_config.get("scenarios", [])
        self.realm_configs = pub_config.get("realm_configs", {})
        for realm in self.realm_configs:
            if realm not in self.realms_topics:
                self.realms_topics[realm] = ["default"]
        self.msgWidgets = []
        self.next_id = 1
        while self.msgLayout.count():
            item = self.msgLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for scenario in scenarios:
            from .pubEditor import PublisherEditorWidget
            widget = MessageConfigWidget(self.next_id, self)
            for realm in scenario.get("realms", ["default"]):
                widget.realmTable.insertRow(widget.realmTable.rowCount())
                widget.realmTable.setItem(widget.realmTable.rowCount()-1, 0, QTableWidgetItem(realm))
                url = scenario.get("router_url", "ws://127.0.0.1:60001")
                widget.realmTable.setItem(widget.realmTable.rowCount()-1, 1, QTableWidgetItem(url))
            for topic in scenario.get("topics", ["default"]):
                row = widget.topicTable.rowCount()
                widget.topicTable.insertRow(row)
                itemTopic = QTableWidgetItem(topic)
                itemTopic.setFlags(itemTopic.flags() | Qt.ItemIsUserCheckable)
                itemTopic.setCheckState(Qt.Checked)
                widget.topicTable.setItem(row, 0, itemTopic)
            widget.defaultUrlEdit.setText(scenario.get("router_url", "ws://127.0.0.1:60001"))
            widget.editorWidget.commonTimeEdit.setText(scenario.get("time", "00:00:00"))
            widget.editorWidget.jsonPreview.setPlainText(json.dumps(scenario.get("content", {}), indent=2, ensure_ascii=False))
            if self.realms_topics:
                widget.updateRealmsTopics(self.realms_topics)
            widget.modeCombo.setCurrentText(scenario.get("mode", "On demand"))
            # Se elimina la sección de template
            widget.templateEdit.setText("")
            self.msgLayout.addWidget(widget)
            self.msgWidgets.append(widget)
            self.next_id += 1

    def loadProject(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Cargar Proyecto", "", "JSON Files (*.json);;All Files (*)")
        if not filepath:
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                project = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo cargar el proyecto:\n{e}")
            return
        pub_config = project.get("publisher", {})
        self.loadProjectFromConfig(pub_config)
        sub_config = project.get("subscriber", {})
        from subscriber.subGUI import SubscriberTab
        if hasattr(self.parent(), "subscriberTab"):
            self.parent().subscriberTab.loadProjectFromConfig(sub_config)
        QMessageBox.information(self, "Proyecto", "Proyecto cargado correctamente.")

    def loadRealmsTopics(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Cargar Realm/Topic", "", "JSON Files (*.json);;All Files (*)")
        if not filepath:
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.realms_topics = data.get("realms", {})
            self.realm_configs = data.get("realm_configs", self.realm_configs)
            for widget in self.msgWidgets:
                widget.updateRealmsTopics(self.realms_topics)
            QMessageBox.information(self, "Realm/Topic", "Realm y Topics recargados correctamente.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo cargar Realm/Topic:\n{e}")

    def autoLoadGlobalRealmTopicConfig(self):
        default_path = os.path.join(os.path.dirname(__file__), "..", "config", "realm_topic_config.json")
        if os.path.exists(default_path):
            try:
                with open(default_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.realms_topics = data.get("realms", {})
                self.realm_configs = data.get("realm_configs", self.realm_configs)
                for widget in self.msgWidgets:
                    widget.updateRealmsTopics(self.realms_topics)
                print("Configuración global de realms/topics cargada automáticamente (publicador).")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error al cargar la configuración global:\n{e}")

    def getRouterURL(self):
        if self.msgWidgets:
            return self.msgWidgets[0].defaultUrlEdit.text().strip()
        return "ws://127.0.0.1:60001"

    def sendAllAsync(self):
        for widget in self.msgWidgets:
            config = widget.getConfig()
            realms = config.get("realms", [])
            topics = config.get("topics", [])
            for realm in realms:
                router_url = self.realm_configs.get(realm, widget.getRouterURL())
                for topic in topics:
                    send_message_now(router_url, realm, topic, config.get("content", {}), delay=0)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sent_message = json.dumps(config.get("content", {}), indent=2, ensure_ascii=False)
            self.addPublisherLog(realms, ", ".join(topics), timestamp, sent_message)

    def getProjectConfig(self):
        scenarios = [widget.getConfig() for widget in self.msgWidgets]
        return {"scenarios": scenarios, "realm_configs": self.realm_configs}

# Fin de PublisherTab
