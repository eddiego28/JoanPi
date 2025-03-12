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

# Clase MessageViewer para mostrar los mensajes recibidos en una tabla
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

# Clase SubscriberTab usando tablas con casillas de verificación para realms y tópicos
class SubscriberTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.realms_topics = {}  # Se cargará desde config/realm_topic_config.json
        self.initUI()
        self.loadGlobalRealmTopicConfig()

    def initUI(self):
        mainLayout = QHBoxLayout(self)
        # Panel de configuración (izquierda)
        configWidget = QWidget()
        configLayout = QVBoxLayout(configWidget)
        
        # Tabla de Realms (2 columnas: Realm y Router URL) con casillas de verificación
        realmsLabel = QLabel("Realms:")
        configLayout.addWidget(realmsLabel)
        self.realmTable = QTableWidget(0, 2)
        self.realmTable.setHorizontalHeaderLabels(["Realm", "Router URL"])
        self.realmTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.realmTable.setSelectionBehavior(QTableWidget.SelectRows)
        self.realmTable.setEditTriggers(QTableWidget.NoEditTriggers)
        # Al hacer clic, se actualiza la tabla de tópicos
        self.realmTable.cellClicked.connect(self.realmCellClicked)
        configLayout.addWidget(self.realmTable)
        
        # Botones para agregar y borrar realms
        realmBtnLayout = QHBoxLayout()
        self.newRealmEdit = QLineEdit()
        self.newRealmEdit.setPlaceholderText("Nuevo realm")
        realmBtnLayout.addWidget(self.newRealmEdit)
        self.addRealmBtn = QPushButton("Agregar")
        self.addRealmBtn.clicked.connect(self.addRealmRow)
        realmBtnLayout.addWidget(self.addRealmBtn)
        self.delRealmBtn = QPushButton("Borrar")
        self.delRealmBtn.clicked.connect(self.deleteRealmRow)
        realmBtnLayout.addWidget(self.delRealmBtn)
        configLayout.addLayout(realmBtnLayout)
        
        # Tabla de Topics (1 columna) con casillas de verificación
        topicsLabel = QLabel("Topics:")
        configLayout.addWidget(topicsLabel)
        self.topicTable = QTableWidget(0, 1)
        self.topicTable.setHorizontalHeaderLabels(["Topic"])
        self.topicTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.topicTable.setSelectionBehavior(QTableWidget.SelectRows)
        self.topicTable.setEditTriggers(QTableWidget.NoEditTriggers)
        configLayout.addWidget(self.topicTable)
        
        # Botones para agregar y borrar tópicos
        topicBtnLayout = QHBoxLayout()
        self.newTopicEdit = QLineEdit()
        self.newTopicEdit.setPlaceholderText("Nuevo tópico")
        topicBtnLayout.addWidget(self.newTopicEdit)
        self.addTopicBtn = QPushButton("Agregar")
        self.addTopicBtn.clicked.connect(self.addTopicRow)
        topicBtnLayout.addWidget(self.addTopicBtn)
        self.delTopicBtn = QPushButton("Borrar")
        self.delTopicBtn.clicked.connect(self.deleteTopicRow)
        topicBtnLayout.addWidget(self.delTopicBtn)
        configLayout.addLayout(topicBtnLayout)
        
        # Campo Router URL
        routerLayout = QHBoxLayout()
        routerLayout.addWidget(QLabel("Router URL:"))
        self.urlEdit = QLineEdit("ws://127.0.0.1:60001/ws")
        routerLayout.addWidget(self.urlEdit)
        configLayout.addLayout(routerLayout)
        
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
        
        # Panel de mensajes (derecha)
        self.viewer = MessageViewer(self)
        mainLayout.addWidget(self.viewer, 2)
        self.setLayout(mainLayout)

    def realmCellClicked(self, row, column):
        if self.realmTable.rowCount() == 0:
            return
        item = self.realmTable.item(row, 0)
        if item:
            realm = item.text()
            self.updateTopicsForRealm(realm)

    def updateTopicsForRealm(self, realm):
        self.topicTable.setRowCount(0)
        if realm in self.realms_topics:
            for t in self.realms_topics[realm]:
                r = self.topicTable.rowCount()
                self.topicTable.insertRow(r)
                t_item = QTableWidgetItem(t)
                t_item.setFlags(t_item.flags() | Qt.ItemIsUserCheckable)
                t_item.setCheckState(Qt.Checked)
                self.topicTable.setItem(r, 0, t_item)
        else:
            r = self.topicTable.rowCount()
            self.topicTable.insertRow(r)
            self.topicTable.setItem(r, 0, QTableWidgetItem("default"))

    def addRealmRow(self):
        new_realm = self.newRealmEdit.text().strip()
        if new_realm:
            row = self.realmTable.rowCount()
            self.realmTable.insertRow(row)
            item = QTableWidgetItem(new_realm)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.realmTable.setItem(row, 0, item)
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
            item = QTableWidgetItem(new_topic)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.topicTable.setItem(row, 0, item)
            self.newTopicEdit.clear()

    def deleteTopicRow(self):
        rows_to_delete = []
        for row in range(self.topicTable.rowCount()):
            item = self.topicTable.item(row, 0)
            if not item or item.text().strip() == "":
                rows_to_delete.append(row)
        for row in sorted(rows_to_delete, reverse=True):
            self.topicTable.removeRow(row)

    def loadGlobalRealmTopicConfig(self):
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "realm_topic_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.realms_topics = data.get("realms", {})
                self.realmCombo.clear()
                self.realmCombo.addItems(list(self.realms_topics.keys()))
                # Actualizamos la tabla de realms
                self.realmTable.setRowCount(0)
                for realm, topics in sorted(self.realms_topics.items()):
                    row = self.realmTable.rowCount()
                    self.realmTable.insertRow(row)
                    self.realmTable.setItem(row, 0, QTableWidgetItem(realm))
                    router = data.get("realm_configs", {}).get(realm, "")
                    self.realmTable.setItem(row, 1, QTableWidgetItem(router))
                # Actualizamos la tabla de tópicos según el primer realm
                if self.realmTable.rowCount() > 0:
                    self.realmCellClicked(0, 0)
                print("Configuración global de realms/topics cargada (suscriptor).")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error al cargar la configuración global:\n{e}")
        else:
            QMessageBox.warning(self, "Advertencia", "No se encontró el archivo realm_topic_config.json.")

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
                # Si se usa una tabla para tópicos, se debe actualizarla. Aquí, por simplicidad, usamos el QListWidget.
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
        # Recopilamos los tópicos de la tabla de tópicos (usando la tabla)
        topics = []
        for row in range(self.topicTable.rowCount()):
            item = self.topicTable.item(row, 0)
            if item and item.checkState() == Qt.Checked:
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
