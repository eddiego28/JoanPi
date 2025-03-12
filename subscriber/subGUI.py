import sys, os, json, datetime, logging, asyncio, threading
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox,
    QListWidget, QAbstractItemView, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog
)
from PyQt5.QtCore import Qt, pyqtSlot, QMetaObject, Q_ARG
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
from common.utils import log_to_file, JsonDetailDialog

global_session_sub = None
global_loop_sub = None

class MultiTopicSubscriber(ApplicationSession):
    def __init__(self, config, topics, on_message_callback):
        super().__init__(config)
        self.topics = topics
        self.on_message_callback = on_message_callback

    async def onJoin(self, details):
        print("Conexión establecida en el subscriptor (realm:", self.config.realm, ")")
        def make_callback(t):
            return lambda *args, **kwargs: self.on_event(t, *args, **kwargs)
        for topic in self.topics:
            self.subscribe(make_callback(topic), topic)

    def on_event(self, topic, *args, **kwargs):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message_data = {"args": args, "kwargs": kwargs}
        message_json = json.dumps(message_data, indent=2, ensure_ascii=False)
        log_to_file(timestamp, topic, self.config.realm, message_json)
        logging.info(f"Recibido: {timestamp} | Topic: {topic} | Realm: {self.config.realm}")
        if self.on_message_callback:
            self.on_message_callback(topic, message_data)

def start_subscriber(url, realm, topics, on_message_callback):
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        runner = ApplicationRunner(url=url, realm=realm)
        runner.run(lambda config: MultiTopicSubscriber(config, topics, on_message_callback))
    threading.Thread(target=run, daemon=True).start()

class MessageViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.messages = []
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
    def add_message(self, realm, topic, timestamp, details):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(timestamp))
        self.table.setItem(row, 1, QTableWidgetItem(topic))
        self.table.setItem(row, 2, QTableWidgetItem(realm))
        self.messages.append(details)
    def showDetails(self, item):
        row = item.row()
        if row < len(self.messages):
            dlg = JsonDetailDialog(self.messages[row], self)
            dlg.exec_()

class SubscriberTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.realms_topics = {}  # Mapeo de realms a topics
        self.initUI()
        self.autoLoadRealmsTopics()  # Carga automática del fichero por defecto

    def initUI(self):
        mainLayout = QHBoxLayout(self)
        configWidget = QWidget()
        configLayout = QVBoxLayout(configWidget)

        connLayout = QHBoxLayout()
        connLayout.addWidget(QLabel("Realm:"))
        self.realmCombo = QComboBox()
        self.realmCombo.addItems(["default"])
        self.realmCombo.setMinimumWidth(200)
        self.realmCombo.currentTextChanged.connect(self.onRealmChanged)
        self.newRealmEdit = QLineEdit()
        self.newRealmEdit.setPlaceholderText("Nuevo realm")
        self.newRealmEdit.setMinimumWidth(300)  # Mayor ancho para textos largos
        self.addRealmButton = QPushButton("Agregar realm")
        self.addRealmButton.clicked.connect(self.addRealm)
        realmLayout = QHBoxLayout()
        realmLayout.addWidget(self.realmCombo)
        realmLayout.addWidget(self.newRealmEdit)
        realmLayout.addWidget(self.addRealmButton)
        connLayout.addLayout(realmLayout)
        connLayout.addWidget(QLabel("Router URL:"))
        self.urlEdit = QLineEdit("ws://127.0.0.1:60001")
        connLayout.addWidget(self.urlEdit)
        configLayout.addLayout(connLayout)

        # Desplegable editable para Topics
        topicsLayout = QHBoxLayout()
        topicsLayout.addWidget(QLabel("Topics:"))
        self.topicsCombo = QComboBox()
        self.topicsCombo.setEditable(True)
        self.topicsCombo.addItem("default")
        topicsLayout.addWidget(self.topicsCombo)
        btnLayout = QVBoxLayout()
        self.loadTopicsButton = QPushButton("Cargar Topics desde archivo")
        self.loadTopicsButton.clicked.connect(self.loadTopics)
        btnLayout.addWidget(self.loadTopicsButton)
        self.newTopicEdit = QLineEdit()
        self.newTopicEdit.setPlaceholderText("Añadir nuevo tópico...")
        btnLayout.addWidget(self.newTopicEdit)
        self.addTopicButton = QPushButton("Agregar")
        self.addTopicButton.clicked.connect(self.addTopic)
        btnLayout.addWidget(self.addTopicButton)
        topicsLayout.addLayout(btnLayout)
        configLayout.addLayout(topicsLayout)

        btnSubLayout = QHBoxLayout()
        self.startButton = QPushButton("Iniciar Suscripción")
        self.startButton.clicked.connect(self.startSubscription)
        btnSubLayout.addWidget(self.startButton)
        self.pauseButton = QPushButton("Pausar Suscripción")
        self.pauseButton.clicked.connect(self.pauseSubscription)
        btnSubLayout.addWidget(self.pauseButton)
        self.resetLogButton = QPushButton("Resetear Log")
        self.resetLogButton.clicked.connect(self.resetLog)
        btnSubLayout.addWidget(self.resetLogButton)
        configLayout.addLayout(btnSubLayout)
        # Botón para cargar configuración de realms/topics para el suscriptor
        self.loadConfigButton = QPushButton("Cargar Realm/Topic del subscriptor")
        self.loadConfigButton.clicked.connect(self.loadProjectConfig)
        configLayout.addWidget(self.loadConfigButton)
        configLayout.addStretch()

        mainLayout.addWidget(configWidget, 1)
        self.viewer = MessageViewer(self)
        mainLayout.addWidget(self.viewer, 2)
        self.setLayout(mainLayout)

    def onRealmChanged(self, new_realm):
        if self.realms_topics and new_realm in self.realms_topics:
            self.topicsCombo.clear()
            self.topicsCombo.addItems(self.realms_topics[new_realm])
        else:
            self.topicsCombo.clear()
            self.topicsCombo.addItem("default")

    def addRealm(self):
        new_realm = self.newRealmEdit.text().strip()
        if new_realm and new_realm not in [self.realmCombo.itemText(i) for i in range(self.realmCombo.count())]:
            self.realmCombo.addItem(new_realm)
            self.newRealmEdit.clear()

    def loadTopics(self):
        from PyQt5.QtWidgets import QFileDialog, QMessageBox
        filepath, _ = QFileDialog.getOpenFileName(self, "Seleccione JSON de Topics", "", "JSON Files (*.json);;All Files (*)")
        if not filepath:
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            topics = data if isinstance(data, list) else data.get("topics", [])
            self.topicsCombo.clear()
            for topic in topics:
                self.topicsCombo.addItem(topic)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo cargar el archivo:\n{e}")

    def addTopic(self):
        new_topic = self.newTopicEdit.text().strip()
        if new_topic:
            self.topicsCombo.addItem(new_topic)
            self.newTopicEdit.clear()

    def autoLoadRealmsTopics(self):
        default_path = os.path.join(os.path.dirname(__file__), "..", "config", "realms_topics.json")
        if os.path.exists(default_path):
            try:
                with open(default_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.realms_topics = data.get("realms", {})
                self.realmCombo.clear()
                self.realmCombo.addItems(sorted(self.realms_topics.keys()))
                current_realm = self.realmCombo.currentText()
                self.topicsCombo.clear()
                if current_realm in self.realms_topics:
                    self.topicsCombo.addItems(self.realms_topics[current_realm])
                else:
                    self.topicsCombo.addItem("default")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error al cargar Realms/Topics por defecto:\n{e}")

    def loadProjectConfig(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Seleccione Configuración de Proyecto", "", "JSON Files (*.json);;All Files (*)")
        if not filepath:
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo cargar la configuración:\n{e}")
            return
        subscriber_config = config.get("subscriber", {})
        realms = subscriber_config.get("realms", [])
        topics = subscriber_config.get("topics", [])
        if realms:
            self.realmCombo.clear()
            self.realmCombo.addItems(realms)
        if topics:
            self.topicsCombo.clear()
            for topic in topics:
                self.topicsCombo.addItem(topic)

    def addSubscriberLog(self, realm, topic, timestamp, details):
        self.viewer.add_message(realm, topic, timestamp, details)

    def startSubscription(self):
        from subscriber.subGUI import start_subscriber
        realm = self.realmCombo.currentText()
        url = self.urlEdit.text().strip()
        topic = self.topicsCombo.currentText().strip()
        if not topic:
            QMessageBox.critical(self, "Error", "Seleccione al menos un tópico.")
            return

        def on_message_callback(topic, content):
            QMetaObject.invokeMethod(
                self,
                "onMessageArrivedMainThread",
                Qt.QueuedConnection,
                Q_ARG(str, topic),
                Q_ARG(dict, content)
            )
        start_subscriber(url, realm, [topic], on_message_callback=on_message_callback)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.addSubscriberLog(realm, "Suscripción iniciada", timestamp, {"info": f"Suscriptor iniciado: realm={realm}, topic={topic}"})

    @pyqtSlot(str, dict)
    def onMessageArrivedMainThread(self, topic, content):
        realm = self.realmCombo.currentText()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.addSubscriberLog(realm, topic, timestamp, content)

    def pauseSubscription(self):
        global global_session_sub, global_loop_sub
        if global_session_sub is not None:
            try:
                global_session_sub.leave()
                print("Suscripción pausada.")
            except Exception as e:
                print("Error al pausar la suscripción:", e)
            global_session_sub = None
            global_loop_sub = None
        else:
            QMessageBox.information(self, "Información", "No hay una suscripción activa.")

    def resetLog(self):
        self.viewer.table.setRowCount(0)
        self.viewer.messages = []

    def getProjectConfig(self):
        pub_config = self.parent().publisherTab.getProjectConfig()
        sub_config = self.getProjectConfigLocal()
        return {"publisher": pub_config, "subscriber": sub_config}

    def getProjectConfigLocal(self):
        realms = [self.realmCombo.itemText(i) for i in range(self.realmCombo.count())]
        topics = []
        for i in range(self.topicsCombo.count()):
            topics.append(self.topicsCombo.itemText(i))
        return {"realms": realms, "topics": topics}

    def loadProjectFromConfig(self, sub_config):
        realms = sub_config.get("realms", [])
        topics = sub_config.get("topics", [])
        if realms:
            self.realmCombo.clear()
            self.realmCombo.addItems(realms)
        if topics:
            self.topicsCombo.clear()
            for topic in topics:
                self.topicsCombo.addItem(topic)
