import sys, os, json, datetime, logging, asyncio, threading
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QPushButton, QSplitter,
    QGroupBox, QFormLayout, QMessageBox, QLineEdit, QFileDialog, QComboBox,
    QTableWidgetItem
)
from PyQt5.QtCore import Qt, QTimer
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
from common.utils import log_to_file, JsonDetailDialog
from .pubEditor import PublisherEditorWidget

global_session = None
global_loop = None

# Componente WAMP para el publicador
class JSONPublisher(ApplicationSession):
    def __init__(self, config, topic):
        super().__init__(config)
        self.topic = topic
    async def onJoin(self, details):
        global global_session, global_loop
        global_session = self
        global_loop = asyncio.get_event_loop()
        print("Conexión establecida en el publicador (realm:", self.config.realm, ")")
        await asyncio.Future()

def start_publisher(url, realm, topic):
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        runner = ApplicationRunner(url=url, realm=realm)
        runner.run(lambda config: JSONPublisher(config, topic))
    threading.Thread(target=run, daemon=True).start()

def send_message_now(router_url, realm, topic, message, delay=0):
    global global_session, global_loop
    if global_session is None or global_loop is None:
        print("No hay sesión activa. Inicia el publicador primero.")
        return
    async def _send():
        if delay > 0:
            await asyncio.sleep(delay)
        global_session.publish(topic, **message)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message_json = json.dumps(message, indent=2, ensure_ascii=False)
        log_to_file(timestamp, topic, realm, message_json)
        logging.info(f"Publicado: {timestamp} | Topic: {topic} | Realm: {realm}")
        print("Mensaje enviado en", topic, "para realm", realm, ":", message)
    asyncio.run_coroutine_threadsafe(_send(), global_loop)

# Widget para ver mensajes enviados
class PublisherMessageViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pubMessages = []
        self.initUI()
        
    def initUI(self):
        layout = QVBoxLayout(self)
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Hora", "Topic", "Realms"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemDoubleClicked.connect(self.showDetails)
        layout.addWidget(self.table)
        self.setLayout(layout)
        self.setFixedHeight(200)

    def add_message(self, realms, topic, timestamp, details):
        if isinstance(details, str):
            details = details.replace("\n", " ")
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(timestamp))
        self.table.setItem(row, 1, QTableWidgetItem(topic))
        self.table.setItem(row, 2, QTableWidgetItem(", ".join(realms)))
        self.pubMessages.append(details)

    def showDetails(self, item):
        row = item.row()
        if row < len(self.pubMessages):
            dlg = JsonDetailDialog(self.pubMessages[row], self)
            dlg.exec_()

# Widget para configurar un mensaje (escenario)
class MessageConfigWidget(QGroupBox):
    def __init__(self, msg_id, parent=None):
        super().__init__(parent)
        self.msg_id = msg_id
        self.realms_topics = {}  # Configuración local (cargada globalmente)
        self.templatePath = ""   # Referencia al template
        self.setTitle(f"Mensaje #{self.msg_id}")
        self.setCheckable(True)
        self.setChecked(True)
        self.toggled.connect(self.toggleContent)
        self.initUI()

    def initUI(self):
        self.contentWidget = QWidget()
        contentLayout = QHBoxLayout()
        formLayout = QFormLayout()
        
        # Realms: tabla con 2 columnas (Realm y Router URL)
        self.realmTable = QTableWidget(0, 2)
        self.realmTable.setHorizontalHeaderLabels(["Realm", "Router URL"])
        self.realmTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        formLayout.addRow("Realms:", self.realmTable)
        # Botones para gestionar realms
        realmBtnLayout = QHBoxLayout()
        self.newRealmEdit = QLineEdit()
        self.newRealmEdit.setPlaceholderText("Nuevo realm")
        realmBtnLayout.addWidget(self.newRealmEdit)
        self.addRealmBtn = QPushButton("Agregar")
        self.addRealmBtn.clicked.connect(self.addRealmRow)
        self.addRealmBtn.setStyleSheet("background-color: #AED6F1;")
        realmBtnLayout.addWidget(self.addRealmBtn)
        self.delRealmBtn = QPushButton("Borrar")
        self.delRealmBtn.clicked.connect(self.deleteRealmRow)
        self.delRealmBtn.setStyleSheet("background-color: #AED6F1;")
        realmBtnLayout.addWidget(self.delRealmBtn)
        formLayout.addRow("", realmBtnLayout)
        
        # Topics: tabla similar (1 columna)
        self.topicTable = QTableWidget(0, 1)
        self.topicTable.setHorizontalHeaderLabels(["Topic"])
        self.topicTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        formLayout.addRow("Topics:", self.topicTable)
        topicBtnLayout = QHBoxLayout()
        self.newTopicEdit = QLineEdit()
        self.newTopicEdit.setPlaceholderText("Nuevo topic")
        topicBtnLayout.addWidget(self.newTopicEdit)
        self.addTopicBtn = QPushButton("Agregar")
        self.addTopicBtn.clicked.connect(self.addTopicRow)
        self.addTopicBtn.setStyleSheet("background-color: #F9E79F;")
        topicBtnLayout.addWidget(self.addTopicBtn)
        self.delTopicBtn = QPushButton("Borrar")
        self.delTopicBtn.clicked.connect(self.deleteTopicRow)
        self.delTopicBtn.setStyleSheet("background-color: #F9E79F;")
        topicBtnLayout.addWidget(self.delTopicBtn)
        formLayout.addRow("", topicBtnLayout)
        
        # Modo de envío
        self.modeCombo = QComboBox()
        self.modeCombo.addItems(["Programado", "Hora de sistema", "On demand"])
        formLayout.addRow("Modo:", self.modeCombo)
        
        # Template: campo y botón para cargar template desde /Templates
        templateLayout = QHBoxLayout()
        self.templateEdit = QLineEdit()
        self.templateEdit.setPlaceholderText("Nombre template (ej. ejemplo.json)")
        templateLayout.addWidget(self.templateEdit)
        self.loadTemplateBtn = QPushButton("Cargar Template")
        self.loadTemplateBtn.setStyleSheet("background-color: #D2B4DE;")
        self.loadTemplateBtn.clicked.connect(self.loadTemplate)
        templateLayout.addWidget(self.loadTemplateBtn)
        formLayout.addRow("Template:", templateLayout)
        
        formContainer = QWidget()
        formContainer.setLayout(formLayout)
        contentLayout.addWidget(formContainer)
        
        # Editor de mensaje (contenido JSON, tiempo, etc.)
        self.editorWidget = PublisherEditorWidget(parent=self)
        contentLayout.addWidget(self.editorWidget)
        
        # Barra lateral de botones: Enviar y Eliminar mensaje (botones con distinto formato)
        sideLayout = QVBoxLayout()
        self.sendButton = QPushButton("Enviar")
        self.sendButton.clicked.connect(self.sendMessage)
        self.sendButton.setStyleSheet("background-color: #F7DC6F; font-weight: bold;")
        sideLayout.addWidget(self.sendButton)
        self.deleteButton = QPushButton("Eliminar")
        self.deleteButton.clicked.connect(self.deleteSelf)
        self.deleteButton.setStyleSheet("background-color: #E74C3C; color: white; font-weight: bold;")
        sideLayout.addWidget(self.deleteButton)
        contentLayout.addLayout(sideLayout)
        
        self.contentWidget.setLayout(contentLayout)
        outerLayout = QVBoxLayout()
        outerLayout.addWidget(self.contentWidget)
        self.setLayout(outerLayout)

    def addRealmRow(self):
        new_realm = self.newRealmEdit.text().strip()
        if new_realm:
            row = self.realmTable.rowCount()
            self.realmTable.insertRow(row)
            itemRealm = QTableWidgetItem(new_realm)
            itemRealm.setFlags(itemRealm.flags() | Qt.ItemIsUserCheckable)
            itemRealm.setCheckState(Qt.Checked)
            self.realmTable.setItem(row, 0, itemRealm)
            self.realmTable.setItem(row, 1, QTableWidgetItem(""))  # URL vacío por defecto
            self.newRealmEdit.clear()

    def deleteRealmRow(self):
        rows_to_delete = []
        for row in range(self.realmTable.rowCount()):
            item = self.realmTable.item(row, 0)
            if item.checkState() != Qt.Checked:
                rows_to_delete.append(row)
        for row in sorted(rows_to_delete, reverse=True):
            self.realmTable.removeRow(row)

    def addTopicRow(self):
        new_topic = self.newTopicEdit.text().strip()
        if new_topic:
            row = self.topicTable.rowCount()
            self.topicTable.insertRow(row)
            itemTopic = QTableWidgetItem(new_topic)
            itemTopic.setFlags(itemTopic.flags() | Qt.ItemIsUserCheckable)
            itemTopic.setCheckState(Qt.Checked)
            self.topicTable.setItem(row, 0, itemTopic)
            self.newTopicEdit.clear()

    def deleteTopicRow(self):
        rows_to_delete = []
        for row in range(self.topicTable.rowCount()):
            item = self.topicTable.item(row, 0)
            if item.checkState() != Qt.Checked:
                rows_to_delete.append(row)
        for row in sorted(rows_to_delete, reverse=True):
            self.topicTable.removeRow(row)

    def loadTemplate(self):
        # Abre un diálogo para seleccionar un template del directorio /Templates
        base_dir = os.path.join(os.path.dirname(__file__), "..", "Templates")
        filepath, _ = QFileDialog.getOpenFileName(self, "Seleccionar Template", base_dir, "JSON Files (*.json);;All Files (*)")
        if filepath:
            self.templateEdit.setText(os.path.basename(filepath))
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    template_data = json.load(f)
                # Se carga el contenido del template en el editor
                self.editorWidget.jsonPreview.setPlainText(json.dumps(template_data, indent=2, ensure_ascii=False))
                QMessageBox.information(self, "Template", "Template cargado correctamente.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo cargar el template:\n{e}")

    def updateRealmsTopics(self, realms_topics):
        self.realms_topics = realms_topics
        self.realmTable.setRowCount(0)
        for realm, topics in sorted(realms_topics.items()):
            row = self.realmTable.rowCount()
            self.realmTable.insertRow(row)
            itemRealm = QTableWidgetItem(realm)
            itemRealm.setFlags(itemRealm.flags() | Qt.ItemIsUserCheckable)
            itemRealm.setCheckState(Qt.Checked)
            self.realmTable.setItem(row, 0, itemRealm)
            url = ""
            self.realmTable.setItem(row, 1, QTableWidgetItem(url))
        self.updateTopicsFromRealms()

    def updateTopicsFromRealms(self):
        rows = self.realmTable.rowCount()
        for row in range(rows):
            item = self.realmTable.item(row, 0)
            if item.checkState() == Qt.Checked:
                realm = item.text()
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
                    default_item = QTableWidgetItem("default")
                    default_item.setFlags(default_item.flags() | Qt.ItemIsUserCheckable)
                    default_item.setCheckState(Qt.Checked)
                    self.topicTable.setItem(r, 0, default_item)
                break

    def getSelectedRealms(self):
        realms = []
        rows = self.realmTable.rowCount()
        for row in range(rows):
            item = self.realmTable.item(row, 0)
            if item.checkState() == Qt.Checked:
                realms.append(item.text())
        return realms if realms else ["default"]

    def getSelectedTopics(self):
        topics = []
        rows = self.topicTable.rowCount()
        for row in range(rows):
            item = self.topicTable.item(row, 0)
            if item.checkState() == Qt.Checked:
                topics.append(item.text())
        return topics if topics else ["default"]

    def getRouterURL(self):
        rows = self.realmTable.rowCount()
        for row in range(rows):
            url_item = self.realmTable.item(row, 1)
            if url_item and url_item.text().strip():
                return url_item.text().strip()
        return self.urlEdit.text().strip()

    def toggleContent(self, checked):
        self.contentWidget.setVisible(checked)
        if not checked:
            realms = self.getSelectedRealms()
            topics = self.getSelectedTopics()
            time_val = self.editorWidget.commonTimeEdit.text()
            self.setTitle(f"Mensaje #{self.msg_id} - {', '.join(topics)} - {time_val} - {', '.join(realms)}")
        else:
            self.setTitle(f"Mensaje #{self.msg_id}")

    def sendMessage(self):
        try:
            h, m, s = map(int, self.editorWidget.commonTimeEdit.text().strip().split(":"))
            delay = h*3600 + m*60 + s
        except:
            delay = 0
        topics = self.getSelectedTopics()
        realms = self.getSelectedRealms()
        try:
            data = json.loads(self.editorWidget.jsonPreview.toPlainText())
        except Exception as e:
            QMessageBox.critical(self, "Error", f"JSON inválido:\n{e}")
            return
        for realm in realms:
            router_url = self.getRouterURL()
            for topic in topics:
                from .pubGUI import send_message_now
                send_message_now(router_url, realm, topic, data, delay)
        publish_time = datetime.datetime.now() + datetime.timedelta(seconds=delay)
        publish_time_str = publish_time.strftime("%Y-%m-%d %H:%M:%S")
        sent_message = json.dumps(data, indent=2, ensure_ascii=False)
        if hasattr(self.parent(), "addPublisherLog"):
            self.parent().addPublisherLog(self.getSelectedRealms(), ", ".join(topics), publish_time_str, sent_message)

    def deleteSelf(self):
        self.parent().parent().removeMessage(self)

    def getConfig(self):
        return {
            "id": self.msg_id,
            "realms": self.getSelectedRealms(),
            "router_url": self.getRouterURL(),
            "topics": self.getSelectedTopics(),
            "time": self.editorWidget.commonTimeEdit.text().strip(),
            "mode": self.modeCombo.currentText(),
            "template": self.templateEdit.text().strip(),
            "content": json.loads(self.editorWidget.jsonPreview.toPlainText())
        }

