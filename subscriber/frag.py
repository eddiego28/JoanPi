def loadGlobalRealmTopicConfig(self):
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "realm_topic_config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.realms_topics = data.get("realms", {})
            # Actualizamos la tabla de realms con checkboxes
            self.realmTable.setRowCount(0)
            for realm, topics in sorted(self.realms_topics.items()):
                row = self.realmTable.rowCount()
                self.realmTable.insertRow(row)
                # Crear QTableWidgetItem checkable para el realm
                item = QTableWidgetItem(realm)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
                self.realmTable.setItem(row, 0, item)
                router = data.get("realm_configs", {}).get(realm, "")
                self.realmTable.setItem(row, 1, QTableWidgetItem(router))
            # Actualizamos la tabla de topics para el primer realm
            if self.realmTable.rowCount() > 0:
                current_realm = self.realmTable.item(0, 0).text()
                self.updateTopicsForRealm(current_realm)
            print("Configuración global de realms/topics cargada (suscriptor).")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al cargar la configuración global:\n{e}")
    else:
        QMessageBox.warning(self, "Advertencia", "No se encontró el archivo realm_topic_config.json.")

def addRealmRow(self):
    new_realm = self.newRealmEdit.text().strip()
    if new_realm:
        row = self.realmTable.rowCount()
        self.realmTable.insertRow(row)
        item = QTableWidgetItem(new_realm)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        self.realmTable.setItem(row, 0, item)
        self.realmTable.setItem(row, 1, QTableWidgetItem(""))
        self.newRealmEdit.clear()
