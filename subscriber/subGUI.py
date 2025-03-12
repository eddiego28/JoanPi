import sys, os, json, datetime, logging, asyncio, threading
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QFileDialog
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

# Clase para visualizar los mensajes recibidos
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
        self.messageTable.setSelectionBehavior(QTableWidget.SelectRows)
        self.messageTable.setEditTriggers(QTableWidget.NoEditTriggers)
        # Al hacer doble clic se muestra el detalle del mensaje
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

# Clase SubscriberTab que contiene dos tablas:
#  - Una tabla para los realms (con columnas "Realm" y "Router URL")
#  - Otra tabla para los topics (actualizada según el realm seleccionado)
# Además se incluyen botones para agregar/borrar realms y topics, y se mantiene la funcionalidad de suscripción.
class SubscriberTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.realms_topics = {}  # Se cargará desde config/realm_topic_config.json
        self.initUI()
        self.loadGlobalRealmTopicConfig()

    def initUI(self):
        mainLayout = QHBoxLayout(self)

        # Panel de configuración (a la izquierda)
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

        # Tabla de Topics
        topicsLayout = QVBoxLayout()
        topicsLabel = QLabel("Topics:")
        topicsLayout.addWidget(topicsLabel)
        self.topicTable = QTableWidget(0, 1)
        self.topicTable.setHorizontalHeaderLabels(["Topic"])
        self.topicTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        topicsLayout.addWidget(self.topicTable)
        btnTopicsLayout = QHBoxLayout()
        self.newTopicEdit = QLineEdit()
        self.newTopicEdit.setPlaceholderText("Nuevo tópico")
        btnTopicsLayout.addWidget(self.newTopicEdit)
        self.addTopicBtn = QPushButton("Agregar")
        self.addTopicBtn.clicked.connect(self.addTopicRow)
        btnTopicsLayout.addWidget(self.addTopicBtn)
        self.delTopicBtn = QPushButton("Borrar")
        self.delTopicBtn.clicked.connect(self.deleteTopicRow)
        btnTopicsLayout.addWidget(self.delTopicBtn)
        topicsLayout.addLayout(btnTopicsLayout)
        configLayout.addLayout(topicsLayout)

        # Cuando se haga clic en un realm, se actualizan los topics de ese realm
        self.realmTable.cellClicked.connect(self.updateTopicsFromSelectedRealm)

        # (Se omite un widget extra de Router URL ya que se muestra en la tabla de realms)
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

        # Panel de visualización de mensajes
        self.viewer = MessageViewer(self)
        mainLayout.addWidget(self.viewer, 2)
        self.setLayout(mainLayout)

    def loadGlobalRealmTopicConfig(self):
        # Carga el archivo global de configuración de realms y topics
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "realm_topic_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.realms_topics = data.get("realms", {})
                # Actualizamos la tabla de realms
                self.realmTable.setRowCount(0)
                for realm, topics in sorted(self.realms_topics.items()):
                    row = self.realmTable.rowCount()
                    self.realmTable.insertRow(row)
                    self.realmTable.setItem(row, 0, QTableWidgetItem(realm))
                    # Si existe Router URL en la configuración global para este realm, se puede mostrar
                    router = data.get("realm_configs", {}).get(realm, "")
                    self.realmTable.setItem(row, 1, QTableWidgetItem(router))
                # Actualizamos los topics según el primer realm seleccionado (o "default")
                self.updateTopicsFromSelectedRealm(0, 0)
                print("Configuración global de realms/topics cargada (suscriptor).")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error al cargar la configuración global:\n{e}")
        else:
            QMessageBox.warning(self, "Advertencia", "No se encontró el archivo realm_topic_config.json.")

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

    def updateTopicsFromSelectedRealm(self, row, column):
        # Cuando se hace clic en un realm, actualiza la tabla de topics con los topics de ese realm
        if self.realmTable.rowCount() == 0:
            return
        item = self.realmTable.item(row, 0)
        realm = item.text() if item else "default"
        self.topicTable.setRowCount(0)
        if realm in self.realms_topics:
            for t in self.realms_topics[realm]:
                r = self.topicTable.rowCount()
                self.topicTable.insertRow(r)
                self.topicTable.setItem(r, 0, QTableWidgetItem(t))
        else:
            r = self.topicTable.rowCount()
            self.topicTable.insertRow(r)
            self.topicTable.setItem(r, 0, QTableWidgetItem("default"))

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
        selected_items = self.topicsList.selectedItems()
        if not selected_items:
            QMessageBox.critical(self, "Error", "Seleccione al menos un tópico.")
            return
        topics = [item.text() for item in selected_items]
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
