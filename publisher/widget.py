class MessageConfigWidget(QGroupBox):
    """
    Configuración individual de un mensaje en el Publicador.
    A la izquierda se muestran las tablas de Realms y Topics;
    a la derecha, el editor JSON, el modo y el tiempo.
    """
    def __init__(self, msg_id, parent=None):
        super().__init__(parent)
        self.msg_id = msg_id
        self.realms_topics = {}  # Se actualizará desde PublisherTab
        self.setTitle(f"Mensaje #{self.msg_id}")
        self.setCheckable(True)
        self.setChecked(True)
        self.initUI()

    def initUI(self):
        mainLayout = QHBoxLayout(self)

        # Lado Izquierdo: Realms y Topics
        leftLayout = QVBoxLayout()
        lblRealms = QLabel("Realms + Router URL:")
        leftLayout.addWidget(lblRealms)
        self.realmTable = QTableWidget(0, 2)
        self.realmTable.setHorizontalHeaderLabels(["Realm", "Router URL"])
        self.realmTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        # Conecta el clic en la celda para actualizar topics
        self.realmTable.cellClicked.connect(self.updateTopicsFromSelectedRealm)
        leftLayout.addWidget(self.realmTable)

        realmBtnLayout = QHBoxLayout()
        self.newRealmEdit = QLineEdit()
        self.newRealmEdit.setPlaceholderText("Nuevo Realm")
        btnAddRealm = QPushButton("Agregar Realm")
        btnAddRealm.clicked.connect(self.addRealmRow)
        btnDelRealm = QPushButton("Borrar Realm")
        btnDelRealm.clicked.connect(self.deleteRealmRow)
        realmBtnLayout.addWidget(self.newRealmEdit)
        realmBtnLayout.addWidget(btnAddRealm)
        realmBtnLayout.addWidget(btnDelRealm)
        leftLayout.addLayout(realmBtnLayout)

        lblTopics = QLabel("Topics:")
        leftLayout.addWidget(lblTopics)
        self.topicTable = QTableWidget(0, 1)
        self.topicTable.setHorizontalHeaderLabels(["Topic"])
        self.topicTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        leftLayout.addWidget(self.topicTable)

        topicBtnLayout = QHBoxLayout()
        self.newTopicEdit = QLineEdit()
        self.newTopicEdit.setPlaceholderText("Nuevo Topic")
        btnAddTopic = QPushButton("Agregar Topic")
        btnAddTopic.clicked.connect(self.addTopicRow)
        btnDelTopic = QPushButton("Borrar Topic")
        btnDelTopic.clicked.connect(self.deleteTopicRow)
        topicBtnLayout.addWidget(self.newTopicEdit)
        topicBtnLayout.addWidget(btnAddTopic)
        topicBtnLayout.addWidget(btnDelTopic)
        leftLayout.addLayout(topicBtnLayout)

        mainLayout.addLayout(leftLayout, stretch=1)

        # Lado Derecho: Editor JSON, modo y tiempo
        rightLayout = QVBoxLayout()
        modeLayout = QHBoxLayout()
        lblMode = QLabel("Modo:")
        self.modeCombo = QComboBox()
        self.modeCombo.addItems(["Programado", "Hora de sistema", "On demand"])
        modeLayout.addWidget(lblMode)
        modeLayout.addWidget(self.modeCombo)
        lblTime = QLabel("Tiempo (HH:MM:SS):")
        self.timeEdit = QLineEdit("00:00:00")
        modeLayout.addWidget(lblTime)
        modeLayout.addWidget(self.timeEdit)
        rightLayout.addLayout(modeLayout)

        self.editorWidget = PublisherEditorWidget(parent=self)
        rightLayout.addWidget(self.editorWidget)

        btnSend = QPushButton("Enviar este Mensaje")
        btnSend.clicked.connect(self.sendMessage)
        rightLayout.addWidget(btnSend)

        mainLayout.addLayout(rightLayout, stretch=1)
        self.setLayout(mainLayout)

    def addRealmRow(self):
        new_realm = self.newRealmEdit.text().strip()
        if new_realm:
            row = self.realmTable.rowCount()
            self.realmTable.insertRow(row)
            realm_item = QTableWidgetItem(new_realm)
            realm_item.setFlags(realm_item.flags() | Qt.ItemIsUserCheckable)
            realm_item.setCheckState(Qt.Checked)
            self.realmTable.setItem(row, 0, realm_item)
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
            t_item = QTableWidgetItem(new_topic)
            t_item.setFlags(t_item.flags() | Qt.ItemIsUserCheckable)
            t_item.setCheckState(Qt.Checked)
            self.topicTable.setItem(row, 0, t_item)
            self.newTopicEdit.clear()

    def deleteTopicRow(self):
        rows_to_delete = []
        for row in range(self.topicTable.rowCount()):
            t_item = self.topicTable.item(row, 0)
            if t_item and t_item.checkState() != Qt.Checked:
                rows_to_delete.append(row)
        for row in reversed(rows_to_delete):
            self.topicTable.removeRow(row)

    def updateTopicsFromSelectedRealm(self, row, column):
        realm_item = self.realmTable.item(row, 0)
        if not realm_item:
            return
        realm = realm_item.text().strip()
        self.topicTable.setRowCount(0)
        if realm in self.realms_topics and "topics" in self.realms_topics[realm]:
            for topic in self.realms_topics[realm]["topics"]:
                r = self.topicTable.rowCount()
                self.topicTable.insertRow(r)
                t_item = QTableWidgetItem(topic)
                t_item.setFlags(t_item.flags() | Qt.ItemIsUserCheckable)
                t_item.setCheckState(Qt.Checked)
                self.topicTable.setItem(r, 0, t_item)
        else:
            self.topicTable.insertRow(0)
            self.topicTable.setItem(0, 0, QTableWidgetItem("default"))

    def getConfig(self):
        realms = []
        for row in range(self.realmTable.rowCount()):
            item = self.realmTable.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                realms.append(item.text().strip())
        topics = []
        for row in range(self.topicTable.rowCount()):
            t_item = self.topicTable.item(row, 0)
            if t_item and t_item.checkState() == Qt.Checked:
                topics.append(t_item.text().strip())
        try:
            content = json.loads(self.editorWidget.jsonPreview.toPlainText())
        except:
            content = {}
        time_val = self.timeEdit.text().strip()
        mode_val = self.modeCombo.currentText()
        return {
            "realms": realms,
            "topics": topics,
            "content": content,
            "time": time_val,
            "mode": mode_val
        }

    def sendMessage(self):
        cfg = self.getConfig()
        realms = cfg["realms"]
        topics = cfg["topics"]
        content = cfg["content"]
        mode = cfg["mode"]
        time_str = cfg["time"]
        delay = 0
        if mode == "Programado":
            try:
                h, m, s = map(int, time_str.split(":"))
                delay = h * 3600 + m * 60 + s
            except:
                delay = 0
        elif mode == "Hora de sistema":
            now = datetime.datetime.now()
            try:
                h, m, s = map(int, time_str.split(":"))
                target = now.replace(hour=h, minute=m, second=s)
                if target < now:
                    target += datetime.timedelta(days=1)
                delay = (target - now).total_seconds()
            except:
                delay = 0
        else:
            delay = 0

        if not realms or not topics:
            QMessageBox.warning(self, "Error", "Selecciona al menos un realm y un topic.")
            return

        for r in realms:
            router_url = self.realms_topics.get(r, {}).get("router_url", "ws://127.0.0.1:60001/ws")
            for t in topics:
                from .pubGUI import start_publisher, send_message_now
                start_publisher(router_url, r, t)
                send_message_now(router_url, r, t, content, delay)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.parent().addPublisherLog(realms, ", ".join(topics), timestamp, json.dumps(content, indent=2, ensure_ascii=False))

    def toggleContent(self, checked):
        pass

# Fin de MessageConfigWidget
