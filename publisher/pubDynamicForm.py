# publisher/pubDynamicForm.py
import json
from PyQt5.QtWidgets import QGroupBox, QLabel, QLineEdit, QFormLayout, QScrollArea, QWidget, QVBoxLayout

class DynamicPublisherMessageForm(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Mensaje (JSON dinámico)", parent)
        self.default_json = {}
        self.initUI()
        
    def initUI(self):
        layout = QVBoxLayout()
        self.formArea = QScrollArea()
        self.formArea.setMinimumSize(600, 400)
        self.formWidget = QWidget()
        self.formLayout = QFormLayout()
        self.formWidget.setLayout(self.formLayout)
        self.formArea.setWidget(self.formWidget)
        self.formArea.setWidgetResizable(True)
        layout.addWidget(QLabel("Campos a editar:"))
        layout.addWidget(self.formArea)
        self.setLayout(layout)
        self.build_form(self.default_json)
        
    def build_form(self, data):
        # Limpia el formulario
        while self.formLayout.count():
            child = self.formLayout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        if data:
            self._build_form_rec(data, self.formLayout, indent=0)
        else:
            self.formLayout.addRow(QLabel("No hay datos importados"))
            
    def _build_form_rec(self, data, layout, indent=0):
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, dict):
                    group = QGroupBox()
                    group.setStyleSheet(f"margin-left: {indent * 20}px;")
                    group_layout = QFormLayout()
                    group.setLayout(group_layout)
                    layout.addRow(QLabel(key), group)
                    self._build_form_rec(value, group_layout, indent + 1)
                elif isinstance(value, list):
                    from PyQt5.QtWidgets import QTextEdit
                    te = QTextEdit()
                    te.setStyleSheet(f"margin-left: {indent * 20}px;")
                    te.setPlainText(json.dumps(value, indent=2, ensure_ascii=False))
                    layout.addRow(QLabel(key), te)
                else:
                    le = QLineEdit(str(value))
                    le.setStyleSheet(f"margin-left: {indent * 20}px;")
                    layout.addRow(QLabel(key), le)
        else:
            le = QLineEdit(str(data))
            le.setStyleSheet(f"margin-left: {indent * 20}px;")
            layout.addRow(QLabel("Valor"), le)
            
    def collect_form_data(self, layout):
        data = {}
        for row in range(layout.rowCount()):
            label_item = layout.itemAt(row, QFormLayout.LabelRole)
            field_item = layout.itemAt(row, QFormLayout.FieldRole)
            if label_item is None or field_item is None:
                continue
            key = label_item.widget().text().strip()
            widget = field_item.widget()
            if widget.__class__.__name__ == "QGroupBox":
                data[key] = self.collect_form_data(widget.layout())
            elif widget.__class__.__name__ == "QTextEdit":
                text = widget.toPlainText().strip()
                try:
                    data[key] = json.loads(text)
                except Exception:
                    data[key] = text
            elif widget.__class__.__name__ == "QLineEdit":
                data[key] = widget.text().strip()
        print("Datos recogidos del formulario dinámico:", data)
        return data
