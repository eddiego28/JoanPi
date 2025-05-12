import sys
import os
import json
import datetime
import asyncio
import threading

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QLineEdit, QFileDialog,
    QDialog, QTreeWidget, QComboBox, QSplitter, QGroupBox, QCheckBox,
    QTabWidget, QTextEdit, QApplication
)
from PyQt5.QtCore import Qt, pyqtSlot, pyqtSignal
from PyQt5.QtGui import QColor
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
from common.utils import log_to_file
from PyQt5.QtWidgets import QTreeWidgetItem

# -----------------------------------------------------------------------------
# Utility: asegúrate de que un directorio existe
# -----------------------------------------------------------------------------
def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

# -----------------------------------------------------------------------------
# Extrae el mensaje real si viene envuelto en args/kwargs
# -----------------------------------------------------------------------------
def extract_message(data):
    if isinstance(data, dict):
        keys = set(data.keys())
        if keys.issubset({"args", "kwargs"}):
            if "args" in data and data["args"]:
                return data["args"][0] if len(data["args"]) == 1 else data["args"]
            if "kwargs" in data and data["kwargs"]:
                return data["kwargs"]
    return data

# -----------------------------------------------------------------------------
# Sesión WAMP para suscripción a múltiples topics
# -----------------------------------------------------------------------------
class MultiTopicSubscriber(ApplicationSession):
    def __init__(self, config):
        super().__init__(config)
        self.topics = []
        self.on_message_callback = None
        self.logged = False

    async def onJoin(self, details):
        realm_name = self.config.realm
        global global_sub_sessions
        global_sub_sessions[realm_name] = self
        errors = []
        for t in self.topics:
            try:
                await self.subscribe(
                    lambda *args, topic=t: self.on_event(realm_name, topic, *args),
                    t
                )
            except Exception as e:
                errors.append(f"{t}: {e}")
        if not self.logged:
            self.logged = True
            if errors:
                self.on_message_callback(realm_name, "Subscription", {"error": "Failed: " + ", ".join(errors)})
            else:
                self.on_message_callback(realm_name, "Subscription", {"success": "Subscribed successfully"})

    async def onDisconnect(self):
        realm_name = self.config.realm
        if not self.logged and self.on_message_callback:
            self.on_message_callback(realm_name, "Connection", {"error": "Connection lost"})
            self.logged = True

    def on_event(self, realm, topic, *args):
        message_data = {"args": args}
        if self.on_message_callback:
            self.on_message_callback(realm, topic, message_data)

    @classmethod
    def factory(cls, topics, on_message_callback):
        def create_session(config):
            session = cls(config)
            session.topics = topics
            session.on_message_callback = on_message_callback
            return session
        return create_session

# -----------------------------------------------------------------------------
# Inicia/reinicia una sesión de suscripción
# -----------------------------------------------------------------------------
global_sub_sessions = {}
def start_subscriber(url, realm, topics, on_message_callback):
    global global_sub_sessions
    if realm in global_sub_sessions:
        try:
            global_sub_sessions[realm].leave("Re-subscribing")
        except:
            pass
        del global_sub_sessions[realm]
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        runner = ApplicationRunner(url=url, realm=realm)
        try:
            runner.run(MultiTopicSubscriber.factory(topics, on_message_callback))
        except Exception as e:
            on_message_callback(realm, "Connection", {"error": str(e)})
    threading.Thread(target=run, daemon=True).start()

# -----------------------------------------------------------------------------
# Diálogo JSON Raw/Tree
# -----------------------------------------------------------------------------
class JsonDetailTabsDialog(QDialog):
    def __init__(self, data, parent=None):
        super().__init__(parent)
        if isinstance(data, str):
            try: data = json.loads(data)
            except: pass
        self.raw_json_str = json.dumps(data, indent=2, ensure_ascii=False)
        self.setWindowTitle("JSON Details")
        self.resize(600, 400)
        layout = QVBoxLayout(self)
        copyBtn = QPushButton("Copy JSON")
        copyBtn.clicked.connect(self.copyJson)
        layout.addWidget(copyBtn)
        tabs = QTabWidget()
        rawTab = QWidget(); rl = QVBoxLayout(rawTab)
        rawText = QTextEdit(); rawText.setReadOnly(True); rawText.setPlainText(self.raw_json_str)
        rl.addWidget(rawText); tabs.addTab(rawTab, "Raw JSON")
        treeTab = QWidget(); tl = QVBoxLayout(treeTab)
        tree = QTreeWidget(); tree.setHeaderHidden(True)
        self.buildTree(data, tree.invisibleRootItem()); tree.expandAll()
        tl.addWidget(tree); tabs.addTab(treeTab, "Tree View")
        layout.addWidget(tabs)

    def buildTree(self, data, parent):
        if isinstance(data, dict):
            for k, v in data.items():
                item = QTreeWidgetItem([str(k)])
                parent.addChild(item)
                self.buildTree(v, item)
        elif isinstance(data, list):
            for i, v in enumerate(data):
                item = QTreeWidgetItem([f"[{i}]"])
                parent.addChild(item)
                self.buildTree(v, item)
        else:
            QTreeWidgetItem(parent, [str(data)])

    def copyJson(self):
        QApplication.clipboard().setText(self.raw_json_str)
        QMessageBox.information(self, "Copied", "JSON copied to clipboard.")

# -----------------------------------------------------------------------------
# Tabla de mensajes recibidos
# -----------------------------------------------------------------------------
class SubscriberMessageViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.messages = []
        self.openDialogs = []
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Time", "Realm", "Topic"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.itemDoubleClicked.connect(self.showDetails)
        layout.addWidget(self.table)

    def add_message(self, realm, topic, timestamp, raw_details, error=False):
        try:
            data = json.loads(raw_details) if isinstance(raw_details, str) else raw_details
        except:
            data = {"message": raw_details}
        row = self.table.rowCount()
        self.table.insertRow(row)
        for col, txt in enumerate([timestamp, realm, topic]):
            item = QTableWidgetItem(txt)
            if error: item.setForeground(QColor("red"))
            self.table.setItem(row, col, item)
        self.messages.append(data)

    def showDetails(self, item):
        dlg = JsonDetailTabsDialog(self.messages[item.row()])
        dlg.setWindowModality(Qt.WindowModal)
        dlg.show()
        self.openDialogs.append(dlg)
        dlg.finished.connect(lambda: self.openDialogs.remove(dlg))

# -----------------------------------------------------------------------------
# SubscriberTab: pestaña principal
# -----------------------------------------------------------------------------
class SubscriberTab(QWidget):
    messageReceived = pyqtSignal(str, str, str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.realms_topics = {}          # { realm: {router_url, topics} }
        self.selected_topics_by_realm = {}
        self.current_realm = None

        # Checkboxes globales
        self.checkAllRealms = QCheckBox("All Realms")
        self.checkAllRealms.stateChanged.connect(self.toggleAllRealms)
        self.checkAllTopics = QCheckBox("All Topics")
        self.checkAllTopics.stateChanged.connect(self.toggleAllTopics)

        self.messageReceived.connect(self.onMessageReceived)

        self.initUI()
        self.loadGlobalRealmTopicConfig()

    def initUI(self):
        mainLayout = QHBoxLayout(self)

        # Panel izquierdo: realms/topics
        left = QVBoxLayout()
        left.addWidget(self.checkAllRealms)
        left.addWidget(QLabel("Realms (checkbox) + Router URL:"))

        self.realmTable = QTableWidget(0, 2)
        self.realmTable.setHorizontalHeaderLabels(["Realm", "Router URL"])
        self.realmTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.realmTable.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.realmTable.cellClicked.connect(self.onRealmClicked)
        self.realmTable.itemChanged.connect(self.onRealmItemChanged)
        left.addWidget(self.realmTable)

        realmBtns = QHBoxLayout()
        self.newRealmEdit = QLineEdit(); self.newRealmEdit.setPlaceholderText("New Realm")
        realmBtns.addWidget(self.newRealmEdit)
        realmBtns.addWidget(QPushButton("Add Realm", clicked=self.addRealmRow))
        realmBtns.addWidget(QPushButton("Remove Realm", clicked=self.deleteRealmRow))
        left.addLayout(realmBtns)

        left.addWidget(self.checkAllTopics)
        left.addWidget(QLabel("Topics (checkbox):"))

        self.topicTable = QTableWidget(0, 1)
        self.topicTable.setHorizontalHeaderLabels(["Topic"])
        self.topicTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.topicTable.itemChanged.connect(self.onTopicChanged)
        left.addWidget(self.topicTable)

        topicBtns = QHBoxLayout()
        self.newTopicEdit = QLineEdit(); self.newTopicEdit.setPlaceholderText("New Topic")
        topicBtns.addWidget(self.newTopicEdit)
        topicBtns.addWidget(QPushButton("Add Topic", clicked=self.addTopicRow))
        topicBtns.addWidget(QPushButton("Remove Topic", clicked=self.deleteTopicRow))
        left.addLayout(topicBtns)

        ctrl = QHBoxLayout()
        ctrl.addWidget(QPushButton("Subscribe", clicked=self.confirmAndStartSubscription))
        ctrl.addWidget(QPushButton("Stop Subscription", clicked=self.stopSubscription))
        ctrl.addWidget(QPushButton("Reset Log", clicked=self.resetLog))
        left.addLayout(ctrl)

        mainLayout.addLayout(left, 1)

        # Panel derecho: log de mensajes
        self.viewer = SubscriberMessageViewer(self)
        mainLayout.addWidget(self.viewer, 2)

    def get_config_path(self):
        if getattr(sys, 'frozen', False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, 'projects', 'subscriber')

    def loadGlobalRealmTopicConfig(self):
        cfg_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'realm_topic_config.json')
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data.get("realms"), list):
                    tmp = {}
                    for it in data["realms"]:
                        r = it.get("realm")
                        tmp[r] = {
                            'router_url': it.get("router_url", ""),
                            'topics': it.get("topics", [])
                        }
                    self.realms_topics = tmp
                else:
                    self.realms_topics = data.get("realms", {})
                self.populateRealmTable()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not load config:\n{e}")
        else:
            QMessageBox.warning(self, "Warning", "realm_topic_config.json not found.")

    def populateRealmTable(self):
        self.realmTable.blockSignals(True)
        self.realmTable.setRowCount(0)
        for realm, info in sorted(self.realms_topics.items()):
            r = self.realmTable.rowCount()
            self.realmTable.insertRow(r)
            itm = QTableWidgetItem(realm)
            itm.setFlags(itm.flags() | Qt.ItemIsUserCheckable)
            itm.setCheckState(Qt.Unchecked)
            self.realmTable.setItem(r, 0, itm)
            urlIt = QTableWidgetItem(info.get('router_url', ''))
            urlIt.setFlags(urlIt.flags() | Qt.ItemIsEditable)
            self.realmTable.setItem(r, 1, urlIt)
        self.realmTable.blockSignals(False)
        if self.realmTable.rowCount() > 0:
            self.onRealmClicked(0, 0)

    def onRealmClicked(self, row, col):
        item = self.realmTable.item(row, 0)
        if not item: return
        realm = item.text()
        self.current_realm = realm
        topics = self.realms_topics.get(realm, {}).get('topics', [])
        self.topicTable.blockSignals(True)
        self.topicTable.setRowCount(0)
        sel = self.selected_topics_by_realm.get(realm, set())
        for t in topics:
            i = self.topicTable.rowCount()
            self.topicTable.insertRow(i)
            tit = QTableWidgetItem(t)
            tit.setFlags(tit.flags() | Qt.ItemIsUserCheckable)
            tit.setCheckState(Qt.Checked if t in sel else Qt.Unchecked)
            self.topicTable.setItem(i, 0, tit)
        self.topicTable.blockSignals(False)

    def onRealmItemChanged(self, item):
        if item.column() != 1: return
        realm = self.realmTable.item(item.row(), 0).text().strip()
        new_url = item.text().strip()
        if realm in self.realms_topics:
            self.realms_topics[realm]['router_url'] = new_url

    def addRealmRow(self):
        new_realm = self.newRealmEdit.text().strip()
        if not new_realm or new_realm in self.realms_topics:
            return
        row = self.realmTable.rowCount()
        self.realmTable.insertRow(row)
        itm = QTableWidgetItem(new_realm)
        itm.setFlags(itm.flags() | Qt.ItemIsUserCheckable)
        itm.setCheckState(Qt.Unchecked)
        self.realmTable.setItem(row, 0, itm)
        urlIt = QTableWidgetItem("ws://127.0.0.1:60001")
        urlIt.setFlags(urlIt.flags() | Qt.ItemIsEditable)
        self.realmTable.setItem(row, 1, urlIt)
        self.realms_topics[new_realm] = {'router_url': urlIt.text(), 'topics': []}
        self.selected_topics_by_realm[new_realm] = set()
        self.newRealmEdit.clear()

    def deleteRealmRow(self):
        rows = []
        for r in range(self.realmTable.rowCount()):
            it = self.realmTable.item(r, 0)
            if it and it.checkState() == Qt.Checked:
                rows.append(r)
        for r in reversed(rows):
            realm = self.realmTable.item(r, 0).text().strip()
            self.realmTable.removeRow(r)
            self.realms_topics.pop(realm, None)
            self.selected_topics_by_realm.pop(realm, None)

    def addTopicRow(self):
        new_topic = self.newTopicEdit.text().strip()
        if not new_topic or not self.current_realm:
            return
        row = self.topicTable.rowCount()
        self.topicTable.insertRow(row)
        tit = QTableWidgetItem(new_topic)
        tit.setFlags(tit.flags() | Qt.ItemIsUserCheckable)
        tit.setCheckState(Qt.Unchecked)
        self.topicTable.setItem(row, 0, tit)
        self.realms_topics[self.current_realm]['topics'].append(new_topic)
        self.newTopicEdit.clear()

    def deleteTopicRow(self):
        if not self.current_realm:
            return
        selected_rows = [idx.row() for idx in self.topicTable.selectionModel().selectedRows()]
        for r in sorted(selected_rows, reverse=True):
            topic = self.topicTable.item(r, 0).text().strip()
            self.topicTable.removeRow(r)
            if topic in self.realms_topics[self.current_realm]['topics']:
                self.realms_topics[self.current_realm]['topics'].remove(topic)
            self.selected_topics_by_realm.get(self.current_realm, set()).discard(topic)

    def onTopicChanged(self, item):
        if not self.current_realm:
            return
        sel = set()
        for r in range(self.topicTable.rowCount()):
            it = self.topicTable.item(r, 0)
            if it and it.checkState() == Qt.Checked:
                sel.add(it.text().strip())
        self.selected_topics_by_realm[self.current_realm] = sel
        self.realms_topics[self.current_realm]['topics'] = list(sel)

    def toggleAllRealms(self, state):
        for r in range(self.realmTable.rowCount()):
            it = self.realmTable.item(r, 0)
            it.setCheckState(Qt.Checked if state == Qt.Checked else Qt.Unchecked)
        if state == Qt.Checked:
            self.selected_topics_by_realm = {
                realm: set(info.get('topics', []))
                for realm, info in self.realms_topics.items()
            }
        else:
            self.selected_topics_by_realm = {realm: set() for realm in self.realms_topics}

    def toggleAllTopics(self, state):
        if not self.current_realm:
            return
        for r in range(self.topicTable.rowCount()):
            it = self.topicTable.item(r, 0)
            it.setCheckState(Qt.Checked if state == Qt.Checked else Qt.Unchecked)
        if state == Qt.Checked:
            self.selected_topics_by_realm[self.current_realm] = set(
                self.realms_topics[self.current_realm].get('topics', [])
            )
        else:
            self.selected_topics_by_realm[self.current_realm] = set()

    def confirmAndStartSubscription(self):
        global global_sub_sessions
        if global_sub_sessions:
            reply = QMessageBox.question(
                self, "Confirm",
                "An active subscription exists. Stop it and start a new one?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
            self.stopSubscription()
        self.startSubscription()

    def startSubscription(self):
        for r in range(self.realmTable.rowCount()):
            realm_it = self.realmTable.item(r, 0)
            url_it = self.realmTable.item(r, 1)
            if realm_it.checkState() == Qt.Checked:
                realm = realm_it.text()
                url = url_it.text() if url_it else ""
                topics = list(self.selected_topics_by_realm.get(realm, []))
                if not topics:
                    QMessageBox.warning(self, "Warning", f"No topics selected for '{realm}'.")
                    continue
                start_subscriber(url, realm, topics, self.handleMessage)

    def stopSubscription(self):
        global global_sub_sessions
        if not global_sub_sessions:
            QMessageBox.warning(self, "Warning", "No active subscriptions.")
            return
        for realm, session in list(global_sub_sessions.items()):
            try:
                session.leave("Stop requested")
            except:
                pass
            del global_sub_sessions[realm]
        QMessageBox.information(self, "Subscriber", "All subscriptions stopped.")

    def handleMessage(self, realm, topic, content):
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # extrae payload
        payload = content.get("args", [])
        # registra en JSON log
        log_to_file(
            ts,
            realm=realm,
            topic=topic,
            ip_source="",  # si lo conoces, pásalo aquí
            ip_dest="",    # idem
            payload=payload
        )
        details = json.dumps(payload, indent=2, ensure_ascii=False)
        self.messageReceived.emit(realm, topic, ts, details)

    @pyqtSlot(str, str, str, object)
    def onMessageReceived(self, realm, topic, timestamp, details):
        error = "error" in details
        self.viewer.add_message(realm, topic, timestamp, details, error)

    def resetLog(self):
        self.viewer.table.setRowCount(0)
        self.viewer.messages.clear()

    def getProjectConfig(self):
        realms = []
        for realm, info in self.realms_topics.items():
            realms.append({
                'realm': realm,
                'router_url': info.get('router_url', ''),
                'topics': info.get('topics', [])
            })
        return {'realms': realms}

    def saveProject(self):
        base_dir = self.get_config_path()
        ensure_dir(base_dir)
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Subscriber Config", base_dir, "JSON Files (*.json)"
        )
        if not filepath:
            return
        try:
            config = self.getProjectConfig()
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Subscriber", "Configuration saved.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save:\n{e}")

    def loadProject(self):
        base_dir = self.get_config_path()
        ensure_dir(base_dir)
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Load Subscriber Config", base_dir, "JSON Files (*.json)"
        )
        if not filepath:
            return
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                config = json.load(f)
            self.loadProjectFromConfig(config)
            QMessageBox.information(self, "Subscriber", "Configuration loaded.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load:\n{e}")

    def loadProjectFromConfig(self, config):
        data = config.get('realms', config)
        new_realms = {}
        if isinstance(data, list):
            for it in data:
                realm = it.get('realm')
                if realm:
                    new_realms[realm] = {
                        'router_url': it.get('router_url', ''),
                        'topics': it.get('topics', [])
                    }
        elif isinstance(data, dict):
            new_realms = data
        self.realms_topics = new_realms
        self.selected_topics_by_realm = {
            realm: set(info.get('topics', []))
            for realm, info in new_realms.items()
        }
        self.populateRealmTable()
