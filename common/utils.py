# common/utils.py
import os, json, datetime, logging
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QFileDialog, QMessageBox, QTreeWidget, QTreeWidgetItem

# Configuración básica de logging
LOG_FILENAME = f"log_{datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')}.txt"
file_logger = logging.getLogger("FileLogger")
file_logger.setLevel(logging.INFO)
fh = logging.FileHandler(LOG_FILENAME, encoding="utf-8")
fh.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
file_logger.addHandler(fh)

def log_to_file(time_str, topic, realm, message_json):
    entry = f"{time_str} | Topic: {topic} | Realm: {realm}\n{message_json}\n"
    file_logger.info(entry)

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
