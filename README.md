# WAMP Pub/Sub Project

Este proyecto es una aplicación en Python que utiliza Crossbar/Autobahn para la comunicación WAMP y PyQt5 para la interfaz gráfica, permitiendo publicar y suscribirse a mensajes a través de un router WAMP.

## Características

- **Módulo Publicador:** Permite configurar y enviar mensajes (con opción a envío asíncrono y programado).
- **Módulo Suscriptor:** Se suscribe a múltiples tópicos y muestra los mensajes recibidos.
- **Interfaz Gráfica:** Construida con PyQt5, con pestañas separadas para el publicador y el suscriptor.
- **Configuración de Proyecto:** Guardado y carga de la configuración de mensajes y suscriptores a archivos JSON.
- **Logging:** Registro de eventos y mensajes publicados/recibidos.
- **Integración con Crossbar:** Utiliza Crossbar como router WAMP. **Recuerda que Crossbar debe estar en ejecución para que la aplicación funcione.**

## Instalación

1. **Clona el repositorio** o descarga el código fuente.

2. **Crea y activa un entorno virtual**:
   - En Windows:
     ```bash
     python -m venv venv
     venv\Scripts\activate
     ```
   - En Linux/Mac:
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```

3. **Instala las dependencias**:
   ```bash
   pip install -r requirements.txt
