import sys, os, json, datetime, logging, asyncio, threading
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QToolBar, QAction, QTabWidget, QWidget,
    QVBoxLayout, QSplashScreen, QMessageBox, QFileDialog, QSplashScreen
)
from PyQt5.QtCore import Qt, QTimer, QSize
from PyQt5.QtGui import QPixmap, QPainter, QColor, QIcon
from publisher.pubGUI import PublisherTab
from subscriber.subGUI import SubscriberTab

def load_stylesheet(app, stylesheet_path):
    try:
        with open(stylesheet_path, "r") as f:
            app.setStyleSheet(f.read())
    except Exception as e:
        print("Error loading stylesheet:", e)

def create_splash_screen():
    # Splash screen size
    width, height = 700, 400
    # Create a pixmap with a pale blue background
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor("#007ACC"))
    
    icon_path = os.path.join(os.path.dirname(__file__), "icons", "logo_wampy.png")
    icon = QPixmap(icon_path)
    if not icon.isNull():
        # Scale the icon and center it at the top with some margin
        icon = icon.scaled(400, 270, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = (width - icon.width()) // 2
        y = 80  # top margin
        painter = QPainter(pixmap)
        painter.drawPixmap(x, y, icon)
        painter.end()
    else:
        print("Error: Could not load image:", icon_path)
    
    # Load and scale the icon image from "icons/open.png"
    icon_path = os.path.join(os.path.dirname(__file__), "icons", "open.png")
    icon = QPixmap(icon_path)
    if not icon.isNull():
        # Scale the icon and center it at the top with some margin
        icon = icon.scaled(200, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = (width - icon.width()) // 2
        y = 20  # top margin
        painter = QPainter(pixmap)
        painter.drawPixmap(x, y, icon)
        painter.end()
    else:
        print("Error: Could not load image:", icon_path)
    
   
    
    splash = QSplashScreen(pixmap, Qt.WindowStaysOnTopHint)
    splash.showMessage("<h1 style='color: #000000 ;'>Loading...</h1>", 
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
        # Only two tabs: Publisher and Subscriber
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
        
        # Toolbar actions without extra buttons below the toolbar
        loadAct = QAction("Load Project", self)
        loadAct.triggered.connect(self.loadProject)
        saveAct = QAction("Save Project", self)
        saveAct.triggered.connect(self.saveProject)
        aboutAct = QAction("About", self)
        aboutAct.triggered.connect(lambda: QMessageBox.information(self, "About", "wamPy v1.0\nDeveloped by Enrique de Diego Henar"))
        self.toolbar.addAction(loadAct)
        self.toolbar.addAction(saveAct)
        self.toolbar.addAction(aboutAct)

    def loadProject(self):
        self.publisherTab.loadProject()

    def saveProject(self):
        self.publisherTab.saveProject()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    icon_path = os.path.join(os.path.dirname(__file__), "icons", "logo_wampy.png")
    app.setWindowIcon(QIcon(icon_path))
    stylesheet_path = os.path.join(os.path.dirname(__file__), "estilo.qss")
    load_stylesheet(app, stylesheet_path)
    
    splash = create_splash_screen()
    splash.show()
    QTimer.singleShot(5000, splash.close)
    
    main_window = MainWindow()
    QTimer.singleShot(5000, main_window.show)
    sys.exit(app.exec_())
