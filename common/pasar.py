import os, json, logging
from datetime import datetime
from abc import ABC, abstractmethod

class ILogger(ABC):
    @abstractmethod
    def log(self, timestamp, realm, topic, ip_source, ip_dest, payload):
        pass

class JSONLogger(ILogger):
    """Implementación de ILogger que vuelca a un JSON en /logs"""
    def __init__(self, base_dir=None):
        bd = base_dir or os.path.dirname(os.path.dirname(__file__))
        self.log_dir = os.path.join(bd, 'logs')
        os.makedirs(self.log_dir, exist_ok=True)
        self.filepath = os.path.join(
            self.log_dir,
            datetime.now().strftime('%Y%m%d_%H%M%S') + '.json'
        )
        self._init_file()

    def _init_file(self):
        template = {
            "comments": "Registro de mensajes WAMP",
            "source": {"version": "1.0", "tool": "wamPy Tester"},
            "defaulttimeformat": "%Y-%m-%d %H:%M:%S",
            "msg_list": []
        }
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(template, f, indent=2, ensure_ascii=False)

    def log(self, timestamp, realm, topic, ip_source, ip_dest, payload):
        with open(self.filepath, 'r+', encoding='utf-8') as f:
            data = json.load(f)
            entries = data.setdefault('msg_list', [])
            date_str, time_str = timestamp.split(' ',1) if ' ' in timestamp else (timestamp, '')
            entry = {
                'timestamp': {'date': date_str,'time': time_str},
                'realm': realm,
                'topic': topic,
                'ip_source': ip_source or '',
                'ip_dest': ip_dest or '',
                'payload': payload
            }
            entries.append(entry)
            f.seek(0)
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.truncate()
            
            
            
            
from abc import ABC, abstractmethod

class IPublisherService(ABC):
    @abstractmethod
    def start_session(self, realm: str, url: str, topic: str):
        pass

    @abstractmethod
    def publish(self, realm: str, topic: str, message: dict):
        pass
    


import asyncio, threading, datetime
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
from common.logger import ILogger

class PublisherService:
    def __init__(self, logger: ILogger):
        self.logger = logger
        self.sessions = {}

    class _Session(ApplicationSession):
        def __init__(self, config, topic, service):
            super().__init__(config)
            self.topic = topic
            self.service = service
        async def onJoin(self, details):
            self.service.sessions[self.config.realm] = self
            await asyncio.Future()

    def start_session(self, realm, url, topic):
        if realm in self.sessions:
            return
        def runner():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            r = ApplicationRunner(url=url, realm=realm)
            r.run(lambda cfg: PublisherService._Session(cfg, topic, self))
        threading.Thread(target=runner, daemon=True).start()

    def publish(self, realm, topic, message):
        session = self.sessions.get(realm)
        if not session:
            raise RuntimeError("Session not started")
        asyncio.run_coroutine_threadsafe(
            session.publish(topic, **message),
            session._endpoint._loop
        )
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.logger.log(ts, realm, topic, ip_source="", ip_dest="", payload=message)
        
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton
from publisher.service import PublisherService
from common.logger import JSONLogger

class PublisherTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = JSONLogger()
        self.service = PublisherService(self.logger)
        # construir UI...

    def on_start_clicked(self):
        realm = ...; url = ...; topic = ...
        self.service.start_session(realm, url, topic)

    def on_send_clicked(self):
        realm = ...; topic = ...; msg = {...}
        self.service.publish(realm, topic, msg)
        
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QTabWidget
from publisher.gui import PublisherTab
from subscriber.gui import SubscriberTab
from common.utils import load_stylesheet, create_splash_screen

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("wamPy Tester v1.0")
        self.resize(1000, 800)

        tabs = QTabWidget()
        tabs.addTab(PublisherTab(), "Publisher")
        tabs.addTab(SubscriberTab(), "Subscriber")
        self.setCentralWidget(tabs)

def main():
    app = QApplication(sys.argv)
    # Opcional: carga stylesheet
    # load_stylesheet(app, "styles.qss")
    splash = create_splash_screen()
    splash.show()
    window = MainWindow()
    QTimer.singleShot(5000, splash.close)
    QTimer.singleShot(5000, window.show)
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()


import threading
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
import asyncio, datetime
from common.utils import log_to_file

global_pub_sessions = {}

class JSONPublisher(ApplicationSession):
    def __init__(self, config, topic, widget):
        super().__init__(config)
        self.topic = topic
        self.widget = widget

    async def onJoin(self, details):
        self.widget.session = self
        self.widget.loop = asyncio.get_event_loop()
        global_pub_sessions[self.config.realm] = self
        await asyncio.Future()  # no autocierra

def start_publisher(url, realm, topic, widget):
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
        if delay > 0:
            await asyncio.sleep(delay)
        session.publish(topic, **message) if isinstance(message, dict) else session.publish(topic, message)
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_to_file(ts, session.config.realm, topic, ip_source="", ip_dest="", payload=message)
    if session and loop:
        asyncio.run_coroutine_threadsafe(_send(), loop)


import threading
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
import asyncio
from common.utils import log_to_file

global_sub_sessions = {}

class MultiTopicSubscriber(ApplicationSession):
    def __init__(self, config):
        super().__init__(config)
        self.topics = []
        self.on_message_callback = None
        self.logged = False

    async def onJoin(self, details):
        realm = self.config.realm
        global_sub_sessions[realm] = self
        errors = []
        for t in self.topics:
            try:
                await self.subscribe(lambda *args, topic=t: self.on_event(realm, topic, *args), t)
            except Exception as e:
                errors.append(str(e))
        if not self.logged:
            self.logged = True
            result = {"error": ", ".join(errors)} if errors else {"success": "Subscribed"}
            self.on_message_callback(realm, "Subscription", result)

    def on_event(self, realm, topic, *args):
        if self.on_message_callback:
            self.on_message_callback(realm, topic, {"args": args})

def start_subscriber(url, realm, topics, on_message_callback):
    if realm in global_sub_sessions:
        try: global_sub_sessions[realm].leave("Re-subscribing")
        except: pass
        del global_sub_sessions[realm]
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        runner = ApplicationRunner(url=url, realm=realm)
        runner.run(MultiTopicSubscriber.factory(topics, on_message_callback))
    threading.Thread(target=run, daemon=True).start()



#######subscirber

from abc import ABC, abstractmethod

class ISubscriberService(ABC):
    @abstractmethod
    def start_session(self, url: str, realm: str, topics: list, callback):
        pass

import asyncio, threading
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
from app.logger import ILogger

class SubscriberService:
    def __init__(self, logger: ILogger):
        self.logger = logger
        self.sessions = {}

    class _Session(ApplicationSession):
        def __init__(self, config, topics, service, callback):
            super().__init__(config)
            self.topics = topics
            self.service = service
            self.callback = callback

        async def onJoin(self, details):
            self.service.sessions[self.config.realm] = self
            for t in self.topics:
                await self.subscribe(lambda *args, topic=t: self.on_event(topic, *args), t)

        def on_event(self, topic, *args):
            msg = args[0] if args else {}
            ts = asyncio.get_event_loop().time()
            self.service.logger.log(
                timestamp=self.service.format_timestamp(ts),
                realm=self.config.realm,
                topic=topic,
                ip_source="",
                ip_dest="",
                payload=msg
            )
            if self.callback:
                self.callback(self.config.realm, topic, msg)

    def start_session(self, url: str, realm: str, topics: list, callback):
        if realm in self.sessions:
            return
        def run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            runner = ApplicationRunner(url=url, realm=realm)
            runner.run(lambda cfg: SubscriberService._Session(cfg, topics, self, callback))
        threading.Thread(target=run, daemon=True).start()

    @staticmethod
    def format_timestamp(ts):
        import datetime
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    
    from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView
from app.logger import JSONLogger
from subscriber.service import SubscriberService

class SubscriberTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = JSONLogger()
        self.service = SubscriberService(self.logger)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)
        self.subscribeBtn = QPushButton("Subscribe")
        self.subscribeBtn.clicked.connect(self.start_subscription)
        layout.addWidget(self.subscribeBtn)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Time", "Realm", "Topic"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)
        self.setLayout(layout)

    def start_subscription(self):
        url = "ws://127.0.0.1:60001"
        realm = "realm1"
        topics = ["msg.topic"]
        self.service.start_session(url, realm, topics, self.handle_message)

    def handle_message(self, realm, topic, payload):
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(now))
        self.table.setItem(row, 1, QTableWidgetItem(realm))
        self.table.setItem(row, 2, QTableWidgetItem(topic))