import sys, os, json, datetime, logging, asyncio, threading
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QPushButton, QSplitter,
    QGroupBox, QFormLayout, QMessageBox, QLineEdit, QFileDialog, QComboBox, QCheckBox,
    QApplication, QMainWindow, QToolBar, QAction, QTabWidget, QDialog, QTreeWidget, QVBoxLayout as QVBox, QTreeWidgetItem
)
from PyQt5.QtCore import Qt, QTimer, QSize
from PyQt5.QtGui import QIcon
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
from common.utils import log_to_file  # <= si lo usas para log, mantenlo
from .pubEditor import PublisherEditorWidget

###############################################################################
# Realms and topics configuration
###############################################################################
REALMS_CONFIG = {}

def get_resource_path(relative_path):
    """Obtiene la ruta absoluta del recurso, compatible con PyInstaller."""
    if getattr(sys, 'frozen', False):
        # Estamos en .exe
        base_path = os.path.dirname(sys.executable)
    else:
        # Estamos en .py
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

def load_realm_topic_config():
    global REALMS_CONFIG
    try:
        # Ruta al archivo config/realm_topic_config_pub.json en el directorio de recursos
        config_path = get_resource_path(os.path.join("config", "realm_topic_config_pub.json"))
        
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        if isinstance(config.get("realms"), list):
            new_dict = {}
            for realm_info in config.get("realms", []):
                realm_name = realm_info.get("realm", "default")
                new_dict[realm_name] = {
                    "router_url": realm_info.get("router_url", "ws://127.0.0.1:60001"),
                    "topics": realm_info.get("topics", [])
                }
            REALMS_CONFIG = new_dict
        else:
            REALMS_CONFIG = config.get("realms", {})

        print("✅ Realms and topics configuration loaded from:", config_path)

    except Exception as e:
        print("❌ Error loading configuration:", e)
        REALMS_CONFIG = {
            "default": {"router_url": "ws://127.0.0.1:60001", "topics": ["MsgEP", "MsgCrEnt"]},
            "default2": {"router_url": "ws://127.0.0.1:60002", "topics": ["MsgInitCtr", "MsgAlerts"]}
        }
        print("⚠️ Using default configuration.")

# Cargar al iniciar
load_realm_topic_config()

###############################################################################
# Global dictionary for publisher sessions (one per realm)
###############################################################################
global_pub_sessions = {}  # key: realm, value: session object

###############################################################################
# JSONPublisher session
###############################################################################
class JSONPublisher(ApplicationSession):
    def __init__(self, config, topic, widget):
        super().__init__(config)
        self.topic = topic
        self.widget = widget  # Reference to the widget that starts this session

    async def onJoin(self, details):
        self.loop = asyncio.get_event_loop()
        self.widget.session = self
        self.widget.loop = self.loop
        global global_pub_sessions
        global_pub_sessions[self.config.realm] = self
        print(f"Connected (realm: {self.config.realm}, topic: {self.topic})")
        await asyncio.Future()

def start_publisher(url, realm, topic, widget):
    global global_pub_sessions
    # If a session for this realm already exists, reuse it
    if realm in global_pub_sessions:
        widget.session = global_pub_sessions[realm]
        widget.loop = widget.session.loop
        print(f"Reusing existing publisher session for realm '{realm}'.")
    else:
        def run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            runner = ApplicationRunner(url=url, realm=realm)
            def session_factory(config):
                session = JSONPublisher(config, topic, widget)
                return session
            runner.run(session_factory)
        threading.Thread(target=run, daemon=True).start()

def send_message_now(session, loop, topic, message, delay=0):
    if session is None or loop is None:
        print("No active session in this widget. Start the publisher first.")
        return

    async def _send():
        if delay > 0:
            await asyncio.sleep(delay)
        if isinstance(message, dict):
            session.publish(topic, **message)
        else:
            session.publish(topic, message)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message_json = json.dumps(message, indent=2, ensure_ascii=False)
        log_to_file(timestamp, topic, session.config.realm, message_json)
        logging.info(f"Published: {timestamp} | Topic: {topic} | Realm: {session.config.realm}")
        print("Message sent on", topic, ":", message)

    asyncio.run_coroutine_threadsafe(_send(), loop)

###############################################################################
# JsonTreeDialog: shows JSON in a tree format
###############################################################################
class JsonTreeDialog(QDialog):
    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("JSON detail - Tree View")
        self.resize(600, 400)
        layout = QVBox(self)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(1)
        self.tree.setHeaderLabels(["JSON"])
        self.tree.header().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.tree)
        self.setLayout(layout)
        self.buildTree(data, self.tree.invisibleRootItem())
        self.tree.expandAll()

    def buildTree(self, data, parent):
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    item = QTreeWidgetItem([f"{key}:"])
                    parent.addChild(item)
                    self.buildTree(value, item)
                else:
                    item = QTreeWidgetItem([f"{key}: {value}"])
                    parent.addChild(item)
        elif isinstance(data, list):
            for index, value in enumerate(data):
                if isinstance(value, (dict, list)):
                    item = QTreeWidgetItem([f"[{index}]:"])
                    parent.addChild(item)
                    self.buildTree(value, item)
                else:
                    item = QTreeWidgetItem([f"[{index}]: {value}"])
                    parent.addChild(item)
        else:
            item = QTreeWidgetItem([str(data)])
            parent.addChild(item)

###############################################################################
# PublisherMessageViewer: log viewer for publisher messages
###############################################################################
class PublisherMessageViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pubMessages = []
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Time", "Realm", "Topic"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemDoubleClicked.connect(self.showDetails)
        layout.addWidget(self.table)
        self.setLayout(layout)

    def add_message(self, realm, topic, timestamp, details):
        """
        details es el contenido crudo (string con JSON, o dict).
        Lo guardamos en la lista self.pubMessages para luego mostrarlo en la vista de árbol.
        """
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(timestamp))
        self.table.setItem(row, 1, QTableWidgetItem(realm))
        self.table.setItem(row, 2, QTableWidgetItem(topic))
        self.pubMessages.append(details)

    def showDetails(self, item):
        """
        Al hacer doble clic en una fila, parseamos el contenido a JSON y lo mostramos en un diálogo de árbol.
        """
        row = item.row()
        if row < len(self.pubMessages):
            raw_details = self.pubMessages[row]
            # Intentar parsear a JSON
            if isinstance(raw_details, str):
                try:
                    data = json.loads(raw_details)
                except Exception:
                    data = {"message": raw_details}
            elif isinstance(raw_details, dict):
                data = raw_details
            else:
                data = {"message": str(raw_details)}

            dlg = JsonTreeDialog(data, self)
            dlg.exec_()

###############################################################################
# MessageConfigWidget
###############################################################################
class MessageConfigWidget(QWidget):
    def __init__(self, msg_id, parent=None):
        super().__init__(parent)
        self.msg_id = msg_id
        self.message_sent = False
        self.session = None
        self.loop = None
        self.message_enabled = True
        self.is_minimized = False
        self.initUI()

        # Conectar la señal de onDemandRadio para deshabilitar el campo de tiempo
        self.editorWidget.onDemandRadio.toggled.connect(self.updateTimeField)

    def initUI(self):
        self.setStyleSheet("QWidget { font-family: 'Segoe UI'; font-size: 10pt; }")
        mainLayout = QVBoxLayout(self)

        # Header: Checkbox, minimize button, label
        self.headerWidget = QWidget()
        headerLayout = QHBoxLayout(self.headerWidget)

        self.enableCheckBox = QCheckBox()
        self.enableCheckBox.setChecked(True)
        self.enableCheckBox.stateChanged.connect(self.onEnableChanged)
        headerLayout.addWidget(self.enableCheckBox)

        self.minimizeButton = QPushButton("–")
        self.minimizeButton.setObjectName("minimizeButton")
        # Establecemos un tamaño basado en el sizeHint() aumentado
        size = self.enableCheckBox.sizeHint()
        self.minimizeButton.setFixedSize(size.width() + 1, size.height())

       
        self.minimizeButton.clicked.connect(self.toggleMinimize)
        headerLayout.addWidget(self.minimizeButton)

        self.headerLabel = QLabel(f"Message #{self.msg_id}")
        headerLayout.addWidget(self.headerLabel)
        headerLayout.addStretch()
        mainLayout.addWidget(self.headerWidget)

        # Content area
        self.contentWidget = QWidget()
        contentLayout = QVBoxLayout(self.contentWidget)

        # Group: Connection Settings
        self.connGroup = QGroupBox("Connection Settings")
        connLayout = QFormLayout()
        self.realmCombo = QComboBox()
        self.realmCombo.addItems(list(REALMS_CONFIG.keys()))
        self.realmCombo.setMinimumWidth(300)
        self.realmCombo.currentTextChanged.connect(self.updateTopics)

        # Layout para agregar realm
        realmAddLayout = QHBoxLayout()
        self.newRealmEdit = QLineEdit()
        self.newRealmEdit.setPlaceholderText("New realm")
        realmAddLayout.addWidget(self.newRealmEdit)
        realmAddLayout.addStretch()
        self.addRealmButton = QPushButton("Add")
        self.addRealmButton.setStyleSheet("""
            QPushButton {
                background-color: #007ACC;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #005A9E;
            }
            QPushButton:pressed {
                background-color: #004A80;
            }
        """)
        self.addRealmButton.clicked.connect(self.addRealm)
        realmAddLayout.addWidget(self.addRealmButton)

        connLayout.addRow("Realm:", self.realmCombo)
        connLayout.addRow("", realmAddLayout)

        self.urlEdit = QLineEdit("ws://127.0.0.1:60001")
        connLayout.addRow("Router URL:", self.urlEdit)

        self.topicCombo = QComboBox()
        self.topicCombo.setEditable(True)
        self.topicCombo.addItems(REALMS_CONFIG.get(self.realmCombo.currentText(), {}).get("topics", []))
        connLayout.addRow("Topic:", self.topicCombo)
        self.connGroup.setLayout(connLayout)
        contentLayout.addWidget(self.connGroup)

        # Group: Message Content
        self.contentGroup = QGroupBox("Message Content")
        contentGroupLayout = QVBoxLayout()

        from .pubEditor import PublisherEditorWidget
        self.editorWidget = PublisherEditorWidget(parent=self)
        contentGroupLayout.addWidget(self.editorWidget)
        self.contentGroup.setLayout(contentGroupLayout)
        contentLayout.addWidget(self.contentGroup)

        self.contentWidget.setLayout(contentLayout)
        mainLayout.addWidget(self.contentWidget)

        # Botón "Send Now"
        self.sendNowButton = QPushButton("Send Now")
        self.sendNowButton.setStyleSheet("""
            QPushButton {
                background-color: #007ACC;
                color: white;
                border: none;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #005A9E;
            }
            QPushButton:pressed {
                background-color: #004A80;
            }
        """)
        self.sendNowButton.clicked.connect(self.sendMessage)
        mainLayout.addWidget(self.sendNowButton)

        self.setLayout(mainLayout)

    def onEnableChanged(self, state):
        self.message_enabled = (state == Qt.Checked)
        self.contentWidget.setDisabled(not self.message_enabled)

    def toggleMinimize(self):
        self.is_minimized = not self.is_minimized
        self.contentWidget.setVisible(not self.is_minimized)
        if self.is_minimized:
            realm = self.realmCombo.currentText().strip()
            topic = self.topicCombo.currentText().strip()
            if self.editorWidget.programadoRadio.isChecked():
                mode = "Programmed"
            elif self.editorWidget.tiempoSistemaRadio.isChecked():
                mode = "System Time"
            else:
                mode = "On Demand"
            time_val = "" if mode == "On Demand" else self.editorWidget.commonTimeEdit.text().strip()
            self.headerLabel.setText(f"Message #{self.msg_id} - {realm} | {topic} | {mode} {time_val}")
            self.minimizeButton.setText("+")
        else:
            self.headerLabel.setText(f"Message #{self.msg_id}")
            self.minimizeButton.setText("–")

    def updateTimeField(self, checked):
        # Si está en modo On-Demand, ponemos el campo de tiempo "inactivo" (o readOnly)
        if self.editorWidget.onDemandRadio.isChecked():
            self.editorWidget.commonTimeEdit.setReadOnly(True)
            self.editorWidget.commonTimeEdit.setStyleSheet("QLineEdit { background-color: #007ACC; color: white; }")
        else:
            self.editorWidget.commonTimeEdit.setReadOnly(False)
            self.editorWidget.commonTimeEdit.setStyleSheet("")

    def addRealm(self):
        new_realm = self.newRealmEdit.text().strip()
        if new_realm and new_realm not in [self.realmCombo.itemText(i) for i in range(self.realmCombo.count())]:
            self.realmCombo.addItem(new_realm)
            REALMS_CONFIG[new_realm] = {"router_url": "ws://127.0.0.1:60001", "topics": []}
            self.newRealmEdit.clear()

    def updateTopics(self, realm):
        details = REALMS_CONFIG.get(realm, {})
        topics = details.get("topics", [])
        self.topicCombo.clear()
        self.topicCombo.addItems(topics)
        self.topicCombo.setEditable(True)
        router_url = details.get("router_url", "ws://127.0.0.1:60001")
        self.urlEdit.setText(router_url + "/ws")

    def stopSession(self):
        if self.session and self.loop:
            async def _leave():
                try:
                    await self.session.leave("Configuration changed")
                except Exception as e:
                    print("Error leaving session:", e)
            try:
                future = asyncio.run_coroutine_threadsafe(_leave(), self.loop)
                future.result(timeout=5)
            except Exception as e:
                print("Error closing session:", e)
        self.session = None
        self.loop = None

    def sendMessage(self):
        # Revisar modo
        if self.editorWidget.onDemandRadio.isChecked():
            delay = 0
        elif self.editorWidget.programadoRadio.isChecked():
            try:
                h, m, s = map(int, self.editorWidget.commonTimeEdit.text().strip().split(":"))
                delay = h * 3600 + m * 60 + s
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Invalid time for Programmed mode:\n{e}")
                return
        elif self.editorWidget.tiempoSistemaRadio.isChecked():
            try:
                h, m, s = map(int, self.editorWidget.commonTimeEdit.text().strip().split(":"))
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Invalid time for System Time mode:\n{e}")
                return
            now = datetime.datetime.now()
            scheduled_time = now.replace(hour=h, minute=m, second=s, microsecond=0)
            if scheduled_time < now:
                scheduled_time += datetime.timedelta(days=1)
            delay = (scheduled_time - now).total_seconds()
        else:
            delay = 0

        topic = self.topicCombo.currentText().strip()
        try:
            data = json.loads(self.editorWidget.jsonPreview.toPlainText())
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Invalid JSON:\n{e}")
            return

        if self.session is None or self.loop is None:
            QMessageBox.warning(self, "Error", "No active session for this message. Start the publisher.")
            return

        from .pubGUI import send_message_now
        send_message_now(self.session, self.loop, topic, data, delay=delay)
        self.message_sent = False
        publish_time = datetime.datetime.now() + datetime.timedelta(seconds=delay)
        publish_time_str = publish_time.strftime("%Y-%m-%d %H:%M:%S")
        sent_message = json.dumps(data, indent=2, ensure_ascii=False)

        # Registrar en el log
        publisherTab = self.parent()
        while publisherTab and not hasattr(publisherTab, "addPublisherLog"):
            publisherTab = publisherTab.parent()
        if publisherTab is not None:
            publisherTab.addPublisherLog(self.realmCombo.currentText(), topic, publish_time_str, sent_message)

    def getConfig(self):
        if self.editorWidget.programadoRadio.isChecked():
            mode = "programmed"
        elif self.editorWidget.tiempoSistemaRadio.isChecked():
            mode = "systemTime"
        else:
            mode = "onDemand"
        return {
            "id": self.msg_id,
            "realm": self.realmCombo.currentText(),
            "router_url": self.urlEdit.text().strip(),
            "topic": self.topicCombo.currentText().strip(),
            "content": json.loads(self.editorWidget.jsonPreview.toPlainText()),
            "mode": mode,
            "time": self.editorWidget.commonTimeEdit.text().strip()
        }

###############################################################################
# PublisherTab
###############################################################################
class PublisherTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.msgWidgets = []
        self.next_id = 1
        self.initUI()

    def initUI(self):
        splitter = QSplitter(Qt.Horizontal)

        # LEFT COLUMN
        leftPanel = QWidget()
        leftLayout = QVBoxLayout(leftPanel)

        # Botones: Start Publisher, Stop Publisher, Reset Log
        topButtonsLayout = QHBoxLayout()
        self.startPublisherButton = QPushButton("Start Publisher")
        self.startPublisherButton.setStyleSheet("""
            QPushButton {
                background-color: green;
                color: white;
                font-weight: bold;
            }
        """)
        self.startPublisherButton.setFixedHeight(40)
        topButtonsLayout.addWidget(self.startPublisherButton)

        self.stopPublisherButton = QPushButton("Stop Publisher")
        self.stopPublisherButton.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                font-weight: bold;
            }
        """)
        self.stopPublisherButton.setFixedHeight(40)
        topButtonsLayout.addWidget(self.stopPublisherButton)

        self.resetLogButton = QPushButton("Reset Log")
        self.resetLogButton.setStyleSheet("""
            QPushButton {
                background-color: #fd7e14;
                color: white;
                font-weight: bold;
            }
        """)
        self.resetLogButton.setFixedHeight(40)
        topButtonsLayout.addWidget(self.resetLogButton)
        topButtonsLayout.setSpacing(10)
        leftLayout.addLayout(topButtonsLayout)

        self.viewer = PublisherMessageViewer(self)
        leftLayout.addWidget(self.viewer)
        splitter.addWidget(leftPanel)

        # RIGHT COLUMN
        rightPanel = QWidget()
        rightLayout = QVBoxLayout(rightPanel)

        self.addMessageButton = QPushButton("Add Message")
        self.addMessageButton.setStyleSheet("""
            QPushButton {
                background-color: #003366;
                color: white;
                font-weight: bold;
            }
        """)
        self.addMessageButton.setFixedHeight(40)
        rightLayout.addWidget(self.addMessageButton)

        self.msgArea = QScrollArea()
        self.msgArea.setWidgetResizable(True)
        self.msgContainer = QWidget()
        self.msgLayout = QVBoxLayout(self.msgContainer)
        self.msgArea.setWidget(self.msgContainer)
        rightLayout.addWidget(self.msgArea)

        bottomLayout = QHBoxLayout()
        self.startScenarioButton = QPushButton("Start Scenario")
        self.startScenarioButton.setStyleSheet("""
            QPushButton {
                background-color: #005A9E;
                color: white;
                font-weight: bold;
            }
        """)
        self.startScenarioButton.setFixedHeight(40)
        self.sendInstantButton = QPushButton("Send Instant Message")
        self.sendInstantButton.setStyleSheet("""
            QPushButton {
                background-color: #17A2B8;
                color: white;
                font-weight: bold;
            }
        """)
        self.sendInstantButton.setFixedHeight(40)
        bottomLayout.addWidget(self.startScenarioButton)
        bottomLayout.addWidget(self.sendInstantButton)
        rightLayout.addLayout(bottomLayout)

        splitter.addWidget(rightPanel)
        splitter.setSizes([300, 600])

        mainLayout = QVBoxLayout(self)
        mainLayout.addWidget(splitter)
        self.setLayout(mainLayout)

        # Conectar señales
        self.addMessageButton.clicked.connect(self.addMessage)
        self.startPublisherButton.clicked.connect(self.confirmAndStartPublisher)
        self.stopPublisherButton.clicked.connect(self.stopAllPublishers)
        self.resetLogButton.clicked.connect(self.resetLog)
        self.startScenarioButton.clicked.connect(self.startScenario)
        self.sendInstantButton.clicked.connect(self.sendAllAsync)

    def confirmAndStartPublisher(self):
        global global_pub_sessions
        if global_pub_sessions:
            reply = QMessageBox.question(self, "Confirm",
                                         "There is an active publisher session. Do you want to stop it and start a new one?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.stopAllPublishers()
            else:
                return
        self.startPublisher()

    def addMessage(self):
        widget = MessageConfigWidget(self.next_id, parent=self)
        self.msgLayout.addWidget(widget)
        self.msgWidgets.append(widget)
        self.next_id += 1

    def addPublisherLog(self, realm, topic, timestamp, details):
        self.viewer.add_message(realm, topic, timestamp, details)

    def startPublisher(self):
        for widget in self.msgWidgets:
            if widget.session is not None:
                widget.stopSession()
            config = widget.getConfig()
            start_publisher(config["router_url"], config["realm"], config["topic"], widget)
            QTimer.singleShot(500, lambda w=widget, conf=config: self.logPublisherStarted(w, conf))

    def logPublisherStarted(self, widget, config):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.addPublisherLog(config["realm"], config["topic"], timestamp, "Publisher started")
        print("Publisher started:", config["realm"], config["topic"])

    def stopAllPublishers(self):
        global global_pub_sessions
        if not global_pub_sessions:
            QMessageBox.warning(self, "Warning", "No active publisher sessions to stop.")
            return
        for realm, session_obj in list(global_pub_sessions.items()):
            try:
                session_obj.leave("Stop publisher requested")
                print(f"Publisher session stopped for realm '{realm}'.")
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.addPublisherLog(realm, "Stopped", timestamp, "Publisher session stopped successfully.")
            except Exception as e:
                print("Error stopping publisher session:", e)
            del global_pub_sessions[realm]

    def resetLog(self):
        self.viewer.table.setRowCount(0)
        self.viewer.pubMessages = []

    def sendAllAsync(self):
        for widget in self.msgWidgets:
            config = widget.getConfig()
            if widget.session is None or widget.loop is None:
                print("No active session in message", widget.msg_id)
                continue
            send_message_now(widget.session, widget.loop, config["topic"], config["content"], delay=0)
            widget.message_sent = False
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sent_message = json.dumps(config["content"], indent=2, ensure_ascii=False)
            self.addPublisherLog(config["realm"], config["topic"], timestamp, sent_message)

    def startScenario(self):
        for widget in self.msgWidgets:
            config = widget.getConfig()
            if widget.editorWidget.onDemandRadio.isChecked():
                delay = 0
            elif widget.editorWidget.programadoRadio.isChecked():
                try:
                    h, m, s = map(int, widget.editorWidget.commonTimeEdit.text().strip().split(":"))
                    delay = h * 3600 + m * 60 + s
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Invalid time for Programmed mode:\n{e}")
                    continue
            elif widget.editorWidget.tiempoSistemaRadio.isChecked():
                try:
                    h, m, s = map(int, widget.editorWidget.commonTimeEdit.text().strip().split(":"))
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Invalid time for System Time mode:\n{e}")
                    continue
                now = datetime.datetime.now()
                scheduled_time = now.replace(hour=h, minute=m, second=s, microsecond=0)
                if scheduled_time < now:
                    scheduled_time += datetime.timedelta(days=1)
                delay = (scheduled_time - now).total_seconds()
            else:
                delay = 0

            if widget.session is None or widget.loop is None:
                print("No active session in message", widget.msg_id)
                continue
            QTimer.singleShot(int(delay * 1000), lambda w=widget, conf=config: self.sendScenarioMessage(w, conf))

    def sendScenarioMessage(self, widget, config):
        send_message_now(widget.session, widget.loop, config["topic"], config["content"], delay=0)
        widget.message_sent = False
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sent_message = json.dumps(config["content"], indent=2, ensure_ascii=False)
        self.addPublisherLog(config["realm"], config["topic"], timestamp, sent_message)
        print("Scenario: message sent on", config["topic"])

    def getProjectConfig(self):
        scenarios = [widget.getConfig() for widget in self.msgWidgets]
        return {"scenarios": scenarios}

    def loadProject(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Select Project File", "", "JSON Files (*.json);;All Files (*)")
        if not filepath:
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                project = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load project:\n{e}")
            return
        pub_config = project.get("publisher", {})
        self.loadProjectFromConfig(pub_config)
        QMessageBox.information(self, "Project", "Project loaded successfully.")

    def loadProjectFromConfig(self, pub_config):
        scenarios = pub_config.get("scenarios", [])
        self.msgWidgets = []
        self.next_id = 1
        while self.msgLayout.count():
            item = self.msgLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for scenario in scenarios:
            widget = MessageConfigWidget(self.next_id, parent=self)
            widget.realmCombo.setCurrentText(scenario.get("realm", "default"))
            widget.urlEdit.setText(scenario.get("router_url", "ws://127.0.0.1:60001"))
            widget.topicCombo.setCurrentText(scenario.get("topic", ""))
            widget.editorWidget.jsonPreview.setPlainText(
                json.dumps(scenario.get("content", {}), indent=2, ensure_ascii=False)
            )
            widget.editorWidget.commonTimeEdit.setText(scenario.get("time", "00:00:00"))
            mode = scenario.get("mode", "onDemand")
            if mode == "programmed":
                widget.editorWidget.programadoRadio.setChecked(True)
            elif mode == "systemTime":
                widget.editorWidget.tiempoSistemaRadio.setChecked(True)
            else:
                widget.editorWidget.onDemandRadio.setChecked(True)
            self.msgLayout.addWidget(widget)
            self.msgWidgets.append(widget)
            self.next_id += 1

    def saveProject(self):
        project_config = {"publisher": self.getProjectConfig()}
        filepath, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "JSON Files (*.json);;All Files (*)")
        if not filepath:
            return
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(project_config, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Project", "Project saved successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save project:\n{e}")