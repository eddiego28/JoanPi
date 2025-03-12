import sys, os, json, datetime, logging, asyncio, threading
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QPushButton, QSplitter,
    QGroupBox, QFormLayout, QMessageBox, QLineEdit, QFileDialog, QComboBox,
    QListWidget, QListWidgetItem
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
        self.realms_topics = {}    # Global: realm -> [topics]
        self.realm_configs = {}    # Global: realm -> router URL
        self.initUI()
        self.autoLoadRealmsTopics()

    def initUI(self):
        layout = QVBoxLayout()
        # Barra de herramientas por grupos
        toolbar = QHBoxLayout()
        # Grupo Mensajes
        groupMensajes = QHBoxLayout()
        btnAgregar = QPushButton("Agregar mensaje")
        btnAgregar.clicked.connect(self.addMessage)
        btnAgregar.setStyleSheet("background-color: #AED6F1; font-weight: bold;")
        groupMensajes.addWidget(btnAgregar)
        btnEliminar = QPushButton("Eliminar mensaje seleccionado")
        btnEliminar.clicked.connect(self.deleteSelectedMessage)
        btnEliminar.setStyleSheet("background-color: #AED6F1; font-weight: bold;")
        groupMensajes.addWidget(btnEliminar)
        toolbar.addLayout(groupMensajes)
        # Grupo Carga
        groupCarga = QHBoxLayout()
        btnCargarProj = QPushButton("Cargar Proyecto")
        btnCargarProj.clicked.connect(self.loadProject)
        btnCargarProj.setStyleSheet("background-color: #A9DFBF;")
        groupCarga.addWidget(btnCargarProj)
        btnCargarRT = QPushButton("Cargar Realm/Topic")
        btnCargarRT.clicked.connect(self.loadRealmsTopics)
        btnCargarRT.setStyleSheet("background-color: #A9DFBF;")
        groupCarga.addWidget(btnCargarRT)
        toolbar.addLayout(groupCarga)
        # Grupo Envío
        groupEnvio = QHBoxLayout()
        btnEnviar = QPushButton("Enviar Mensaje Instantáneo")
        btnEnviar.clicked.connect(self.sendAllAsync)
        btnEnviar.setStyleSheet("background-color: #F9E79F;")
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
                item = QListWidgetItem(realm)
                item.setCheckState(Qt.Checked)
                widget.realmTable.insertRow(widget.realmTable.rowCount())
                widget.realmTable.setItem(widget.realmTable.rowCount()-1, 0, QTableWidgetItem(realm))
                url = scenario.get("router_url", "ws://127.0.0.1:60001")
                widget.realmTable.setItem(widget.realmTable.rowCount()-1, 1, QTableWidgetItem(url))
            for topic in scenario.get("topics", ["default"]):
                item = QListWidgetItem(topic)
                item.setCheckState(Qt.Checked)
                widget.topicList.addItem(item)
            widget.urlEdit.setText(scenario.get("router_url", "ws://127.0.0.1:60001"))
            widget.editorWidget.commonTimeEdit.setText(scenario.get("time", "00:00:00"))
            widget.editorWidget.jsonPreview.setPlainText(json.dumps(scenario.get("content", {}), indent=2, ensure_ascii=False))
            if self.realms_topics:
                widget.updateRealmsTopics(self.realms_topics)
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
        filepath, _ = QFileDialog.getOpenFileName(self, "Cargar Realms/Topics", "", "JSON Files (*.json);;All Files (*)")
        if not filepath:
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.realms_topics = data.get("realms", {})
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

class MessageConfigWidget(QGroupBox):
    def __init__(self, msg_id, parent=None):
        super().__init__(parent)
        self.msg_id = msg_id
        self.realms_topics = {}  # Configuración local para este mensaje
        self.setTitle(f"Mensaje #{self.msg_id}")
        self.setCheckable(True)
        self.setChecked(True)
        self.toggled.connect(self.toggleContent)
        self.initUI()

    def initUI(self):
        self.contentWidget = QWidget()
        contentLayout = QHBoxLayout()
        formLayout = QFormLayout()
        # Realms: tabla con 2 columnas (Realm y Router URL)
        self.realmTable = QTableWidget(0, 2)
        self.realmTable.setHorizontalHeaderLabels(["Realm", "Router URL"])
        self.realmTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        formLayout.addRow("Realms:", self.realmTable)
        # Botones para gestionar realms en la tabla
        realmBtnLayout = QHBoxLayout()
        self.newRealmEdit = QLineEdit()
        self.newRealmEdit.setPlaceholderText("Nuevo realm")
        realmBtnLayout.addWidget(self.newRealmEdit)
        self.addRealmBtn = QPushButton("Agregar")
        self.addRealmBtn.clicked.connect(self.addRealmRow)
        realmBtnLayout.addWidget(self.addRealmBtn)
        self.delRealmBtn = QPushButton("Borrar")
        self.delRealmBtn.clicked.connect(self.deleteRealmRow)
        realmBtnLayout.addWidget(self.delRealmBtn)
        formLayout.addRow("", realmBtnLayout)

        # Topics: QListWidget con botones Agregar y Borrar
        self.topicList = QListWidget()
        self.topicList.setSelectionMode(QListWidget.MultiSelection)
        default_topic = QListWidgetItem("default")
        default_topic.setCheckState(Qt.Checked)
        self.topicList.addItem(default_topic)
        topicLayout = QHBoxLayout()
        topicLayout.addWidget(self.topicList)
        self.newTopicEdit = QLineEdit()
        self.newTopicEdit.setPlaceholderText("Nuevo topic")
        topicLayout.addWidget(self.newTopicEdit)
        self.addTopicBtn = QPushButton("Agregar")
        self.addTopicBtn.clicked.connect(self.addTopic)
        topicLayout.addWidget(self.addTopicBtn)
        self.delTopicBtn = QPushButton("Borrar")
        self.delTopicBtn.clicked.connect(self.deleteTopic)
        topicLayout.addWidget(self.delTopicBtn)
        formLayout.addRow("Topics:", topicLayout)

        # Modo de envío
        self.modeCombo = QComboBox()
        self.modeCombo.addItems(["Programado", "Hora de sistema", "On demand"])
        formLayout.addRow("Modo:", self.modeCombo)

        formContainer = QWidget()
        formContainer.setLayout(formLayout)
        contentLayout.addWidget(formContainer)
        # Editor de mensaje
        self.editorWidget = PublisherEditorWidget(parent=self)
        contentLayout.addWidget(self.editorWidget)
        # Barra lateral de botones: Enviar y Eliminar mensaje
        sideLayout = QVBoxLayout()
        self.sendButton = QPushButton("Enviar")
        self.sendButton.clicked.connect(self.sendMessage)
        sideLayout.addWidget(self.sendButton)
        self.deleteButton = QPushButton("Eliminar")
        self.deleteButton.clicked.connect(self.deleteSelf)
        sideLayout.addWidget(self.deleteButton)
        contentLayout.addLayout(sideLayout)
        self.contentWidget.setLayout(contentLayout)
        outerLayout = QVBoxLayout()
        outerLayout.addWidget(self.contentWidget)
        self.setLayout(outerLayout)

    def addRealmRow(self):
        new_realm = self.newRealmEdit.text().strip()
        if new_realm:
            row = self.realmTable.rowCount()
            self.realmTable.insertRow(row)
            itemRealm = QTableWidgetItem(new_realm)
            itemRealm.setFlags(itemRealm.flags() | Qt.ItemIsUserCheckable)
            itemRealm.setCheckState(Qt.Checked)
            self.realmTable.setItem(row, 0, itemRealm)
            self.realmTable.setItem(row, 1, QTableWidgetItem(""))
            self.newRealmEdit.clear()

    def deleteRealmRow(self):
        rows_to_delete = []
        for row in range(self.realmTable.rowCount()):
            item = self.realmTable.item(row, 0)
            if item.checkState() != Qt.Checked:
                rows_to_delete.append(row)
        for row in sorted(rows_to_delete, reverse=True):
            self.realmTable.removeRow(row)

    def addTopic(self):
        new_topic = self.newTopicEdit.text().strip()
        if new_topic:
            item = QListWidgetItem(new_topic)
            item.setCheckState(Qt.Checked)
            self.topicList.addItem(item)
            self.newTopicEdit.clear()

    def deleteTopic(self):
        indices = []
        for i in range(self.topicList.count()):
            item = self.topicList.item(i)
            if item.checkState() != Qt.Checked:
                indices.append(i)
        for index in sorted(indices, reverse=True):
            self.topicList.takeItem(index)

    def updateRealmsTopics(self, realms_topics):
        self.realms_topics = realms_topics
        self.realmTable.setRowCount(0)
        for realm, topics in sorted(realms_topics.items()):
            row = self.realmTable.rowCount()
            self.realmTable.insertRow(row)
            itemRealm = QTableWidgetItem(realm)
            itemRealm.setFlags(itemRealm.flags() | Qt.ItemIsUserCheckable)
            itemRealm.setCheckState(Qt.Checked)
            self.realmTable.setItem(row, 0, itemRealm)
            url = ""
            self.realmTable.setItem(row, 1, QTableWidgetItem(url))
        self.updateTopicsFromRealms()

    def updateTopicsFromRealms(self):
        rows = self.realmTable.rowCount()
        for row in range(rows):
            item = self.realmTable.item(row, 0)
            if item.checkState() == Qt.Checked:
                realm = item.text()
                self.topicList.clear()
                if realm in self.realms_topics:
                    for t in self.realms_topics[realm]:
                        t_item = QListWidgetItem(t)
                        t_item.setCheckState(Qt.Checked)
                        self.topicList.addItem(t_item)
                else:
                    default_topic = QListWidgetItem("default")
                    default_topic.setCheckState(Qt.Checked)
                    self.topicList.addItem(default_topic)
                break

    def toggleContent(self, checked):
        self.contentWidget.setVisible(checked)
        if not checked:
            realms = self.getSelectedRealms()
            topics = self.getSelectedTopics()
            time_val = self.editorWidget.commonTimeEdit.text()
            self.setTitle(f"Mensaje #{self.msg_id} - {', '.join(topics)} - {time_val} - {', '.join(realms)}")
        else:
            self.setTitle(f"Mensaje #{self.msg_id}")

    def getSelectedRealms(self):
        realms = []
        rows = self.realmTable.rowCount()
        for row in range(rows):
            item = self.realmTable.item(row, 0)
            if item.checkState() == Qt.Checked:
                realms.append(item.text())
        return realms if realms else ["default"]

    def getSelectedTopics(self):
        topics = []
        for i in range(self.topicList.count()):
            item = self.topicList.item(i)
            if item.checkState() == Qt.Checked:
                topics.append(item.text())
        return topics if topics else ["default"]

    def getRouterURL(self):
        rows = self.realmTable.rowCount()
        for row in range(rows):
            url_item = self.realmTable.item(row, 1)
            if url_item and url_item.text().strip():
                return url_item.text().strip()
        return self.urlEdit.text().strip()

    def sendMessage(self):
        try:
            h, m, s = map(int, self.editorWidget.commonTimeEdit.text().strip().split(":"))
            delay = h * 3600 + m * 60 + s
        except:
            delay = 0
        topics = self.getSelectedTopics()
        realms = self.getSelectedRealms()
        try:
            data = json.loads(self.editorWidget.jsonPreview.toPlainText())
        except Exception as e:
            QMessageBox.critical(self, "Error", f"JSON inválido:\n{e}")
            return
        for realm in realms:
            router_url = self.getRouterURL()
            for topic in topics:
                from .pubGUI import send_message_now
                send_message_now(router_url, realm, topic, data, delay)
        publish_time = datetime.datetime.now() + datetime.timedelta(seconds=delay)
        publish_time_str = publish_time.strftime("%Y-%m-%d %H:%M:%S")
        sent_message = json.dumps(data, indent=2, ensure_ascii=False)
        if hasattr(self.parent(), "addPublisherLog"):
            self.parent().addPublisherLog(self.getSelectedRealms(), ", ".join(topics), publish_time_str, sent_message)

    def deleteSelf(self):
        self.parent().parent().removeMessage(self)

    def getConfig(self):
        return {
            "id": self.msg_id,
            "realms": self.getSelectedRealms(),
            "router_url": self.getRouterURL(),
            "topics": self.getSelectedTopics(),
            "time": self.editorWidget.commonTimeEdit.text().strip(),
            "mode": self.modeCombo.currentText() if hasattr(self, "modeCombo") else "On demand",
            "content": json.loads(self.editorWidget.jsonPreview.toPlainText())
        }
