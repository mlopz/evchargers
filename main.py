import requests
import threading
import datetime
import tkinter as tk
from tkinter import ttk, messagebox

# URL endpoint por defecto
default_url = "https://app.eve-move.com/eve/miem"

# Nuevas columnas para visualizar JSON de estaciones
COLUMNS = ["Nombre", "Estado", "Latitud", "Longitud", "Horario", "Conectores", "Tipos", "Potencia(kW)"]


def fetch_data(url):
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            records = data.get('data', [])
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


class App:
    def __init__(self, root):
        self.root = root
        root.title("Monitor EV Chargers")
        root.geometry("800x600")

        top_frame = ttk.Frame(root)
        top_frame.pack(fill='x', padx=10, pady=5)

        ttk.Label(top_frame, text="Endpoint URL:").pack(side='left')
        self.url_var = tk.StringVar(value=default_url)
        ttk.Entry(top_frame, textvariable=self.url_var, width=60).pack(side='left', padx=(5,5))
        ttk.Button(top_frame, text="Actualizar", command=self.on_update).pack(side='left')

        columns = COLUMNS
        self.tree = ttk.Treeview(root, columns=columns, show='headings')
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, anchor='center', width=100)
        self.tree.pack(fill='both', expand=True, padx=10, pady=5)

    def on_update(self):
        threading.Thread(target=self.fetch_and_update, daemon=True).start()

    def fetch_and_update(self):
        url = self.url_var.get()
        rows, err = fetch_data(url)
        self.root.after(0, lambda: self.update_ui(rows, err))

    def update_ui(self, rows, err):
        if err:
            messagebox.showerror("Error", f"Error al obtener datos:\n{err}")
        else:
            for i in self.tree.get_children():
                self.tree.delete(i)
            for row in rows:
                self.tree.insert("", "end", values=row)


if __name__ == '__main__':
    root = tk.Tk()
    app = App(root)
    root.mainloop()
