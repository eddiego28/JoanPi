import json
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTabWidget,
    QPlainTextEdit, QTreeWidget, QTreeWidgetItem, QPushButton, QMessageBox,
    QFileDialog, QSizePolicy, QMenu
)
from PyQt5.QtCore import Qt

class PublisherEditorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.updating = False
        self.initUI()
    
    def initUI(self):
        self.setStyleSheet("QWidget { font-family: 'Segoe UI'; font-size: 10pt; }")
        layout = QVBoxLayout(self)

        # Línea de tiempo y modos de envío
        timeModeLayout = QHBoxLayout()
        timeLabel = QLabel("Time (HH:MM:SS):")
        timeModeLayout.addWidget(timeLabel)
        self.commonTimeEdit = QLineEdit("00:00:00")
        self.commonTimeEdit.setMaximumWidth(100)
        timeModeLayout.addWidget(self.commonTimeEdit)
        from PyQt5.QtWidgets import QRadioButton
        self.onDemandRadio = QRadioButton("On-Demand")
        self.programadoRadio = QRadioButton("Programmed")
        self.tiempoSistemaRadio = QRadioButton("System Time")
        self.onDemandRadio.setChecked(True)
        timeModeLayout.addWidget(self.onDemandRadio)
        timeModeLayout.addWidget(self.programadoRadio)
        timeModeLayout.addWidget(self.tiempoSistemaRadio)
        layout.addLayout(timeModeLayout)

        # Pestañas de edición JSON
        self.tabWidget = QTabWidget()

        # --- Pestaña JSON de texto ---
        self.jsonTab = QWidget()
        jsonLayout = QVBoxLayout(self.jsonTab)
        self.loadJsonButton1 = QPushButton("Load JSON from file")
        self.loadJsonButton1.clicked.connect(self.loadJsonFromFile)
        jsonLayout.addWidget(self.loadJsonButton1)
        self.jsonPreview = QPlainTextEdit()
        self.jsonPreview.setPlainText("{}")
        self.jsonPreview.setMinimumHeight(350)
        self.jsonPreview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        jsonLayout.addWidget(self.jsonPreview)
        self.jsonTab.setLayout(jsonLayout)
        self.tabWidget.addTab(self.jsonTab, "JSON")

        # --- Pestaña JSON en árbol ---
        self.treeTab = QWidget()
        treeLayout = QVBoxLayout(self.treeTab)
        self.loadJsonButton2 = QPushButton("Load JSON from file")
        self.loadJsonButton2.clicked.connect(self.loadJsonFromFile)
        treeLayout.addWidget(self.loadJsonButton2)
        self.jsonTree = QTreeWidget()
        self.jsonTree.setHeaderLabels(["Key", "Value"])
        self.jsonTree.setMinimumHeight(350)
        self.jsonTree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.jsonTree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.jsonTree.customContextMenuRequested.connect(self.showContextMenu)
        treeLayout.addWidget(self.jsonTree)
        self.treeTab.setLayout(treeLayout)
        self.tabWidget.addTab(self.treeTab, "JSON Tree")

        # Sincronización entre pestañas
        self.tabWidget.currentChanged.connect(self.onTabChanged)
        self.jsonPreview.textChanged.connect(self.autoUpdateTree)
        self.jsonTree.itemChanged.connect(self.autoUpdateJson)

        layout.addWidget(self.tabWidget)
        self.setLayout(layout)

    def loadJsonFromFile(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Load JSON", "", "JSON Files (*.json);;All Files (*)")
        if filepath:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                json_str = json.dumps(data, indent=2, ensure_ascii=False)
                self.jsonPreview.setPlainText(json_str)
                self.loadTreeFromJson()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error loading JSON:\n{e}")

    def onTabChanged(self, index):
        if self.tabWidget.tabText(index) == "JSON Tree":
            self.loadTreeFromJson()
        elif self.tabWidget.tabText(index) == "JSON":
            self.updateJsonFromTree()

    def loadTreeFromJson(self):
        if self.updating:
            return
        try:
            data = json.loads(self.jsonPreview.toPlainText())
        except Exception:
            return
        self.updating = True
        self.jsonTree.clear()
        self.addItems(self.jsonTree.invisibleRootItem(), data)
        self.jsonTree.expandAll()
        self.updating = False

    def addItems(self, parent, data):
        if isinstance(data, dict):
            for key, value in data.items():
                item = QTreeWidgetItem([str(key), ""])
                if isinstance(value, (dict, list)):
                    self.addItems(item, value)
                else:
                    item.setText(1, str(value))
                    item.setFlags(item.flags() | Qt.ItemIsEditable)
                parent.addChild(item)
        elif isinstance(data, list):
            for index, value in enumerate(data):
                item = QTreeWidgetItem([str(index), ""])
                if isinstance(value, (dict, list)):
                    self.addItems(item, value)
                else:
                    item.setText(1, str(value))
                    item.setFlags(item.flags() | Qt.ItemIsEditable)
                parent.addChild(item)
        else:
            parent.setText(1, str(data))
            parent.setFlags(parent.flags() | Qt.ItemIsEditable)

    def updateJsonFromTree(self):
        if self.updating:
            return
        self.updating = True
        root = self.jsonTree.invisibleRootItem()
        data = self.treeToJson(root)
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        self.jsonPreview.setPlainText(json_str)
        self.updating = False

    def treeToJson(self, parent):
        count = parent.childCount()
        if count == 0:
            return parent.text(1)
        keys = [parent.child(i).text(0) for i in range(count)]
        # Si todas las claves son dígitos, es lista
        if all(k.isdigit() for k in keys):
            lst = []
            for i in range(count):
                lst.append(self.treeToJson(parent.child(i)))
            return lst
        else:
            d = {}
            for i in range(count):
                child = parent.child(i)
                d[child.text(0)] = self.treeToJson(child)
            return d

    def autoUpdateTree(self):
        if self.updating:
            return
        self.loadTreeFromJson()

    def autoUpdateJson(self, item, column):
        if self.updating:
            return
        self.updateJsonFromTree()

    def removeField(self):
        item = self.jsonTree.currentItem()
        if not item:
            return
        parent = item.parent()
        if parent is None:
            return
        index = parent.indexOfChild(item)
        parent.takeChild(index)

    def showContextMenu(self, pos):
        item = self.jsonTree.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        removeAction = menu.addAction("Remove Field")
        action = menu.exec_(self.jsonTree.mapToGlobal(pos))
        if action == removeAction:
            self.removeField()
