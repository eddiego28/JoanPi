class MessageConfigWidget(QGroupBox):
    def __init__(self, msg_id, publisherTab):
        super().__init__(publisherTab)
        self.publisherTab = publisherTab  # Referencia al PublisherTab
        self.msg_id = msg_id
        self.realms_topics = {}  # Configuración local (se actualizará con la global)
        self.setTitle(f"Mensaje #{self.msg_id}")
        self.setCheckable(True)
        self.setChecked(True)
        self.toggled.connect(self.toggleContent)
        self.initUI()

    def initUI(self):
        self.contentWidget = QWidget()
        contentLayout = QHBoxLayout()
        formLayout = QFormLayout()
        # Tabla de Realms: dos columnas (Realm y Router URL)
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
        realmBtnLayout.addWidget(self.addRealmBtn)
        self.delRealmBtn = QPushButton("Borrar")
        self.delRealmBtn.clicked.connect(self.deleteRealmRow)
        realmBtnLayout.addWidget(self.delRealmBtn)
        formLayout.addRow("", realmBtnLayout)
        # Tabla de Topics
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
        topicBtnLayout.addWidget(self.addTopicBtn)
        self.delTopicBtn = QPushButton("Borrar")
        self.delTopicBtn.clicked.connect(self.deleteTopicRow)
        topicBtnLayout.addWidget(self.delTopicBtn)
        formLayout.addRow("", topicBtnLayout)
        # Campo Default Router URL (en caso de que la tabla no tenga valor)
        self.defaultUrlEdit = QLineEdit("ws://127.0.0.1:60001")
        formLayout.addRow("Default Router URL:", self.defaultUrlEdit)
        # Modo de envío
        self.modeCombo = QComboBox()
        self.modeCombo.addItems(["Programado", "Hora de sistema", "On demand"])
        formLayout.addRow("Modo:", self.modeCombo)
        formContainer = QWidget()
        formContainer.setLayout(formLayout)
        contentLayout.addWidget(formContainer)
        # Editor de mensaje (se asume que PublisherEditorWidget existe)
        self.editorWidget = PublisherEditorWidget(parent=self)
        contentLayout.addWidget(self.editorWidget)
        # Solo se deja el botón de Enviar (se elimina el de borrar en el widget)
        sideLayout = QHBoxLayout()
        self.sendButton = QPushButton("Enviar")
        self.sendButton.clicked.connect(self.sendMessage)
        sideLayout.addWidget(self.sendButton)
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
            self.realmTable.setItem(row, 1, QTableWidgetItem(""))
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
            url = self.publisherTab.realm_configs.get(realm, "")
            self.realmTable.setItem(row, 1, QTableWidgetItem(url))
        if self.realmTable.rowCount() > 0:
            self.updateTopicsFromSelectedRealm(0, 0)

    def updateTopicsFromSelectedRealm(self, row, column):
        if self.realmTable.rowCount() == 0:
            return
        item = self.realmTable.item(row, 0)
        realm = item.text() if item else "default"
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
        return self.defaultUrlEdit.text().strip()

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
            delay = h * 3600 + m * 60 + s
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
            router_url = self.publisherTab.realm_configs.get(realm, self.getRouterURL())
            for topic in topics:
                from .pubGUI import send_message_now
                send_message_now(router_url, realm, topic, data, delay)
        publish_time = datetime.datetime.now() + datetime.timedelta(seconds=delay)
        publish_time_str = publish_time.strftime("%Y-%m-%d %H:%M:%S")
        sent_message = json.dumps(data, indent=2, ensure_ascii=False)
        if hasattr(self.publisherTab, "addPublisherLog"):
            self.publisherTab.addPublisherLog(self.getSelectedRealms(), ", ".join(topics), publish_time_str, sent_message)

    def deleteSelf(self):
        self.publisherTab.removeMessage(self)

    def getConfig(self):
        return {
            "id": self.msg_id,
            "realms": self.getSelectedRealms(),
            "router_url": self.getRouterURL(),
            "topics": self.getSelectedTopics(),
            "time": self.editorWidget.commonTimeEdit.text().strip(),
            "mode": self.modeCombo.currentText(),
            "template": "",  # Se elimina la sección de template
            "content": json.loads(self.editorWidget.jsonPreview.toPlainText())
        }
