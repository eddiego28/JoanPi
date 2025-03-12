import sys, os, json, datetime, logging, asyncio, threading
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QPushButton, QSplitter,
    QGroupBox, QFormLayout, QMessageBox, QLineEdit, QFileDialog, QComboBox, QDialog, QDialogButtonBox
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

def send_message_now(topic, message, delay=0):
    global global_session, global_loop
    if global_session is None or global_loop is None:
        print("No hay sesión activa. Inicia el publicador primero.")
        return
    async def _send():
        if delay > 0:
            await asyncio.sleep(delay)
        if isinstance(message, dict):
            global_session.publish(topic, **message)
        else:
            global_session.publish(topic, message)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message_json = json.dumps(message, indent=2, ensure_ascii=False)
        log_to_file(timestamp, topic, global_session.config.realm, message_json)
        logging.info(f"Publicado: {timestamp} | Topic: {topic} | Realm: {global_session.config.realm}")
        print("Mensaje enviado en", topic, ":", message)
    asyncio.run_coroutine_threadsafe(_send(), global_loop)

# Diálogo para agregar una configuración de realm (realm + router URL)
class RealmConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Agregar Configuración de Realm")
        self.setModal(True)
        layout = QFormLayout(self)
        self.realmEdit = QLineEdit()
        self.routerUrlEdit = QLineEdit()
        layout.addRow("Realm:", self.realmEdit)
        layout.addRow("Router URL:", self.routerUrlEdit)
        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        layout.addWidget(self.buttonBox)

    def getData(self):
        return self.realmEdit.text().strip(), self.routerUrlEdit.text().strip()

class PublisherMessageViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pubMessages = []
        self.initUI()
        
    def initUI(self):
        layout = QVBoxLayout(self)
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Hora", "Topic", "Realm"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemDoubleClicked.connect(self.showDetails)
        layout.addWidget(self.table)
        self.setLayout(layout)
        self.setFixedHeight(200)

    def add_message(self, realm, topic, timestamp, details):
        if isinstance(details, str):
            details = details.replace("\n", " ")
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(timestamp))
        self.table.setItem(row, 1, QTableWidgetItem(topic))
        self.table.setItem(row, 2, QTableWidgetItem(realm))
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
        self.realm_configs = {}   # Mapeo: realm -> router URL (global)
        self.initUI()
        self.autoLoadRealmsTopics()  # Carga automática desde config

    def initUI(self):
        layout = QVBoxLayout()
        # Top layout con botones para mensajes y proyecto
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

        # Sección para gestionar configuraciones de realms (realm y router URL)
        realmConfigGroup = QGroupBox("Configuración de Realms")
        rcLayout = QVBoxLayout()
        self.realmTable = QTableWidget(0, 2)
        self.realmTable.setHorizontalHeaderLabels(["Realm", "Router URL"])
        self.realmTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        rcLayout.addWidget(self.realmTable)
        rcButtonsLayout = QHBoxLayout()
        self.addRealmConfigButton = QPushButton("Agregar Configuración")
        self.addRealmConfigButton.clicked.connect(self.addRealmConfig)
        rcButtonsLayout.addWidget(self.addRealmConfigButton)
        self.delRealmConfigButton = QPushButton("Eliminar Configuración")
        self.delRealmConfigButton.clicked.connect(self.deleteRealmConfig)
        rcButtonsLayout.addWidget(self.delRealmConfigButton)
        rcLayout.addLayout(rcButtonsLayout)
        realmConfigGroup.setLayout(rcLayout)
        layout.addWidget(realmConfigGroup)

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

    def addRealmConfig(self):
        dlg = RealmConfigDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            realm, router_url = dlg.getData()
            if realm:
                row = self.realmTable.rowCount()
                self.realmTable.insertRow(row)
                self.realmTable.setItem(row, 0, QTableWidgetItem(realm))
                self.realmTable.setItem(row, 1, QTableWidgetItem(router_url))
                self.realm_configs[realm] = router_url
                # Actualizar realms en widgets
                self.updateRealmsInWidgets()

    def deleteRealmConfig(self):
        selected = self.realmTable.selectedItems()
        if selected:
            row = selected[0].row()
            realm_item = self.realmTable.item(row, 0)
            if realm_item:
                realm = realm_item.text()
                self.realmTable.removeRow(row)
                if realm in self.realm_configs:
                    del self.realm_configs[realm]
                self.updateRealmsInWidgets()

    def updateRealmsInWidgets(self):
        # Actualiza self.realms_topics basado en las claves de realm_configs
        for realm in self.realm_configs:
            if realm not in self.realms_topics:
                self.realms_topics[realm] = ["default"]
        for widget in self.msgWidgets:
            widget.updateRealmsTopics(self.realms_topics)

    def addMessage(self):
        from .pubEditor import PublisherEditorWidget
        widget = MessageConfigWidget(self.next_id, parent=self)
        if self.realms_topics:
            widget.updateRealmsTopics(self.realms_topics)
        # Si el realm seleccionado tiene un router configurado, se asigna
        selected_realm = widget.realmCombo.currentText()
        if selected_realm in self.realm_configs:
            widget.urlEdit.setText(self.realm_configs[selected_realm])
        self.msgLayout.addWidget(widget)
        self.msgWidgets.append(widget)
        self.next_id += 1

    def removeMessage(self, widget):
        if widget in self.msgWidgets:
            self.msgWidgets.remove(widget)
            widget.setParent(None)
            widget.deleteLater()

    def addPublisherLog(self, realm, topic, timestamp, details):
        self.viewer.add_message(realm, topic, timestamp, details)

    def startPublisher(self):
        for widget in self.msgWidgets:
            config = widget.getConfig()
            if config["realm"] in self.realm_configs:
                config["router_url"] = self.realm_configs[config["realm"]]
                widget.urlEdit.setText(config["router_url"])
            start_publisher(config["router_url"], config["realm"], config["topic"])
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.addPublisherLog(config["realm"], config["topic"], timestamp, f"Publicador iniciado: {config}")
            if widget.editorWidget.commonTimeEdit.text().strip() != "00:00:00":
                try:
                    h, m, s = map(int, widget.editorWidget.commonTimeEdit.text().strip().split(":"))
                    delay = h * 3600 + m * 60 + s
                except:
                    delay = 0
                QTimer.singleShot(delay * 1000, widget.sendMessage)

    def sendAllAsync(self):
        for widget in self.msgWidgets:
            config = widget.getConfig()
            send_message_now(config["topic"], config["content"], delay=0)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sent_message = json.dumps(config["content"], indent=2, ensure_ascii=False)
            self.addPublisherLog(config["realm"], config["topic"], timestamp, sent_message)

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
            widget.realmCombo.setCurrentText(scenario.get("realm", "default"))
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
                for widget in self.msgWidgets:
                    widget.updateRealmsTopics(self.realms_topics)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error al cargar Realms/Topics por defecto:\n{e}")

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
        # Configuración del realm
        self.realmCombo = QComboBox()
        self.realmCombo.addItems(["default"])
        self.realmCombo.setMinimumWidth(200)
        self.realmCombo.currentTextChanged.connect(self.onRealmChanged)
        self.newRealmEdit = QLineEdit()
        self.newRealmEdit.setPlaceholderText("Nuevo realm")
        self.addRealmButton = QPushButton("Agregar realm")
        self.addRealmButton.clicked.connect(self.addRealm)
        realmLayout = QHBoxLayout()
        realmLayout.addWidget(self.realmCombo)
        realmLayout.addWidget(self.newRealmEdit)
        realmLayout.addWidget(self.addRealmButton)
        formLayout.addRow("Realm:", realmLayout)
        self.urlEdit = QLineEdit("ws://127.0.0.1:60001")
        formLayout.addRow("Router URL:", self.urlEdit)
        # Configuración del topic
        topicLayout = QHBoxLayout()
        self.topicCombo = QComboBox()
        self.topicCombo.setEditable(True)
        self.topicCombo.addItem("default")
        topicLayout.addWidget(self.topicCombo)
        self.newTopicEdit = QLineEdit()
        self.newTopicEdit.setPlaceholderText("Nuevo topic")
        topicLayout.addWidget(self.newTopicEdit)
        self.addTopicButton = QPushButton("Agregar topic")
        self.addTopicButton.clicked.connect(self.addTopic)
        topicLayout.addWidget(self.addTopicButton)
        formLayout.addRow("Topic:", topicLayout)

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
        self.parent().parent().removeMessage(self)

    def addRealm(self):
        new_realm = self.newRealmEdit.text().strip()
        if new_realm and new_realm not in [self.realmCombo.itemText(i) for i in range(self.realmCombo.count())]:
            self.realmCombo.addItem(new_realm)
            self.newRealmEdit.clear()

    def addTopic(self):
        new_topic = self.newTopicEdit.text().strip()
        if new_topic and new_topic not in [self.topicCombo.itemText(i) for i in range(self.topicCombo.count())]:
            self.topicCombo.addItem(new_topic)
            self.newTopicEdit.clear()

    def onRealmChanged(self, new_realm):
        if self.realms_topics and new_realm in self.realms_topics:
            self.topicCombo.clear()
            self.topicCombo.addItems(self.realms_topics[new_realm])
        else:
            self.topicCombo.clear()
            self.topicCombo.addItem("default")

    def updateRealmsTopics(self, realms_topics):
        self.realms_topics = realms_topics
        current_realm = self.realmCombo.currentText()
        self.realmCombo.clear()
        self.realmCombo.addItems(sorted(realms_topics.keys()))
        if current_realm not in realms_topics:
            current_realm = sorted(realms_topics.keys())[0] if realms_topics else "default"
        self.realmCombo.setCurrentText(current_realm)
        self.onRealmChanged(current_realm)

    def toggleContent(self, checked):
        self.contentWidget.setVisible(checked)
        if not checked:
            topic = self.topicCombo.currentText().strip()
            time_val = self.editorWidget.commonTimeEdit.text()
            self.setTitle(f"Mensaje #{self.msg_id} - {topic} - {time_val}")
        else:
            self.setTitle(f"Mensaje #{self.msg_id}")

    def sendMessage(self):
        try:
            h, m, s = map(int, self.editorWidget.commonTimeEdit.text().strip().split(":"))
            delay = h * 3600 + m * 60 + s
        except:
            delay = 0
        if self.editorWidget.commonTimeEdit.text().strip() == "00:00:00":
            delay = 0
        topic = self.topicCombo.currentText().strip()
        try:
            data = json.loads(self.editorWidget.jsonPreview.toPlainText())
        except Exception as e:
            QMessageBox.critical(self, "Error", f"JSON inválido:\n{e}")
            return
        from .pubGUI import send_message_now
        send_message_now(topic, data, delay=delay)
        publish_time = datetime.datetime.now() + datetime.timedelta(seconds=delay)
        publish_time_str = publish_time.strftime("%Y-%m-%d %H:%M:%S")
        sent_message = json.dumps(data, indent=2, ensure_ascii=False)
        if hasattr(self.parent(), "addPublisherLog"):
            self.parent().addPublisherLog(self.realmCombo.currentText(), topic, publish_time_str, sent_message)

    def getConfig(self):
        return {
            "id": self.msg_id,
            "realm": self.realmCombo.currentText(),
            "router_url": self.urlEdit.text().strip(),
            "topic": self.topicCombo.currentText().strip(),
            "time": self.editorWidget.commonTimeEdit.text().strip(),
            "content": json.loads(self.editorWidget.jsonPreview.toPlainText())
        }
