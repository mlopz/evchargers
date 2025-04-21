import time
import csv
import os
import requests
import datetime

# Parámetros
ENDPOINT = "https://app.eve-move.com/eve/miem"
LOG_FILE = "monitor_log.csv"
POWER_THRESHOLD = 60  # kW

# Cabecera del CSV
HEADER = ["timestamp", "station", "connector_type", "status"]

# Crear archivo con cabecera si no existe
if not os.path.isfile(LOG_FILE):
    with open(LOG_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(HEADER)

print("Iniciando monitoreo de conectores >= 60 kW cada 60s...")
while True:
    timestamp = datetime.datetime.now().isoformat(timespec='seconds')
    try:
        resp = requests.get(ENDPOINT, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # Extraer lista de estaciones
        if isinstance(data, dict):
            records = data.get('data', [])
        elif isinstance(data, list):
            records = data
        else:
            records = []
        # Agrupar conectores por estación y tipo para asignar índices
        station_connector_count = {}
        rows = []
        for item in records:
            name = item.get("name", "")
            cnns = item.get("cnns", [])
            for c in cnns:
                power = float(c.get("power", 0))
                if power >= POWER_THRESHOLD:
                    connector_type = c.get("type", "")
                    # Inicializar contador para la estación y tipo
                    key = (name, connector_type)
                    if key not in station_connector_count:
                        station_connector_count[key] = 1
                    else:
                        station_connector_count[key] += 1
                    # Generar identificador único
                    connector_id = f"{connector_type} #{station_connector_count[key]}"
                    row = [
                        timestamp,
                        name,
                        connector_id,
                        c.get("status", "")
                    ]
                    rows.append(row)
        # Escribir filas en el CSV
        if rows:
            with open(LOG_FILE, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerows(rows)
            print(f"[{timestamp}] Registrados {len(rows)} conectores >= {POWER_THRESHOLD}kW")
    except Exception as e:
        print(f"[{timestamp}] Error al consultar endpoint: {e}")
    time.sleep(60)
