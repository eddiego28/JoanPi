# subscriber/subGUI.py
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
        self.subMessages = []
        self.realms_topics = {}  # Se cargará desde el archivo global
        self.initUI()
    def initUI(self):
        mainLayout = QHBoxLayout(self)
        configWidget = QWidget()
        configLayout = QVBoxLayout(configWidget)

        # Grupo de Realms: Combobox y botones para agregar/borrar realms
        connLayout = QHBoxLayout()
        connLayout.addWidget(QLabel("Realm:"))
        self.realmCombo = QComboBox()
        self.realmCombo.addItems(["default"])  # Se actualizará al cargar la configuración global
        self.realmCombo.setMinimumWidth(200)
        connLayout.addWidget(self.realmCombo)
        self.newRealmEdit = QLineEdit()
        self.newRealmEdit.setPlaceholderText("Nuevo realm")
        connLayout.addWidget(self.newRealmEdit)
        self.addRealmButton = QPushButton("Agregar realm")
        self.addRealmButton.clicked.connect(self.addRealm)
        connLayout.addWidget(self.addRealmButton)
        configLayout.addLayout(connLayout)

        # Grupo de Topics: Lista con selección múltiple y botones para agregar/borrar topics
        topicsLayout = QHBoxLayout()
        topicsLayout.addWidget(QLabel("Topics:"))
        self.topicsList = QListWidget()
        self.topicsList.setSelectionMode(QAbstractItemView.MultiSelection)
        self.topicsList.addItem("default")
        topicsLayout.addWidget(self.topicsList)
        btnLayout = QVBoxLayout()
        self.loadTopicsButton = QPushButton("Cargar Topics desde archivo")
        self.loadTopicsButton.clicked.connect(self.loadTopics)
        btnLayout.addWidget(self.loadTopicsButton)
        self.newTopicEdit = QLineEdit()
        self.newTopicEdit.setPlaceholderText("Añadir nuevo tópico")
        btnLayout.addWidget(self.newTopicEdit)
        self.addTopicButton = QPushButton("Agregar")
        self.addTopicButton.clicked.connect(self.addTopic)
        btnLayout.addWidget(self.addTopicButton)
        topicsLayout.addLayout(btnLayout)
        configLayout.addLayout(topicsLayout)

        # Se omite el widget adicional de Router URL (ya se muestra junto al realm en el ComboBox si es necesario)
        # Botones de suscripción
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
        self.loadConfigButton = QPushButton("Cargar Configuración de Proyecto")
        self.loadConfigButton.clicked.connect(self.loadProjectConfig)
        configLayout.addWidget(self.loadConfigButton)
        configLayout.addStretch()

        mainLayout.addWidget(configWidget, 1)
        self.viewer = MessageViewer(self)
        mainLayout.addWidget(self.viewer, 2)
        self.setLayout(mainLayout)

    def addRealm(self):
        new_realm = self.newRealmEdit.text().strip()
        if new_realm and new_realm not in [self.realmCombo.itemText(i) for i in range(self.realmCombo.count())]:
            self.realmCombo.addItem(new_realm)
            self.newRealmEdit.clear()

    def loadTopics(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Seleccione JSON de Topics", "", "JSON Files (*.json);;All Files (*)")
        if not filepath:
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo cargar el archivo:\n{e}")
            return
        topics = data if isinstance(data, list) else data.get("topics", [])
        self.topicsList.clear()
        for topic in topics:
            self.topicsList.addItem(topic)

    def addTopic(self):
        new_topic = self.newTopicEdit.text().strip()
        if new_topic:
            self.topicsList.addItem(new_topic)
            self.newTopicEdit.clear()

    def loadProjectConfig(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Cargar Configuración de Proyecto", "", "JSON Files (*.json);;All Files (*)")
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
            self.topicsList.clear()
            for topic in topics:
                self.topicsList.addItem(topic)

    def addSubscriberLog(self, realm, topic, timestamp, details):
        self.viewer.add_message(realm, topic, timestamp, details)

    def startSubscription(self):
        from subscriber.subGUI import start_subscriber
        realm = self.realmCombo.currentText()
        selected_items = self.topicsList.selectedItems()
        if not selected_items:
            QMessageBox.critical(self, "Error", "Seleccione al menos un tópico.")
            return
        topics = [item.text() for item in selected_items]
        # Se toma el Router URL de la configuración global si fuera necesario (aquí se puede definir un valor fijo)
        url = ""  # En este ejemplo, se asume que el URL se configura en el archivo global y se usa en PublisherTab.
        def on_message_callback(topic, content):
            QMetaObject.invokeMethod(
                self,
                "onMessageArrivedMainThread",
                Qt.QueuedConnection,
                Q_ARG(str, topic),
                Q_ARG(dict, content)
            )
        start_subscriber(url, realm, topics, on_message_callback=on_message_callback)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.addSubscriberLog(realm, "Suscripción iniciada", timestamp, {"info": f"Suscriptor iniciado: realm={realm}, topics={topics}"})

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

    def getProjectConfigLocal(self):
        realms = [self.realmCombo.itemText(i) for i in range(self.realmCombo.count())]
        topics = []
        for i in range(self.topicsList.count()):
            topics.append(self.topicsList.item(i).text())
        return {"realms": realms, "topics": topics}

    def loadProjectFromConfig(self, sub_config):
        realms = sub_config.get("realms", [])
        topics = sub_config.get("topics", [])
        if realms:
            self.realmCombo.clear()
            self.realmCombo.addItems(realms)
        if topics:
            self.topicsList.clear()
            for topic in topics:
                self.topicsList.addItem(topic)
