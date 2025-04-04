import os
import json
import datetime
import logging
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QFileDialog, QMessageBox, QTreeWidget, QTreeWidgetItem

# Obtener la ruta del directorio actual (donde se encuentra este archivo utils.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Definir el directorio de logs: se creará en la raíz del proyecto en una carpeta llamada "logs"
LOG_DIR = os.path.join(BASE_DIR, "..", "logs")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Crear un nombre para el fichero de log basado en la fecha y hora actuales
LOG_FILENAME = os.path.join(LOG_DIR, f"log_{datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')}.txt")

# Configurar el logger
logger = logging.getLogger("FileLogger")
logger.setLevel(logging.INFO)

# Crear un FileHandler para escribir en el archivo de log, usando UTF-8
file_handler = logging.FileHandler(LOG_FILENAME, encoding="utf-8")
formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

def log_to_file(time_str, realm, topic, message_json):
    """
    Escribe una entrada en el log con el siguiente formato:
    
    [time_str] | Realm: [realm] | Topic: [topic]
    [message_json formateado]
    
    Se añade una línea en blanco al final para separar entradas.
    """
    entry = f"{time_str} | Realm: {realm} | Topic: {topic}\n{message_json}\n\n"
    logger.info(entry)

class JsonDetailDialog(QDialog):
    """
    Diálogo para mostrar el contenido del JSON formateado.
    """
    def __init__(self, message_details, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Detalle JSON")
        self.resize(600, 400)
        layout = QVBoxLayout(self)
        self.textEdit = QTextEdit(self)
        self.textEdit.setReadOnly(True)
        json_str = json.dumps(message_details, indent=2, ensure_ascii=False)
        self.textEdit.setPlainText(json_str)
        layout.addWidget(self.textEdit)
        self.setLayout(layout)

def build_tree_items(data):
    """
    Construye recursivamente una lista de QTreeWidgetItem a partir de un diccionario o lista.
    Cada item muestra la clave en la primera columna y, si es un valor simple, lo muestra en la segunda.
    """
    items = []
    if isinstance(data, dict):
        for key, value in data.items():
            item = QTreeWidgetItem([str(key), ""])
            if isinstance(value, (dict, list)):
                children = build_tree_items(value)
                item.addChildren(children)
            else:
                item.setText(1, str(value))
            items.append(item)
    elif isinstance(data, list):
        for i, value in enumerate(data):
            item = QTreeWidgetItem([f"[{i}]", ""])
            if isinstance(value, (dict, list)):
                children = build_tree_items(value)
                item.addChildren(children)
            else:
                item.setText(1, str(value))
            items.append(item)
    else:
        items.append(QTreeWidgetItem([str(data), ""]))
    return items
