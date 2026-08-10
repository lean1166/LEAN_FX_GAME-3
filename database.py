"""
Base de datos SQLite para LEAN FX GAME
Guarda: viewers, balances, wins, losses, historial, configuración
"""
import sqlite3
import os
import sys
from datetime import datetime

# Si esta corriendo como .exe (PyInstaller), guardar la DB al lado del .exe
# (persistente), no en la carpeta temporal donde se extraen los archivos.
if getattr(sys, 'frozen', False):
    DB_DIR = os.path.dirname(sys.executable)
else:
    DB_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(DB_DIR, "lean_fx_game.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Crear tablas si no existen"""
    conn = get_connection()
    c = conn.cursor()

    # Tabla de viewers/jugadores
    c.execute('''CREATE TABLE IF NOT EXISTS players (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        balance REAL DEFAULT 10000,
        wins INTEGER DEFAULT 0,
        losses INTEGER DEFAULT 0,
        avatar_url TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_active TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    # Tabla de historial de trades
    c.execute('''CREATE TABLE IF NOT EXISTS trade_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id INTEGER,
        trade_type TEXT,
        result TEXT,
        pnl REAL,
        rr_ratio REAL DEFAULT 0,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (player_id) REFERENCES players(id)
    )''')

    # MIGRACIÓN: Agregar columna rr_ratio si no existe (SQLite no lo hace solo con CREATE TABLE IF NOT EXISTS)
    try:
        c.execute("ALTER TABLE trade_history ADD COLUMN rr_ratio REAL DEFAULT 0")
        print("[DB] Columna 'rr_ratio' agregada a 'trade_history'")
    except sqlite3.OperationalError:
        # La columna probablemente ya existe
        pass

    # Tabla de configuración
    c.execute('''CREATE TABLE IF NOT EXISTS config (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')

    # Tabla de reset mensual
    c.execute('''CREATE TABLE IF NOT EXISTS resets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reset_date TEXT DEFAULT CURRENT_TIMESTAMP,
        reason TEXT
    )''')

    # --- TABLAS DE ANALYTICS (FASE 2) ---
    # Tabla de sesiones
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        start_time TEXT DEFAULT CURRENT_TIMESTAMP,
        end_time TEXT,
        peak_viewers INTEGER DEFAULT 0,
        avg_viewers_sum INTEGER DEFAULT 0,
        avg_viewers_count INTEGER DEFAULT 0,
        total_likes INTEGER DEFAULT 0,
        total_messages INTEGER DEFAULT 0,
        total_rounds INTEGER DEFAULT 0,
        unique_participants_count INTEGER DEFAULT 0,
        fxp_distributed REAL DEFAULT 0
    )''')

    # Tabla de votos de sesión
    c.execute('''CREATE TABLE IF NOT EXISTS session_votes (
        session_id INTEGER,
        vote_type TEXT, -- 'SUBE' o 'BAJA'
        count INTEGER DEFAULT 0,
        PRIMARY KEY (session_id, vote_type),
        FOREIGN KEY (session_id) REFERENCES sessions(id)
    )''')

    # Tabla de RR stats por sesión
    c.execute('''CREATE TABLE IF NOT EXISTS session_rr_stats (
        session_id INTEGER,
        rr_ratio REAL,
        win_count INTEGER DEFAULT 0,
        loss_count INTEGER DEFAULT 0,
        PRIMARY KEY (session_id, rr_ratio),
        FOREIGN KEY (session_id) REFERENCES sessions(id)
    )''')

    # Tabla de eventos activados en sesión
    c.execute('''CREATE TABLE IF NOT EXISTS session_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        event_name TEXT,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES sessions(id)
    )''')

    # Insertar streamer si no existe
    c.execute('''INSERT OR IGNORE INTO players (username, balance) VALUES (?, ?)''',
              ("LEAN FX", 10000))

    # Insertar config por defecto
    defaults = {
        "timer_duration": "10000",
        "tp_multiplier": "3.0",
        "sl_buffer": "3.0",
        "trade_risk": "100",
        "bot_win_rate": "0.70",
        "bot_cooldown": "300000",
        "bot_max_ops_hour": "4",
        "last_reset": datetime.now().strftime("%Y-%m"),
        # Sistema de liquidez por likes (V2)
        "liq_interval_min": "10",     # Cada cuantos minutos se dispara un evento
        "liq_a_target": "100",        # Meta de likes para evento A (bloqueante)
        "liq_c1_likes": "100",        # Evento C - Nivel 1: meta de likes
        "liq_c1_bonus": "500",        # Evento C - Nivel 1: bono FXP
        "liq_c2_likes": "200",        # Evento C - Nivel 2: meta de likes
        "liq_c2_bonus": "1000",       # Evento C - Nivel 2: bono FXP
        "liq_c3_likes": "400",        # Evento C - Nivel 3: meta de likes
        "liq_c3_bonus": "2000",       # Evento C - Nivel 3: bono FXP
        "liq_d_target": "150",        # Meta de likes para evento D (barra unica)
        "liq_d_bonus": "800",         # Bono FXP del evento D
        "tiktok_username": "lean.fx1",  # Cuenta TikTok Live a conectar
        "color_bg": "8,12,20",         # Color de fondo general
        "color_bull": "38,166,154",    # Color velas alcistas
        "color_bear": "239,83,80",     # Color velas bajistas
    }
    for key, value in defaults.items():
        c.execute('''INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)''', (key, value))

    conn.commit()
    conn.close()


def get_player(username):
    """Obtener un jugador por nombre"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM players WHERE username = ?", (username,))
    player = c.fetchone()
    conn.close()
    return player


def create_player(username):
    """Crear un nuevo jugador con balance inicial"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO players (username) VALUES (?)", (username,))
        conn.commit()
    except sqlite3.IntegrityError:
        pass  # Ya existe
    conn.close()


def update_player_balance(username, new_balance, win=False, loss=False):
    """Actualizar balance y stats de un jugador"""
    conn = get_connection()
    c = conn.cursor()
    if win:
        c.execute("UPDATE players SET balance = ?, wins = wins + 1, last_active = CURRENT_TIMESTAMP WHERE username = ?",
                  (new_balance, username))
    elif loss:
        c.execute("UPDATE players SET balance = ?, losses = losses + 1, last_active = CURRENT_TIMESTAMP WHERE username = ?",
                  (new_balance, username))
    else:
        c.execute("UPDATE players SET balance = ?, last_active = CURRENT_TIMESTAMP WHERE username = ?",
                  (new_balance, username))
    conn.commit()
    conn.close()


def add_trade_history(username, trade_type, result, pnl, rr_ratio=0):
    """Registrar un trade en el historial"""
    conn = get_connection()
    c = conn.cursor()
    player = get_player(username)
    if player:
        c.execute("INSERT INTO trade_history (player_id, trade_type, result, pnl, rr_ratio) VALUES (?, ?, ?, ?, ?)",
                  (player["id"], trade_type, result, pnl, rr_ratio))
    conn.commit()
    conn.close()


def get_top_players(limit=5):
    """Obtener los top jugadores por balance (excluyendo al streamer)"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""SELECT username, balance, wins, losses 
                 FROM players 
                 WHERE username != 'LEAN FX'
                 ORDER BY balance DESC 
                 LIMIT ?""", (limit,))
    players = c.fetchall()
    conn.close()
    return [dict(p) for p in players]


def get_streamer_stats():
    """Obtener stats del streamer"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM players WHERE username = 'LEAN FX'")
    streamer = c.fetchone()
    conn.close()
    if streamer:
        return dict(streamer)
    return {"username": "LEAN FX", "balance": 10000, "wins": 0, "losses": 0}


def get_config(key, default=None):
    """Obtener un valor de configuración"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM config WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    if row:
        return row["value"]
    return default


def set_config(key, value):
    """Guardar un valor de configuración"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()


def reset_all_players():
    """Reiniciar todos los balances y stats (reset mensual)"""
    import time as _time
    for attempt in range(3):
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute("UPDATE players SET balance = 10000, wins = 0, losses = 0")
            c.execute("INSERT INTO resets (reason) VALUES (?)", ("Reset mensual",))
            c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ("last_reset", datetime.now().strftime("%Y-%m")))
            conn.commit()
            conn.close()
            return
        except Exception as e:
            print(f"[DB] Reset intento {attempt+1}/3 falló: {e}")
            _time.sleep(0.5)
    print("[DB] No se pudo resetear después de 3 intentos")


def check_monthly_reset():
    """Verificar si hay que hacer reset mensual"""
    last_reset = get_config("last_reset", "")
    current_month = datetime.now().strftime("%Y-%m")
    if last_reset != current_month:
        reset_all_players()
        return True
    return False


def get_all_players_count():
    """Obtener cantidad total de jugadores"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as count FROM players WHERE username != 'LEAN FX'")
    result = c.fetchone()
    conn.close()
    return result["count"]


# Inicializar DB al importar
init_db()



def get_recent_results(username, limit=20):
    """
    Obtener los resultados (WIN/LOSS) más recientes de un jugador, del más
    nuevo al más viejo. Usado por window_streamer.py para calcular la racha
    actual sin depender del trade_history en memoria de main.py (que vive en
    otro proceso).
    """
    conn = get_connection()
    c = conn.cursor()
    player = get_player(username)
    if not player:
        conn.close()
        return []
    c.execute("""SELECT result FROM trade_history
                 WHERE player_id = ?
                 ORDER BY id DESC
                 LIMIT ?""", (player["id"], limit))
    rows = c.fetchall()
    conn.close()
    return [r["result"] for r in rows]


def add_bonus_to_all_players(amount):
    """
    Sumar un bono de FXP al balance de TODOS los viewers (no al streamer),
    usado por los eventos de 'liquidez por likes' cuando se alcanza la meta.
    No cuenta como win/loss, solo suma balance.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE players SET balance = balance + ? WHERE username != 'LEAN FX'", (amount,))
    conn.commit()
    conn.close()


def get_all_players_ranked():
    """Obtener todos los jugadores ordenados por balance (excluyendo streamer)"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""SELECT username, balance, wins, losses 
                 FROM players 
                 WHERE username != 'LEAN FX'
                 ORDER BY balance DESC""")
    players = c.fetchall()
    conn.close()
    return [dict(p) for p in players]


# --- FUNCIONES DE ANALYTICS (FASE 2) ---

def start_session():
    """Inicia una nueva sesión y devuelve su ID"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO sessions (start_time) VALUES (CURRENT_TIMESTAMP)")
    session_id = c.lastrowid
    conn.commit()
    conn.close()
    return session_id


def end_session(session_id):
    """Finaliza una sesión marcando el end_time"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE sessions SET end_time = CURRENT_TIMESTAMP WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()


def update_session_metrics(session_id, viewers, likes, messages, participants_count):
    """Actualiza métricas acumuladas y picos de la sesión"""
    conn = get_connection()
    c = conn.cursor()
    # Actualizar pico y promedios
    c.execute("""UPDATE sessions SET 
                 peak_viewers = MAX(peak_viewers, ?),
                 avg_viewers_sum = avg_viewers_sum + ?,
                 avg_viewers_count = avg_viewers_count + 1,
                 total_likes = ?,
                 total_messages = ?,
                 unique_participants_count = MAX(unique_participants_count, ?)
                 WHERE id = ?""", (viewers, viewers, likes, messages, participants_count, session_id))
    conn.commit()
    conn.close()


def add_session_round(session_id):
    """Incrementa el contador de rondas de la sesión"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE sessions SET total_rounds = total_rounds + 1 WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()


def add_session_vote(session_id, vote_type):
    """Registra un voto en la sesión"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO session_votes (session_id, vote_type, count) 
                 VALUES (?, ?, 1)
                 ON CONFLICT(session_id, vote_type) 
                 DO UPDATE SET count = count + 1""", (session_id, vote_type))
    conn.commit()
    conn.close()


def add_session_rr_result(session_id, rr_ratio, win=True):
    """Registra el resultado de un RR en la sesión"""
    conn = get_connection()
    c = conn.cursor()
    if win:
        c.execute("""INSERT INTO session_rr_stats (session_id, rr_ratio, win_count) 
                     VALUES (?, ?, 1)
                     ON CONFLICT(session_id, rr_ratio) 
                     DO UPDATE SET win_count = win_count + 1""", (session_id, rr_ratio))
    else:
        c.execute("""INSERT INTO session_rr_stats (session_id, rr_ratio, loss_count) 
                     VALUES (?, ?, 1)
                     ON CONFLICT(session_id, rr_ratio) 
                     DO UPDATE SET loss_count = loss_count + 1""", (session_id, rr_ratio))
    conn.commit()
    conn.close()


def add_session_event(session_id, event_name):
    """Registra la activación de un evento en la sesión"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO session_events (session_id, event_name) VALUES (?, ?)", (session_id, event_name))
    conn.commit()
    conn.close()


def add_session_fxp(session_id, amount):
    """Acumula el FXP repartido en la sesión"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE sessions SET fxp_distributed = fxp_distributed + ? WHERE id = ?", (amount, session_id))
    conn.commit()
    conn.close()


def get_analytics_data(filter_type='hoy', custom_dates=None):
    """
    Obtiene datos agregados según el filtro:
    'hoy', 'ayer', '7d', '3d', 'mes', 'custom'
    """
    conn = get_connection()
    c = conn.cursor()

    where_clause = ""
    params = []

    if filter_type == 'hoy':
        where_clause = "date(start_time) = date('now')"
    elif filter_type == 'ayer':
        where_clause = "date(start_time) = date('now', '-1 day')"
    elif filter_type == '3d':
        where_clause = "date(start_time) >= date('now', '-3 days')"
    elif filter_type == '7d':
        where_clause = "date(start_time) >= date('now', '-7 days')"
    elif filter_type == 'mes':
        where_clause = "date(start_time) >= date('now', 'start of month')"
    elif filter_type == 'custom' and custom_dates:
        where_clause = "date(start_time) BETWEEN ? AND ?"
        params = [custom_dates[0], custom_dates[1]]

    # Resumen general de sesiones
    query_sessions = f"""
        SELECT 
            COUNT(*) as sessions_count,
            SUM(total_rounds) as rounds,
            MAX(peak_viewers) as max_peak,
            AVG(CAST(avg_viewers_sum AS REAL) / MAX(1, avg_viewers_count)) as global_avg_viewers,
            SUM(total_likes) as likes,
            SUM(total_messages) as messages,
            SUM(unique_participants_count) as participants,
            SUM(fxp_distributed) as fxp,
            SUM(strftime('%s', end_time) - strftime('%s', start_time)) as total_duration_secs
        FROM sessions
        WHERE {where_clause}
    """
    c.execute(query_sessions, params)
    summary = dict(c.fetchone())

    # Votos Sube vs Baja
    query_votes = f"""
        SELECT vote_type, SUM(count) as total
        FROM session_votes
        WHERE session_id IN (SELECT id FROM sessions WHERE {where_clause})
        GROUP BY vote_type
    """
    c.execute(query_votes, params)
    votes = {r['vote_type']: r['total'] for r in c.fetchall()}

    # RR Stats
    query_rr = f"""
        SELECT rr_ratio, SUM(win_count) as wins, SUM(loss_count) as losses
        FROM session_rr_stats
        WHERE session_id IN (SELECT id FROM sessions WHERE {where_clause})
        GROUP BY rr_ratio
        ORDER BY (SUM(win_count) + SUM(loss_count)) DESC
    """
    c.execute(query_rr, params)
    rr_stats = [dict(r) for r in c.fetchall()]

    # Eventos
    query_events = f"""
        SELECT event_name, COUNT(*) as count
        FROM session_events
        WHERE session_id IN (SELECT id FROM sessions WHERE {where_clause})
        GROUP BY event_name
    """
    c.execute(query_events, params)
    events = [dict(r) for r in c.fetchall()]

    # Evolución (por día)
    query_evolution = f"""
        SELECT date(start_time) as day, COUNT(*) as sessions, SUM(total_likes) as likes, SUM(total_rounds) as rounds
        FROM sessions
        WHERE {where_clause}
        GROUP BY day
        ORDER BY day ASC
    """
    c.execute(query_evolution, params)
    evolution = [dict(r) for r in c.fetchall()]

    # Mejor horario (agrupado por hora del día)
    query_hours = f"""
        SELECT strftime('%H', start_time) as hour, SUM(total_likes) as likes, AVG(CAST(avg_viewers_sum AS REAL) / MAX(1, avg_viewers_count)) as avg_viewers
        FROM sessions
        WHERE {where_clause}
        GROUP BY hour
        ORDER BY avg_viewers DESC
    """
    c.execute(query_hours, params)
    best_hours = [dict(r) for r in c.fetchall()]

    conn.close()
    return {
        "summary": summary,
        "votes": votes,
        "rr_stats": rr_stats,
        "events": events,
        "evolution": evolution,
        "best_hours": best_hours
    }
