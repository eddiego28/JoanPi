import sys, os, json, datetime, asyncio, threading
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QLineEdit, QFileDialog,
    QDialog, QTreeWidget, QComboBox, QSplitter, QGroupBox
)
from PyQt5.QtCore import Qt, QTimer
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
from common.utils import log_to_file, JsonDetailDialog
from .pubEditor import PublisherEditorWidget

# Variables globales para la sesión del publicador
global_session = None
global_loop = None

# --------------------------------------------------------------------
# JSONPublisher: sesión WAMP para publicar en un realm/topic
# --------------------------------------------------------------------
class JSONPublisher(ApplicationSession):
    def __init__(self, config, topic):
        super().__init__(config)
        self.topic = topic

    async def onJoin(self, details):
        global global_session, global_loop
        global_session = self
        global_loop = asyncio.get_event_loop()
        print("Conexión establecida en el publicador (realm:", self.config.realm, ")")
        await asyncio.Future()  # Mantiene la sesión activa

# --------------------------------------------------------------------
# start_publisher: inicia la sesión en un hilo separado.
# --------------------------------------------------------------------
def start_publisher(url, realm, topic):
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        runner = ApplicationRunner(url=url, realm=realm)
        runner.run(lambda config: JSONPublisher(config, topic))
    threading.Thread(target=run, daemon=True).start()

# --------------------------------------------------------------------
# send_message_now: envía el mensaje con delay (opcional)
# --------------------------------------------------------------------
def send_message_now(topic, message, delay=0):
    global global_session, global_loop
    if global_session is None or global_loop is None:
        print("No hay sesión activa. Inicia el publicador primero.")
        return
    async def _send():
        if delay > 0:
            await asyncio.sleep(delay)
        if isinstance(message, dict):
            global_session.publish(topic, **message)
        else:
            global_session.publish(topic, message)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message_json = json.dumps(message, indent=2, ensure_ascii=False)
        log_to_file(timestamp, topic, "publicador", message_json)
        print("Mensaje enviado en", topic, ":", message)
    asyncio.run_coroutine_threadsafe(_send(), global_loop)

# --------------------------------------------------------------------
# JsonTreeDialog: muestra el JSON en formato de árbol (una columna)
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
# PublisherMessageViewer: visor de mensajes enviados (una fila por mensaje)
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
# MessageConfigWidget: widget de configuración individual del mensaje.
# – En el panel izquierdo se muestran las tablas de realms y topics.
# – Se conserva el estado de los checkboxes hasta que el usuario los desmarca.
# – Se utiliza la referencia publisherTab para acceder al visor.
# --------------------------------------------------------------------
class MessageConfigWidget(QGroupBox):
    def __init__(self, msg_id, parent=None):
        super().__init__(parent)
        self.msg_id = msg_id
        self.realms_topics = {}  # Configuración global de realms (se actualizará)
        self.selected_topics_by_realm = {}  # Conserva la selección de topics para cada realm
        self.current_realm = None
        self.publisherTab = None  # Se asigna desde PublisherTab al agregar este widget
        self.initUI()

    def initUI(self):
        self.setTitle(f"Mensaje #{self.msg_id}")
        self.setCheckable(True)
        self.setChecked(True)
        self.toggled.connect(self.toggleContent)
        layout = QVBoxLayout(self)

        # Layout horizontal: panel izquierdo (tablas) y derecho (editor JSON y controles)
        hLayout = QHBoxLayout()
        # Panel izquierdo
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
        # Conecta clic en realm y cambios en topic
        self.realmTable.cellClicked.connect(self.onRealmClicked)
        self.topicTable.itemChanged.connect(self.onTopicChanged)
        hLayout.addLayout(leftPanel, stretch=1)
        # Panel derecho: editor JSON y controles
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
            topics = self.publisherTab.realms_topics.get(realm, {}).get("topics", [])
            self.topicTable.blockSignals(True)
            self.topicTable.setRowCount(0)
            if realm not in self.selected_topics_by_realm:
                # Por defecto, se inician DESMARCADOS para que el usuario elija
                self.selected_topics_by_realm[realm] = set()
            for t in topics:
                row_idx = self.topicTable.rowCount()
                self.topicTable.insertRow(row_idx)
                t_item = QTableWidgetItem(t)
                t_item.setFlags(t_item.flags() | Qt.ItemIsUserCheckable)
                # Se marca según la selección guardada
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
        # Para cada realm, usar la selección almacenada de topics
        all_topics = {}
        for realm in realms:
            all_topics[realm] = list(self.selected_topics_by_realm.get(realm, []))
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
        for realm in realms:
            router_url = None
            for r in range(self.realmTable.rowCount()):
                r_item = self.realmTable.item(r, 0)
                if r_item and r_item.text().strip() == realm:
                    router_url = self.realmTable.item(r, 1).text().strip()
                    break
            if router_url is None:
                router_url = "ws://127.0.0.1:60001/ws"
            topics = all_topics.get(realm, [])
            if topics:
                # Inicia la suscripción para este realm y sus topics (aquí se usa start_subscriber en el pub, si se desea)
                # En el publicador se puede simplemente enviar mensajes a cada combinación
                for topic in topics:
                    start_publisher(router_url, realm, topic)
                    send_message_now(topic, content, delay)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_info = {
            "action": "publish",
            "realms": realms,
            "topics": all_topics,
            "mode": mode,
            "time": time_str,
            "content": content
        }
        details = json.dumps(log_info, indent=2, ensure_ascii=False)
        self.publisherTab.viewer.add_message(", ".join(realms), ", ".join([", ".join(all_topics[r]) for r in realms]), timestamp, details)
        print(f"Mensaje publicado en realms {realms} con topics {all_topics} a las {timestamp}")

    def getConfig(self):
        realms = []
        for r in range(self.realmTable.rowCount()):
            r_item = self.realmTable.item(r, 0)
            if r_item and r_item.checkState() == Qt.Checked:
                realms.append(r_item.text().strip())
        topics = {}
        for realm in realms:
            topics[realm] = list(self.selected_topics_by_realm.get(realm, []))
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
# PublisherTab: interfaz principal del publicador.
# --------------------------------------------------------------------
class PublisherTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.msgWidgets = []
        self.next_id = 1
        self.realms_topics = {}   # Se carga desde el JSON de configuración
        self.realm_configs = {}   # Se carga desde el mismo JSON
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
        # Área de mensajes: QSplitter para separar lista y visor
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
        # Botón global para iniciar el publicador (sesión vacía)
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
        widget.publisherTab = self  # Asigna la referencia para acceder al visor
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
            # Enviar mensaje para cada realm según la selección almacenada
            for realm in config.get("realms", []):
                router_url = self.realm_configs.get(realm, widget.getRouterURL())
                topics = list(config.get("topics", {}).get(realm, []))
                for topic in topics:
                    send_message_now(topic, config.get("content", {}), delay=0)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sent_message = json.dumps(config.get("content", {}), indent=2, ensure_ascii=False)
            # Para mostrar, se unen todos los realms y se muestra la lista de topics por realm
            realms_str = ", ".join(config.get("realms", []))
            topics_str = "; ".join([f"{r}: {', '.join(config.get('topics', {}).get(r, []))}" for r in config.get("realms", [])])
            self.viewer.add_message(realms_str, topics_str, timestamp, sent_message)
            print(f"Mensaje publicado en realms {config.get('realms', [])} y topics {config.get('topics', {})} a las {timestamp}")

    def getProjectConfig(self):
        scenarios = [widget.getConfig() for widget in self.msgWidgets]
        return {"scenarios": scenarios, "realm_configs": self.realm_configs}

    def loadProject(self):
        # Método dummy para evitar error; implementar según tus necesidades.
        pass

# --------------------------------------------------------------------
# Fin de PublisherTab
