import sys, os, json, datetime, logging, asyncio, threading
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QFileDialog
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

# En el suscriptor, usamos tablas para mostrar realms y topics de forma consistente
class SubscriberTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.realms_topics = {}  # Global: realm -> [topics]
        self.initUI()
        self.autoLoadRealmsTopics()
    def initUI(self):
        mainLayout = QHBoxLayout(self)
        configWidget = QWidget()
        configLayout = QVBoxLayout(configWidget)
        # Tabla de Realms
        realmsLayout = QVBoxLayout()
        realmsLabel = QLabel("Realms:")
        realmsLayout.addWidget(realmsLabel)
        self.realmTable = QTableWidget(0, 2)
        self.realmTable.setHorizontalHeaderLabels(["Realm", "Router URL"])
        self.realmTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        realmsLayout.addWidget(self.realmTable)
        btnRealmsLayout = QHBoxLayout()
        self.newRealmEdit = QLineEdit()
        self.newRealmEdit.setPlaceholderText("Nuevo realm")
        btnRealmsLayout.addWidget(self.newRealmEdit)
        self.addRealmBtn = QPushButton("Agregar")
        self.addRealmBtn.clicked.connect(self.addRealmRow)
        btnRealmsLayout.addWidget(self.addRealmBtn)
        self.delRealmBtn = QPushButton("Borrar")
        self.delRealmBtn.clicked.connect(self.deleteRealmRow)
        btnRealmsLayout.addWidget(self.delRealmBtn)
        realmsLayout.addLayout(btnRealmsLayout)
        configLayout.addLayout(realmsLayout)
        # Tabla de Topics (misma dimensión que Realms)
        topicsLayout = QVBoxLayout()
        topicsLabel = QLabel("Topics:")
        topicsLayout.addWidget(topicsLabel)
        self.topicTable = QTableWidget(0, 1)
        self.topicTable.setHorizontalHeaderLabels(["Topic"])
        self.topicTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        topicsLayout.addWidget(self.topicTable)
        btnTopicsLayout = QHBoxLayout()
        self.newTopicEdit = QLineEdit()
        self.newTopicEdit.setPlaceholderText("Nuevo topic")
        btnTopicsLayout.addWidget(self.newTopicEdit)
        self.addTopicBtn = QPushButton("Agregar")
        self.addTopicBtn.clicked.connect(self.addTopicRow)
        btnTopicsLayout.addWidget(self.addTopicBtn)
        self.delTopicBtn = QPushButton("Borrar")
        self.delTopicBtn.clicked.connect(self.deleteTopicRow)
        btnTopicsLayout.addWidget(self.delTopicBtn)
        topicsLayout.addLayout(btnTopicsLayout)
        configLayout.addLayout(topicsLayout)
        # Router URL: se coloca junto a la tabla de realms
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
        self.loadConfigButton = QPushButton("Cargar Realm/Topic")
        self.loadConfigButton.clicked.connect(self.loadProjectConfig)
        configLayout.addWidget(self.loadConfigButton)
        configLayout.addStretch()
        mainLayout.addWidget(configWidget, 1)
        # Área de mensajes recibidos
        self.viewer = SubscriberMessageViewer(self)
        mainLayout.addWidget(self.viewer, 2)
        self.setLayout(mainLayout)
    def addRealmRow(self):
        new_realm = self.newRealmEdit.text().strip()
        if new_realm:
            row = self.realmTable.rowCount()
            self.realmTable.insertRow(row)
            self.realmTable.setItem(row, 0, QTableWidgetItem(new_realm))
            self.realmTable.setItem(row, 1, QTableWidgetItem(""))
            self.newRealmEdit.clear()
    def deleteRealmRow(self):
        rows_to_delete = []
        for row in range(self.realmTable.rowCount()):
            item = self.realmTable.item(row, 0)
            if not item or item.text().strip() == "":
                rows_to_delete.append(row)
        for row in sorted(rows_to_delete, reverse=True):
            self.realmTable.removeRow(row)
    def addTopicRow(self):
        new_topic = self.newTopicEdit.text().strip()
        if new_topic:
            row = self.topicTable.rowCount()
            self.topicTable.insertRow(row)
            self.topicTable.setItem(row, 0, QTableWidgetItem(new_topic))
            self.newTopicEdit.clear()
    def deleteTopicRow(self):
        rows_to_delete = []
        for row in range(self.topicTable.rowCount()):
            item = self.topicTable.item(row, 0)
            if not item or item.text().strip() == "":
                rows_to_delete.append(row)
        for row in sorted(rows_to_delete, reverse=True):
            self.topicTable.removeRow(row)
    def autoLoadRealmsTopics(self):
        default_path = os.path.join(os.path.dirname(__file__), "..", "config", "realms_topics.json")
        if os.path.exists(default_path):
            try:
                with open(default_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.realms_topics = data.get("realms", {})
                self.realmTable.setRowCount(0)
                for realm, topics in sorted(self.realms_topics.items()):
                    row = self.realmTable.rowCount()
                    self.realmTable.insertRow(row)
                    self.realmTable.setItem(row, 0, QTableWidgetItem(realm))
                    self.realmTable.setItem(row, 1, QTableWidgetItem(""))
                self.updateTopicsFromRealms()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error al cargar Realms/Topics por defecto:\n{e}")
    def updateTopicsFromRealms(self):
        if self.realmTable.rowCount() > 0:
            # Usar el primer realm de la tabla
            item = self.realmTable.item(0, 0)
            realm = item.text() if item else "default"
            self.topicTable.setRowCount(0)
            if realm in self.realms_topics:
                for t in self.realms_topics[realm]:
                    row = self.topicTable.rowCount()
                    self.topicTable.insertRow(row)
                    self.topicTable.setItem(row, 0, QTableWidgetItem(t))
            else:
                row = self.topicTable.rowCount()
                self.topicTable.insertRow(row)
                self.topicTable.setItem(row, 0, QTableWidgetItem("default"))
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
            self.realmTable.setRowCount(0)
            for realm in realms:
                row = self.realmTable.rowCount()
                self.realmTable.insertRow(row)
                self.realmTable.setItem(row, 0, QTableWidgetItem(realm))
                self.realmTable.setItem(row, 1, QTableWidgetItem(""))
        if topics:
            self.topicTable.setRowCount(0)
            for t in topics:
                row = self.topicTable.rowCount()
                self.topicTable.insertRow(row)
                self.topicTable.setItem(row, 0, QTableWidgetItem(t))
    def addSubscriberLog(self, realm, topic, timestamp, details):
        self.viewer.add_message(realm, topic, timestamp, details)
    def startSubscription(self):
        from subscriber.subGUI import start_subscriber
        # Para suscribirse se usan los topics de la tabla
        realms = []
        for row in range(self.realmTable.rowCount()):
            item = self.realmTable.item(row, 0)
            if item and item.text().strip():
                realms.append(item.text())
        topics = []
        for row in range(self.topicTable.rowCount()):
            item = self.topicTable.item(row, 0)
            if item and item.text().strip():
                topics.append(item.text())
        if not topics:
            QMessageBox.critical(self, "Error", "Seleccione al menos un tópico.")
            return
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
        realm = "default"
        if self.realmTable.rowCount() > 0:
            item = self.realmTable.item(0, 0)
            realm = item.text() if item else "default"
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
        for row in range(self.realmTable.rowCount()):
            item = self.realmTable.item(row, 0)
            if item:
                realms.append(item.text())
        topics = []
        for row in range(self.topicTable.rowCount()):
            item = self.topicTable.item(row, 0)
            if item:
                topics.append(item.text())
        return {"realms": realms, "topics": topics}
    def loadProjectFromConfig(self, sub_config):
        realms = sub_config.get("realms", [])
        topics = sub_config.get("topics", [])
        if realms:
            self.realmTable.setRowCount(0)
            for realm in realms:
                row = self.realmTable.rowCount()
                self.realmTable.insertRow(row)
                self.realmTable.setItem(row, 0, QTableWidgetItem(realm))
                self.realmTable.setItem(row, 1, QTableWidgetItem(""))
        if topics:
            self.topicTable.setRowCount(0)
            for t in topics:
                row = self.topicTable.rowCount()
                self.topicTable.insertRow(row)
                self.topicTable.setItem(row, 0, QTableWidgetItem(t))
