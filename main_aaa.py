import sys, os, json, datetime, logging, asyncio, threading
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QToolBar, QAction, QTabWidget, QWidget,
    QVBoxLayout, QSplashScreen, QMessageBox, QFileDialog
)
from PyQt5.QtCore import Qt, QTimer, QSize
from PyQt5.QtGui import QPixmap, QPainter, QColor, QIcon
from publisher.pubGUI import PublisherTab
from subscriber.subGUI import SubscriberTab

# Función para acceder a recursos correctamente en .py y .exe
def get_resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

# Utility para asegurar que un directorio exista
def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

# Función para cargar la hoja de estilos (opcional)
def load_stylesheet(app, stylesheet_path):
    try:
        with open(stylesheet_path, "r") as f:
            app.setStyleSheet(f.read())
    except Exception as e:
        print("❌ Error loading stylesheet:", e)

# Función para crear la pantalla de splash
def create_splash_screen():
    width, height = 700, 400
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor("#007ACC"))

    painter = QPainter(pixmap)

    # Logo principal
    logo_path = get_resource_path(os.path.join("icons", "logo_wampy.png"))
    logo = QPixmap(logo_path)
    if not logo.isNull():
        logo = logo.scaled(450, 290, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = (width - logo.width()) // 2
        y = 80
        painter.drawPixmap(x, y, logo)
    else:
        print("❌ Error: Could not load image:", logo_path)

    # Icono secundario
    icon_path = get_resource_path(os.path.join("icons", "open.png"))
    icon = QPixmap(icon_path)
    if not icon.isNull():
        icon = icon.scaled(200, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = (width - icon.width()) // 2
        y = 20
        painter.drawPixmap(x, y, icon)
    else:
        print("❌ Error: Could not load image:", icon_path)

    painter.end()

    splash = QSplashScreen(pixmap, Qt.WindowStaysOnTopHint)
    splash.showMessage("<h1 style='color: #000000;'>Loading...</h1>",
                       Qt.AlignCenter | Qt.AlignBottom, Qt.white)
    return splash

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("wamPy Tester v1.0 - Publisher and Subscriber Tool")
        self.resize(1000, 800)
        self.initUI()

    def initUI(self):
        self.createToolBar()
        centralWidget = QWidget()
        mainLayout = QVBoxLayout(centralWidget)
        self.tabs = QTabWidget()
        self.publisherTab = PublisherTab(self)
        self.subscriberTab = SubscriberTab(self)
        self.tabs.addTab(self.publisherTab, "Publisher")
        self.tabs.addTab(self.subscriberTab, "Subscriber")
        mainLayout.addWidget(self.tabs)
        self.setCentralWidget(centralWidget)

    def createToolBar(self):
        self.toolbar = QToolBar("Main Toolbar")
        self.toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)

        # Acciones separadas
        loadPubAct = QAction("Load Publisher", self)
        loadPubAct.triggered.connect(self.publisherTab.loadProject)
        loadSubAct = QAction("Load Subscriber", self)
        loadSubAct.triggered.connect(self.subscriberTab.loadProject)
        loadProjAct = QAction("Load Project", self)
        loadProjAct.triggered.connect(self.loadProject)

        savePubAct = QAction("Save Publisher", self)
        savePubAct.triggered.connect(self.publisherTab.saveProject)
        saveSubAct = QAction("Save Subscriber", self)
        saveSubAct.triggered.connect(self.subscriberTab.saveProject)
        saveProjAct = QAction("Save Project", self)
        saveProjAct.triggered.connect(self.saveProject)

        aboutAct = QAction("About", self)
        aboutAct.triggered.connect(lambda: QMessageBox.information(
            self, "About", "wamPy v1.0\nDeveloped by Enrique de Diego Henar"))

        self.toolbar.addAction(loadPubAct)
        self.toolbar.addAction(loadSubAct)
        self.toolbar.addAction(loadProjAct)
        self.toolbar.addAction(savePubAct)
        self.toolbar.addAction(saveSubAct)
        self.toolbar.addAction(saveProjAct)
        self.toolbar.addAction(aboutAct)

    def saveProject(self):
        """Guarda configuración combinada de Publisher y Subscriber en un JSON."""
        base_dir = get_resource_path(os.path.join('config', 'projects'))
        ensure_dir(base_dir)
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Project", base_dir, "JSON Files (*.json)")
        if not filepath:
            return
        project = {
            "publisher": self.publisherTab.getProjectConfig(),
            "subscriber": self.subscriberTab.getProjectConfig()
        }
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(project, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Project", "Combined project saved successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save project:\n{e}")

    def loadProject(self):
        """Carga configuración combinada de Publisher y Subscriber desde un JSON."""
        base_dir = get_resource_path(os.path.join('config', 'projects'))
        ensure_dir(base_dir)
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Load Project", base_dir, "JSON Files (*.json)")
        if not filepath:
            return
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                project = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load project:\n{e}")
            return
        self.publisherTab.loadProjectFromConfig(project.get('publisher', {}))
        self.subscriberTab.loadProjectFromConfig(project.get('subscriber', {}))
        QMessageBox.information(self, "Project", "Combined project loaded successfully.")

if __name__ == "__main__":
    app = QApplication(sys.argv)

    icon_path = get_resource_path(os.path.join("icons", "logo_wampy.png"))
    app.setWindowIcon(QIcon(icon_path))

    # Opcional: cargar stylesheet si se desea
    # load_stylesheet(app, get_resource_path("styles.qss"))

    splash = create_splash_screen()
    if splash:
        splash.show()

    main_window = MainWindow()
    QTimer.singleShot(5000, splash.close)
    QTimer.singleShot(5000, main_window.show)

    sys.exit(app.exec_())
