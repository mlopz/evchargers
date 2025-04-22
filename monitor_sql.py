import time
import requests
import datetime
import sqlite3

# Parámetros
ENDPOINT = "https://app.eve-move.com/eve/miem"
DB_FILE = "monitor_log.db"
POWER_THRESHOLD = 60  # kW

# Inicializa la base si no existe
conn = sqlite3.connect(DB_FILE)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS sessions_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    station TEXT NOT NULL,
    connector_type TEXT NOT NULL,
    status TEXT NOT NULL
)''')
conn.commit()
conn.close()

def log_event(station, connector_type, status):
    ts = datetime.datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO sessions_log (timestamp, station, connector_type, status) VALUES (?, ?, ?, ?)',
              (ts, station, connector_type, status))
    conn.commit()
    conn.close()

def monitor():
    print("Iniciando monitoreo de conectores >= 60 kW cada 60s...")
    while True:
        try:
            resp = requests.get(ENDPOINT, timeout=10)
            data = resp.json()
            for item in data:
                name = item.get("name") or item.get("station")
                connectors = item.get("connectors") or item.get("cnns", [])
                type_counter = {}
                for c in connectors:
                    power = c.get("power", 0)
                    if power >= POWER_THRESHOLD:
                        connector_type = c.get("type", "")
                        # Asignar índice incremental
                        if connector_type not in type_counter:
                            type_counter[connector_type] = 1
                        else:
                            type_counter[connector_type] += 1
                        connector_id = f"{connector_type} #{type_counter[connector_type]}"
                        status = c.get("status", "")
                        log_event(name, connector_id, status)
            print(f"[{datetime.datetime.utcnow().isoformat()}] Registrados eventos de conectores >= 60kW")
        except Exception as e:
            print("[ERROR]", e)
        time.sleep(60)

if __name__ == "__main__":
    monitor()
