import streamlit as st
import requests
import datetime

# URL endpoint por defecto
default_url = "https://app.eve-move.com/eve/miem"

# Columnas para la tabla
COLUMNS = ["Nombre", "Estado", "Latitud", "Longitud", "Horario", "Conectores", "Tipos", "Potencia(kW)"]

def fetch_data(url):
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            records = data.get("data", [])
        elif isinstance(data, list):
            records = data
        else:
            records = []
        rows = []
        for item in records:
            name = item.get("name", "")
            status = item.get("status", "")
            lat = item.get("latitude", "")
            lon = item.get("longitude", "")
            horario = item.get("openTime", "")
            cnns = item.get("cnns", [])
            n_conn = len(cnns)
            types = "; ".join(f"{c.get('type','')}({c.get('power','')}kW)" for c in cnns)
            total_power = sum(c.get("power", 0) for c in cnns)
            rows.append([name, status, lat, lon, horario, n_conn, types, total_power])
        return rows, None
    except Exception as e:
        return [], str(e)


def main():
    st.title("Dashboard EV Chargers Monitor")
    url = st.text_input("Endpoint URL", value=default_url)
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        st.subheader("JSON crudo")
        st.json(data)
        rows, err = fetch_data(url)
    except Exception as e:
        st.error(f"Error al obtener datos HTTP:\n{e}")
        rows, err = [], str(e)
    # Mostrar tabla o mensajes según resultado
    if err:
        st.error(f"Error al procesar datos:\n{err}")
    elif rows:
        table = [dict(zip(COLUMNS, row)) for row in rows]
        st.table(table)
    else:
        st.info("No hay datos para mostrar.")


if __name__ == '__main__':
    main()
