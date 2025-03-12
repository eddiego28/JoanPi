import sys, os, json, datetime, logging, asyncio, threading
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QPushButton, QListWidget,
    QListWidgetItem, QMessageBox, QFileDialog
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
        self.viewerLabel = QLabel("Mensajes recibidos:")
        layout.addWidget(self.viewerLabel)
        self.messageList = QListWidget()
        layout.addWidget(self.messageList)
        self.setLayout(layout)
    def add_message(self, realm, topic, timestamp, details):
        text = f"{timestamp} | {topic} | {realm}"
        self.messageList.addItem(text)
        self.messages.append(details)

class SubscriberTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.realms_topics = {}  # Global: realm -> [topics]
        self.initUI()
        self.autoLoadRealmsTopics()  # Carga automática desde config

    def initUI(self):
        mainLayout = QHBoxLayout(self)
        configWidget = QWidget()
        configLayout = QVBoxLayout(configWidget)

        # Grupo Realms
        realmLayout = QHBoxLayout()
        realmLabel = QLabel("Realms:")
        realmLayout.addWidget(realmLabel)
        self.realmList = QListWidget()
        self.realmList.setSelectionMode(QListWidget.MultiSelection)
        default_item = QListWidgetItem("default")
        default_item.setCheckState(Qt.Checked)
        self.realmList.addItem(default_item)
        realmLayout.addWidget(self.realmList)
        self.newRealmEdit = QLineEdit()
        self.newRealmEdit.setPlaceholderText("Nuevo realm")
        self.newRealmEdit.setMinimumWidth(300)
        realmLayout.addWidget(self.newRealmEdit)
        self.addRealmButton = QPushButton("Agregar")
        self.addRealmButton.clicked.connect(self.addRealm)
        realmLayout.addWidget(self.addRealmButton)
        self.deleteRealmButton = QPushButton("Borrar")
        self.deleteRealmButton.clicked.connect(self.deleteRealm)
        realmLayout.addWidget(self.deleteRealmButton)
        configLayout.addLayout(realmLayout)

        # Grupo Topics
        topicLayout = QHBoxLayout()
        topicLabel = QLabel("Topics:")
        topicLayout.addWidget(topicLabel)
        self.topicsList = QListWidget()
        self.topicsList.setSelectionMode(QListWidget.MultiSelection)
        default_topic = QListWidgetItem("default")
        default_topic.setCheckState(Qt.Checked)
        self.topicsList.addItem(default_topic)
        topicLayout.addWidget(self.topicsList)
        self.newTopicEdit = QLineEdit()
        self.newTopicEdit.setPlaceholderText("Nuevo tópico")
        topicLayout.addWidget(self.newTopicEdit)
        self.addTopicButton = QPushButton("Agregar")
        self.addTopicButton.clicked.connect(self.addTopic)
        topicLayout.addWidget(self.addTopicButton)
        self.deleteTopicButton = QPushButton("Borrar")
        self.deleteTopicButton.clicked.connect(self.deleteTopic)
        topicLayout.addWidget(self.deleteTopicButton)
        configLayout.addLayout(topicLayout)

        # Router URL al lado de Realms
        routerLayout = QHBoxLayout()
        routerLayout.addWidget(QLabel("Router URL:"))
        self.urlEdit = QLineEdit("ws://127.0.0.1:60001")
        routerLayout.addWidget(self.urlEdit)
        configLayout.addLayout(routerLayout)

        # Botones de suscripción
        btnLayout = QHBoxLayout()
        self.startButton = QPushButton("Iniciar Suscripción")
        self.startButton.clicked.connect(self.startSubscription)
        btnLayout.addWidget(self.startButton)
        self.pauseButton = QPushButton("Pausar Suscripción")
        self.pauseButton.clicked.connect(self.pauseSubscription)
        btnLayout.addWidget(self.pauseButton)
        self.resetLogButton = QPushButton("Resetear Log")
        self.resetLogButton.clicked.connect(self.resetLog)
        btnLayout.addWidget(self.resetLogButton)
        configLayout.addLayout(btnLayout)
        # Botón para cargar configuración global
        self.loadConfigButton = QPushButton("Cargar Realm/Topic")
        self.loadConfigButton.clicked.connect(self.loadProjectConfig)
        configLayout.addWidget(self.loadConfigButton)
        configLayout.addStretch()

        mainLayout.addWidget(configWidget, 1)
        self.viewer = MessageViewer(self)
        mainLayout.addWidget(self.viewer, 2)
        self.setLayout(mainLayout)

    def addRealm(self):
        new_realm = self.newRealmEdit.text().strip()
        if new_realm:
            item = QListWidgetItem(new_realm)
            item.setCheckState(Qt.Checked)
            self.realmList.addItem(item)
            self.newRealmEdit.clear()

    def deleteRealm(self):
        indices = []
        for i in range(self.realmList.count()):
            item = self.realmList.item(i)
            if item.checkState() != Qt.Checked:
                indices.append(i)
        for index in sorted(indices, reverse=True):
            self.realmList.takeItem(index)

    def addTopic(self):
        new_topic = self.newTopicEdit.text().strip()
        if new_topic:
            item = QListWidgetItem(new_topic)
            item.setCheckState(Qt.Checked)
            self.topicsList.addItem(item)
            self.newTopicEdit.clear()

    def deleteTopic(self):
        indices = []
        for i in range(self.topicsList.count()):
            item = self.topicsList.item(i)
            if item.checkState() != Qt.Checked:
                indices.append(i)
        for index in sorted(indices, reverse=True):
            self.topicsList.takeItem(index)

    def autoLoadRealmsTopics(self):
        default_path = os.path.join(os.path.dirname(__file__), "..", "config", "realms_topics.json")
        if os.path.exists(default_path):
            try:
                with open(default_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.realms_topics = data.get("realms", {})
                self.realmList.clear()
                for realm in sorted(self.realms_topics.keys()):
                    item = QListWidgetItem(realm)
                    item.setCheckState(Qt.Checked)
                    self.realmList.addItem(item)
                self.updateTopicsFromRealms()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error al cargar Realms/Topics por defecto:\n{e}")

    def updateTopicsFromRealms(self):
        if self.realmList.count() > 0:
            for i in range(self.realmList.count()):
                item = self.realmList.item(i)
                if item.checkState() == Qt.Checked:
                    realm = item.text()
                    self.topicsList.clear()
                    if realm in self.realms_topics:
                        for t in self.realms_topics[realm]:
                            t_item = QListWidgetItem(t)
                            t_item.setCheckState(Qt.Checked)
                            self.topicsList.addItem(t_item)
                    else:
                        default_topic = QListWidgetItem("default")
                        default_topic.setCheckState(Qt.Checked)
                        self.topicsList.addItem(default_topic)
                    break

    def loadProjectConfig(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Cargar Configuración", "", "JSON Files (*.json);;All Files (*)")
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
            self.realmList.clear()
            for realm in realms:
                item = QListWidgetItem(realm)
                item.setCheckState(Qt.Checked)
                self.realmList.addItem(item)
        if topics:
            self.topicsList.clear()
            for t in topics:
                item = QListWidgetItem(t)
                item.setCheckState(Qt.Checked)
                self.topicsList.addItem(item)

    def addSubscriberLog(self, realm, topic, timestamp, details):
        self.viewer.add_message(realm, topic, timestamp, details)

    def startSubscription(self):
        from subscriber.subGUI import start_subscriber
        # Obtener realms seleccionados
        realms = []
        for i in range(self.realmList.count()):
            item = self.realmList.item(i)
            if item.checkState() == Qt.Checked:
                realms.append(item.text())
        # Obtener topics seleccionados
        topics = []
        for i in range(self.topicsList.count()):
            item = self.topicsList.item(i)
            if item.checkState() == Qt.Checked:
                topics.append(item.text())
        if not topics:
            QMessageBox.critical(self, "Error", "Seleccione al menos un tópico.")
            return
        # Para este ejemplo, usamos el primer realm seleccionado para suscribirse
        realm = realms[0] if realms else "default"
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
        realm = None
        for i in range(self.realmList.count()):
            item = self.realmList.item(i)
            if item.checkState() == Qt.Checked:
                realm = item.text()
                break
        if not realm:
            realm = "default"
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
        self.viewer.messageList.clear()
        self.viewer.messages = []

    def getProjectConfigLocal(self):
        realms = []
        for i in range(self.realmList.count()):
            item = self.realmList.item(i)
            realms.append(item.text())
        topics = []
        for i in range(self.topicsList.count()):
            item = self.topicsList.item(i)
            topics.append(item.text())
        return {"realms": realms, "topics": topics}

    def loadProjectFromConfig(self, sub_config):
        realms = sub_config.get("realms", [])
        topics = sub_config.get("topics", [])
        if realms:
            self.realmList.clear()
            for realm in realms:
                item = QListWidgetItem(realm)
                item.setCheckState(Qt.Checked)
                self.realmList.addItem(item)
        if topics:
            self.topicsList.clear()
            for t in topics:
                item = QListWidgetItem(t)
                item.setCheckState(Qt.Checked)
                self.topicsList.addItem(item)
