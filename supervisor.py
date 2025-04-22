import time
import subprocess
import requests
import sys
import psutil

BACKEND_CMD = [sys.executable, 'webapp.py']
BACKEND_URL = 'http://localhost:8501'
MONITOR_CMD = [sys.executable, 'monitor_sql.py']
CHECK_INTERVAL = 300  # 5 minutos en segundos


def is_process_running(script_name):
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['cmdline'] and script_name in proc.info['cmdline']:
                return True
        except Exception:
            continue
    return False


def check_backend():
    try:
        resp = requests.get(BACKEND_URL, timeout=5)
        if resp.status_code == 200:
            print('[Supervisor] Backend OK')
            return True
        else:
            print(f'[Supervisor] Backend responde pero con status {resp.status_code}')
            return False
    except Exception as e:
        print(f'[Supervisor] Backend NO responde: {e}')
        return False


def start_process(cmd, name):
    print(f'[Supervisor] Lanzando {name}...')
    subprocess.Popen(cmd)


def main():
    while True:
        # Backend
        if not check_backend():
            if not is_process_running('webapp.py'):
                start_process(BACKEND_CMD, 'backend')
            else:
                print('[Supervisor] Proceso webapp.py ya existe, esperando...')
        # Monitor
        if not is_process_running('monitor_sql.py'):
            start_process(MONITOR_CMD, 'monitor_sql.py')
        else:
            print('[Supervisor] Proceso monitor_sql.py ya existe, esperando...')
        time.sleep(CHECK_INTERVAL)


if __name__ == '__main__':
    main()
