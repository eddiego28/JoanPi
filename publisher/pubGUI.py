import sys, os, json, datetime, asyncio, threading
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QLineEdit, QFileDialog,
    QDialog, QTreeWidget, QComboBox, QSplitter, QGroupBox, QPushButton,
    QTreeWidgetItem
)
from PyQt5.QtCore import Qt, QTimer
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
from common.utils import log_to_file, JsonDetailDialog
from .pubEditor import PublisherEditorWidget

# Diccionario global para almacenar sesiones de publicación
# La clave es (router_url, realm, topic)
publisher_sessions = {}

# --------------------------------------------------------------------
# Clase JSONPublisher: sesión WAMP para publicar en un realm/topic específicos.
# Se guarda en publisher_sessions cuando se conecta.
# --------------------------------------------------------------------
class JSONPublisher(ApplicationSession):
    def __init__(self, config, topic, key):
        super().__init__(config)
        self.topic = topic
        self.key = key  # clave (router_url, realm, topic)

    async def onJoin(self, details):
        # Al conectarse, se almacena esta sesión en publisher_sessions
        publisher_sessions[self.key] = self
        print("Conexión establecida en el publicador (realm:", self.config.realm, ")")
        await asyncio.Future()  # Mantiene la sesión activa

# --------------------------------------------------------------------
# Función start_publisher: inicia la sesión para una clave (router_url, realm, topic).
# Si ya existe la sesión en publisher_sessions, no hace nada.
# --------------------------------------------------------------------
def start_publisher(router_url, realm, topic):
    key = (router_url, realm, topic)
    if key in publisher_sessions:
        return  # Ya existe la sesión
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        runner = ApplicationRunner(url=router_url, realm=realm)
        # runner.run es bloqueante, por lo que cuando se conecte, la sesión se almacenará en publisher_sessions
        runner.run(lambda config: JSONPublisher(config, topic, key))
    threading.Thread(target=run, daemon=True).start()

# --------------------------------------------------------------------
# Función send_message_now: utiliza la sesión almacenada en publisher_sessions para publicar.
# Si no existe la sesión para la combinación, se la inicia y se espera (breve delay).
# --------------------------------------------------------------------
def send_message_now(key, message, delay=0):
    # key es (router_url, realm, topic)
    async def _send(session):
        if delay > 0:
            await asyncio.sleep(delay)
        if isinstance(message, dict):
            session.publish(key[2], **message)
        else:
            session.publish(key[2], message)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message_json = json.dumps(message, indent=2, ensure_ascii=False)
        log_to_file(timestamp, key[2], key[1], message_json)
        print("Mensaje enviado en", key[2], "para realm", key[1], ":", message)
    # Si la sesión aún no existe, esperar un breve momento para que se conecte.
    if key not in publisher_sessions:
        start_publisher(key[0], key[1], key[2])
        # Esperamos 1 segundo; en una implementación real se debería esperar de forma asíncrona.
        import time
        time.sleep(1)
    session = publisher_sessions.get(key)
    if session:
        asyncio.run_coroutine_threadsafe(_send(session), session.loop)

# --------------------------------------------------------------------
# Clase JsonTreeDialog: muestra el JSON en formato de árbol (1 columna)
# --------------------------------------------------------------------
class JsonTreeDialog(QDialog):
    def __init__(self, json_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Detalle JSON - Árbol")
        self.resize(600, 400)
        layout = QVBoxLayout(self)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(1)
        self.tree.setHeaderLabels(["JSON"])
        self.tree.header().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.tree)
        self.setLayout(layout)
        self.buildTree(json_data, self.tree.invisibleRootItem())
        self.tree.expandAll()

    def buildTree(self, data, parent):
        if isinstance(data, dict):
            for key, value in data.items():
                text = f"{key}: {value}" if not isinstance(value, (dict, list)) else f"{key}:"
                item = QTreeWidgetItem([text])
                parent.addChild(item)
                self.buildTree(value, item)
        elif isinstance(data, list):
            for index, value in enumerate(data):
                text = f"[{index}]: {value}" if not isinstance(value, (dict, list)) else f"[{index}]:"
                item = QTreeWidgetItem([text])
                parent.addChild(item)
                self.buildTree(value, item)
        else:
            item = QTreeWidgetItem([str(data)])
            parent.addChild(item)

# --------------------------------------------------------------------
# Clase PublisherMessageViewer: muestra los mensajes enviados (una fila por mensaje)
# Se fija la altura a 200 px.
# --------------------------------------------------------------------
class PublisherMessageViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pubMessages = []
        self.initUI()
        
    def initUI(self):
        layout = QVBoxLayout(self)
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Hora", "Realm", "Topic"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.itemDoubleClicked.connect(self.showDetails)
        layout.addWidget(self.table)
        self.setLayout(layout)
        self.setFixedHeight(200)

    def add_message(self, realms, topics, timestamp, details):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(timestamp))
        self.table.setItem(row, 1, QTableWidgetItem(", ".join(realms)))
        self.table.setItem(row, 2, QTableWidgetItem(", ".join(topics)))
        self.pubMessages.append(details)

    def showDetails(self, item):
        row = item.row()
        if row < len(self.pubMessages):
            data = self.pubMessages[row]
            dlg = JsonTreeDialog(data, self)
            dlg.exec_()

# --------------------------------------------------------------------
# Clase MessageConfigWidget: configuración individual del mensaje.
# – En el lado izquierdo se muestran las tablas de realms y topics (con checkboxes)
# – Se conserva el estado de los checkboxes para cada realm hasta que el usuario lo modifique
# --------------------------------------------------------------------
class MessageConfigWidget(QGroupBox):
    def __init__(self, msg_id, parent=None):
        super().__init__(parent)
        self.msg_id = msg_id
        self.realms_topics = {}  # Configuración global (se actualiza)
        self.selected_topics_by_realm = {}  # Para conservar la selección por realm
        self.current_realm = None
        self.initUI()

    def initUI(self):
        self.setTitle(f"Mensaje #{self.msg_id}")
        self.setCheckable(True)
        self.setChecked(True)
        self.toggled.connect(self.toggleContent)
        layout = QVBoxLayout(self)

        # Layout horizontal: izquierda (tablas) y derecha (editor JSON y controles)
        hLayout = QHBoxLayout()
        # Panel izquierdo: Tablas de realms y topics
        leftPanel = QVBoxLayout()
        self.realmTable = QTableWidget(0, 2)
        self.realmTable.setHorizontalHeaderLabels(["Realm", "Router URL"])
        self.realmTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        leftPanel.addWidget(QLabel("Realms (checkbox):"))
        leftPanel.addWidget(self.realmTable)
        self.topicTable = QTableWidget(0, 1)
        self.topicTable.setHorizontalHeaderLabels(["Topic"])
        self.topicTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        leftPanel.addWidget(QLabel("Topics (checkbox):"))
        leftPanel.addWidget(self.topicTable)
        # Conectar señales para actualizar selección: al hacer clic en realm y al cambiar topic
        self.realmTable.cellClicked.connect(self.onRealmClicked)
        self.topicTable.itemChanged.connect(self.onTopicChanged)
        hLayout.addLayout(leftPanel, stretch=1)

        # Panel derecho: Editor JSON y controles de modo/tiempo
        rightPanel = QVBoxLayout()
        self.editorWidget = PublisherEditorWidget(self)
        rightPanel.addWidget(QLabel("Editor JSON:"))
        rightPanel.addWidget(self.editorWidget)
        modeLayout = QHBoxLayout()
        modeLayout.addWidget(QLabel("Modo:"))
        self.modeCombo = QComboBox()
        self.modeCombo.addItems(["Programado", "Hora de sistema", "On demand"])
        modeLayout.addWidget(self.modeCombo)
        modeLayout.addWidget(QLabel("Tiempo (HH:MM:SS):"))
        self.timeEdit = QLineEdit("00:00:00")
        modeLayout.addWidget(self.timeEdit)
        rightPanel.addLayout(modeLayout)
        hLayout.addLayout(rightPanel, stretch=1)
        layout.addLayout(hLayout)

        # Botones para agregar/borrar realms y topics (debajo del panel izquierdo)
        btnLayout = QHBoxLayout()
        self.newRealmEdit = QLineEdit()
        self.newRealmEdit.setPlaceholderText("Nuevo Realm")
        self.btnAddRealm = QPushButton("Agregar Realm")
        self.btnAddRealm.clicked.connect(self.addRealmRow)
        self.btnDelRealm = QPushButton("Borrar Realm")
        self.btnDelRealm.clicked.connect(self.deleteRealmRow)
        btnLayout.addWidget(self.newRealmEdit)
        btnLayout.addWidget(self.btnAddRealm)
        btnLayout.addWidget(self.btnDelRealm)
        self.newTopicEdit = QLineEdit()
        self.newTopicEdit.setPlaceholderText("Nuevo Topic")
        self.btnAddTopic = QPushButton("Agregar Topic")
        self.btnAddTopic.clicked.connect(self.addTopicRow)
        self.btnDelTopic = QPushButton("Borrar Topic")
        self.btnDelTopic.clicked.connect(self.deleteTopicRow)
        btnLayout.addWidget(self.newTopicEdit)
        btnLayout.addWidget(self.btnAddTopic)
        btnLayout.addWidget(self.btnDelTopic)
        layout.addLayout(btnLayout)

        # Botón de enviar mensaje
        self.sendButton = QPushButton("Enviar")
        self.sendButton.clicked.connect(self.sendMessage)
        layout.addWidget(self.sendButton)

        self.setLayout(layout)

    def toggleContent(self, checked):
        self.setFlat(not checked)

    def addRealmRow(self):
        new_realm = self.newRealmEdit.text().strip()
        if new_realm:
            row = self.realmTable.rowCount()
            self.realmTable.insertRow(row)
            item = QTableWidgetItem(new_realm)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.realmTable.setItem(row, 0, item)
            self.realmTable.setItem(row, 1, QTableWidgetItem("ws://127.0.0.1:60001/ws"))
            self.newRealmEdit.clear()

    def deleteRealmRow(self):
        rows_to_delete = []
        for row in range(self.realmTable.rowCount()):
            item = self.realmTable.item(row, 0)
            if item and item.checkState() != Qt.Checked:
                rows_to_delete.append(row)
        for row in reversed(rows_to_delete):
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
            if self.current_realm:
                self.selected_topics_by_realm.setdefault(self.current_realm, set()).add(new_topic)

    def deleteTopicRow(self):
        rows_to_delete = []
        for row in range(self.topicTable.rowCount()):
            item = self.topicTable.item(row, 0)
            if item and item.checkState() != Qt.Checked:
                rows_to_delete.append(row)
        for row in reversed(rows_to_delete):
            t_item = self.topicTable.item(row, 0)
            if t_item and self.current_realm:
                self.selected_topics_by_realm[self.current_realm].discard(t_item.text().strip())
            self.topicTable.removeRow(row)

    def onRealmClicked(self, row, col):
        realm_item = self.realmTable.item(row, 0)
        if realm_item:
            realm = realm_item.text().strip()
            self.current_realm = realm
            # Cargar topics del realm según la configuración global
            topics = self.realms_topics.get(realm, {}).get("topics", [])
            self.topicTable.blockSignals(True)
            self.topicTable.setRowCount(0)
            # Si ya hay selección previa para este realm, conservarla; de lo contrario, marcar todos
            if realm not in self.selected_topics_by_realm:
                self.selected_topics_by_realm[realm] = set(topics)
            for t in topics:
                row_idx = self.topicTable.rowCount()
                self.topicTable.insertRow(row_idx)
                t_item = QTableWidgetItem(t)
                t_item.setFlags(t_item.flags() | Qt.ItemIsUserCheckable)
                if t in self.selected_topics_by_realm[realm]:
                    t_item.setCheckState(Qt.Checked)
                else:
                    t_item.setCheckState(Qt.Unchecked)
                self.topicTable.setItem(row_idx, 0, t_item)
            self.topicTable.blockSignals(False)

    def onTopicChanged(self, item):
        if not self.current_realm:
            return
        realm = self.current_realm
        selected = set()
        for row in range(self.topicTable.rowCount()):
            t_item = self.topicTable.item(row, 0)
            if t_item and t_item.checkState() == Qt.Checked:
                selected.add(t_item.text().strip())
        self.selected_topics_by_realm[realm] = selected

    def updateRealmsTopics(self, realms_topics):
        self.realms_topics = realms_topics
        self.realmTable.blockSignals(True)
        self.realmTable.setRowCount(0)
        for realm, info in sorted(realms_topics.items()):
            row = self.realmTable.rowCount()
            self.realmTable.insertRow(row)
            item = QTableWidgetItem(realm)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            # Marcar por defecto
            item.setCheckState(Qt.Checked)
            self.realmTable.setItem(row, 0, item)
            router_url = info.get("router_url", "ws://127.0.0.1:60001/ws")
            self.realmTable.setItem(row, 1, QTableWidgetItem(router_url))
        self.realmTable.blockSignals(False)
        if self.realmTable.rowCount() > 0:
            self.realmTable.selectRow(0)
            self.onRealmClicked(0, 0)

    def getRouterURL(self):
        if self.realmTable.rowCount() > 0:
            return self.realmTable.item(0, 1).text().strip()
        return "ws://127.0.0.1:60001/ws"

    def sendMessage(self):
        realms = []
        for r in range(self.realmTable.rowCount()):
            r_item = self.realmTable.item(r, 0)
            if r_item and r_item.checkState() == Qt.Checked:
                realms.append(r_item.text().strip())
        topics = []
        for r in range(self.topicTable.rowCount()):
            t_item = self.topicTable.item(r, 0)
            if t_item and t_item.checkState() == Qt.Checked:
                topics.append(t_item.text().strip())
        content_text = self.editorWidget.jsonPreview.toPlainText()
        try:
            content = json.loads(content_text)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"JSON inválido:\n{e}")
            return
        mode = self.modeCombo.currentText()
        time_str = self.timeEdit.text().strip()
        delay = 0
        if mode == "Programado":
            try:
                h, m, s = map(int, time_str.split(":"))
                delay = h * 3600 + m * 60 + s
            except:
                delay = 0
        # Enviar el mensaje a cada combinación de realm y topic marcados
        for realm in realms:
            router_url = None
            for r in range(self.realmTable.rowCount()):
                r_item = self.realmTable.item(r, 0)
                if r_item and r_item.text().strip() == realm:
                    router_url = self.realmTable.item(r, 1).text().strip()
                    break
            if router_url is None:
                router_url = "ws://127.0.0.1:60001/ws"
            for topic in topics:
                start_publisher(router_url, realm, topic)
                send_message_now(topic, content, delay)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_info = {
            "action": "publish",
            "realms": realms,
            "topics": topics,
            "mode": mode,
            "time": time_str,
            "content": content
        }
        details = json.dumps(log_info, indent=2, ensure_ascii=False)
        self.parent().viewer.add_message(", ".join(realms), ", ".join(topics), timestamp, details)
        print(f"Mensaje publicado en realms {realms} y topics {topics} a las {timestamp}")

    def getConfig(self):
        realms = []
        for r in range(self.realmTable.rowCount()):
            r_item = self.realmTable.item(r, 0)
            if r_item and r_item.checkState() == Qt.Checked:
                realms.append(r_item.text().strip())
        topics = []
        for r in range(self.topicTable.rowCount()):
            t_item = self.topicTable.item(r, 0)
            if t_item and t_item.checkState() == Qt.Checked:
                topics.append(t_item.text().strip())
        content_text = self.editorWidget.jsonPreview.toPlainText()
        try:
            content = json.loads(content_text)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"JSON inválido:\n{e}")
            return {}
        mode = self.modeCombo.currentText()
        time_str = self.timeEdit.text().strip()
        return {
            "realms": realms,
            "topics": topics,
            "content": content,
            "mode": mode,
            "time": time_str,
            "router_url": self.realmTable.item(0,1).text().strip() if self.realmTable.rowCount() > 0 else "ws://127.0.0.1:60001/ws"
        }

# --------------------------------------------------------------------
# Clase PublisherTab: interfaz principal del publicador.
# --------------------------------------------------------------------
class PublisherTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.msgWidgets = []
        self.next_id = 1
        self.realms_topics = {}    # Se carga desde el JSON de configuración
        self.realm_configs = {}    # Se carga desde el mismo JSON
        self.initUI()
        self.loadGlobalRealmTopicConfig()

    def initUI(self):
        layout = QVBoxLayout()
        # Barra de herramientas
        toolbar = QHBoxLayout()
        btnAgregar = QPushButton("Agregar mensaje")
        btnAgregar.clicked.connect(self.addMessage)
        toolbar.addWidget(btnAgregar)
        btnEliminar = QPushButton("Eliminar mensaje")
        btnEliminar.clicked.connect(self.deleteSelectedMessage)
        toolbar.addWidget(btnEliminar)
        btnCargarProj = QPushButton("Cargar Proyecto")
        btnCargarProj.clicked.connect(self.loadProject)
        toolbar.addWidget(btnCargarProj)
        btnRecargarRT = QPushButton("Recargar Realm/Topic")
        btnRecargarRT.clicked.connect(self.loadGlobalRealmTopicConfig)
        toolbar.addWidget(btnRecargarRT)
        btnEnviarTodos = QPushButton("Enviar Mensaje a Todos")
        btnEnviarTodos.clicked.connect(self.sendAllAsync)
        toolbar.addWidget(btnEnviarTodos)
        layout.addLayout(toolbar)
        # Área de mensajes: QSplitter para separar la lista y el visor
        splitter = QSplitter(Qt.Vertical)
        self.msgArea = QScrollArea()
        self.msgArea.setWidgetResizable(True)
        self.msgContainer = QWidget()
        self.msgLayout = QVBoxLayout()
        self.msgContainer.setLayout(self.msgLayout)
        self.msgArea.setWidget(self.msgContainer)
        splitter.addWidget(self.msgArea)
        self.viewer = PublisherMessageViewer(self)
        splitter.addWidget(self.viewer)
        splitter.setSizes([500, 200])
        layout.addWidget(splitter)
        # Botón global para iniciar el publicador (para iniciar sesión vacía)
        connLayout = QHBoxLayout()
        connLayout.addWidget(QLabel("Publicador Global"))
        self.globalStartButton = QPushButton("Iniciar Publicador")
        self.globalStartButton.clicked.connect(self.startPublisher)
        connLayout.addWidget(self.globalStartButton)
        layout.addLayout(connLayout)
        layout.addWidget(QLabel("Resumen de mensajes enviados:"))
        layout.addWidget(self.viewer)
        self.setLayout(layout)

    def loadGlobalRealmTopicConfig(self):
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "realm_topic_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    realms_dict = {}
                    for item in data:
                        realm = item.get("realm")
                        if realm:
                            realms_dict[realm] = {
                                "router_url": item.get("router_url", "ws://127.0.0.1:60001/ws"),
                                "topics": item.get("topics", [])
                            }
                    data = {"realms": realms_dict}
                self.realms_topics = data.get("realms", {})
                self.realm_configs = {realm: info.get("router_url", "ws://127.0.0.1:60001/ws")
                                      for realm, info in self.realms_topics.items()}
                print("Configuración global de realms/topics cargada (publicador).")
                for widget in self.msgWidgets:
                    widget.updateRealmsTopics(self.realms_topics)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo cargar realm_topic_config.json:\n{e}")
        else:
            QMessageBox.warning(self, "Advertencia", "No se encontró realm_topic_config.json.")

    def addMessage(self):
        widget = MessageConfigWidget(self.next_id, self)
        if self.realms_topics:
            widget.updateRealmsTopics(self.realms_topics)
        self.msgLayout.addWidget(widget)
        self.msgWidgets.append(widget)
        self.next_id += 1

    def deleteSelectedMessage(self):
        if self.msgWidgets:
            self.removeMessage(self.msgWidgets[-1])

    def removeMessage(self, widget):
        if widget in self.msgWidgets:
            self.msgWidgets.remove(widget)
            widget.setParent(None)
            widget.deleteLater()

    def startPublisher(self):
        if self.msgWidgets:
            config = self.msgWidgets[0].getConfig()
            start_publisher(config["router_url"], config["realms"][0], config["topics"][0])
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_info = {"action": "start_publisher", "realm": config["realms"][0], "topic": config["topics"][0]}
            details = json.dumps(log_info, indent=2, ensure_ascii=False)
            self.viewer.add_message([config["realms"][0]], [config["topics"][0]], timestamp, details)
            print(f"Sesión de publicador iniciada en realm '{config['realms'][0]}' con topic '{config['topics'][0]}'")
        else:
            print("No hay mensajes configurados.")

    def sendAllAsync(self):
        for widget in self.msgWidgets:
            config = widget.getConfig()
            for realm in config.get("realms", []):
                router_url = self.realm_configs.get(realm, widget.getRouterURL())
                for topic in config.get("topics", []):
                    # Para cada combinación, iniciamos (o reutilizamos) la sesión y publicamos
                    key = (router_url, realm, topic)
                    start_publisher(router_url, realm, topic)
                    send_message_now(key[2], config.get("content", {}), delay=0)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sent_message = json.dumps(config.get("content", {}), indent=2, ensure_ascii=False)
            self.viewer.add_message(", ".join(config.get("realms", [])),
                                     ", ".join(config.get("topics", [])),
                                     timestamp, sent_message)
            print(f"Mensaje publicado en realms {config.get('realms', [])} y topics {config.get('topics', [])} a las {timestamp}")

    def getProjectConfig(self):
        scenarios = [widget.getConfig() for widget in self.msgWidgets]
        return {"scenarios": scenarios, "realm_configs": self.realm_configs}

    def loadProject(self):
        # Método dummy para evitar error; implementar según sea necesario.
        pass

# --------------------------------------------------------------------
# Fin de PublisherTab
