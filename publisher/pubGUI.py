import sys, os, json, datetime, logging, asyncio, threading
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QPushButton, QSplitter,
    QGroupBox, QFormLayout, QMessageBox, QLineEdit, QFileDialog, QComboBox, QListWidget, QListWidgetItem, QDialog, QDialogButtonBox
)
from PyQt5.QtCore import Qt, QTimer
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
from common.utils import log_to_file, JsonDetailDialog
from .pubEditor import PublisherEditorWidget

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
        # Se publica para el realm actual
        global_session.publish(topic, **message)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message_json = json.dumps(message, indent=2, ensure_ascii=False)
        log_to_file(timestamp, topic, realm, message_json)
        logging.info(f"Publicado: {timestamp} | Topic: {topic} | Realm: {realm}")
        print("Mensaje enviado en", topic, "para realm", realm, ":", message)
    asyncio.run_coroutine_threadsafe(_send(), global_loop)

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
        if isinstance(details, str):
            details = details.replace("\n", " ")
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

class PublisherTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.msgWidgets = []
        self.next_id = 1
        self.realms_topics = {}   # Mapeo: realm -> [topics]
        self.realm_configs = {}   # Mapeo: realm -> router URL
        self.initUI()
        self.autoLoadRealmsTopics()  # Carga automática del fichero de configuración

    def initUI(self):
        layout = QVBoxLayout()
        # Layout superior con botones globales
        topLayout = QHBoxLayout()
        self.addMsgButton = QPushButton("Agregar mensaje")
        self.addMsgButton.clicked.connect(self.addMessage)
        topLayout.addWidget(self.addMsgButton)
        self.asyncSendButton = QPushButton("Enviar Mensaje Instantáneo")
        self.asyncSendButton.clicked.connect(self.sendAllAsync)
        topLayout.addWidget(self.asyncSendButton)
        self.loadProjectButton = QPushButton("Cargar Proyecto")
        self.loadProjectButton.clicked.connect(self.loadProject)
        topLayout.addWidget(self.loadProjectButton)
        self.loadRealmsButton = QPushButton("Cargar Realms/Topics")
        self.loadRealmsButton.clicked.connect(self.loadRealmsTopics)
        topLayout.addWidget(self.loadRealmsButton)
        layout.addLayout(topLayout)

        # Sección para gestionar las configuraciones de realm (sin widget complejo, se asume que se cargan desde el fichero)
        # En este ejemplo, las configuraciones de router URL se registran automáticamente desde el fichero
        # Si el usuario las modifica manualmente en cada mensaje, se utilizará ese valor

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

        connLayout = QHBoxLayout()
        connLayout.addWidget(QLabel("Publicador Global"))
        self.globalStartButton = QPushButton("Iniciar Publicador")
        self.globalStartButton.clicked.connect(self.startPublisher)
        connLayout.addWidget(self.globalStartButton)
        layout.addLayout(connLayout)

        layout.addWidget(QLabel("Resumen de mensajes enviados:"))
        layout.addWidget(self.viewer)
        self.setLayout(layout)

    def addMessage(self):
        from .pubEditor import PublisherEditorWidget
        widget = MessageConfigWidget(self.next_id, parent=self)
        # Actualiza los realms en el widget si ya se han cargado
        if self.realms_topics:
            widget.updateRealmsTopics(self.realms_topics)
        # Si el realm seleccionado tiene un router configurado, se asigna al URL de mensaje
        # (En este ejemplo, cada mensaje tiene un campo de URL editable para sobreescribir el global)
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
            topic = config.get("topic", "default")
            delay = 0
            try:
                h, m, s = map(int, config.get("time", "00:00:00").split(":"))
                delay = h * 3600 + m * 60 + s
            except:
                delay = 0
            # Enviar a cada realm seleccionado
            for realm in realms:
                router_url = self.realm_configs.get(realm, widget.urlEdit.text().strip())
                start_publisher(router_url, realm, topic)
                send_message_now(router_url, realm, topic, config.get("content", {}), delay)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.addPublisherLog(realms, topic, timestamp, f"Publicador iniciado: {config}")

    def sendAllAsync(self):
        for widget in self.msgWidgets:
            config = widget.getConfig()
            realms = config.get("realms", [])
            topic = config.get("topic", "default")
            for realm in realms:
                router_url = self.realm_configs.get(realm, widget.urlEdit.text().strip())
                send_message_now(router_url, realm, topic, config.get("content", {}), delay=0)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sent_message = json.dumps(config.get("content", {}), indent=2, ensure_ascii=False)
            self.addPublisherLog(realms, topic, timestamp, sent_message)

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
            widget = MessageConfigWidget(self.next_id, parent=self)
            widget.realmList.setSelectedItems(scenario.get("realms", ["default"]))
            widget.urlEdit.setText(scenario.get("router_url", "ws://127.0.0.1:60001"))
            widget.topicCombo.setCurrentText(scenario.get("topic", "default"))
            widget.editorWidget.commonTimeEdit.setText(scenario.get("time", "00:00:00"))
            widget.editorWidget.jsonPreview.setPlainText(json.dumps(scenario.get("content", {}), indent=2, ensure_ascii=False))
            if self.realms_topics:
                widget.updateRealmsTopics(self.realms_topics)
            self.msgLayout.addWidget(widget)
            self.msgWidgets.append(widget)
            self.next_id += 1

    def loadProject(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Seleccione Archivo de Proyecto", "", "JSON Files (*.json);;All Files (*)")
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
        filepath, _ = QFileDialog.getOpenFileName(self, "Cargar Realms/Topics", "", "JSON Files (*.json);;All Files (*)")
        if not filepath:
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.realms_topics = data.get("realms", {})
            # Si en el fichero se definen router URL para cada realm, actualizar realm_configs:
            self.realm_configs = data.get("realm_configs", self.realm_configs)
            for widget in self.msgWidgets:
                widget.updateRealmsTopics(self.realms_topics)
            QMessageBox.information(self, "Realms/Topics", "Realms y Topics cargados correctamente.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo cargar Realms/Topics:\n{e}")

    def autoLoadRealmsTopics(self):
        default_path = os.path.join(os.path.dirname(__file__), "..", "config", "realms_topics.json")
        if os.path.exists(default_path):
            try:
                with open(default_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.realms_topics = data.get("realms", {})
                self.realm_configs = data.get("realm_configs", self.realm_configs)
                for widget in self.msgWidgets:
                    widget.updateRealmsTopics(self.realms_topics)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error al cargar Realms/Topics por defecto:\n{e}")

# Modificación en MessageConfigWidget:
# Se reemplaza el QComboBox de realms por un QListWidget para selección múltiple.
class MessageConfigWidget(QGroupBox):
    def __init__(self, msg_id, parent=None):
        super().__init__(parent)
        self.msg_id = msg_id
        self.realms_topics = {}  # Mapeo para este widget
        self.setTitle(f"Mensaje #{self.msg_id}")
        self.setCheckable(True)
        self.setChecked(True)
        self.toggled.connect(self.toggleContent)
        self.initUI()

    def initUI(self):
        self.contentWidget = QWidget()
        contentLayout = QVBoxLayout()
        formLayout = QFormLayout()
        # Configuración de realms: Usamos un QListWidget para selección múltiple
        self.realmList = QListWidget()
        self.realmList.setSelectionMode(QAbstractItemView.MultiSelection)
        # Se carga inicialmente con "default"
        item = QListWidgetItem("default")
        item.setCheckState(Qt.Checked)
        self.realmList.addItem(item)
        formLayout.addRow("Realms:", self.realmList)
        self.urlEdit = QLineEdit("ws://127.0.0.1:60001")
        formLayout.addRow("Router URL:", self.urlEdit)
        # Configuración del topic (único)
        self.topicCombo = QComboBox()
        self.topicCombo.setEditable(True)
        self.topicCombo.addItem("default")
        formLayout.addRow("Topic:", self.topicCombo)

        contentLayout.addLayout(formLayout)
        from .pubEditor import PublisherEditorWidget
        self.editorWidget = PublisherEditorWidget(parent=self)
        contentLayout.addWidget(self.editorWidget)
        # Botones para enviar y eliminar mensaje
        btnLayout = QHBoxLayout()
        self.sendButton = QPushButton("Enviar")
        self.sendButton.clicked.connect(self.sendMessage)
        btnLayout.addWidget(self.sendButton)
        self.deleteButton = QPushButton("Eliminar")
        self.deleteButton.clicked.connect(self.deleteSelf)
        btnLayout.addWidget(self.deleteButton)
        contentLayout.addLayout(btnLayout)

        self.contentWidget.setLayout(contentLayout)
        mainLayout = QVBoxLayout()
        mainLayout.addWidget(self.contentWidget)
        self.setLayout(mainLayout)

    def deleteSelf(self):
        # Llama al método removeMessage del PublisherTab (accediendo dos niveles arriba)
        self.parent().parent().removeMessage(self)

    def updateRealmsTopics(self, realms_topics):
        self.realms_topics = realms_topics
        self.realmList.clear()
        # Se agregan todos los realms disponibles y se dejan seleccionados por defecto
        for realm in sorted(realms_topics.keys()):
            item = QListWidgetItem(realm)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.realmList.addItem(item)

    def toggleContent(self, checked):
        self.contentWidget.setVisible(checked)
        if not checked:
            topics = self.topicCombo.currentText().strip()
            # Se obtiene la lista de realms seleccionados
            realms = self.getSelectedRealms()
            time_val = self.editorWidget.commonTimeEdit.text()
            self.setTitle(f"Mensaje #{self.msg_id} - {topics} - {time_val} - {', '.join(realms)}")
        else:
            self.setTitle(f"Mensaje #{self.msg_id}")

    def getSelectedRealms(self):
        realms = []
        for index in range(self.realmList.count()):
            item = self.realmList.item(index)
            if item.checkState() == Qt.Checked:
                realms.append(item.text())
        if not realms:
            realms = ["default"]
        return realms

    def sendMessage(self):
        try:
            h, m, s = map(int, self.editorWidget.commonTimeEdit.text().strip().split(":"))
            delay = h * 3600 + m * 60 + s
        except:
            delay = 0
        topic = self.topicCombo.currentText().strip()
        try:
            data = json.loads(self.editorWidget.jsonPreview.toPlainText())
        except Exception as e:
            QMessageBox.critical(self, "Error", f"JSON inválido:\n{e}")
            return
        realms = self.getSelectedRealms()
        # Enviar el mensaje a cada realm seleccionado
        for realm in realms:
            # Obtener el router URL del mensaje (si está definido en el widget, sino se usa el campo URL)
            router_url = self.urlEdit.text().strip()
            from .pubGUI import send_message_now
            send_message_now(router_url, realm, topic, data, delay=delay)
        publish_time = datetime.datetime.now() + datetime.timedelta(seconds=delay)
        publish_time_str = publish_time.strftime("%Y-%m-%d %H:%M:%S")
        sent_message = json.dumps(data, indent=2, ensure_ascii=False)
        if hasattr(self.parent(), "addPublisherLog"):
            self.parent().addPublisherLog(self.getSelectedRealms(), topic, publish_time_str, sent_message)

    def getConfig(self):
        return {
            "id": self.msg_id,
            "realms": self.getSelectedRealms(),
            "router_url": self.urlEdit.text().strip(),
            "topic": self.topicCombo.currentText().strip(),
            "time": self.editorWidget.commonTimeEdit.text().strip(),
            "content": json.loads(self.editorWidget.jsonPreview.toPlainText())
        }
