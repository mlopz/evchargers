import sqlite3

# Inicializa la base de datos y la tabla de sesiones
conn = sqlite3.connect('monitor_log.db')
c = conn.cursor()
c.execute('''
CREATE TABLE IF NOT EXISTS sessions_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    station TEXT NOT NULL,
    connector_type TEXT NOT NULL,
    status TEXT NOT NULL
)
''')
conn.commit()
conn.close()
