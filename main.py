import sys, json
from PyQt5.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QHBoxLayout, QPushButton, QVBoxLayout, QFileDialog, QMessageBox
from publisher.pubGUI import PublisherTab
from subscriber.subGUI import SubscriberTab

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sistema WAMP: Publicador y Suscriptor")
        self.resize(900, 700)
        self.initUI()

    def initUI(self):
        centralWidget = QWidget()
        mainLayout = QVBoxLayout(centralWidget)
        self.tabs = QTabWidget()
        self.publisherTab = PublisherTab(self)
        self.subscriberTab = SubscriberTab(self)
        self.tabs.addTab(self.publisherTab, "Publicador")
        self.tabs.addTab(self.subscriberTab, "Suscriptor")
        mainLayout.addWidget(self.tabs)

        # Botones para cargar y guardar proyecto
        projLayout = QHBoxLayout()
        self.loadProjButton = QPushButton("Cargar Proyecto")
        self.loadProjButton.clicked.connect(self.loadProject)
        projLayout.addWidget(self.loadProjButton)
        self.saveProjButton = QPushButton("Guardar Proyecto")
        self.saveProjButton.clicked.connect(self.saveProject)
        projLayout.addWidget(self.saveProjButton)
        mainLayout.addLayout(projLayout)

        self.setCentralWidget(centralWidget)

    def getProjectConfig(self):
        pub_config = self.publisherTab.getProjectConfig()
        sub_config = self.subscriberTab.getProjectConfigLocal()
        return {"publisher": pub_config, "subscriber": sub_config}

    def loadProject(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Cargar Proyecto", "", "JSON Files (*.json);;All Files (*)")
        if not filepath:
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                proj = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo cargar el proyecto:\n{e}")
            return
        pub_config = proj.get("publisher", {})
        self.publisherTab.loadProjectFromConfig(pub_config)
        sub_config = proj.get("subscriber", {})
        self.subscriberTab.loadProjectFromConfig(sub_config)
        QMessageBox.information(self, "Proyecto", "Proyecto cargado correctamente.")

    def saveProject(self):
        proj_config = self.getProjectConfig()
        filepath, _ = QFileDialog.getSaveFileName(self, "Guardar Proyecto", "", "JSON Files (*.json);;All Files (*)")
        if not filepath:
            return
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(proj_config, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Proyecto", "Proyecto guardado correctamente.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo guardar el proyecto:\n{e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
