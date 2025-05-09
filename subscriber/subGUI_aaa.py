    def get_config_path(self, subfolder):
        """
        Devuelve la ruta a /projects/subscriber o /projects/<subfolder>
        en la raíz de la aplicación.
        """
        # Si está congelado, base es el ejecutable; si no, el directorio del .py
        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        # subfolder esperado: 'subscriber'
        return os.path.join(os.path.dirname(base_path), 'projects', subfolder)

    def saveProject(self):
        """Guarda la configuración de Subscriber en /projects/subscriber."""
        base_dir = self.get_config_path('subscriber')
        ensure_dir(base_dir)
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Save Subscriber Config",
            base_dir,
            "JSON Files (*.json)"
        )
        if not filepath:
            return
        try:
            config = self.getProjectConfig()
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Subscriber", "Subscriber configuration saved successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save subscriber config:\n{e}")

    def loadProject(self):
        """Carga la configuración de Subscriber desde /projects/subscriber."""
        base_dir = self.get_config_path('subscriber')
        ensure_dir(base_dir)
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Load Subscriber Config",
            base_dir,
            "JSON Files (*.json)"
        )
        if not filepath:
            return
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                config = json.load(f)
            self.loadProjectFromConfig(config)
            QMessageBox.information(self, "Subscriber", "Subscriber configuration loaded successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load subscriber config:\n{e}")
