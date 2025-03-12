def updateTopicsFromSelectedRealm(self, row, column):
    if self.realmTable.rowCount() == 0:
        return
    item = self.realmTable.item(row, 0)
    realm = item.text() if item else "default"
    # Vaciar la tabla de topics
    self.topicTable.setRowCount(0)
    # Supongamos que la configuración global de realms y topics está en:
    # self.publisherTab.realms_topics
    if realm in self.publisherTab.realms_topics:
        for t in self.publisherTab.realms_topics[realm]:
            r = self.topicTable.rowCount()
            self.topicTable.insertRow(r)
            t_item = QTableWidgetItem(t)
            t_item.setFlags(t_item.flags() | Qt.ItemIsUserCheckable)
            t_item.setCheckState(Qt.Checked)
            self.topicTable.setItem(r, 0, t_item)
    else:
        r = self.topicTable.rowCount()
        self.topicTable.insertRow(r)
        self.topicTable.setItem(r, 0, QTableWidgetItem("default"))

# Conectar el evento de clic en la tabla de realms para actualizar topics
self.realmTable.cellClicked.connect(self.updateTopicsFromSelectedRealm)
#HOLA Y ADIOS
