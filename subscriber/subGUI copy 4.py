def deleteRealmRow(self):
    # Borra solo las filas seleccionadas (por selección de fila)
    rows = sorted({idx.row() for idx in self.realmTable.selectionModel().selectedRows()}, reverse=True)
    for row in rows:
        item = self.realmTable.item(row, 0)
        if not item:
            continue
        realm = item.text().strip()
        self.realmTable.removeRow(row)
        # Elimina del estado interno sin lanzar KeyError
        self.realms_topics.pop(realm, None)
        self.selected_topics_by_realm.pop(realm, None)

    # Si el current_realm ha desaparecido, limpialo y la tabla de topics
    if not self.current_realm or self.current_realm not in self.realms_topics:
        self.current_realm = None
        self.topicTable.setRowCount(0)
    else:
        # Si sigue existiendo, recarga sus topics
        for r in range(self.realmTable.rowCount()):
            if self.realmTable.item(r, 0).text().strip() == self.current_realm:
                self.onRealmClicked(r, 0)
                break

def deleteTopicRow(self):
    # Asegúrate de que el realm sigue existiendo
    if not self.current_realm or self.current_realm not in self.realms_topics:
        return

    rows = sorted({idx.row() for idx in self.topicTable.selectionModel().selectedRows()}, reverse=True)
    for row in rows:
        item = self.topicTable.item(row, 0)
        if not item:
            continue
        topic = item.text().strip()
        self.topicTable.removeRow(row)
        # Elimina topic de la lista interna sin error
        topics = self.realms_topics.get(self.current_realm, {}).get('topics', [])
        if topic in topics:
            topics.remove(topic)
        # Asegura que el set existe antes de descartar
        sel = self.selected_topics_by_realm.get(self.current_realm)
        if sel is not None:
            sel.discard(topic)
