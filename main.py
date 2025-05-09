    def saveProject(self):
        """Guarda configuración combinada Publisher+Subscriber en /projects."""
        base_dir = get_resource_path('projects')
        ensure_dir(base_dir)
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Save Project",
            base_dir,
            "JSON Files (*.json)"
        )
        if not filepath:
            return
        project = {
            "publisher": self.publisherTab.getProjectConfig(),
            "subscriber": self.subscriberTab.getProjectConfig()
        }
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(project, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Project", "Project saved successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save project:\n{e}")

    def loadProject(self):
        """Carga configuración combinada Publisher+Subscriber desde /projects."""
        base_dir = get_resource_path('projects')
        ensure_dir(base_dir)
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Load Project",
            base_dir,
            "JSON Files (*.json)"
        )
        if not filepath:
            return
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                project = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load project:\n{e}")
            return
        # Cargamos en ambos tabs
        self.publisherTab.loadProjectFromConfig(project.get('publisher', {}))
        self.subscriberTab.loadProjectFromConfig(project.get('subscriber', {}))
        QMessageBox.information(self, "Project", "Project loaded successfully.")
