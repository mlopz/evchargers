from flask import Flask, request, render_template_string, send_file, jsonify, render_template
import requests
import datetime
import pandas as pd
from io import BytesIO
import numpy as np
import subprocess
import sys
import os
import json
import traceback
try:
    import psutil
except ImportError:
    psutil = None

# URL endpoint por defecto
default_url = "https://app.eve-move.com/eve/miem"

# Potencia mínima para mostrar conectores
POWER_THRESHOLD = 60  # kW mínimo

# Columnas para la tabla avanzada
COLUMNS = [
    "Nombre",
    "Tipo Conector",
    "Estado",
    "Potencia (kW)",
    "Sesiones de carga",
    "Cargando Hace",
    "Última sesión"
]

TIMEOUT_MINUTES = 2  # Umbral de hueco para desconexión

def build_sessions_with_timeout(df):
    # Devuelve lista de sesiones (inicio, fin, duración) considerando huecos
    results = []
    df = df.sort_values("timestamp").reset_index(drop=True)
    in_session = False
    start_time = None
    # Si el primer registro es Charging, tomarlo como inicio de sesión
    if not df.empty and df.iloc[0]["status"] == "Charging":
        start_time = df.iloc[0]["timestamp"]
        in_session = True
    for idx, row in df.iterrows():
        ts = row["timestamp"]
        status = row["status"]
        if status == "Charging":
            if not in_session:
                start_time = ts
                in_session = True
        else:
            if in_session:
                end_time = ts
                duration = (end_time - start_time).total_seconds() // 60
                if duration > 0:
                    results.append({
                        "start": start_time,
                        "end": end_time,
                        "duration": int(duration),
                        "in_progress": False
                    })
                in_session = False
    # Si queda una sesión abierta al final (en curso), agregarla aunque la duración sea 0
    if in_session and start_time is not None:
        now = pd.Timestamp.now(tz='America/Montevideo')
        duration = (now - start_time).total_seconds() // 60
        results.append({
            "start": start_time,
            "end": None,
            "duration": int(duration),
            "in_progress": True
        })
    return results

def fetch_data(url):
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            records = data.get('data', data)
        elif isinstance(data, list):
            records = data
        else:
            records = []
        # Cargar log de sesiones
        try:
            df = pd.read_csv("monitor_log.csv", parse_dates=["timestamp"])
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC').dt.tz_convert('America/Montevideo')
        except Exception:
            df = pd.DataFrame(columns=["timestamp","station","connector_type","status"])
        rows = []
        # --- AJUSTE: usar now con tz-aware ---
        import pytz
        tz_mvd = pytz.timezone('America/Montevideo')
        now = datetime.datetime.now(tz_mvd)
        for item in records:
            name = item.get("name", "")
            # Asegurarse de que el campo correcto para conectores es 'connectors'
            cnns = item.get("connectors")
            if cnns is None:
                cnns = item.get("cnns", [])
            # Agrupar conectores por tipo para asignar índices únicos
            type_counter = {}
            for c in cnns:
                power = c.get("power", 0)
                if power >= POWER_THRESHOLD:
                    connector_type = c.get("type", "")
                    # Asignar índice incremental
                    if connector_type not in type_counter:
                        type_counter[connector_type] = 1
                    else:
                        type_counter[connector_type] += 1
                    connector_id = f"{connector_type} #{type_counter[connector_type]}"
                    estado = c.get("status", "")
                    # Buscar sesiones para este conector único
                    sesiones = []
                    cargando_hace = "-"
                    ultima_sesion = "-"
                    if not df.empty:
                        log_filt = df[(df["station"] == name) & (df["connector_type"] == connector_id)]
                        sesiones_list = build_sessions_with_timeout(log_filt)
                        if sesiones_list:
                            sesiones = len(sesiones_list)
                            last_session = sesiones_list[-1]
                            if last_session.get("in_progress"):
                                # --- AJUSTE: asegurar que ambas fechas sean tz-aware ---
                                start_dt = pd.to_datetime(last_session.get("start"))
                                if start_dt.tzinfo is None:
                                    start_dt = tz_mvd.localize(start_dt)
                                # Log para depuración
                                print(f"[DEBUG] now: {now} ({now.tzinfo}), start_dt: {start_dt} ({start_dt.tzinfo})")
                                minutos = int((now - start_dt.to_pydatetime()).total_seconds() // 60)
                                cargando_hace = f"{minutos} min"
                            if last_session.get("end"):
                                ultima_sesion = pd.to_datetime(last_session.get("end")).strftime("%d/%m/%Y %H:%M")
                    row = [
                        name,
                        connector_id,
                        estado,
                        power,
                        sesiones,
                        cargando_hace,
                        ultima_sesion
                    ]
                    rows.append(row)
        return rows, None
    except Exception as e:
        return [], str(e)


def is_monitor_running():
    if psutil is None:
        return False
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['cmdline'] and 'monitor.py' in proc.info['cmdline']:
                return True
        except Exception:
            continue
    return False

def start_monitor():
    if not is_monitor_running():
        subprocess.Popen([sys.executable, 'monitor.py'], cwd=os.path.dirname(__file__))
        print("monitor.py lanzado automáticamente.")

start_monitor()

app = Flask(__name__)

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <title>Monitoreo de cargadores</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.datatables.net/1.13.4/css/dataTables.bootstrap5.min.css">
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://cdn.datatables.net/1.13.4/js/jquery.dataTables.min.js"></script>
    <script src="https://cdn.datatables.net/1.13.4/js/dataTables.bootstrap5.min.js"></script>
    <style>
        body { background: #f8fafc; }
        h1 { margin: 30px 0 20px 0; }
        .table-hover tbody tr:hover { background-color: #e3f2fd; }
        .dataTables_filter input { border-radius: 5px; }
        .modal-header { background: #0d6efd; color: white; }
        .modal-title { color: white; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary mb-4">
      <div class="container-fluid">
        <a class="navbar-brand" href="/">
          <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" fill="currentColor" class="bi bi-ev-station" viewBox="0 0 16 16"><path d="M6 4V2.5A1.5 1.5 0 0 1 7.5 1h1A1.5 1.5 0 0 1 10 2.5V4h.5A1.5 1.5 0 0 1 12 5.5V6h1a1 1 0 0 1 1 1v2.5a2.5 2.5 0 1 1-3 0V7a1 1 0 0 1 1-1h1v-.5a.5.5 0 0 0-.5-.5H12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5.5A1.5 1.5 0 0 1 5.5 4H6Zm1-1.5a.5.5 0 0 0-.5.5V4h2V2.5a.5.5 0 0 0-.5-.5h-1Zm3.5 8.5a1.5 1.5 0 1 0 3 0V7a.5.5 0 0 0-.5-.5h-2a.5.5 0 0 0-.5.5v3Zm-7 2A1 1 0 0 0 6 14h4a1 1 0 0 0 1-1V5.5a.5.5 0 0 0-.5-.5h-5a.5.5 0 0 0-.5.5V13Z"></path></svg> Monitoreo de cargadores
        </a>
        <ul class="navbar-nav ms-auto">
          <li class="nav-item"><a class="nav-link active" href="/">Dashboard</a></li>
          <li class="nav-item"><a class="nav-link" href="/data">Datos</a></li>
          <li class="nav-item"><a class="nav-link" href="/recaudacion">Recaudación</a></li>
        </ul>
      </div>
    </nav>
    <div class="container">
    <form action="/" method="get" class="row g-3 mb-3">
        <div class="col-md-8">
            <input type="text" id="url" name="url" class="form-control" value="{{ url }}" placeholder="Endpoint URL">
        </div>
        <div class="col-md-2">
            <input type="submit" value="Actualizar" class="btn btn-primary w-100">
        </div>
        <div class="col-md-2">
            <a href="/download-report" class="btn btn-success w-100">Descargar XLS</a>
        </div>
    </form>
    {% if error %}
        <div class="alert alert-danger">Error: {{ error }}</div>
    {% endif %}
    {% if rows %}
        <div class="table-responsive">
        <table id="chargers-table" class="table table-striped table-hover">
            <thead class="table-primary">
            <tr>
            {% for col in columns %}
                <th>{{ col }}</th>
            {% endfor %}
            </tr>
            </thead>
            <tbody>
            {% for row in rows %}
            <tr class="con-row" data-station="{{ row[0] }}" data-connector="{{ row[1] }}">
                {% for cell in row %}
                    <td>{{ cell }}</td>
                {% endfor %}
            </tr>
            {% endfor %}
            </tbody>
        </table>
        </div>

        <!-- Modal Detalle Sesiones -->
        <div class="modal fade" id="sessionsModal" tabindex="-1" aria-labelledby="sessionsModalLabel" aria-hidden="true">
          <div class="modal-dialog modal-lg">
            <div class="modal-content">
              <div class="modal-header">
                <h5 class="modal-title" id="sessionsModalLabel">Detalle de sesiones</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Cerrar"></button>
              </div>
              <div class="modal-body">
                <div id="sessions-content">
                  <p>Cargando...</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <script>
        $(document).ready(function() {
            var table = $('#chargers-table').DataTable({
                "order": [[ 0, "asc" ]],
                "language": {
                    "search": "Buscar:",
                    "lengthMenu": "Mostrar _MENU_ registros",
                    "info": "Mostrando _START_ a _END_ de _TOTAL_ registros",
                    "paginate": {
                        "first": "Primero",
                        "last": "Último",
                        "next": "Siguiente",
                        "previous": "Anterior"
                    }
                }
            });
            // Modal detalle de sesiones
            $(document).on('click', '.con-row', function() {
                var station = $(this).data('station');
                var connector = $(this).data('connector');
                $('#sessionsModalLabel').text('Detalle de sesiones: ' + station + ' - ' + connector);
                $('#sessions-content').html('<p>Cargando...</p>');
                $('#sessionsModal').modal('show');
                $.getJSON('/sessions', {station: station, connector: connector}, function(data) {
                    if(data.length === 0) {
                        $('#sessions-content').html('<p>No hay sesiones registradas.</p>');
                    } else {
                        var html = '<table class="table table-bordered"><thead><tr><th>Inicio</th><th>Fin</th><th>Duración</th></tr></thead><tbody>';
                        data.forEach(function(s) {
                            html += '<tr><td>' + s.start + '</td><td>' + (s.end ? s.end : 'En curso') + '</td><td>' + s.duration + '</td></tr>';
                        });
                        html += '</tbody></table>';
                        $('#sessions-content').html(html);
                    }
                });
            });
        });
        </script>
    {% else %}
        <div class="alert alert-info">No hay datos para mostrar.</div>
    {% endif %}
    </div>
</body>
</html>
'''

# --- UTILITARIO: Forzar timestamps tz-aware en America/Montevideo ---
def localize_api_timestamps(records, keys=("start", "end", "timestamp")):
    import pandas as pd
    for rec in records:
        for k in keys:
            if k in rec and rec[k]:
                try:
                    # Si ya es pd.Timestamp y aware, dejar igual
                    if hasattr(rec[k], 'tzinfo') and rec[k].tzinfo is not None:
                        continue
                    # Si termina en Z o tiene UTC, parsear y convertir
                    if isinstance(rec[k], str) and rec[k].endswith('Z'):
                        rec[k] = pd.to_datetime(rec[k], utc=True).tz_convert('America/Montevideo')
                    else:
                        # Si es string naive, parsear y localizar
                        rec[k] = pd.to_datetime(rec[k])
                        if rec[k].tzinfo is None:
                            rec[k] = rec[k].tz_localize('America/Montevideo')
                except Exception as e:
                    print(f"[DEBUG] Error localizando {k}: {rec[k]} - {e}")
    return records

@app.route("/", methods=["GET"])
def index():
    url = request.args.get("url", default_url)
    rows, err = fetch_data(url)
    return render_template_string(HTML_TEMPLATE, rows=rows, columns=COLUMNS, error=err, url=url)


@app.route("/sessions", methods=["GET"])
def sessions_detail():
    station = request.args.get("station")
    connector = request.args.get("connector")
    try:
        df = pd.read_csv("monitor_log.csv", parse_dates=["timestamp"])
        df['timestamp'] = df['timestamp'].dt.tz_localize('UTC').dt.tz_convert('America/Montevideo')
    except Exception:
        return jsonify([])
    # Buscar por identificador único de conector
    log_filt = df[(df["station"] == station) & (df["connector_type"] == connector)]
    sessions = []
    if not log_filt.empty:
        sesiones_list = build_sessions_with_timeout(log_filt)
        # Filtro final: eliminar sesiones de duración 0 SOLO si no están en curso
        sessions = [s for s in sesiones_list if (s.get('duration', 0) > 0 or s.get('in_progress', False))]
    return jsonify(sessions)


@app.route("/download-report", methods=["GET"])
def download_report():
    # Leer logs y generar sesiones
    df = pd.read_csv("monitor_log.csv", parse_dates=["timestamp"])
    df['timestamp'] = df['timestamp'].dt.tz_localize('UTC').dt.tz_convert('America/Montevideo')
    sessions_df = build_sessions_with_timeout(df)
    # Generar archivo Excel en memoria
    output = BytesIO()
    sessions_df.to_excel(output, index=False, engine="openpyxl")
    output.seek(0)
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        download_name="occupancy_report.xlsx",
        as_attachment=True
    )


# Ruta para la pestaña de datos
@app.route("/data")
def data_page():
    return render_template("data.html")


# Endpoint de métricas
@app.route("/data-metrics", methods=["GET"])
def data_metrics():
    try:
        import pandas as pd
        import datetime
        from flask import request
        start = request.args.get('start')
        end = request.args.get('end')
        date_format = '%d/%m/%Y'
        try:
            import pandas as pd
            start_dt = pd.to_datetime(start, format=date_format).tz_localize('America/Montevideo') if start else None
            end_dt = pd.to_datetime(end, format=date_format).tz_localize('America/Montevideo') if end else None
        except Exception:
            start_dt = end_dt = None
        print(f"[DEBUG] params: start={request.args.get('start')}, end={request.args.get('end')}")
        try:
            df = pd.read_csv("monitor_log.csv", parse_dates=["timestamp"])
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC').dt.tz_convert('America/Montevideo')
        except Exception:
            return {"status": "error", "message": "No se pudo leer el log"}
        if start_dt is not None:
            df = df[df["timestamp"] >= start_dt]
        if end_dt is not None:
            df = df[df["timestamp"] <= end_dt + pd.Timedelta(days=1)]
        df["day"] = df["timestamp"].dt.date
        df["hour"] = df["timestamp"].dt.hour
        print(f"[DEBUG] df['timestamp'] dtype: {df['timestamp'].dtype}, tz: {getattr(df['timestamp'].dt, 'tz', None)}")
        # Construcción de sesiones por station + connector_type
        def build_sessions_timeout(grp):
            sessions = []
            in_session = False
            start_time = None
            for idx, row in grp.iterrows():
                ts = row["timestamp"]
                status = row["status"]
                if status == "Charging":
                    if not in_session:
                        start_time = ts
                        in_session = True
                else:
                    if in_session:
                        end_time = ts
                        duration = (end_time - start_time).total_seconds() // 60
                        if duration > 0:
                            sessions.append((start_time, end_time, duration))
                        in_session = False
            if in_session and start_time is not None:
                end_time = grp["timestamp"].max()
                if end_time.tzinfo is None:
                    end_time = end_time.tz_localize('America/Montevideo')
                duration = (end_time - start_time).total_seconds() // 60
                if duration > 0:
                    sessions.append((start_time, end_time, duration))
            return sessions
        sessions = []
        for (station, connector), grp in df.groupby(["station", "connector_type"]):
            grp = grp.sort_values("timestamp").reset_index(drop=True)
            for start, end, mins in build_sessions_timeout(grp):
                is_last = False
                if end == grp["timestamp"].max() and grp.iloc[-1]["status"] == "Charging":
                    is_last = True
                sessions.append({
                    "station": station,
                    "connector": connector,
                    "start": start,
                    "end": end,
                    "duration": int(mins),
                    "in_progress": is_last
                })
        sessions_df = pd.DataFrame(sessions)
        # --- Rankings por cargador ---
        summary = sessions_df.groupby("station").agg(
            total_duration = ("duration", "sum"),
            num_connectors = ("connector", "nunique")
        ).reset_index()
        top_chargers = summary.sort_values("total_duration", ascending=False).head(10).to_dict(orient="records")
        least_chargers = summary.sort_values("total_duration", ascending=True).head(10).to_dict(orient="records")
        # --- Ranking de horas ---
        # Para cada sesión, sumar minutos en cada hora involucrada
        hour_usage = [0]*24
        for _, row in sessions_df.iterrows():
            if pd.isnull(row["start"]) or pd.isnull(row["end"]):
                continue
            current = row["start"]
            # --- AJUSTE CRÍTICO: asegurar current y end tz-aware ---
            if current.tzinfo is None:
                current = current.tz_localize('America/Montevideo')
            if row["end"].tzinfo is None:
                row["end"] = row["end"].tz_localize('America/Montevideo')
            # --- LOG DE DIAGNÓSTICO ---
            print(f"[DEBUG] current: {current}, tzinfo: {getattr(current, 'tzinfo', None)}")
            print(f"[DEBUG] end: {row['end']}, tzinfo: {getattr(row['end'], 'tzinfo', None)}")
            while current < row["end"]:
                next_hour = (current + pd.Timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
                if next_hour.tzinfo is None:
                    next_hour = next_hour.tz_localize('America/Montevideo')
                if next_hour > row["end"]:
                    next_hour = row["end"]
                mins = int((next_hour - current).total_seconds() // 60)
                hour_idx = current.hour
                hour_usage[hour_idx] += mins
                current = next_hour
        top_hours = [
            {"hour": h, "duration": hour_usage[h]}
            for h in range(24)
        ]
        top_hours = sorted(top_hours, key=lambda x: x["duration"], reverse=True)[:10]
        return {
            "status": "ok",
            "top_chargers": top_chargers,
            "least_chargers": least_chargers,
            "top_hours": top_hours
        }
    except Exception as e:
        print("[ERROR] Excepción en /data-metrics:")
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


# Endpoint de datos para el mapa (a implementar)
@app.route("/data-map", methods=["GET"])
def data_map():
    # Obtener lista de cargadores con latitude/longitude desde la API
    try:
        resp = requests.get("https://app.eve-move.com/eve/miem", timeout=10)
        data = resp.json()
        result = []
        count_total = 0
        count_filtrados = 0
        power_samples = []
        for item in data:
            name = item.get("name") or item.get("station")
            lat = item.get("lat")
            lon = item.get("lon")
            if lat is None:
                lat = item.get("latitude")
            if lon is None:
                lon = item.get("longitude")
            cnns = item.get("cnns", [])
            max_power = 0
            for cnn in cnns:
                try:
                    p = cnn.get("power")
                    if isinstance(p, str):
                        p_val = float(p.strip())
                    else:
                        p_val = float(p) if p is not None else 0
                except Exception:
                    p_val = 0
                if p_val > max_power:
                    max_power = p_val
            if count_total < 10:
                power_samples.append(max_power)
            count_total += 1
            if name and lat is not None and lon is not None and max_power >= POWER_THRESHOLD:
                result.append({"station": name, "lat": float(lat), "lon": float(lon), "power": max_power})
                count_filtrados += 1
        print(f"[DEBUG] Ejemplos de max_power: {power_samples}")
        print(f"[DEBUG] Total cargadores: {count_total}, >=60kW: {count_filtrados}")
        return {"status": "ok", "chargers": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.route('/data-demand-map')
def data_demand_map():
    import pandas as pd
    import datetime
    from flask import request
    # Cargar ubicaciones
    with open('cargadores_ubicaciones.json', encoding='utf-8') as f:
        ubicaciones = {x['station']: x for x in json.load(f) if x.get('lat') is not None and x.get('lon') is not None}
    # Obtener sesiones usando la misma lógica que /data-metrics
    start = request.args.get('start')
    end = request.args.get('end')
    # Formato esperado: DD/MM/YYYY
    date_format = '%d/%m/%Y'
    try:
        import pandas as pd
        start_dt = pd.to_datetime(start, format=date_format).tz_localize('America/Montevideo') if start else None
        end_dt = pd.to_datetime(end, format=date_format).tz_localize('America/Montevideo') if end else None
    except Exception:
        start_dt = end_dt = None
    # Leer log
    try:
        df = pd.read_csv("monitor_log.csv", parse_dates=["timestamp"])
        df['timestamp'] = df['timestamp'].dt.tz_localize('UTC').dt.tz_convert('America/Montevideo')
    except Exception:
        return {"status": "error", "message": "No se pudo leer el log"}
    if start_dt is not None:
        df = df[df["timestamp"] >= start_dt]
    if end_dt is not None:
        df = df[df["timestamp"] <= end_dt + pd.Timedelta(days=1)]
    # Normalizar columnas
    df["day"] = df["timestamp"].dt.date
    df["hour"] = df["timestamp"].dt.hour
    # Sesiones Charging con timeout
    def build_sessions_timeout(grp):
        sessions = []
        in_session = False
        start_time = None
        for idx, row in grp.iterrows():
            ts = row["timestamp"]
            status = row["status"]
            if status == "Charging":
                if not in_session:
                    start_time = ts
                    in_session = True
            else:
                if in_session:
                    end_time = ts
                    duration = (end_time - start_time).total_seconds() // 60
                    if duration > 0:
                        sessions.append((start_time, end_time, duration))
                    in_session = False
        # Si queda una sesión abierta al final
        if in_session and start_time is not None:
            end_time = grp["timestamp"].max()
            if end_time.tzinfo is None:
                end_time = end_time.tz_localize('America/Montevideo')
            duration = (end_time - start_time).total_seconds() // 60
            if duration > 0:
                sessions.append((start_time, end_time, duration))
        return sessions
    # Cálculo de métricas
    sessions = []
    for (station, connector), grp in df.groupby(["station", "connector_type"]):
        grp = grp.sort_values("timestamp").reset_index(drop=True)
        for start, end, mins in build_sessions_timeout(grp):
            # Identificar si la sesión está en curso
            is_last = False
            if end == grp["timestamp"].max() and grp.iloc[-1]["status"] == "Charging":
                is_last = True
            sessions.append({
                "station": station,
                "connector": connector,
                "start": start,
                "end": end,
                "duration": int(mins),
                "in_progress": is_last
            })
    sessions_df = pd.DataFrame(sessions)
    # Minutos Charging por cargador
    charger_usage = sessions_df.groupby(["station", "connector"]).agg({"duration": "sum"}).reset_index()
    charger_usage = charger_usage.sort_values("duration", ascending=False)
    # Agrupar minutos por cargador
    grouped = charger_usage.groupby('station')['duration'].sum().reset_index()
    demanda = []
    for _, row in grouped.iterrows():
        st = row['station']
        if st in ubicaciones:
            demanda.append({
                'station': st,
                'lat': ubicaciones[st]['lat'],
                'lon': ubicaciones[st]['lon'],
                'duration': float(row['duration'])
            })
    return {'chargers': demanda}


@app.route('/data-chargers-summary')
def data_chargers_summary():
    try:
        import pandas as pd
        import datetime
        from flask import request
        start = request.args.get('start')
        end = request.args.get('end')
        date_format = '%d/%m/%Y'
        try:
            import pandas as pd
            start_dt = pd.to_datetime(start, format=date_format).tz_localize('America/Montevideo') if start else None
            end_dt = pd.to_datetime(end, format=date_format).tz_localize('America/Montevideo') if end else None
        except Exception:
            start_dt = end_dt = None
        print(f"[DEBUG] params: start={request.args.get('start')}, end={request.args.get('end')}")
        try:
            df = pd.read_csv("monitor_log.csv", parse_dates=["timestamp"])
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC').dt.tz_convert('America/Montevideo')
        except Exception:
            return {"status": "error", "message": "No se pudo leer el log"}
        if start_dt is not None:
            df = df[df["timestamp"] >= start_dt]
        if end_dt is not None:
            df = df[df["timestamp"] <= end_dt + pd.Timedelta(days=1)]
        df["day"] = df["timestamp"].dt.date
        df["hour"] = df["timestamp"].dt.hour
        print(f"[DEBUG] df['timestamp'] dtype: {df['timestamp'].dtype}, tz: {getattr(df['timestamp'].dt, 'tz', None)}")
        # Construcción de sesiones por station + connector_type
        def build_sessions_timeout(grp):
            sessions = []
            in_session = False
            start_time = None
            for idx, row in grp.iterrows():
                ts = row["timestamp"]
                status = row["status"]
                if status == "Charging":
                    if not in_session:
                        start_time = ts
                        in_session = True
                else:
                    if in_session:
                        end_time = ts
                        duration = (end_time - start_time).total_seconds() // 60
                        if duration > 0:
                            sessions.append((start_time, end_time, duration))
                        in_session = False
            if in_session and start_time is not None:
                end_time = grp["timestamp"].max()
                if end_time.tzinfo is None:
                    end_time = end_time.tz_localize('America/Montevideo')
                duration = (end_time - start_time).total_seconds() // 60
                if duration > 0:
                    sessions.append((start_time, end_time, duration))
            return sessions
        sessions = []
        for (station, connector), grp in df.groupby(["station", "connector_type"]):
            grp = grp.sort_values("timestamp").reset_index(drop=True)
            for start, end, mins in build_sessions_timeout(grp):
                is_last = False
                if end == grp["timestamp"].max() and grp.iloc[-1]["status"] == "Charging":
                    is_last = True
                sessions.append({
                    "station": station,
                    "connector": connector,
                    "start": start,
                    "end": end,
                    "duration": int(mins),
                    "in_progress": is_last
                })
        sessions_df = pd.DataFrame(sessions)
        # Agrupar por station (cargador)
        summary = sessions_df.groupby("station").agg(
            total_duration = ("duration", "sum"),
            num_connectors = ("connector", "nunique")
        ).reset_index()
        summary_list = summary.to_dict(orient="records")
        return {"status": "ok", "chargers": summary_list}
    except Exception as e:
        print("[ERROR] Excepción en /data-chargers-summary:")
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.route('/data-recaudacion')
def data_recaudacion():
    try:
        import pandas as pd
        import datetime
        from flask import request
        import numpy as np
        import os
        import json
        start = request.args.get('start')
        end = request.args.get('end')
        date_format = '%d/%m/%Y'
        try:
            import pandas as pd
            start_dt = pd.to_datetime(start, format=date_format).tz_localize('America/Montevideo') if start else None
            end_dt = pd.to_datetime(end, format=date_format).tz_localize('America/Montevideo') if end else None
        except Exception:
            start_dt = end_dt = None
        print(f"[DEBUG] params: start={request.args.get('start')}, end={request.args.get('end')}")
        try:
            df = pd.read_csv("monitor_log.csv", parse_dates=["timestamp"])
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC').dt.tz_convert('America/Montevideo')
        except Exception:
            return {"status": "error", "message": "No se pudo leer el log"}
        # Leer tarifas desde el CSV
        tarifas = {}
        try:
            tarifas_df = pd.read_csv("costo energia.csv")
            for _, row in tarifas_df.iterrows():
                key = (row["Tarifa"], row["Franja horaria"])
                tarifas[key] = float(str(row["Precio estimado (UYU $/kWh)"]).replace(",","."))
        except Exception as e:
            tarifas = {}
        if start_dt is not None and end_dt is not None and start_dt.date() == end_dt.date():
            mask = (df["timestamp"].dt.date == start_dt.date())
            df = df[mask]
        else:
            if start_dt is not None:
                df = df[df["timestamp"] >= start_dt]
            if end_dt is not None:
                end_dt_full = end_dt + datetime.timedelta(days=1) - datetime.timedelta(seconds=1)
                df = df[df["timestamp"] <= end_dt_full]
        print(f"[DEBUG] df['timestamp'] dtype: {df['timestamp'].dtype}, tz: {getattr(df['timestamp'].dt, 'tz', None)}")
        def build_sessions_timeout(grp):
            sessions = []
            in_session = False
            start_time = None
            for idx, row in grp.iterrows():
                ts = row["timestamp"]
                status = row["status"]
                if status == "Charging":
                    if not in_session:
                        start_time = ts
                        in_session = True
                else:
                    if in_session:
                        end_time = ts
                        duration = (end_time - start_time).total_seconds() // 60
                        if duration > 0:
                            sessions.append((start_time, end_time, duration))
                        in_session = False
            if in_session and start_time is not None:
                end_time = grp["timestamp"].max()
                if end_time.tzinfo is None:
                    end_time = end_time.tz_localize('America/Montevideo')
                duration = (end_time - start_time).total_seconds() // 60
                if duration > 0:
                    sessions.append((start_time, end_time, duration))
            return sessions
        sessions = []
        for (station, connector), grp in df.groupby(["station", "connector_type"]):
            grp = grp.sort_values("timestamp").reset_index(drop=True)
            for start_s, end_s, mins in build_sessions_timeout(grp):
                sessions.append({
                    "station": station,
                    "connector": connector,
                    "start": start_s,
                    "end": end_s,
                    "duration": int(mins)
                })
        sessions_df = pd.DataFrame(sessions)
        if sessions_df.empty:
            return {"status": "ok", "recaudacion": []}
        # Agrupar por station
        summary = sessions_df.groupby("station").agg(
            total_minutes = ("duration", "sum"),
            num_connectors = ("connector", "nunique"),
            conexiones = ("start", "count")
        ).reset_index()
        recaudacion_list = []
        for idx, row in summary.iterrows():
            nombre = row["station"]
            minutos = row["total_minutes"]
            conexiones = row["conexiones"]
            conectores = row["num_connectors"]
            # Calcular energía total y por franja
            kwh = (minutos / 60) * 60  # Potencia promedio 60 kW
            kwh_punta = 0
            kwh_llano = 0
            kwh_valle = 0
            if not sessions_df[sessions_df["station"] == nombre].empty:
                for _, srow in sessions_df[sessions_df["station"] == nombre].iterrows():
                    start_s = srow["start"]
                    end_s = srow["end"]
                    if pd.isnull(start_s) or pd.isnull(end_s):
                        continue
                    current = start_s
                    # --- AJUSTE CRÍTICO: asegurar current y end_s tz-aware ---
                    if current.tzinfo is None:
                        current = current.tz_localize('America/Montevideo')
                    if end_s.tzinfo is None:
                        end_s = end_s.tz_localize('America/Montevideo')
                    # --- LOG DE DIAGNÓSTICO ---
                    print(f"[DEBUG] current: {current}, tzinfo: {getattr(current, 'tzinfo', None)}")
                    print(f"[DEBUG] end_s: {end_s}, tzinfo: {getattr(end_s, 'tzinfo', None)}")
                    while current < end_s:
                        next_hour = (current + pd.Timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
                        if next_hour.tzinfo is None:
                            next_hour = next_hour.tz_localize('America/Montevideo')
                        if next_hour > end_s:
                            next_hour = end_s
                        mins = int((next_hour - current).total_seconds() // 60)
                        hour = current.hour
                        # Horario punta: 18-22
                        if 18 <= hour < 22:
                            kwh_punta += (mins / 60) * 60
                        # Horario valle: 0-6
                        elif 0 <= hour < 6:
                            kwh_valle += (mins / 60) * 60
                        else:
                            kwh_llano += (mins / 60) * 60
                        current = next_hour
            # Calcular recaudación original
            nota = ""
            recaudacion = None
            nombre_low = nombre.lower()
            if "ute" in nombre_low:
                recaudacion = conexiones * 121.9 + kwh * 10.8
            elif "eone" in nombre_low:
                recaudacion = kwh * 13.42
            else:
                if not sessions_df[sessions_df["station"] == nombre].empty:
                    recaudacion = kwh_llano * 12.54 + kwh_punta * 25.62
                else:
                    nota = "Faltan datos"
            if recaudacion is None:
                nota = "Faltan datos"
            # Escenarios de costo
            # 1. SG (Simple)
            costo_sg = kwh * tarifas.get(("SG (Simple)", "Todo el día"), 0)
            # 2. SDBH (Horaria) - buscar por inclusión en vez de coincidencia exacta
            tarifa_punta = next((v for (t, f), v in tarifas.items() if t == "SDBH (Horaria)" and "Punta" in f), 0)
            tarifa_llano = next((v for (t, f), v in tarifas.items() if t == "SDBH (Horaria)" and ("Llano" in f or "Valle" in f)), 0)
            costo_sdbh = kwh_punta * tarifa_punta + kwh_llano * tarifa_llano
            # 3. GDM (Media tensión)
            tarifa_gdm_punta = next((v for (t, f), v in tarifas.items() if t == "GDM (Media tensión)" and "Punta" in f), 0)
            tarifa_gdm_llano = next((v for (t, f), v in tarifas.items() if t == "GDM (Media tensión)" and "Llano" in f), 0)
            tarifa_gdm_valle = next((v for (t, f), v in tarifas.items() if t == "GDM (Media tensión)" and "Valle" in f), 0)
            costo_gdm = kwh_punta * tarifa_gdm_punta + kwh_llano * tarifa_gdm_llano + kwh_valle * tarifa_gdm_valle
            # 4. GMT (Grandes Usuarios)
            costo_gmt = kwh * tarifas.get(("GMT (Grandes Usuarios)", "Variable"), 0)
            # Recaudación neta
            neta_sg = recaudacion - costo_sg if recaudacion is not None else None
            neta_sdbh = recaudacion - costo_sdbh if recaudacion is not None else None
            neta_gdm = recaudacion - costo_gdm if recaudacion is not None else None
            neta_gmt = recaudacion - costo_gmt if recaudacion is not None else None
            recaudacion_list.append({
                "station": nombre,
                "kwh": float(f"{kwh:.2f}"),
                "recaudacion": float(f"{recaudacion:.2f}") if recaudacion is not None else None,
                "num_connectors": conectores,
                "nota": nota,
                "costo_sg": float(f"{costo_sg:.2f}"),
                "costo_sdbh": float(f"{costo_sdbh:.2f}"),
                "costo_gdm": float(f"{costo_gdm:.2f}"),
                "costo_gmt": float(f"{costo_gmt:.2f}"),
                "neta_sg": float(f"{neta_sg:.2f}") if neta_sg is not None else None,
                "neta_sdbh": float(f"{neta_sdbh:.2f}") if neta_sdbh is not None else None,
                "neta_gdm": float(f"{neta_gdm:.2f}") if neta_gdm is not None else None,
                "neta_gmt": float(f"{neta_gmt:.2f}") if neta_gmt is not None else None
            })
        return {"status": "ok", "recaudacion": recaudacion_list}
    except Exception as e:
        print("[ERROR] Excepción en /data-recaudacion:")
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.route('/recaudacion')
def recaudacion():
    return render_template('recaudacion.html')


@app.route('/limpiar-datos', methods=['POST'])
def limpiar_datos():
    import os
    try:
        open('monitor_log.csv', 'w').close()
        return {'status': 'ok', 'message': 'Datos limpiados'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8501)
