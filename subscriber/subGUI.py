import sys, os, json, datetime, logging, asyncio, threading
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QPushButton, 
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QFileDialog,
    QListWidget, QAbstractItemView, QComboBox
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

# Clase para visualizar los mensajes recibidos en una tabla
class MessageViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.messages = []
        self.initUI()
        
    def initUI(self):
        layout = QVBoxLayout(self)
        self.viewerLabel = QLabel("Mensajes recibidos:")
        layout.addWidget(self.viewerLabel)
        self.messageTable = QTableWidget()
        self.messageTable.setColumnCount(3)
        self.messageTable.setHorizontalHeaderLabels(["Hora", "Topic", "Realm"])
        self.messageTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.messageTable.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.messageTable.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.messageTable.itemDoubleClicked.connect(self.showDetails)
        layout.addWidget(self.messageTable)
        self.setLayout(layout)

    def add_message(self, realm, topic, timestamp, details):
        row = self.messageTable.rowCount()
        self.messageTable.insertRow(row)
        self.messageTable.setItem(row, 0, QTableWidgetItem(timestamp))
        self.messageTable.setItem(row, 1, QTableWidgetItem(topic))
        self.messageTable.setItem(row, 2, QTableWidgetItem(realm))
        self.messages.append(details)

    def showDetails(self, item):
        row = item.row()
        if row < len(self.messages):
            dlg = JsonDetailDialog(self.messages[row], self)
            dlg.exec_()

# Clase SubscriberTab: ahora se usan dos widgets: un QComboBox para el realm
# y un QListWidget (topicsList) para los tópicos. Además se incluye una tabla
# de visualización de mensajes (MessageViewer).
class SubscriberTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.realms_topics = {}  # Se cargará desde config/realm_topic_config.json
        self.initUI()
        self.loadGlobalRealmTopicConfig()

    def initUI(self):
        mainLayout = QHBoxLayout(self)
        
        # Panel de configuración
        configWidget = QWidget()
        configLayout = QVBoxLayout(configWidget)
        
        # Configuración de Realm (QComboBox)
        realmLayout = QHBoxLayout()
        realmLayout.addWidget(QLabel("Realm:"))
        self.realmCombo = QComboBox()
        self.realmCombo.addItems(["default"])
        self.realmCombo.setMinimumWidth(200)
        realmLayout.addWidget(self.realmCombo)
        self.newRealmEdit = QLineEdit()
        self.newRealmEdit.setPlaceholderText("Nuevo realm")
        realmLayout.addWidget(self.newRealmEdit)
        self.addRealmButton = QPushButton("Agregar realm")
        self.addRealmButton.clicked.connect(self.addRealm)
        realmLayout.addWidget(self.addRealmButton)
        configLayout.addLayout(realmLayout)
        
        # Configuración de Topics (QListWidget: topicsList)
        topicsLayout = QHBoxLayout()
        topicsLayout.addWidget(QLabel("Topics:"))
        self.topicsList = QListWidget()
        self.topicsList.setSelectionMode(QAbstractItemView.MultiSelection)
        self.topicsList.addItem("default")
        topicsLayout.addWidget(self.topicsList)
        btnLayout = QVBoxLayout()
        self.newTopicEdit = QLineEdit()
        self.newTopicEdit.setPlaceholderText("Nuevo tópico")
        btnLayout.addWidget(self.newTopicEdit)
        self.addTopicButton = QPushButton("Agregar")
        self.addTopicButton.clicked.connect(self.addTopic)
        btnLayout.addWidget(self.addTopicButton)
        self.delTopicButton = QPushButton("Borrar")
        self.delTopicButton.clicked.connect(self.deleteTopic)
        btnLayout.addWidget(self.delTopicButton)
        topicsLayout.addLayout(btnLayout)
        configLayout.addLayout(topicsLayout)
        
        # Router URL
        routerLayout = QHBoxLayout()
        routerLayout.addWidget(QLabel("Router URL:"))
        self.urlEdit = QLineEdit("ws://127.0.0.1:60001/ws")
        routerLayout.addWidget(self.urlEdit)
        configLayout.addLayout(routerLayout)
        
        # Botones de suscripción
        subBtnLayout = QHBoxLayout()
        self.startButton = QPushButton("Iniciar Suscripción")
        self.startButton.clicked.connect(self.startSubscription)
        subBtnLayout.addWidget(self.startButton)
        self.pauseButton = QPushButton("Pausar Suscripción")
        self.pauseButton.clicked.connect(self.pauseSubscription)
        subBtnLayout.addWidget(self.pauseButton)
        self.resetLogButton = QPushButton("Resetear Log")
        self.resetLogButton.clicked.connect(self.resetLog)
        subBtnLayout.addWidget(self.resetLogButton)
        configLayout.addLayout(subBtnLayout)
        
        self.loadConfigButton = QPushButton("Cargar Configuración de Proyecto")
        self.loadConfigButton.clicked.connect(self.loadProjectConfig)
        configLayout.addWidget(self.loadConfigButton)
        configLayout.addStretch()
        mainLayout.addWidget(configWidget, 1)
        
        # Panel de mensajes (MessageViewer)
        self.viewer = MessageViewer(self)
        mainLayout.addWidget(self.viewer, 2)
        self.setLayout(mainLayout)

    def loadGlobalRealmTopicConfig(self):
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "realm_topic_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.realms_topics = data.get("realms", {})
                self.realmCombo.clear()
                self.realmCombo.addItems(list(self.realms_topics.keys()))
                self.updateTopicsFromGlobal()
                print("Configuración global de realms/topics cargada (suscriptor).")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error al cargar la configuración global:\n{e}")
        else:
            QMessageBox.warning(self, "Advertencia", "No se encontró el archivo realm_topic_config.json.")

    def updateTopicsFromGlobal(self):
        current_realm = self.realmCombo.currentText()
        self.topicsList.clear()
        if current_realm in self.realms_topics:
            for t in self.realms_topics[current_realm]:
                self.topicsList.addItem(t)
        else:
            self.topicsList.addItem("default")

    def addRealm(self):
        new_realm = self.newRealmEdit.text().strip()
        if new_realm and new_realm not in [self.realmCombo.itemText(i) for i in range(self.realmCombo.count())]:
            self.realmCombo.addItem(new_realm)
            self.newRealmEdit.clear()

    def addTopic(self):
        new_topic = self.newTopicEdit.text().strip()
        if new_topic:
            self.topicsList.addItem(new_topic)
            self.newTopicEdit.clear()

    def deleteTopic(self):
        for item in self.topicsList.selectedItems():
            self.topicsList.takeItem(self.topicsList.row(item))

    def loadProjectConfig(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Cargar Configuración de Proyecto", "", "JSON Files (*.json);;All Files (*)")
        if not filepath:
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                config = json.load(f)
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
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo cargar la configuración:\n{e}")

    def addSubscriberLog(self, realm, topic, timestamp, details):
        self.viewer.add_message(realm, topic, timestamp, details)

    def startSubscription(self):
        from subscriber.subGUI import start_subscriber
        realm = self.realmCombo.currentText()
        topics = []
        # Recopilar los tópicos seleccionados de topicsList
        for i in range(self.topicsList.count()):
            item = self.topicsList.item(i)
            if item.isSelected():
                topics.append(item.text())
        if not topics:
            QMessageBox.critical(self, "Error", "Seleccione al menos un tópico.")
            return
        url = self.urlEdit.text().strip()
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
        self.viewer.messageTable.setRowCount(0)
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
