import sys, os, json, datetime, logging, asyncio, threading
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QPushButton, QSplitter,
    QGroupBox, QFormLayout, QMessageBox, QLineEdit, QFileDialog, QComboBox, QCheckBox,
    QApplication, QMainWindow, QToolBar, QAction, QTabWidget
)
from PyQt5.QtCore import Qt, QTimer, QSize
from PyQt5.QtGui import QIcon
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
from common.utils import log_to_file, JsonDetailDialog
from .pubEditor import PublisherEditorWidget

# --------------------------
# REALMS AND TOPICS CONFIGURATION
# --------------------------
# Expected configuration file: ../config/realm_topic_config_pub.json
# Example structure:
# {
#   "realms": [
#     {"realm": "default", "router_url": "ws://127.0.0.1:60001", "topics": ["MsgEP", "MsgCrEnt"]},
#     {"realm": "default2", "router_url": "ws://127.0.0.1:60002", "topics": ["MsgInitCtr", "MsgAlerts"]}
#   ]
# }
REALMS_CONFIG = {}

def load_realm_topic_config():
    global REALMS_CONFIG
    try:
        base_path = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(base_path, "..", "config", "realm_topic_config_pub.json")
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        for realm_info in config.get("realms", []):
            realm_name = realm_info.get("realm", "default")
            REALMS_CONFIG[realm_name] = {
                "router_url": realm_info.get("router_url", "ws://127.0.0.1:60001"),
                "topics": realm_info.get("topics", [])
            }
        print("Realms and topics configuration loaded from", config_path)
    except Exception as e:
        print("Error loading configuration:", e)
        REALMS_CONFIG = {
            "default": {"router_url": "ws://127.0.0.1:60001", "topics": ["MsgEP", "MsgCrEnt"]},
            "default2": {"router_url": "ws://127.0.0.1:60002", "topics": ["MsgInitCtr", "MsgAlerts"]}
        }
        print("Using default configuration.")

load_realm_topic_config()

# --------------------------
# CLASSES FOR PUBLICATION
# --------------------------
class JSONPublisher(ApplicationSession):
    def __init__(self, config, topic, widget):
        super().__init__(config)
        self.topic = topic
        self.widget = widget  # Reference to the widget that starts this session
    async def onJoin(self, details):
        self.widget.session = self
        self.widget.loop = asyncio.get_event_loop()
        print("Connected (realm:", self.config.realm, ", topic:", self.topic,")")
        await asyncio.Future()

def start_publisher(url, realm, topic, widget):
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

# --------------------------
# MESSAGE VIEWER (LOG)
# --------------------------
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
        if isinstance(details, str):
            details = details.replace("\n", " ")
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(timestamp))
        self.table.setItem(row, 1, QTableWidgetItem(realm))
        self.table.setItem(row, 2, QTableWidgetItem(topic))
        self.pubMessages.append(details)
    def showDetails(self, item):
        row = item.row()
        if row < len(self.pubMessages):
            dlg = JsonDetailDialog(self.pubMessages[row], self)
            dlg.exec_()

# --------------------------
# MESSAGE CONFIGURATION WIDGET
# --------------------------
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
        self.editorWidget.onDemandRadio.toggled.connect(self.updateTimeField)
    def initUI(self):
        mainLayout = QVBoxLayout(self)
        # Header: CheckBox, label, and minimize/expand button
        self.headerWidget = QWidget()
        headerLayout = QHBoxLayout(self.headerWidget)
        self.enableCheckBox = QCheckBox()
        self.enableCheckBox.setChecked(True)
        self.enableCheckBox.stateChanged.connect(self.onEnableChanged)
        self.headerLabel = QLabel(f"Message #{self.msg_id}")
        headerLayout.addWidget(self.enableCheckBox)
        headerLayout.addWidget(self.headerLabel)
        headerLayout.addStretch()
        self.minimizeButton = QPushButton("–")
        self.minimizeButton.setFixedSize(20, 20)
        self.minimizeButton.clicked.connect(self.toggleMinimize)
        headerLayout.addWidget(self.minimizeButton)
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
        self.newRealmEdit = QLineEdit()
        self.newRealmEdit.setPlaceholderText("New realm")
        self.addRealmButton = QPushButton("Add")
        self.addRealmButton.clicked.connect(self.addRealm)
        realmLayout = QHBoxLayout()
        realmLayout.addWidget(self.realmCombo)
        realmLayout.addWidget(self.newRealmEdit)
        realmLayout.addWidget(self.addRealmButton)
        connLayout.addRow("Realm:", realmLayout)
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
        if checked:
            self.editorWidget.commonTimeEdit.setDisabled(True)
        else:
            self.editorWidget.commonTimeEdit.setDisabled(False)
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
        self.message_sent = True
        publish_time = datetime.datetime.now() + datetime.timedelta(seconds=delay)
        publish_time_str = publish_time.strftime("%Y-%m-%d %H:%M:%S")
        sent_message = json.dumps(data, indent=2, ensure_ascii=False)
        if hasattr(self.parent(), "addPublisherLog"):
            self.parent().addPublisherLog(self.realmCombo.currentText(), topic, publish_time_str, sent_message)
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

# --------------------------
# PUBLISHER TAB CLASS
# --------------------------
class PublisherTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.msgWidgets = []
        self.next_id = 1
        self.initUI()

    def initUI(self):
        # Splitter to separate left (QTable) and right (configuration) columns
        splitter = QSplitter(Qt.Horizontal)

        # 1) LEFT COLUMN
        leftPanel = QWidget()
        leftLayout = QVBoxLayout(leftPanel)

        # -- "Start Publisher" alone at the top, green background --
        self.startPublisherButton = QPushButton("Start Publisher")
        self.startPublisherButton.setStyleSheet("""
            QPushButton {
                background-color: green;
                color: white;
                font-weight: bold;
            }
        """)
        self.startPublisherButton.setFixedHeight(40)

        # Center it horizontally if desired
        publisherLayout = QHBoxLayout()
        publisherLayout.addStretch()
        publisherLayout.addWidget(self.startPublisherButton)
        publisherLayout.addStretch()
        leftLayout.addLayout(publisherLayout)

        # -- QTable (log viewer) below --
        self.viewer = PublisherMessageViewer(self)
        leftLayout.addWidget(self.viewer)

        splitter.addWidget(leftPanel)

        # 2) RIGHT COLUMN
        rightPanel = QWidget()
        rightLayout = QVBoxLayout(rightPanel)

        # -- "Add Message" alone at the top, dark blue background --
        self.addMessageButton = QPushButton("Add Message")
        self.addMessageButton.setStyleSheet("""
            QPushButton {
                background-color: #003366; /* dark blue */
                color: white;
                font-weight: bold;
            }
        """)
        self.addMessageButton.setFixedHeight(40)

        addLayout = QHBoxLayout()
        addLayout.addStretch()
        addLayout.addWidget(self.addMessageButton)
        addLayout.addStretch()
        rightLayout.addLayout(addLayout)

        # -- Scroll area for message config in the middle --
        self.msgArea = QScrollArea()
        self.msgArea.setWidgetResizable(True)
        self.msgContainer = QWidget()
        self.msgLayout = QVBoxLayout(self.msgContainer)
        self.msgArea.setWidget(self.msgContainer)
        rightLayout.addWidget(self.msgArea)

        # -- A row at the bottom for "Start Scenario" + "Send Instant Message" side by side --
        bottomLayout = QHBoxLayout()

        self.startScenarioButton = QPushButton("Start Scenario")
        self.startScenarioButton.setStyleSheet("""
            QPushButton {
                background-color: #007BFF; /* optional: bootstrap-like blue */
                color: white;
                font-weight: bold;
            }
        """)
        self.startScenarioButton.setFixedHeight(40)

        self.sendInstantButton = QPushButton("Send Instant Message")
        self.sendInstantButton.setStyleSheet("""
            QPushButton {
                background-color: #17A2B8; /* optional: teal-ish color */
                color: white;
                font-weight: bold;
            }
        """)
        self.sendInstantButton.setFixedHeight(40)

        bottomLayout.addWidget(self.startScenarioButton)
        bottomLayout.addWidget(self.sendInstantButton)
        rightLayout.addLayout(bottomLayout)

        splitter.addWidget(rightPanel)

        # Adjust initial sizes: left ~ 300 px, right ~ 600 px
        splitter.setSizes([300, 600])

        # Final layout for the entire PublisherTab
        mainLayout = QVBoxLayout(self)
        mainLayout.addWidget(splitter)
        self.setLayout(mainLayout)

        # Connect signals
        self.addMessageButton.clicked.connect(self.addMessage)
        self.startPublisherButton.clicked.connect(self.startPublisher)
        self.startScenarioButton.clicked.connect(self.startScenario)
        self.sendInstantButton.clicked.connect(self.sendAllAsync)

    def addMessage(self):
        widget = MessageConfigWidget(self.next_id, parent=self)
        self.msgLayout.addWidget(widget)
        self.msgWidgets.append(widget)
        self.next_id += 1
    def addPublisherLog(self, realm, topic, timestamp, details):
        self.viewer.add_message(realm, topic, timestamp, details)
    def startPublisher(self):
        # For each message widget, close previous session (if any) and start a new one
        for widget in self.msgWidgets:
            if widget.session is not None:
                widget.stopSession()
            config = widget.getConfig()
            start_publisher(config["router_url"], config["realm"], config["topic"], widget)
            QTimer.singleShot(2000, lambda w=widget, conf=config: self.logPublisherStarted(w, conf))
    def logPublisherStarted(self, widget, config):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.addPublisherLog(config["realm"], config["topic"], timestamp, "Publisher started")
        print("Publisher started:", config["realm"], config["topic"])
    def sendAllAsync(self):
        # Send all messages from each widget
        for widget in self.msgWidgets:
            if not widget.message_sent:
                config = widget.getConfig()
                if widget.session is None or widget.loop is None:
                    print("No active session in message", widget.msg_id)
                    continue
                send_message_now(widget.session, widget.loop, config["topic"], config["content"], delay=0)
                widget.message_sent = True
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                sent_message = json.dumps(config["content"], indent=2, ensure_ascii=False)
                self.addPublisherLog(config["realm"], config["topic"], timestamp, sent_message)
    def startScenario(self):
        # Send messages according to their order and programmed delays
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
        widget.message_sent = True
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
            widget.urlEdit.setText(scenario.get("router_url", "ws://127.0.0.1:60001/ws"))
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


