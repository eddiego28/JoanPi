# -------------------------------------------------------------------
# SubscriberTab con splitter para redimensionar paneles
# -------------------------------------------------------------------
class SubscriberTab(QWidget):
    messageReceived = pyqtSignal(str, str, str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.realms_topics = {}
        self.selected_topics_by_realm = {}
        self.current_realm = None

        self.checkAllRealms = QCheckBox("All Realms")
        self.checkAllRealms.stateChanged.connect(self.toggleAllRealms)
        self.checkAllTopics = QCheckBox("All Topics")
        self.checkAllTopics.stateChanged.connect(self.toggleAllTopics)

        self.messageReceived.connect(self.onMessageReceived)

        self.initUI()
        self.loadGlobalRealmTopicConfig()

    def initUI(self):
        splitter = QSplitter(Qt.Horizontal)

        # Izquierda: realms & topics
        leftPanel = QWidget()
        leftLayout = QVBoxLayout(leftPanel)
        leftLayout.addWidget(self.checkAllRealms)
        leftLayout.addWidget(QLabel("Realms (select row then Remove Realm):"))

        self.realmTable = QTableWidget(0, 2)
        self.realmTable.setHorizontalHeaderLabels(["Realm", "Router URL"])
        self.realmTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.realmTable.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.realmTable.setSelectionBehavior(QTableWidget.SelectRows)
        self.realmTable.cellClicked.connect(self.onRealmClicked)
        self.realmTable.itemChanged.connect(self.onRealmItemChanged)
        leftLayout.addWidget(self.realmTable)

        realmBtns = QHBoxLayout()
        self.newRealmEdit = QLineEdit(); self.newRealmEdit.setPlaceholderText("New Realm")
        realmBtns.addWidget(self.newRealmEdit)
        realmBtns.addWidget(QPushButton("Add Realm", clicked=self.addRealmRow))
        realmBtns.addWidget(QPushButton("Remove Realm", clicked=self.deleteRealmRow))
        leftLayout.addLayout(realmBtns)

        leftLayout.addWidget(self.checkAllTopics)
        leftLayout.addWidget(QLabel("Topics (select row then Remove Topic):"))

        self.topicTable = QTableWidget(0, 1)
        self.topicTable.setHorizontalHeaderLabels(["Topic"])
        self.topicTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.topicTable.setSelectionBehavior(QTableWidget.SelectRows)
        self.topicTable.itemChanged.connect(self.onTopicChanged)
        leftLayout.addWidget(self.topicTable)

        topicBtns = QHBoxLayout()
        self.newTopicEdit = QLineEdit(); self.newTopicEdit.setPlaceholderText("New Topic")
        topicBtns.addWidget(self.newTopicEdit)
        topicBtns.addWidget(QPushButton("Add Topic", clicked=self.addTopicRow))
        topicBtns.addWidget(QPushButton("Remove Topic", clicked=self.deleteTopicRow))
        leftLayout.addLayout(topicBtns)

        ctrl = QHBoxLayout()
        ctrl.addWidget(QPushButton("Subscribe", clicked=self.confirmAndStartSubscription))
        ctrl.addWidget(QPushButton("Stop Subscription", clicked=self.stopSubscription))
        ctrl.addWidget(QPushButton("Reset Log", clicked=self.resetLog))
        leftLayout.addLayout(ctrl)

        splitter.addWidget(leftPanel)

        # Derecha: log de mensajes
        self.viewer = SubscriberMessageViewer(self)
        splitter.addWidget(self.viewer)

        splitter.setSizes([300, 600])

        mainLayout = QVBoxLayout(self)
        mainLayout.addWidget(splitter)
        self.setLayout(mainLayout)