import sys, os, json, datetime, logging, asyncio, threading
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QPushButton, QSplitter,
    QGroupBox, QFormLayout, QMessageBox, QLineEdit, QFileDialog, QComboBox, QCheckBox
)
from PyQt5.QtCore import Qt, QTimer, QSize
from PyQt5.QtGui import QIcon, QColor
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
from common.utils import log_to_file, JsonDetailDialog
from .pubEditor import PublisherEditorWidget

# Utility para asegurar que un directorio exista
def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

# --------------------------
# REALMS AND TOPICS CONFIGURATION
# --------------------------
REALMS_CONFIG = {}

def load_realm_topic_config():
    global REALMS_CONFIG
    try:
        base_path = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(base_path, "..", "config", "realm_topic_config_pub.json")
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
# GLOBAL DICTIONARY FOR PUBLISHER SESSIONS (one per realm)
# --------------------------
global_pub_sessions = {}  # key: realm, value: session object

# --------------------------
# JSONPublisher: sesión WAMP para publicación
# --------------------------
class JSONPublisher(ApplicationSession):
    def __init__(self, config, topic, widget):
        super().__init__(config)
        self.topic = topic
        self.widget = widget

    async def onJoin(self, details):
        self.loop = asyncio.get_event_loop()
        self.widget.session = self
        self.widget.loop = self.loop
        global global_pub_sessions
        global_pub_sessions[self.config.realm] = self
        print(f"Connected (realm: {self.config.realm}, topic: {self.topic})")
        await asyncio.Future()  # stay alive

def start_publisher(url, realm, topic, widget):
    global global_pub_sessions
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
                return JSONPublisher(config, topic, widget)
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
# JsonDetailTabsDialog: muestra JSON en raw y árbol
# --------------------------
class JsonDetailTabsDialog(QDialog):
    def __init__(self, data, parent=None):
        super().__init__(parent)
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                pass
        self.setWindowTitle("JSON Details")
        self.resize(600, 400)
        layout = QVBoxLayout(self)
        tab_widget = QTabWidget(self)

        raw_tab = QWidget()
        raw_layout = QVBoxLayout(raw_tab)
        raw_text = QTextEdit()
        raw_text.setReadOnly(True)
        raw_text.setPlainText(json.dumps(data, indent=2, ensure_ascii=False))
        raw_layout.addWidget(raw_text)
        tab_widget.addTab(raw_tab, "Raw JSON")

        tree_tab = QWidget()
        tree_layout = QVBoxLayout(tree_tab)
        tree = QTreeWidget()
        tree.setColumnCount(1)
        tree.header().hide()
        self.buildTree(data, tree.invisibleRootItem())
        tree.expandAll()
        tree_layout.addWidget(tree)
        tab_widget.addTab(tree_tab, "Tree View")

        layout.addWidget(tab_widget)
        self.setLayout(layout)

    def buildTree(self, data, parent):
        if isinstance(data, dict):
            for key, value in data.items():
                item = QTreeWidgetItem([f"{key}:"])
                parent.addChild(item)
                if isinstance(value, (dict, list)):
                    self.buildTree(value, item)
                else:
                    value_item = QTreeWidgetItem([str(value)])
                    item.addChild(value_item)
        elif isinstance(data, list):
            for index, value in enumerate(data):
                item = QTreeWidgetItem([f"[{index}]:"])
                parent.addChild(item)
                if isinstance(value, (dict, list)):
                    self.buildTree(value, item)
                else:
                    value_item = QTreeWidgetItem([str(value)])
                    item.addChild(value_item)
        else:
            item = QTreeWidgetItem([str(data)])
            parent.addChild(item)

# --------------------------
# PublisherMessageViewer: visor de logs
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
    def add_message(self, realm, topic, timestamp, details, error=False):
        if isinstance(details, str):
            details = details.replace("\n", " ")
        row = self.table.rowCount()
        self.table.insertRow(row)
        time_item = QTableWidgetItem(timestamp)
        realm_item = QTableWidgetItem(realm)
        topic_item = QTableWidgetItem(topic)
        if error:
            time_item.setForeground(QColor("red"))
            realm_item.setForeground(QColor("red"))
            topic_item.setForeground(QColor("red"))
        self.table.setItem(row, 0, time_item)
        self.table.setItem(row, 1, realm_item)
        self.table.setItem(row, 2, topic_item)
        self.pubMessages.append(details)
    def showDetails(self, item):
        row = item.row()
        if row < len(self.pubMessages):
            data = self.pubMessages[row]
            dlg = JsonDetailTabsDialog(data)
            dlg.setWindowModality(Qt.WindowModal)
            dlg.show()
            self.openDialogs = getattr(self, "openDialogs", [])
            self.openDialogs.append(dlg)
            dlg.finished.connect(lambda result, dlg=dlg: self.openDialogs.remove(dlg))

# --------------------------
# MessageConfigWidget: configuración de cada mensaje
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
        self.setStyleSheet("QWidget { font-family: 'Segoe UI'; font-size: 10pt; }")
        mainLayout = QVBoxLayout(self)
        # Header
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
        self.deleteButton = QPushButton("Delete")
        self.deleteButton.setFixedSize(50, 20)
        self.deleteButton.clicked.connect(self.deleteSelf)
        headerLayout.addWidget(self.deleteButton)
        mainLayout.addWidget(self.headerWidget)

        # Content: Connection + Message
        self.contentWidget = QWidget()
        contentLayout = QVBoxLayout(self.contentWidget)
        # Connection Settings
        self.connGroup = QGroupBox("Connection Settings")
        connLayout = QFormLayout()
        self.realmCombo = QComboBox()
        self.realmCombo.addItems(list(REALMS_CONFIG.keys()))
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

        # Message Content
        self.contentGroup = QGroupBox("Message Content")
        contentGroupLayout = QVBoxLayout()
        self.editorWidget = PublisherEditorWidget(parent=self)
        contentGroupLayout.addWidget(self.editorWidget)
        self.contentGroup.setLayout(contentGroupLayout)
        contentLayout.addWidget(self.contentGroup)
        self.contentWidget.setLayout(contentLayout)
        mainLayout.addWidget(self.contentWidget)

        # Send Now button
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
        self.urlEdit.setText(router_url)

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

        try:
            data = json.loads(self.editorWidget.jsonPreview.toPlainText())
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Invalid JSON:\n{e}")
            return

        if self.session is None or self.loop is None:
            QMessageBox.warning(self, "Error", "No active session for this message. Start the publisher.")
            return

        send_message_now(self.session, self.loop, self.topicCombo.currentText().strip(), data, delay=delay)
        publish_time = datetime.datetime.now() + datetime.timedelta(seconds=delay)
        publish_time_str = publish_time.strftime("%Y-%m-%d %H:%M:%S")
        sent_message = json.dumps(data, indent=2, ensure_ascii=False)
        self.parent().addPublisherLog(self.realmCombo.currentText(), self.topicCombo.currentText(), publish_time_str, sent_message)

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

    def deleteSelf(self):
        reply = QMessageBox.question(self, "Confirm Delete", f"Delete Message #{self.msg_id}?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            parent = self.parentWidget()
            while parent and not hasattr(parent, "removeMessageWidget"):
                parent = parent.parentWidget()
            if parent:
                parent.removeMessageWidget(self)

# --------------------------
# PublisherTab: pestaña principal
# --------------------------
class PublisherTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.msgWidgets = []
        self.next_id = 1
        self.initUI()

    def initUI(self):
        splitter = QSplitter(Qt.Horizontal)

        # LEFT: controls y log
        leftPanel = QWidget()
        leftLayout = QVBoxLayout(leftPanel)
        topButtonsLayout = QHBoxLayout()
        self.startPublisherButton = QPushButton("Start Publisher")
        self.startPublisherButton.setStyleSheet("background-color: green; color: white; font-weight: bold;")
        self.startPublisherButton.setFixedHeight(40)
        topButtonsLayout.addWidget(self.startPublisherButton)
        self.stopPublisherButton = QPushButton("Stop Publisher")
        self.stopPublisherButton.setStyleSheet("background-color: #dc3545; color: white; font-weight: bold;")
        self.stopPublisherButton.setFixedHeight(40)
        topButtonsLayout.addWidget(self.stopPublisherButton)
        topButtonsLayout.setSpacing(10)
        leftLayout.addLayout(topButtonsLayout)
        self.viewer = PublisherMessageViewer(self)
        leftLayout.addWidget(self.viewer)
        splitter.addWidget(leftPanel)

        # RIGHT: mensajes
        rightPanel = QWidget()
        rightLayout = QVBoxLayout(rightPanel)
        self.addMessageButton = QPushButton("Add Message")
        self.addMessageButton.setStyleSheet("background-color: #003366; color: white; font-weight: bold;")
        self.addMessageButton.setFixedHeight(40)
        rightLayout.addWidget(self.addMessageButton)
        self.msgArea = QScrollArea()
        self.msgArea.setWidgetResizable(True)
        self.msgContainer = QWidget()
        self.msgLayout = QVBoxLayout()
        self.msgContainer.setLayout(self.msgLayout)
        self.msgArea.setWidget(self.msgContainer)
        rightLayout.addWidget(self.msgArea)
        bottomLayout = QHBoxLayout()
        self.startScenarioButton = QPushButton("Start Scenario")
        self.startScenarioButton.setStyleSheet("background-color: #005A9E; color: white; font-weight: bold;")
        self.startScenarioButton.setFixedHeight(40)
        self.sendInstantButton = QPushButton("Send Instant Message")
        self.sendInstantButton.setStyleSheet("background-color: #17A2B8; color: white; font-weight: bold;")
        self.sendInstantButton.setFixedHeight(40)
        bottomLayout.addWidget(self.startScenarioButton)
        bottomLayout.addWidget(self.sendInstantButton)
        rightLayout.addLayout(bottomLayout)
        splitter.addWidget(rightPanel)
        splitter.setSizes([300,600])
        mainLayout = QVBoxLayout(self)
        mainLayout.addWidget(splitter)
        self.setLayout(mainLayout)

        # conexiones
        self.addMessageButton.clicked.connect(self.addMessage)
        self.startPublisherButton.clicked.connect(self.confirmAndStartPublisher)
        self.stopPublisherButton.clicked.connect(self.stopAllPublishers)
        self.startScenarioButton.clicked.connect(self.startScenario)
        self.sendInstantButton.clicked.connect(self.sendAllAsync)

    def removeMessageWidget(self, widget):
        if widget in self.msgWidgets:
            self.msgWidgets.remove(widget)
            self.msgLayout.removeWidget(widget)
            widget.deleteLater()

    def addMessage(self):
        widget = MessageConfigWidget(self.next_id, parent=self)
        self.msgLayout.addWidget(widget)
        self.msgWidgets.append(widget)
        self.next_id += 1

    def addPublisherLog(self, realm, topic, timestamp, details, error=False):
        self.viewer.add_message(realm, topic, timestamp, details, error)

    def confirmAndStartPublisher(self):
        global global_pub_sessions
        if global_pub_sessions:
            reply = QMessageBox.question(self, "Confirm",
                                         "There is an active publisher session. Stop it and start new?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.stopAllPublishers()
            else:
                return
        self.startPublisher()

    def startPublisher(self):
        for widget in self.msgWidgets:
            if widget.session:
                widget.stopSession()
            config = widget.getConfig()
            start_publisher(config["router_url"], config["realm"], config["topic"], widget)
            QTimer.singleShot(500, lambda w=widget, c=config: self.logPublisherStarted(w,c))

    def logPublisherStarted(self, widget, config):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not widget.session:
            self.addPublisherLog(config["realm"], config["topic"], timestamp, "Failed to connect publisher", True)
        else:
            self.addPublisherLog(config["realm"], config["topic"], timestamp, "Publisher started")

    def stopAllPublishers(self):
        global global_pub_sessions
        if not global_pub_sessions:
            QMessageBox.warning(self, "Warning", "No active publisher sessions.")
            return
        for realm, session in list(global_pub_sessions.items()):
            try:
                session.leave("Stop publisher requested")
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.addPublisherLog(realm, "Stopped", timestamp, "Publisher session stopped successfully.")
            except Exception as e:
                print("Error stopping publisher session:", e)
            del global_pub_sessions[realm]

    def sendAllAsync(self):
        for widget in self.msgWidgets:
            config = widget.getConfig()
            if not widget.session or not widget.loop:
                continue
            send_message_now(widget.session, widget.loop, config["topic"], config["content"], delay=0)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.addPublisherLog(config["realm"], config["topic"], timestamp, json.dumps(config["content"], indent=2, ensure_ascii=False))

    def startScenario(self):
        for widget in self.msgWidgets:
            config = widget.getConfig()
            if widget.editorWidget.onDemandRadio.isChecked():
                delay = 0
            elif widget.editorWidget.programadoRadio.isChecked():
                try:
                    h, m, s = map(int, widget.editorWidget.commonTimeEdit.text().split(":"))
                    delay = h*3600 + m*60 + s
                except:
                    continue
            elif widget.editorWidget.tiempoSistemaRadio.isChecked():
                try:
                    h, m, s = map(int, widget.editorWidget.commonTimeEdit.text().split(":"))
                except:
                    continue
                now = datetime.datetime.now()
                sched = now.replace(hour=h, minute=m, second=s)
                if sched < now: sched += datetime.timedelta(days=1)
                delay = (sched - now).total_seconds()
            else:
                delay = 0
            if widget.session and widget.loop:
                QTimer.singleShot(int(delay*1000), lambda w=widget, c=config: self.sendScenarioMessage(w,c))

    def sendScenarioMessage(self, widget, config):
        send_message_now(widget.session, widget.loop, config["topic"], config["content"], delay=0)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.addPublisherLog(config["realm"], config["topic"], timestamp, json.dumps(config["content"], indent=2, ensure_ascii=False))

    def getProjectConfig(self):
        scenarios = [w.getConfig() for w in self.msgWidgets]
        return {"scenarios": scenarios}

    def loadProject(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Select Project File", "", "JSON Files (*.json)")
        if not filepath: return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                project = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load project:\n{e}")
            return
        self.loadProjectFromConfig(project.get("publisher", {}))
        QMessageBox.information(self, "Project", "Project loaded successfully.")

    def loadProjectFromConfig(self, pub_config):
        scenarios = pub_config.get("scenarios", [])
        # Reset
        for i in reversed(range(self.msgLayout.count())):
            w = self.msgLayout.itemAt(i).widget()
            if w: w.deleteLater()
        self.msgWidgets.clear()
        self.next_id = 1
        for sc in scenarios:
            w = MessageConfigWidget(self.next_id, parent=self)
            w.realmCombo.setCurrentText(sc.get("realm",""))
            w.urlEdit.setText(sc.get("router_url",""))
            w.topicCombo.setCurrentText(sc.get("topic",""))
            w.editorWidget.jsonPreview.setPlainText(json.dumps(sc.get("content",{}), indent=2, ensure_ascii=False))
            w.editorWidget.commonTimeEdit.setText(sc.get("time","00:00:00"))
            mode = sc.get("mode","onDemand")
            if mode=="programmed": w.editorWidget.programadoRadio.setChecked(True)
            elif mode=="systemTime": w.editorWidget.tiempoSistemaRadio.setChecked(True)
            else: w.editorWidget.onDemandRadio.setChecked(True)
            self.msgLayout.addWidget(w)
            self.msgWidgets.append(w)
            self.next_id += 1

    def saveProject(self):
        project_config = {"publisher": self.getProjectConfig()}
        filepath, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "JSON Files (*.json)")
        if not filepath: return
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(project_config, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Project", "Project saved successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save project:\n{e}")
