import argparse
import pandas as pd
from datetime import datetime, timedelta

DEFAULT_LOG = "monitor_log.csv"

def parse_args():
    parser = argparse.ArgumentParser(description="Generar reporte de sesiones de carga y offline.")
    parser.add_argument("--month", type=str, help="Mes en formato YYYY-MM.")
    parser.add_argument("--start-date", type=str, help="Fecha inicio YYYY-MM-DD.")
    parser.add_argument("--end-date", type=str, help="Fecha fin YYYY-MM-DD.")
    parser.add_argument("--log-file", type=str, default=DEFAULT_LOG, help="Ruta al CSV de logs.")
    args = parser.parse_args()
    if args.month and (args.start_date or args.end_date):
        parser.error("No mezclar --month con --start-date/--end-date.")
    if args.start_date and not args.end_date:
        parser.error("--start-date requiere --end-date.")
    if args.end_date and not args.start_date:
        parser.error("--end-date requiere --start-date.")
    return args


def compute_period(args):
    if args.month:
        year, month = map(int, args.month.split("-"))
        start = datetime(year, month, 1)
        if month == 12:
            end = datetime(year + 1, 1, 1)
        else:
            end = datetime(year, month + 1, 1)
        report_name = f"occupancy_report_{args.month}.csv"
    elif args.start_date:
        start = datetime.strptime(args.start_date, "%Y-%m-%d")
        end = datetime.strptime(args.end_date, "%Y-%m-%d") + timedelta(days=1)
        report_name = f"occupancy_report_{args.start_date}_{args.end_date}.csv"
    else:
        start = None
        end = None
        report_name = "occupancy_report.csv"
    return start, end, report_name


def load_filter_data(log_file, start, end):
    df = pd.read_csv(log_file, parse_dates=["timestamp"])
    if start and end:
        df = df[(df["timestamp"] >= start) & (df["timestamp"] < end)]
    return df


def build_sessions(df):
    results = []
    group_cols = ["station", "connector_type"]
    for (station, connector), grp in df.groupby(group_cols):
        grp = grp.sort_values("timestamp")
        session_start = None
        session_status = None
        prev_time = None
        for _, row in grp.iterrows():
            curr_status = row["status"]
            curr_time = row["timestamp"]
            # Detectar inicio de sesión
            if curr_status in ("Charging", "Unavailable"):
                if session_start is None:
                    session_start = curr_time
                    session_status = curr_status
                elif curr_status != session_status:
                    # Cerrar sesión anterior
                    session_end = prev_time
                    duration = session_end - session_start
                    results.append({
                        "station": station,
                        "connector_type": connector,
                        "status": session_status,
                        "start": session_start,
                        "end": session_end,
                        "duration": str(duration)
                    })
                    # Iniciar nueva sesión
                    session_start = curr_time
                    session_status = curr_status
            else:
                # curr_status == Available => cerrar sesión si existe
                if session_start is not None:
                    session_end = prev_time
                    duration = session_end - session_start
                    results.append({
                        "station": station,
                        "connector_type": connector,
                        "status": session_status,
                        "start": session_start,
                        "end": session_end,
                        "duration": str(duration)
                    })
                    session_start = None
                    session_status = None
            prev_time = curr_time
        # Al final de grupo, cerrar sesión abierta
        if session_start is not None:
            session_end = prev_time
            duration = session_end - session_start
            results.append({
                "station": station,
                "connector_type": connector,
                "status": session_status,
                "start": session_start,
                "end": session_end,
                "duration": str(duration)
            })
    return pd.DataFrame(results)


def main():
    args = parse_args()
    start, end, report_file = compute_period(args)
    df = load_filter_data(args.log_file, start, end)
    if df.empty:
        print("No hay datos en el periodo especificado.")
        return
    report_df = build_sessions(df)
    report_df.to_csv(report_file, index=False)
    print(f"Reporte generado: {report_file}")


if __name__ == "__main__":
    main()
