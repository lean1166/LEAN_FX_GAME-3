"""
LEAN FX GAME - Launcher (V2, arquitectura multi-ventana)

Arranca los 3 procesos del juego con un solo doble-click:
  1. main.py            -> el gráfico (velas, zonas, timer, voto TikTok, audio)
  2. window_streamer.py -> panel del streamer (siempre visible)
  3. window_ranking.py  -> TOP 5 / ranking (siempre visible)

Cada uno abre su propia ventana pygame independiente, así en OBS podés
agregar cada una como una "Captura de ventana" separada y ubicarla donde
quieras en el layout del live.

Comportamiento de cierre: main.py es el proceso "principal" (tiene el menú,
el ESC, el diálogo de salir). Cuando main.py termina (lo cerrás desde el
juego o con la X), el launcher cierra automáticamente las otras dos
ventanas satélite. Si cerrás el launcher directamente (Ctrl+C en consola,
o matás el proceso), también se cierran las 3.
"""
import os
import sys
import subprocess
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SCRIPTS = [
    "main.py", 
    "window_streamer.py", 
    "window_ranking.py", 
    "banner_marquee.py",
    "window_analytics.py"
]


def launch(script_name):
    script_path = os.path.join(BASE_DIR, script_name)
    return subprocess.Popen([sys.executable, script_path], cwd=BASE_DIR)


def terminate(proc, name, timeout=3):
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"[launcher] {name} no respondió, forzando cierre...")
        proc.kill()
    except Exception as e:
        print(f"[launcher] Error cerrando {name}: {e}")


def main():
    print("[launcher] Iniciando LEAN FX GAME (arquitectura multi-ventana)...")
    processes = {}
    try:
        for script in SCRIPTS:
            print(f"[launcher] Lanzando {script}...")
            processes[script] = launch(script)
            time.sleep(0.5)  # Pequeño delay para que no compitan por la GPU al abrir

        main_proc = processes["main.py"]

        # Mientras main.py (el gráfico) siga corriendo, todo sigue abierto.
        while True:
            if main_proc.poll() is not None:
                print("[launcher] main.py se cerró. Cerrando ventanas satélite...")
                break
            # Si alguna ventana satélite crashea sola, no cerramos todo el juego
            # (el streamer, el ranking o analytics pueden reintentarse manualmente después),
            # solo lo avisamos por consola.
            for name in ("window_streamer.py", "window_ranking.py", "banner_marquee.py", "window_analytics.py"):
                p = processes.get(name)
                if p is not None and p.poll() is not None and p.poll() != 0:
                    print(f"[launcher] AVISO: {name} se cerró inesperadamente (código {p.poll()}).")
                    processes[name] = None
            time.sleep(1)

    except KeyboardInterrupt:
        print("[launcher] Interrumpido por el usuario. Cerrando todo...")
    finally:
        for name, proc in processes.items():
            terminate(proc, name)
        print("[launcher] Todos los procesos cerrados.")


if __name__ == "__main__":
    main()

    
