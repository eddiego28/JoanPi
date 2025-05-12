def deleteRealmRow(self):
    # Borra las filas seleccionadas en la tabla de realms
    selected_rows = [idx.row() for idx in self.realmTable.selectionModel().selectedRows()]
    for row in sorted(selected_rows, reverse=True):
        realm = self.realmTable.item(row, 0).text().strip()
        self.realmTable.removeRow(row)
        self.realms_topics.pop(realm, None)
        self.selected_topics_by_realm.pop(realm, None)

    # Si el realm actual ha sido borrado, limpia topics y resetea current_realm
    if self.current_realm not in self.realms_topics:
        self.current_realm = None
        self.topicTable.setRowCount(0)
    else:
        # Si sigue habiendo ese realm, recarga su lista de topics
        for r in range(self.realmTable.rowCount()):
            if self.realmTable.item(r, 0).text() == self.current_realm:
                self.onRealmClicked(r, 0)
                break

def deleteTopicRow(self):
    # Asegura que el realm sigue existiendo antes de borrar topics
    if not self.current_realm or self.current_realm not in self.realms_topics:
        return

    selected_rows = [idx.row() for idx in self.topicTable.selectionModel().selectedRows()]
    for row in sorted(selected_rows, reverse=True):
        topic = self.topicTable.item(row, 0).text().strip()
        self.topicTable.removeRow(row)
        # Elimina del dict interno
        if topic in self.realms_topics[self.current_realm]['topics']:
            self.realms_topics[self.current_realm]['topics'].remove(topic)
        self.selected_topics_by_realm[self.current_realm].discard(topic)
