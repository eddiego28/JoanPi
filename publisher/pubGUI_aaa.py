import sys
import os
import json
import datetime
import logging
import asyncio
import threading

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QPushButton, QSplitter,
    QGroupBox, QFormLayout, QMessageBox, QLineEdit, QFileDialog, QComboBox, QCheckBox, QTreeWidget, 
    QTreeWidgetItem, QDialog, QTextEdit, QTabWidget)

from PyQt5.QtCore import Qt, QTimer, QSize
from PyQt5.QtGui import QIcon, QColor
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
from common.utils import log_to_file, JsonDetailDialog

from .pubEditor import PublisherEditorWidget

# Utility para asegurar que un directorio exista
def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

# --------------------------
# REALMS AND TOPICS CONFIGURATION
# --------------------------
REALMS_CONFIG = {}
def load_realm_topic_config():
    global REALMS_CONFIG
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        cfg_path = os.path.join(base, "..", "config", "realm_topic_config_pub.json")
        with open(cfg_path,'r',encoding='utf-8') as f:
            cfg=json.load(f)
        if isinstance(cfg.get("realms"),list):
            tmp={}
            for it in cfg["realms"]:
                r=it.get("realm","default")
                tmp[r]={"router_url":it.get("router_url","ws://127.0.0.1:60001"),"topics":it.get("topics",[])}
            REALMS_CONFIG=tmp
        else:
            REALMS_CONFIG=cfg.get("realms",{})
    except:
        REALMS_CONFIG={"default":{"router_url":"ws://127.0.0.1:60001","topics":[]}}
load_realm_topic_config()

# GLOBAL DICT for publisher sessions
global_pub_sessions = {}

class JSONPublisher(ApplicationSession):
    def __init__(self, config, topic, widget):
        super().__init__(config)
        self.topic = topic
        self.widget = widget

    async def onJoin(self, details):
        self.loop = asyncio.get_event_loop()
        self.widget.session = self
        self.widget.loop = self.loop
        global global_pub_sessions
        global_pub_sessions[self.config.realm] = self
        await asyncio.Future()

def start_publisher(url, realm, topic, widget):
    global global_pub_sessions
    if realm in global_pub_sessions:
        widget.session = global_pub_sessions[realm]
        widget.loop = widget.session.loop
    else:
        def run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            runner = ApplicationRunner(url=url, realm=realm)
            runner.run(lambda cfg: JSONPublisher(cfg, topic, widget))
        threading.Thread(target=run, daemon=True).start()

def send_message_now(session, loop, topic, message, delay=0):
    async def _send():
        if delay>0: await asyncio.sleep(delay)
        if isinstance(message,dict):
            session.publish(topic, **message)
        else:
            session.publish(topic, message)
        ts=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_to_file(ts, topic, session.config.realm, json.dumps(message,indent=2,ensure_ascii=False))
    if session and loop:
        asyncio.run_coroutine_threadsafe(_send(), loop)

class JsonDetailTabsDialog(QDialog):
    def __init__(self, data, parent=None):
        super().__init__(parent)
        if isinstance(data,str):
            try: data=json.loads(data)
            except: pass
        self.setWindowTitle("JSON Details")
        self.resize(600,400)
        layout=QVBoxLayout(self)
        tabs=QTabWidget()
        raw=QWidget(); rl=QVBoxLayout(raw)
        txt=QTextEdit(); txt.setReadOnly(True); txt.setPlainText(json.dumps(data,indent=2,ensure_ascii=False))
        rl.addWidget(txt); tabs.addTab(raw,"Raw JSON")
        tree=QWidget(); tl=QVBoxLayout(tree)
        tw=QTreeWidget(); tw.setHeaderHidden(True)
        self._buildTree(data,tw.invisibleRootItem()); tw.expandAll()
        tl.addWidget(tw); tabs.addTab(tree,"Tree View")
        layout.addWidget(tabs)

    def _buildTree(self,data,parent):
        if isinstance(data,dict):
            for k,v in data.items():
                it=QTreeWidgetItem([str(k)]); parent.addChild(it)
                self._buildTree(v,it)
        elif isinstance(data,list):
            for i,v in enumerate(data):
                it=QTreeWidgetItem([f"[{i}]"]); parent.addChild(it)
                self._buildTree(v,it)
        else:
            QTreeWidgetItem(parent,[str(data)])

class PublisherMessageViewer(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.logs=[]
        layout=QVBoxLayout(self)
        self.table=QTableWidget(0,3)
        self.table.setHorizontalHeaderLabels(["Time","Realm","Topic"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.itemDoubleClicked.connect(self.showDetails)
        layout.addWidget(self.table)

    def add_message(self, realm, topic, timestamp, details, error=False):
        r=self.table.rowCount(); self.table.insertRow(r)
        for i,txt in enumerate([timestamp,realm,topic]):
            it=QTableWidgetItem(txt)
            if error: it.setForeground(QColor("red"))
            self.table.setItem(r,i,it)
        self.logs.append(details)

    def showDetails(self,item):
        d=self.logs[item.row()]
        dlg=JsonDetailTabsDialog(d)
        dlg.show()

class MessageConfigWidget(QWidget):
    def __init__(self,msg_id,parent=None):
        super().__init__(parent)
        self.msg_id=msg_id
        self.session=None; self.loop=None
        self.initUI()

    def initUI(self):
        layout=QVBoxLayout(self)
        # header
        hdr=QHBoxLayout()
        self.enable=QCheckBox(); self.enable.setChecked(True)
        self.enable.stateChanged.connect(self.onEnableChanged)
        hdr.addWidget(self.enable)
        self.lbl=QLabel(f"Message #{self.msg_id}")
        hdr.addWidget(self.lbl); hdr.addStretch()
        self.minBtn=QPushButton("–"); self.minBtn.clicked.connect(self.toggleMinimize)
        hdr.addWidget(self.minBtn)
        self.delBtn=QPushButton("Delete"); self.delBtn.clicked.connect(self.deleteSelf)
        hdr.addWidget(self.delBtn)
        layout.addLayout(hdr)
        # content
        self.content=QWidget(); cl=QVBoxLayout(self.content)
        # Connection
        cg=QGroupBox("Connection Settings"); fl=QFormLayout()
        self.realmCombo=QComboBox(); self.realmCombo.addItems(list(REALMS_CONFIG.keys()))
        self.realmCombo.currentTextChanged.connect(self.updateTopics)
        fl.addRow("Realm:",self.realmCombo)
        self.urlEdit=QLineEdit(); fl.addRow("Router URL:",self.urlEdit)
        self.topicCombo=QComboBox(); fl.addRow("Topic:",self.topicCombo)
        cg.setLayout(fl); cl.addWidget(cg)
        # Message
        mg=QGroupBox("Message Content"); ml=QVBoxLayout()
        self.editor=PublisherEditorWidget(self)
        ml.addWidget(self.editor)
        mg.setLayout(ml); cl.addWidget(mg)
        layout.addWidget(self.content)
        # Send button
        btn=QPushButton("Send Now"); btn.clicked.connect(self.sendMessage)
        layout.addWidget(btn)
        self.setLayout(layout)
        self.editor.onDemandRadio.toggled.connect(self.onDemandToggled)
        self.updateTopics(self.realmCombo.currentText())

    def onEnableChanged(self,st):
        self.content.setDisabled(st!=Qt.Checked)

    def toggleMinimize(self):
        vis=not self.content.isVisible()
        self.content.setVisible(vis)
        self.minBtn.setText("+" if not vis else "–")

    def deleteSelf(self):
        parent=self.parent()
        parent.removeMessageWidget(self)

    def onDemandToggled(self,checked):
        self.editor.commonTimeEdit.setDisabled(checked)

    def updateTopics(self, realm):
        topics=REALMS_CONFIG.get(realm,{}).get("topics",[])
        self.topicCombo.clear(); self.topicCombo.addItems(topics)
        self.urlEdit.setText(REALMS_CONFIG.get(realm,{}).get("router_url",""))

    def sendMessage(self):
        # similar lógica a la tuya, omito detalles por brevedad
        pass

    def getConfig(self):
        mode="onDemand"
        if self.editor.programmedRadio.isChecked(): mode="programmed"
        elif self.editor.SystemRadioTime.isChecked(): mode="systemTime"
        return {
            "id":self.msg_id,
            "realm":self.realmCombo.currentText(),
            "router_url":self.urlEdit.text(),
            "topic":self.topicCombo.currentText(),
            "content":json.loads(self.editor.jsonPreview.toPlainText()),
            "mode":mode,
            "time":self.editor.commonTimeEdit.text()
        }

class PublisherTab(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.msgWidgets=[]
        self.next_id=1
        self.initUI()

    def initUI(self):
        splitter=QSplitter(Qt.Horizontal)
        # Left
        left=QWidget(); ll=QVBoxLayout(left)
        hl=QHBoxLayout()
        self.startBtn=QPushButton("Start Publisher"); hl.addWidget(self.startBtn)
        self.stopBtn=QPushButton("Stop Publisher"); hl.addWidget(self.stopBtn)
        ll.addLayout(hl)
        self.viewer=PublisherMessageViewer(self); ll.addWidget(self.viewer)
        splitter.addWidget(left)
        # Right
        right=QWidget(); rl=QVBoxLayout(right)
        add=QPushButton("Add Message"); add.clicked.connect(self.addMessage)
        rl.addWidget(add)
        self.msgArea=QScrollArea(); self.msgArea.setWidgetResizable(True)
        self.msgContainer=QWidget(); self.msgLayout=QVBoxLayout(self.msgContainer)
        self.msgArea.setWidget(self.msgContainer); rl.addWidget(self.msgArea)
        bl=QHBoxLayout()
        self.scenarioBtn=QPushButton("Start Scenario"); bl.addWidget(self.scenarioBtn)
        self.instantBtn=QPushButton("Send Instant Message"); bl.addWidget(self.instantBtn)
        rl.addLayout(bl)
        splitter.addWidget(right)
        splitter.setSizes([300,600])
        m=QVBoxLayout(self); m.addWidget(splitter)
        # conexiones
        self.startBtn.clicked.connect(self.confirmAndStartPublisher)
        self.stopBtn.clicked.connect(self.stopAllPublishers)
        self.scenarioBtn.clicked.connect(self.startScenario)
        self.instantBtn.clicked.connect(self.sendAllAsync)

    def get_config_path(self,sub):
        if getattr(sys,'frozen',False):
            base=os.path.dirname(sys.executable)
        else:
            base=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base,'config',sub)

    def addMessage(self):
        w=MessageConfigWidget(self.next_id,self)
        self.msgLayout.addWidget(w)
        self.msgWidgets.append(w)
        self.next_id+=1

    def confirmAndStartPublisher(self):
        global global_pub_sessions
        if global_pub_sessions:
            r=QMessageBox.question(self,"Confirm","Stop existing and start new?",QMessageBox.Yes|QMessageBox.No)
            if r==QMessageBox.No: return
            self.stopAllPublishers()
        self.startPublisher()

    def startPublisher(self):
        for w in self.msgWidgets:
            cfg=w.getConfig()
            start_publisher(cfg["router_url"],cfg["realm"],cfg["topic"],w)
            QTimer.singleShot(500,lambda w=w,c=cfg: self.logStarted(w,c))

    def logStarted(self,w,cfg):
        ts=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not w.session:
            self.viewer.add_message(cfg["realm"],cfg["topic"],ts,"Failed to start",True)
        else:
            self.viewer.add_message(cfg["realm"],cfg["topic"],ts,"Started")

    def stopAllPublishers(self):
        global global_pub_sessions
        for r,s in list(global_pub_sessions.items()):
            try:s.leave("stop")
            except:pass
            del global_pub_sessions[r]
        QMessageBox.information(self,"Publisher","All stopped.")

    def sendAllAsync(self):
        for w in self.msgWidgets:
            cfg=w.getConfig()
            send_message_now(w.session,w.loop,cfg["topic"],cfg["content"],0)
            ts=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.viewer.add_message(cfg["realm"],cfg["topic"],ts,json.dumps(cfg["content"],indent=2),False)

    def startScenario(self):
        # implementación análoga a tu versión original
        pass

    def loadProject(self):
        base=self.get_config_path("projects")
        ensure_dir(base)
        fp,_=QFileDialog.getOpenFileName(self,"Load Publisher Config",base,"JSON Files (*.json)")
        if not fp:return
        with open(fp,'r',encoding='utf-8') as f:
            cfg=json.load(f)
        self.loadProjectFromConfig(cfg)
        QMessageBox.information(self,"Publisher","Loaded.")

    def loadProjectFromConfig(self,cfg):
        # similar al code anterior
        pass

    def saveProject(self):
        base=self.get_config_path("projects/publisher")
        ensure_dir(base)
        fp,_=QFileDialog.getSaveFileName(self,"Save Publisher Config",base,"JSON Files (*.json)")
        if not fp:return
        with open(fp,'w',encoding='utf-8') as f:
            json.dump(self.getProjectConfig(),f,indent=2,ensure_ascii=False)
        QMessageBox.information(self,"Publisher","Saved.")

    def getProjectConfig(self):
        return {"scenarios":[w.getConfig() for w in self.msgWidgets]}
