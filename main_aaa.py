import sys
import os
import json
import datetime
import logging
import asyncio
import threading

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QToolBar, QToolButton, QAction, QMenu,
    QTabWidget, QWidget, QVBoxLayout, QSplashScreen, QMessageBox, QFileDialog
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

# Función para crear la pantalla de splash (igual que tu versión original)
def create_splash_screen():
    width, height = 700, 400
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor("#007ACC"))

    painter = QPainter(pixmap)

    logo_path = get_resource_path(os.path.join("icons", "logo_wampy.png"))
    logo = QPixmap(logo_path)
    if not logo.isNull():
        logo = logo.scaled(450, 290, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = (width - logo.width()) // 2
        y = 80
        painter.drawPixmap(x, y, logo)

    icon_path = get_resource_path(os.path.join("icons", "open.png"))
    icon = QPixmap(icon_path)
    if not icon.isNull():
        icon = icon.scaled(200, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = (width - icon.width()) // 2
        y = 20
        painter.drawPixmap(x, y, icon)

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

        # --- Load Menu ---
        loadBtn = QToolButton(self)
        loadBtn.setText("Load")
        loadMenu = QMenu(self)
        projLoad = QAction("Project", self)
        projLoad.triggered.connect(self.loadProject)
        pubLoad = QAction("Publisher", self)
        pubLoad.triggered.connect(self.publisherTab.loadProject)
        subLoad = QAction("Subscriber", self)
        subLoad.triggered.connect(self.subscriberTab.loadProject)
        loadMenu.addAction(projLoad)
        loadMenu.addAction(pubLoad)
        loadMenu.addAction(subLoad)
        loadBtn.setMenu(loadMenu)
        loadBtn.setPopupMode(QToolButton.InstantPopup)
        self.toolbar.addWidget(loadBtn)

        # --- Save Menu ---
        saveBtn = QToolButton(self)
        saveBtn.setText("Save")
        saveMenu = QMenu(self)
        projSave = QAction("Project", self)
        projSave.triggered.connect(self.saveProject)
        pubSave = QAction("Publisher", self)
        pubSave.triggered.connect(self.publisherTab.saveProject)
        subSave = QAction("Subscriber", self)
        subSave.triggered.connect(self.subscriberTab.saveProject)
        saveMenu.addAction(projSave)
        saveMenu.addAction(pubSave)
        saveMenu.addAction(subSave)
        saveBtn.setMenu(saveMenu)
        saveBtn.setPopupMode(QToolButton.InstantPopup)
        self.toolbar.addWidget(saveBtn)

        # --- About Menu ---
        aboutBtn = QToolButton(self)
        aboutBtn.setText("About")
        aboutMenu = QMenu(self)
        aboutAct = QAction("About", self)
        aboutAct.triggered.connect(lambda: QMessageBox.information(
            self, "About", "wamPy v1.0\nDeveloped by Enrique de Diego Henar"))
        aboutMenu.addAction(aboutAct)
        aboutBtn.setMenu(aboutMenu)
        aboutBtn.setPopupMode(QToolButton.InstantPopup)
        self.toolbar.addWidget(aboutBtn)

        # --- Help Button ---
        helpAct = QAction("Help", self)
        helpAct.triggered.connect(self.showHelp)
        self.toolbar.addAction(helpAct)

    def showHelp(self):
        QMessageBox.information(self, "Help",
            "Use the Load/Save menus to manage Publisher, Subscriber or full Project configurations.\n"
            "Load → Project opens 'config/projects',\n"
            "Load → Publisher opens 'config/projects/publisher',\n"
            "Load → Subscriber opens 'config/projects/subscriber'."
        )

    def saveProject(self):
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
    splash = create_splash_screen()
    if splash:
        splash.show()
    main_window = MainWindow()
    QTimer.singleShot(5000, splash.close)
    QTimer.singleShot(5000, main_window.show)
    sys.exit(app.exec_())
