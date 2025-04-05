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

def load_stylesheet(app, stylesheet_path):
    try:
        with open(stylesheet_path, "r") as f:
            app.setStyleSheet(f.read())
    except Exception as e:
        print("❌ Error loading stylesheet:", e)

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

        loadAct = QAction("Load Project", self)
        loadAct.triggered.connect(self.loadProject)
        saveAct = QAction("Save Project", self)
        saveAct.triggered.connect(self.saveProject)
        aboutAct = QAction("About", self)
        aboutAct.triggered.connect(lambda: QMessageBox.information(
            self, "About", "wamPy v1.0\nDeveloped by Enrique de Diego Henar"))
        self.toolbar.addAction(loadAct)
        self.toolbar.addAction(saveAct)
        self.toolbar.addAction(aboutAct)

    def loadProject(self):
        self.publisherTab.loadProject()

    def saveProject(self):
        self.publisherTab.saveProject()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Icono de la ventana
    icon_path = get_resource_path(os.path.join("icons", "logo_wampy.png"))
    app.setWindowIcon(QIcon(icon_path))

    # Splash screen
    splash = create_splash_screen()
    if splash:
        splash.show()

    # Mostrar ventana principal después del splash screen
    main_window = MainWindow()
    QTimer.singleShot(5000, splash.close)
    QTimer.singleShot(5000, main_window.show)

    sys.exit(app.exec_())
