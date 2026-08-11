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
    # Usamos datetime.now() para asegurar hora local del sistema
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        c.execute("INSERT INTO players (username, created_at, last_active) VALUES (?, ?, ?)", (username, now_str, now_str))
        conn.commit()
    except sqlite3.IntegrityError:
        pass  # Ya existe
    conn.close()


def update_player_balance(username, new_balance, win=False, loss=False):
    """Actualizar balance y stats de un jugador"""
    conn = get_connection()
    c = conn.cursor()
    # Usamos datetime.now() para asegurar hora local del sistema
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if win:
        c.execute("UPDATE players SET balance = ?, wins = wins + 1, last_active = ? WHERE username = ?",
                  (new_balance, now_str, username))
    elif loss:
        c.execute("UPDATE players SET balance = ?, losses = losses + 1, last_active = ? WHERE username = ?",
                  (new_balance, now_str, username))
    else:
        c.execute("UPDATE players SET balance = ?, last_active = ? WHERE username = ?",
                  (new_balance, now_str, username))
    conn.commit()
    conn.close()


def add_trade_history(username, trade_type, result, pnl, rr_ratio=0):
    """Registrar un trade en el historial"""
    conn = get_connection()
    c = conn.cursor()
    player = get_player(username)
    if player:
        # Usamos datetime.now() para asegurar hora local del sistema
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO trade_history (player_id, trade_type, result, pnl, rr_ratio, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                  (player["id"], trade_type, result, pnl, rr_ratio, now_str))
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
            # Usamos datetime.now() para asegurar hora local del sistema
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("UPDATE players SET balance = 10000, wins = 0, losses = 0")
            c.execute("INSERT INTO resets (reason, reset_date) VALUES (?, ?)", ("Reset mensual", now_str))
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
    """
    Inicia una nueva sesión. Si ya hay una abierta (sin end_time), la devuelve.
    Si no, crea una fresca con un ID incremental y la hora actual.
    """
    conn = get_connection()
    c = conn.cursor()
    
    # 1. Buscar si hay una sesión abierta (sin end_time) para evitar duplicados en la misma ejecución
    c.execute("SELECT id FROM sessions WHERE end_time IS NULL ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    if row:
        session_id = row['id']
        conn.close()
        return session_id
        
    # 2. Si no hay abierta, CREAR SIEMPRE UNA NUEVA (ID incremental automático)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO sessions (start_time) VALUES (?)", (now_str,))
    session_id = c.lastrowid
    conn.commit()
    conn.close()
    return session_id


def end_session(session_id):
    """Finaliza una sesión marcando el end_time"""
    conn = get_connection()
    c = conn.cursor()
    # Usamos datetime.now() para asegurar hora local del sistema
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("UPDATE sessions SET end_time = ? WHERE id = ?", (now_str, session_id))
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
    # Usamos datetime.now() para asegurar hora local del sistema
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO session_events (session_id, event_name, timestamp) VALUES (?, ?, ?)", (session_id, event_name, now_str))
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
        where_clause = "date(start_time) = date('now', 'localtime')"
    elif filter_type == 'ayer':
        where_clause = "date(start_time) = date('now', 'localtime', '-1 day')"
    elif filter_type == '3d':
        where_clause = "date(start_time) >= date('now', 'localtime', '-3 days')"
    elif filter_type == '7d':
        where_clause = "date(start_time) >= date('now', 'localtime', '-7 days')"
    elif filter_type == 'ayer_7d':
        where_clause = "date(start_time) BETWEEN date('now', 'localtime', '-14 days') AND date('now', 'localtime', '-7 days')"
    elif filter_type == 'mes':
        where_clause = "date(start_time) >= date('now', 'localtime', 'start of month')"
    elif filter_type == 'ayer_mes':
        where_clause = "date(start_time) BETWEEN date('now', 'localtime', 'start of month', '-1 month') AND date('now', 'localtime', 'start of month', '-1 day')"
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
        SELECT 
            date(start_time) as day, 
            COUNT(*) as sessions, 
            SUM(total_likes) as likes, 
            SUM(total_rounds) as rounds,
            MAX(peak_viewers) as max_peak,
            AVG(CAST(avg_viewers_sum AS REAL) / MAX(1, avg_viewers_count)) as avg_viewers,
            SUM(total_messages) as messages,
            SUM(unique_participants_count) as participants,
            SUM(fxp_distributed) as fxp
        FROM sessions
        WHERE {where_clause}
        GROUP BY day
        ORDER BY day ASC
    """
    c.execute(query_evolution, params)
    evolution = [dict(r) for r in c.fetchall()]

    # Mejor horario (agrupado por hora del día)
    query_hours = f"""
        SELECT 
            strftime('%H', start_time) as hour, 
            SUM(total_likes) as likes, 
            AVG(CAST(avg_viewers_sum AS REAL) / MAX(1, avg_viewers_count)) as avg_viewers,
            SUM(total_messages) as messages,
            SUM(unique_participants_count) as participants
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


def get_sessions_history(limit=50):
    """Obtiene el historial de sesiones registradas"""
    conn = get_connection()
    c = conn.cursor()
    query = """
        SELECT 
            id,
            start_time,
            end_time,
            total_rounds as rounds,
            peak_viewers as max_viewers,
            (CAST(avg_viewers_sum AS REAL) / MAX(1, avg_viewers_count)) as avg_viewers,
            unique_participants_count as participants,
            fxp_distributed as fxp,
            (strftime('%s', end_time) - strftime('%s', start_time)) as duration_secs
        FROM sessions
        WHERE end_time IS NOT NULL
        ORDER BY start_time DESC
        LIMIT ?
    """
    c.execute(query, (limit,))
    sessions = [dict(r) for r in c.fetchall()]
    conn.close()
    return sessions


def get_session_details(session_id):
    """Obtiene el resumen completo de una sesión específica"""
    conn = get_connection()
    c = conn.cursor()
    
    # Resumen base
    c.execute("""
        SELECT *, 
               (strftime('%s', end_time) - strftime('%s', start_time)) as duration_secs
        FROM sessions WHERE id = ?
    """, (session_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    summary = dict(row)
    
    # Votos
    c.execute("SELECT vote_type, count FROM session_votes WHERE session_id = ?", (session_id,))
    votes = {r['vote_type']: r['count'] for r in c.fetchall()}
    
    # RR Stats
    c.execute("SELECT rr_ratio, win_count, loss_count FROM session_rr_stats WHERE session_id = ?", (session_id,))
    rr_stats = [dict(r) for r in c.fetchall()]
    
    # Eventos
    c.execute("SELECT event_name, timestamp FROM session_events WHERE session_id = ? ORDER BY timestamp ASC", (session_id,))
    events = [dict(r) for r in c.fetchall()]
    
    conn.close()
    return {
        "summary": summary,
        "votes": votes,
        "rr_stats": rr_stats,
        "events": events
    }


def get_best_time_analysis():
    """Realiza un análisis profundo para recomendar el mejor horario de live"""
    conn = get_connection()
    c = conn.cursor()
    
    # Agrupar por día de la semana y hora
    # 0=Sunday, 1=Monday, ..., 6=Saturday en strftime('%w', ...)
    query = """
        SELECT 
            strftime('%w', start_time) as dow,
            strftime('%H', start_time) as hour,
            AVG(CAST(avg_viewers_sum AS REAL) / MAX(1, avg_viewers_count)) as avg_v,
            MAX(peak_viewers) as peak_v,
            SUM(unique_participants_count) as total_p,
            SUM(total_messages) as total_m,
            COUNT(*) as session_count
        FROM sessions
        WHERE end_time IS NOT NULL
        GROUP BY dow, hour
        HAVING session_count > 0
        ORDER BY avg_v DESC
    """
    c.execute(query)
    results = c.fetchall()
    
    if not results:
        conn.close()
        return "No hay suficiente información histórica para recomendar un horario."
    
    best = results[0]
    days = ["Domingo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]
    day_name = days[int(best['dow'])]
    
    # Formatear recomendación
    recommendation = f"Mejor horario detectado: {day_name} {best['hour']}:00 - {int(best['hour'])+1:02d}:00"
    
    conn.close()
    return {
        "recommendation": recommendation,
        "best_day": day_name,
        "best_hour": f"{best['hour']}:00",
        "avg_viewers": best['avg_v'],
        "peak_viewers": best['peak_v'],
        "all_data": [dict(r) for r in results]
    }


def get_comparison_data(filter1='hoy', custom1=None, filter2='ayer', custom2=None):
    """Compara métricas entre dos períodos"""
    data1 = get_analytics_data(filter1, custom1)
    data2 = get_analytics_data(filter2, custom2)
    
    s1 = data1['summary']
    s2 = data2['summary']
    
    metrics_to_compare = [
        ('max_peak', 'Viewers Máximos'),
        ('global_avg_viewers', 'Viewers Promedio'),
        ('participants', 'Participantes'),
        ('messages', 'Mensajes'),
        ('likes', 'Likes'),
        ('rounds', 'Rondas'),
        ('fxp', 'FXP Repartido')
    ]
    
    comparison = []
    for key, label in metrics_to_compare:
        val1 = s1.get(key, 0) or 0
        val2 = s2.get(key, 0) or 0
        diff = val1 - val2
        pct = (diff / val2 * 100) if val2 > 0 else (100 if val1 > 0 else 0)
        comparison.append({
            'label': label,
            'val1': val1,
            'val2': val2,
            'diff': diff,
            'pct': pct
        })
        
    # Comparar Votos
    v1 = data1['votes']
    v2 = data2['votes']
    sube1, baja1 = v1.get('SUBE', 0), v1.get('BAJA', 0)
    sube2, baja2 = v2.get('SUBE', 0), v2.get('BAJA', 0)
    
    comparison.append({
        'label': 'Votos SUBE',
        'val1': sube1,
        'val2': sube2,
        'diff': sube1 - sube2,
        'pct': ((sube1 - sube2) / sube2 * 100) if sube2 > 0 else (100 if sube1 > 0 else 0)
    })
    comparison.append({
        'label': 'Votos BAJA',
        'val1': baja1,
        'val2': baja2,
        'diff': baja1 - baja2,
        'pct': ((baja1 - baja2) / baja2 * 100) if baja2 > 0 else (100 if baja1 > 0 else 0)
    })
    
    return comparison

def merge_v2_data(v2_db_path):
    """
    Importa y suma los datos de la Versión 2 a la Versión 3 actual.
    Si el jugador ya existe, suma el balance y las stats. Si no, lo crea.
    """
    if not os.path.exists(v2_db_path):
        print(f"[DB] Archivo V2 no encontrado en: {v2_db_path}")
        return False, "Archivo no encontrado"

    try:
        # Conexión a la DB de la V2
        conn_v2 = sqlite3.connect(v2_db_path)
        conn_v2.row_factory = sqlite3.Row
        c_v2 = conn_v2.cursor()
        
        # Obtener todos los jugadores de la V2 (excluyendo streamer para evitar conflictos de balance base)
        c_v2.execute("SELECT username, balance, wins, losses, created_at FROM players WHERE username != 'LEAN FX'")
        v2_players = c_v2.fetchall()
        
        if not v2_players:
            conn_v2.close()
            return True, "No hay jugadores para importar"

        # Conexión a la DB de la V3
        conn_v3 = get_connection()
        c_v3 = conn_v3.cursor()
        
        imported_count = 0
        updated_count = 0
        
        for p in v2_players:
            username = p['username']
            v2_balance = p['balance']
            v2_wins = p['wins']
            v2_losses = p['losses']
            v2_created = p['created_at']
            
            # Verificar si existe en V3
            c_v3.execute("SELECT id, balance, wins, losses FROM players WHERE username = ?", (username,))
            existing = c_v3.fetchone()
            
            if existing:
                # Sumar a lo existente (Ranking Histórico Total)
                new_balance = existing['balance'] + (v2_balance - 10000) # Solo sumamos la ganancia/perdida neta sobre el base
                new_wins = existing['wins'] + v2_wins
                new_losses = existing['losses'] + v2_losses
                
                c_v3.execute("""UPDATE players 
                             SET balance = ?, wins = ?, losses = ?, last_active = CURRENT_TIMESTAMP 
                             WHERE username = ?""", 
                          (new_balance, new_wins, new_losses, username))
                updated_count += 1
            else:
                # Crear nuevo con los datos de la V2
                c_v3.execute("""INSERT INTO players (username, balance, wins, losses, created_at, last_active) 
                             VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                          (username, v2_balance, v2_wins, v2_losses, v2_created))
                imported_count += 1
        
        conn_v3.commit()
        conn_v3.close()
        conn_v2.close()
        
        msg = f"Migración completada: {imported_count} nuevos, {updated_count} actualizados."
        print(f"[DB] {msg}")
        return True, msg
        
    except Exception as e:
        print(f"[DB] Error en la migración: {e}")
        return False, str(e)
