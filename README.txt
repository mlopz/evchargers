# EV Chargers Monitor - Despliegue Manual

## Requisitos
- Python 3.8+
- pip

## Instalación
1. Descomprime este ZIP en tu servidor o PC.
2. Instala las dependencias:
   pip install -r requirements.txt
3. (Opcional) Revisa y ajusta los archivos CSV de datos según tu entorno.
4. Ejecuta la app:
   python3 webapp.py

La app estará disponible en http://localhost:8501 o en la IP configurada.

## Archivos importantes
- webapp.py: Servidor principal Flask.
- monitor.py, main.py, report.py: Scripts auxiliares.
- templates/: Plantillas HTML.
- requirements.txt: Dependencias Python.
- costo energia.csv: Tarifas energéticas.
- monitor_log.csv: Log de sesiones (puede estar vacío).

## Notas
- El botón "Limpiar datos" borra el contenido de monitor_log.csv.
- Puedes subir y ejecutar este paquete en PythonAnywhere, Railway, Heroku (con Gunicorn), o tu propio VPS.
- No subas archivos de log reales si contienen datos sensibles.
