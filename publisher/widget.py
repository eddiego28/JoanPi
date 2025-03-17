def onRealmClicked(self, row, col):
    realm_item = self.realmTable.item(row, 0)
    if realm_item:
        realm = realm_item.text().strip()
        self.current_realm = realm
        topics = self.realms_topics.get(realm, {}).get("topics", [])
        self.topicTable.blockSignals(True)
        self.topicTable.setRowCount(0)
        # Inicializa la selección con todos los topics de ese realm si no existe aún
        if realm not in self.selected_topics_by_realm:
            self.selected_topics_by_realm[realm] = set(topics)
        for t in topics:
            row_idx = self.topicTable.rowCount()
            self.topicTable.insertRow(row_idx)
            t_item = QTableWidgetItem(t)
            t_item.setFlags(t_item.flags() | Qt.ItemIsUserCheckable)
            if t in self.selected_topics_by_realm[realm]:
                t_item.setCheckState(Qt.Checked)
            else:
                t_item.setCheckState(Qt.Unchecked)
            self.topicTable.setItem(row_idx, 0, t_item)
        self.topicTable.blockSignals(False)
