
import sys, json
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QHBoxLayout, QPushButton, QVBoxLayout, QFileDialog, QMessageBox, QLabel, QAction
from publisher.pubGUI import PublisherTab
from subscriber.subGUI import SubscriberTab

# Función para cargar el QSS (estilo) desde un archivo externo
def load_stylesheet(app, path):
    try:
        with open(path, "r") as f:
            app.setStyleSheet(f.read())
    except Exception as e:
        print("No se pudo cargar el estilo:", e)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()       
        self.initUI()
        self.showStartupDialog()
        self.setWindowTitle("Aplicación Profesional")
        self.resize(1200, 800)      
        
        
    def initUI(self):
         # Crear la barra de menú
        self.create_menu()

        # Crear un QTabWidget como widget central
        self.tabWidget = QTabWidget()
        self.setCentralWidget(self.tabWidget)

        # Aquí se insertan tus widgets actuales (por ejemplo, PublisherTab, SubscriberTab)
        # Para este ejemplo usaremos pestañas con contenido de ejemplo.
        self.publisherTab = QWidget()
        self.subscriberTab = QWidget()

        # Contenido de la pestaña del publicador
        pub_layout = QVBoxLayout()
        pub_layout.addWidget(QLabel("<h2>Área del Publicador</h2>"))
        # Aquí insertarías tu PublisherTab o el widget correspondiente.
        self.publisherTab.setLayout(pub_layout)

        # Contenido de la pestaña del suscriptor
        sub_layout = QVBoxLayout()
        sub_layout.addWidget(QLabel("<h2>Área del Suscriptor</h2>"))
        # Aquí insertarías tu SubscriberTab o el widget correspondiente.
        self.subscriberTab.setLayout(sub_layout)

        self.tabWidget.addTab(self.publisherTab, "Publicador")
        self.tabWidget.addTab(self.subscriberTab, "Suscriptor")
        centralWidget = QWidget()
        
        mainLayout = QVBoxLayout(centralWidget)
        self.tabs = QTabWidget()
        self.publisherTab = PublisherTab(self)
        self.subscriberTab = SubscriberTab(self)
        self.tabs.addTab(self.publisherTab, "Publicador")
        self.tabs.addTab(self.subscriberTab, "Suscriptor")
        mainLayout.addWidget(self.tabs)

        # Barra de herramientas global para cargar/guardar proyecto
        projLayout = QHBoxLayout()
        self.loadProjButton = QPushButton("Cargar Proyecto")
        self.loadProjButton.clicked.connect(self.loadProject)
        projLayout.addWidget(self.loadProjButton)
        self.saveProjButton = QPushButton("Guardar Proyecto")
        self.saveProjButton.clicked.connect(self.saveProject)
        projLayout.addWidget(self.saveProjButton)
        mainLayout.addLayout(projLayout)

        self.setCentralWidget(centralWidget)

    def showStartupDialog(self):
        reply = QMessageBox.question(self, "Cargar Proyecto", "¿Deseas cargar un proyecto existente?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.loadProject()

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
       

    def create_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("Archivo")

        load_project_action = QAction("Cargar Proyecto", self)
        load_project_action.triggered.connect(self.load_project)
        file_menu.addAction(load_project_action)

        new_project_action = QAction("Nuevo Proyecto", self)
        new_project_action.triggered.connect(self.new_project)
        file_menu.addAction(new_project_action)

        exit_action = QAction("Salir", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

    def load_project(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Cargar Proyecto", "", "JSON Files (*.json);;All Files (*)")
        if filepath:
            # Aquí se implementa la carga de proyecto (ejemplo)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    project = json.load(f)
                QMessageBox.information(self, "Proyecto", f"Proyecto cargado correctamente desde:\n{filepath}")
                # Inserta aquí la lógica para actualizar tus widgets con el proyecto cargado
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo cargar el proyecto:\n{e}")

    def new_project(self):
        # Lógica para iniciar un nuevo proyecto
        QMessageBox.information(self, "Nuevo Proyecto", "Creando un nuevo proyecto...")
        # Aquí podrías reiniciar o limpiar la configuración actual

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

    # Cargar el estilo QSS
    stylesheet_path = os.path.join(os.path.dirname(__file__), "estilo.qss")
    load_stylesheet(app, stylesheet_path)

    # Crear y mostrar la Splash Screen
    splash_pix = QPixmap(400, 300)
    splash_pix.fill(Qt.darkBlue)  # Puedes cargar una imagen en vez de llenar de color
    splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
    splash.showMessage("<h2 style='color: white;'>Cargando...</h2>", Qt.AlignCenter | Qt.AlignBottom, Qt.white)
    splash.show()

    # Simula un proceso de carga (3 segundos)
    QTimer.singleShot(3000, splash.close)

    # Mostrar la ventana principal después de cerrar la Splash Screen
    main_window = MainWindow()
    QTimer.singleShot(3000, main_window.show)

    sys.exit(app.exec_())
