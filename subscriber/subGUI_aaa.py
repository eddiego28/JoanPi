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
from common.utils import log_to_file, JsonDetailDialog
from PyQt5.QtWidgets import QTreeWidgetItem

# Utility para asegurar que un directorio exista
def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

# Función auxiliar para extraer el contenido si el mensaje está envuelto solo en args/kwargs
def extract_message(data):
    if isinstance(data, dict):
        keys = set(data.keys())
        if keys.issubset({"args", "kwargs"}):
            if "args" in data and data["args"]:
                if len(data["args"]) == 1:
                    return data["args"][0]
                else:
                    return data["args"]
            elif "kwargs" in data and data["kwargs"]:
                return data["kwargs"]
            else:
                return data
        else:
            return data
    else:
        return data

# Diccionario global para almacenar las sesiones activas (una por realm)
global_sub_sessions = {}  # key: realm, value: session object

# MultiTopicSubscriber: sesión WAMP para suscripción
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
                    lambda *args, topic=t, **kwargs: self.on_event(realm_name, topic, *args, **kwargs),
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

    def on_event(self, realm, topic, *args, **kwargs):
        message_data = {"args": args, "kwargs": kwargs}
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

# start_subscriber: inicia una sesión para cada realm suscrito
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

# JsonDetailTabsDialog: muestra JSON en raw y tree
class JsonDetailTabsDialog(QDialog):
    def __init__(self, data, parent=None):
        super().__init__(parent)
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except:
                pass
        self.raw_json_str = json.dumps(data, indent=2, ensure_ascii=False)
        self.setWindowTitle("JSON Details")
        self.resize(600, 400)
        layout = QVBoxLayout(self)
        copyBtn = QPushButton("Copy JSON")
        copyBtn.clicked.connect(self.copyJson)
        layout.addWidget(copyBtn)

        tabs = QTabWidget()
        # Raw
        rawTab = QWidget()
        rawLayout = QVBoxLayout(rawTab)
        rawText = QTextEdit()
        rawText.setReadOnly(True)
        rawText.setPlainText(self.raw_json_str)
        rawLayout.addWidget(rawText)
        tabs.addTab(rawTab, "Raw JSON")
        # Tree
        treeTab = QWidget()
        treeLayout = QVBoxLayout(treeTab)
        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        self.buildTree(data, tree.invisibleRootItem())
        tree.expandAll()
        treeLayout.addWidget(tree)
        tabs.addTab(treeTab, "Tree View")
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

# SubscriberMessageViewer: visor de mensajes recibidos
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
            data = {"msg": raw_details}
        row = self.table.rowCount()
        self.table.insertRow(row)
        for col, txt in enumerate([timestamp, realm, topic]):
            item = QTableWidgetItem(txt)
            if error:
                item.setForeground(QColor("red"))
            self.table.setItem(row, col, item)
        self.messages.append(data)

    def showDetails(self, item):
        row = item.row()
        dlg = JsonDetailTabsDialog(self.messages[row])
        dlg.setWindowModality(Qt.WindowModal)
        dlg.show()
        self.openDialogs.append(dlg)
        dlg.finished.connect(lambda: self.openDialogs.remove(dlg))

# SubscriberTab: interfaz principal del suscriptor
class SubscriberTab(QWidget):
    messageReceived = pyqtSignal(str, str, str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.realms_topics = {}
        self.selected_topics_by_realm = {}
        self.current_realm = None

        self.checkAllRealms = QCheckBox("All Realms")
        self.checkAllRealms.stateChanged.connect(self.toggleAllRealms)
        self.checkAllTopics = QCheckBox("All Topics")
        self.checkAllTopics.stateChanged.connect(self.toggleAllTopics)
        self.messageReceived.connect(self.onMessageReceived)

        self.initUI()
        self.loadGlobalRealmTopicConfig()

    def initUI(self):
        mainLayout = QHBoxLayout(self)
        left = QVBoxLayout()

        left.addWidget(self.checkAllRealms)
        left.addWidget(QLabel("Realms (checkbox) + Router URL:"))
        self.realmTable = QTableWidget(0, 2)
        self.realmTable.setHorizontalHeaderLabels(["Realm", "Router URL"])
        self.realmTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.realmTable.cellClicked.connect(self.onRealmClicked)
        left.addWidget(self.realmTable)

        realmBtns = QHBoxLayout()
        self.newRealmEdit = QLineEdit()
        self.newRealmEdit.setPlaceholderText("New Realm")
        realmBtns.addWidget(self.newRealmEdit)
        b1 = QPushButton("Add Realm"); b1.clicked.connect(self.addRealmRow)
        realmBtns.addWidget(b1)
        b2 = QPushButton("Remove Realm"); b2.clicked.connect(self.deleteRealmRow)
        realmBtns.addWidget(b2)
        left.addLayout(realmBtns)

        left.addWidget(self.checkAllTopics)
        left.addWidget(QLabel("Topics (checkbox):"))
        self.topicTable = QTableWidget(0, 1)
        self.topicTable.setHorizontalHeaderLabels(["Topic"])
        self.topicTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.topicTable.itemChanged.connect(self.onTopicChanged)
        left.addWidget(self.topicTable)

        topicBtns = QHBoxLayout()
        self.newTopicEdit = QLineEdit()
        self.newTopicEdit.setPlaceholderText("New Topic")
        topicBtns.addWidget(self.newTopicEdit)
        t1 = QPushButton("Add Topic"); t1.clicked.connect(self.addTopicRow)
        topicBtns.addWidget(t1)
        t2 = QPushButton("Remove Topic"); t2.clicked.connect(self.deleteTopicRow)
        topicBtns.addWidget(t2)
        left.addLayout(topicBtns)

        ctl = QHBoxLayout()
        s1 = QPushButton("Subscribe"); s1.clicked.connect(self.confirmAndStartSubscription)
        ctl.addWidget(s1)
        s2 = QPushButton("Stop Subscription"); s2.clicked.connect(self.stopSubscription)
        ctl.addWidget(s2)
        s3 = QPushButton("Reset Log"); s3.clicked.connect(self.resetLog)
        ctl.addWidget(s3)
        left.addLayout(ctl)

        mainLayout.addLayout(left, 1)
        self.viewer = SubscriberMessageViewer(self)
        mainLayout.addWidget(self.viewer, 2)

    def get_config_path(self, subfolder):
        if getattr(sys, 'frozen', False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, 'config', subfolder)

    def loadGlobalRealmTopicConfig(self):
        path = self.get_config_path("realm_topic_config.json")
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data.get("realms"), list):
                    tmp = {}
                    for it in data["realms"]:
                        r = it.get("realm")
                        tmp[r] = {"router_url": it.get("router_url", ""), "topics": it.get("topics", [])}
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
            item = QTableWidgetItem(realm)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.realmTable.setItem(r, 0, item)
            self.realmTable.setItem(r, 1, QTableWidgetItem(info.get("router_url", "")))
        self.realmTable.blockSignals(False)
        if self.realmTable.rowCount()>0:
            self.onRealmClicked(0,0)

    def onRealmClicked(self, row, col):
        realm = self.realmTable.item(row,0).text()
        self.current_realm = realm
        topics = self.realms_topics.get(realm,{}).get("topics",[])
        self.topicTable.blockSignals(True)
        self.topicTable.setRowCount(0)
        if realm not in self.selected_topics_by_realm:
            self.selected_topics_by_realm[realm] = set()
        for t in topics:
            i = self.topicTable.rowCount()
            self.topicTable.insertRow(i)
            it = QTableWidgetItem(t)
            it.setFlags(it.flags()|Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if t in self.selected_topics_by_realm[realm] else Qt.Unchecked)
            self.topicTable.setItem(i,0,it)
        self.topicTable.blockSignals(False)

    def onRealmItemChanged(self, item):
        pass

    def onTopicChanged(self, item):
        if not self.current_realm: return
        sel = set()
        for i in range(self.topicTable.rowCount()):
            it = self.topicTable.item(i,0)
            if it.checkState()==Qt.Checked:
                sel.add(it.text())
        self.selected_topics_by_realm[self.current_realm] = sel

    def addRealmRow(self):
        nr = self.newRealmEdit.text().strip()
        if nr:
            r = self.realmTable.rowCount()
            self.realmTable.insertRow(r)
            it = QTableWidgetItem(nr)
            it.setFlags(it.flags()|Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            self.realmTable.setItem(r,0,it)
            self.realmTable.setItem(r,1,QTableWidgetItem("ws://127.0.0.1:60001"))
            self.newRealmEdit.clear()

    def deleteRealmRow(self):
        to_del=[]
        for r in range(self.realmTable.rowCount()):
            it=self.realmTable.item(r,0)
            if it.checkState()!=Qt.Checked:
                to_del.append(r)
        for r in reversed(to_del):
            self.realmTable.removeRow(r)

    def addTopicRow(self):
        nt=self.newTopicEdit.text().strip()
        if nt:
            r=self.topicTable.rowCount()
            self.topicTable.insertRow(r)
            it=QTableWidgetItem(nt)
            it.setFlags(it.flags()|Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            self.topicTable.setItem(r,0,it)
            self.newTopicEdit.clear()

    def deleteTopicRow(self):
        to_del=[]
        for r in range(self.topicTable.rowCount()):
            it=self.topicTable.item(r,0)
            if it.checkState()!=Qt.Checked:
                to_del.append(r)
        for r in reversed(to_del):
            self.topicTable.removeRow(r)

    def toggleAllRealms(self, state):
        for r in range(self.realmTable.rowCount()):
            it=self.realmTable.item(r,0)
            it.setCheckState(Qt.Checked if state==Qt.Checked else Qt.Unchecked)
        for realm in self.realms_topics:
            self.selected_topics_by_realm[realm] = set(self.realms_topics[realm]["topics"] if state==Qt.Checked else [])

    def toggleAllTopics(self, state):
        if not self.current_realm: return
        for r in range(self.topicTable.rowCount()):
            it=self.topicTable.item(r,0)
            it.setCheckState(Qt.Checked if state==Qt.Checked else Qt.Unchecked)
        if state==Qt.Checked:
            self.selected_topics_by_realm[self.current_realm]=set(self.realms_topics[self.current_realm]["topics"])
        else:
            self.selected_topics_by_realm[self.current_realm]=set()

    def confirmAndStartSubscription(self):
        global global_sub_sessions
        if global_sub_sessions:
            rep=QMessageBox.question(self,"Confirm","Stop existing and start new?",QMessageBox.Yes|QMessageBox.No)
            if rep==QMessageBox.No: return
            else: self.stopSubscription()
        self.startSubscription()

    def startSubscription(self):
        for r in range(self.realmTable.rowCount()):
            it=self.realmTable.item(r,0)
            if it.checkState()==Qt.Checked:
                realm=it.text()
                url=self.realmTable.item(r,1).text()
                sel=self.selected_topics_by_realm.get(realm,set())
                if not sel:
                    sel=set(self.realms_topics.get(realm,{}).get("topics",[]))
                if sel:
                    start_subscriber(url, realm, list(sel), self.handleMessage)
                else:
                    QMessageBox.warning(self,"Warning",f"No topics for {realm}")

    def stopSubscription(self):
        global global_sub_sessions
        for realm,session in list(global_sub_sessions.items()):
            try: session.leave("stop")
            except: pass
            del global_sub_sessions[realm]
        QMessageBox.information(self,"Subscriber","All subscriptions stopped.")

    def handleMessage(self, realm, topic, content):
        ts=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        err=isinstance(content,dict) and "error" in content
        msg=extract_message(content)
        self.messageReceived.emit(realm, topic, ts, json.dumps(msg, ensure_ascii=False))
        log_to_file(ts, realm, topic, json.dumps(msg, ensure_ascii=False))

    @pyqtSlot(str,str,str,object)
    def onMessageReceived(self, realm, topic, timestamp, data_str):
        self.viewer.add_message(realm, topic, timestamp, data_str, error=("error" in data_str))

    def resetLog(self):
        self.viewer.table.setRowCount(0)
        self.viewer.messages=[]

    def getProjectConfig(self):
        lst=[]
        for realm,info in self.realms_topics.items():
            lst.append({"realm":realm,"router_url":info.get("router_url",""),"topics":info.get("topics",[])})
        return {"realms":lst}

    def saveProject(self):
        base=self.get_config_path("projects/subscriber")
        ensure_dir(base)
        fp,_=QFileDialog.getSaveFileName(self,"Save Subscriber Config",base,"JSON Files (*.json)")
        if not fp: return
        try:
            with open(fp,"w",encoding="utf-8") as f:
                json.dump(self.getProjectConfig(),f,indent=2,ensure_ascii=False)
            QMessageBox.information(self,"Subscriber","Saved successfully.")
        except Exception as e:
            QMessageBox.critical(self,"Error",f"{e}")

    def loadProject(self):
        base=self.get_config_path("projects/subscriber")
        ensure_dir(base)
        fp,_=QFileDialog.getOpenFileName(self,"Load Subscriber Config",base,"JSON Files (*.json)")
        if not fp: return
        try:
            with open(fp,"r",encoding="utf-8") as f:
                cfg=json.load(f)
            self.loadProjectFromConfig(cfg)
            QMessageBox.information(self,"Subscriber","Loaded successfully.")
        except Exception as e:
            QMessageBox.critical(self,"Error",f"{e}")

    def loadProjectFromConfig(self, sub_config):
        data=sub_config.get("realms",sub_config)
        if isinstance(data,list):
            tmp={}
            for it in data:
                r=it.get("realm")
                tmp[r]={"router_url":it.get("router_url",""),"topics":it.get("topics",[])}
            data=tmp
        self.realms_topics=data
        self.selected_topics_by_realm={r:set(info["topics"]) for r,info in data.items()}
        self.populateRealmTable()
