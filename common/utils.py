import os
import json
import logging
from datetime import datetime
from PyQt5.QtWidgets import (
    QDialog, QMessageBox, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QPushButton, QTextEdit, QTabWidget, QWidget, QApplication
)

# -------------------------------------------------------------------------
# Configuración de carpeta y fichero de logs
# -------------------------------------------------------------------------
# Directorio base del proyecto
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Directorio para logs
LOG_DIR = os.path.join(BASE_DIR, 'logs')
# Crear directorio si no existe
os.makedirs(LOG_DIR, exist_ok=True)
# Nombre de fichero con fecha y hora actuales
LOGFILE = os.path.join(
    LOG_DIR,
    datetime.now().strftime('%Y%m%d_%H%M%S') + '.json'
)

# Inicializar fichero con plantilla si no existe
if not os.path.exists(LOGFILE):
    initial = {
        "comments": "Registro de mensajes WAMP",
        "source": {"version": "1.0", "tool": "wamPy Tester"},
        "defaulttimeformat": "%Y-%m-%d %H:%M:%S",
        "msg_list": []
    }
    try:
        with open(LOGFILE, 'w', encoding='utf-8') as f:
            json.dump(initial, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logging.error(f"No se pudo crear el fichero de logs: {e}")

# -------------------------------------------------------------------------
# Función para registrar mensajes en el JSON de logs
# -------------------------------------------------------------------------
def log_to_file(timestamp, realm, topic, ip_source, ip_dest, payload):
    """
    Añade una entrada a LOGFILE en "msg_list" con campos:
      - timestamp: { date, time }
      - realm, topic
      - ip_source, ip_dest
      - payload (dict o raw)
    """
    # separar fecha y hora
    try:
        date_str, time_str = timestamp.split(' ', 1)
    except ValueError:
        date_str, time_str = timestamp, ''

    # cargar datos existentes
    try:
        with open(LOGFILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        logging.error(f"Error leyendo {LOGFILE}: {e}")
        return

    # asegurar lista
    entries = data.get('msg_list')
    if not isinstance(entries, list):
        entries = []
        data['msg_list'] = entries

    # construir entrada
    entry = {
        'timestamp': {'date': date_str, 'time': time_str},
        'realm': realm,
        'topic': topic,
        'ip_source': ip_source or '',
        'ip_dest': ip_dest or '',
        'payload': payload if isinstance(payload, dict) else {'raw': str(payload)}
    }
    entries.append(entry)

    # guardar de vuelta
    try:
        with open(LOGFILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logging.error(f"Error escribiendo en {LOGFILE}: {e}")
