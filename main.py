import sys
import os
import random
import math
import pygame
import tkinter as tk
from tkinter import colorchooser

from shared_paths import BASE_DIR, SOUND_DIR, PROFILE_DIR, find_asset, find_profile_image
from avatar_utils import get_viewer_avatar
from database import (get_streamer_stats, update_player_balance, add_trade_history,
                      check_monthly_reset, get_config, set_config, create_player,
                      get_player, get_all_players_ranked, add_bonus_to_all_players,
                      reset_all_players, merge_v2_data,
                      # Fase 2 Analytics
                      start_session, end_session, update_session_metrics,
                      add_session_round, add_session_vote, add_session_rr_result,
                      add_session_event, add_session_fxp)
from ranking_utils import load_top_viewers
from tiktok_chat import TikTokChatReader
# Inicializar el lector de TikTok globalmente para que arranque al iniciar main.py
tiktok_reader = TikTokChatReader(username="lean.fx1")
tiktok_reader.start()
import luvvoice_tts

# --- CONFIGURACIÓN DE COLORES PERSONALIZABLES ---
def parse_color(c_str, default=(255, 255, 255)):
    try:
        r, g, b = map(int, c_str.split(","))
        return (r, g, b)
    except:
        return default

def pick_color(initial_color=(255, 255, 255)):
    """Abre un selector de color de sistema y devuelve (r, g, b) o None."""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    color = colorchooser.askcolor(color=initial_color, title="Seleccionar Color")
    root.destroy()
    if color[0]:
        return tuple(map(int, color[0]))
    return None

COLOR_PRESETS_BG = [
    (8, 12, 20), (0, 0, 0), (13, 17, 23), (20, 20, 25), (10, 15, 30)
]
COLOR_PRESETS_BULL = [
    (38, 166, 154), (34, 197, 94), (0, 220, 255), (230, 230, 230), (0, 255, 0)
]
COLOR_PRESETS_BEAR = [
    (239, 83, 80), (255, 68, 68), (255, 152, 0), (255, 0, 255), (100, 100, 100)
]

# --- CLASE DE GESTIÓN DE AUDIO CON COLA Y CONGELAMIENTO ---
class AudioManager:
    def __init__(self, audio_dir=None):
        from shared_paths import SOUND_DIR
        self.audio_dir = audio_dir if audio_dir else SOUND_DIR
        self._pausa_activa = False
        self._force_pause = False # Nueva bandera para pausas manuales (ej: durante TTS)
        # Canal dedicado para locuciones y eventos (evita conflictos con música ambiental)
        self.channel = pygame.mixer.Channel(2)

    def play(self, audio_item, pausar_mercado=False):
        """Reproduce un audio. Si pausar_mercado es True, la bandera juego_pausado se mantendrá activa mientras suene."""
        if not audio_item:
            return
            
        sound = None
        if isinstance(audio_item, pygame.mixer.Sound):
            sound = audio_item
        elif isinstance(audio_item, str):
            if os.path.isabs(audio_item):
                full_path = audio_item
            else:
                full_path = os.path.join(self.audio_dir, audio_item)
            
            if os.path.exists(full_path):
                try:
                    sound = pygame.mixer.Sound(full_path)
                except Exception as e:
                    print(f"[AUDIO MANAGER] Error cargando {full_path}: {e}")
        
        if sound:
            # Si se solicita pausa, activamos la marca. El estado real de pausa
            # se consultará vía property que verifica si el canal está ocupado.
            self._pausa_activa = pausar_mercado
            self.channel.play(sound)

    def set_force_pause(self, state: bool):
        """Activa o desactiva la pausa forzada del mercado."""
        self._force_pause = state

    @property
    def juego_pausado(self):
        """Devuelve True si el mercado debe estar congelado (audio con pausa en curso o pausa forzada)."""
        return self._force_pause or (self._pausa_activa and self.channel.get_busy())

    def is_playing(self):
        """Devuelve True si hay audio sonando en el canal de locución."""
        return self.channel.get_busy()

try:
    pygame.init()
    pygame.mixer.init()
    # Detectar resolución de pantalla automáticamente
    display_info = pygame.display.Info()
    SCREEN_W = display_info.current_w
    SCREEN_H = display_info.current_h
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.NOFRAME)
    pygame.display.set_caption("LEAN FX GAME")
except Exception as e:
    print("[ERROR GRAFICO]:", e)
    sys.exit(1)

# Instancia global del gestor de audio
audio_manager = AudioManager()

# Vincular Luvvoice TTS con nuestro gestor de colas para congelar el precio
luvvoice_tts.set_audio_callback(audio_manager.play)

# NOTA (arquitectura multi-ventana V2): main.py ya NO dibuja el panel del
# streamer ni el TOP 5 / ranking. Esas ventanas viven en window_streamer.py
# y window_ranking.py (procesos separados, para poder capturarlas como
# fuentes independientes en OBS). main.py sigue siendo el único dueño del
# audio y de la conexión al chat de TikTok. Lanzarlos juntos con launcher.py.

# Icono del juego (fuera del try principal para que no crashee)
icon_path = find_asset("icon.png", "icon.ico")
if icon_path:
    try:
        pygame.display.set_icon(pygame.image.load(icon_path))
    except:
        print("[AVISO] No se pudo cargar el icono")

# --- CARGAR SONIDOS ---
def load_sound(filename):
    path = os.path.join(SOUND_DIR, filename)
    if os.path.exists(path):
        return pygame.mixer.Sound(path)
    else:
        print(f"[AVISO] Sonido no encontrado: {path}")
        return None

sound_bos = load_sound("BOS.mp3")
sound_fractal = load_sound("FRACTAL.mp3")
sound_win = load_sound("WIN.mp3")
sound_loss = load_sound("LOSS.mp3")
sound_zoom = load_sound("ZOOM.mp3")
sound_liquidity_start = load_sound("LIQUIDITY_START.mp3")   # Arranca un evento de likes
sound_like_milestone = load_sound("LIKE_MILESTONE.mp3")     # Se alcanza un nivel/meta
sound_liquidity_success = load_sound("LIQUIDITY_SUCCESS.mp3")  # Bono pagado con exito
sound_tick = load_sound("TICK.mp3")
sound_ambient = load_sound("AMBIENT.mp3")
sound_game_music = load_sound("GAME_MUSIC.mp3")
sound_levelup = load_sound("LEVELUP.mp3")  # Sonido cuando alguien sube en TOP 5

# --- PLAYLIST DE MÚSICA (detecta automáticamente 1.mp3, 2.mp3, etc.) ---
music_playlist = []
for i in range(1, 36):
    mp = os.path.join(SOUND_DIR, f"{i}.mp3")
    if os.path.exists(mp):
        music_playlist.append(mp)
if not music_playlist and sound_game_music is not None:
    music_playlist = []  # Usa GAME_MUSIC como fallback
random.shuffle(music_playlist)
music_current_index = 0
music_playing = False

# --- CARGAR VOCES DE ZONA (Jorge de México) ---
zona_voices = []
for i in range(1, 13):
    sv = load_sound(f"ZONA_VOZ_{i}.mp3")
    if sv is not None:
        zona_voices.append(sv)
zona_voice_last = -1  # Para no repetir la misma voz 2 veces seguidas

# Voces LEAN FX opera
lean_buy_voices = []
for i in range(1, 4):
    sv = load_sound(f"LEAN_BUY_{i}.mp3")
    if sv is not None:
        lean_buy_voices.append(sv)
lean_sell_voices = []
for i in range(1, 4):
    sv = load_sound(f"LEAN_SELL_{i}.mp3")
    if sv is not None:
        lean_sell_voices.append(sv)

# Voces resultado
voz_win_voices = []
for i in range(1, 4):
    sv = load_sound(f"VOZ_WIN_{i}.mp3")
    if sv is not None:
        voz_win_voices.append(sv)
voz_loss_voices = []
for i in range(1, 4):
    sv = load_sound(f"VOZ_LOSS_{i}.mp3")
    if sv is not None:
        voz_loss_voices.append(sv)

# Estado de voz (para que el timer empiece después de que termine de hablar)
zona_voice_playing = False
zona_voice_playing = False
zona_voice_channel = None
total_operations = 0  # Contador de operaciones totales en el stream
# Freeze por voz: congela el gráfico mientras habla (WIN/LOSS/LEAN FX)
voice_freeze_active = False
voice_freeze_start = 0
VOICE_FREEZE_DURATION = 5000  # 5 seg máximo de freeze por voz de resultado
# --- STREAK SYSTEM ---
viewer_streaks = {}  # {"username": current_streak_count}
streak_display = None  # {"name": str, "streak": int, "start_time": ms} activo en pantalla
STREAK_DISPLAY_DURATION = 4000  # 4 segundos visible
SL_HIT_AUDIO_FLAG = False  # Flag para activar audios en el futuro
STREAK_MIN = 2  # Mínimo de wins seguidos para mostrar (2 para testing, 3 para producción)

# --- TICKER DE EVENTOS (CONSOLA) ---
ticker_events = []
def add_ticker_event(msg):
    global ticker_events
    timestamp = pygame.time.get_ticks()
    # Limpiar formato de mensajes
    clean_msg = msg.strip().upper()
    ticker_events.append({"msg": clean_msg, "time": timestamp})
    if len(ticker_events) > 8: # Mantener solo los últimos 8
        ticker_events.pop(0)

def play_sound(sound):
    if sound is not None and game_started:
        audio_manager.play(sound, pausar_mercado=False)

game_started = False  # Se activa al presionar INICIAR

def trade_win(amount, rr_ratio=0):
    """Llamar cuando se gana un trade. Suma al balance"""
    global fxp_balance, wins
    fxp_balance += amount
    wins += 1
    update_player_balance("LEAN FX", fxp_balance, win=True)
    add_trade_history("LEAN FX", "BUY", "WIN", amount, rr_ratio)
    add_ticker_event(f"STREAMER WIN: +{int(amount)} FXP (RR {rr_ratio})")

def trade_loss(amount, rr_ratio=1.0):
    """Llamar cuando se pierde un trade. Resta del balance"""
    global fxp_balance, losses
    fxp_balance -= amount
    update_player_balance("LEAN FX", fxp_balance, loss=True)
    add_trade_history("LEAN FX", "SELL", "LOSS", -amount, rr_ratio)
    add_ticker_event(f"STREAMER LOSS: -{int(amount)} FXP")

def close_position(trade_data, g_dir, grp, lvl, is_viewer=False):
    """Cierra una posición de forma forzosa al tocar la Meta Máxima."""
    global market_exhaustion_active, market_exhaustion_start, market_exhaustion_dir
    global flash_active, flash_start_time, flash_color, flash_text, total_operations
    global active_trade, viewer_trade_active, bot_bias_active
    
    current_time = pygame.time.get_ticks()
    
    # 1. Bloqueo de Seguridad: Marcar como resuelto e impedir más cálculos
    lvl["resolved"] = True
    grp["resolved"] = True
    trade_data["cerrada"] = True
    
    # 2. Feedback Visual y Audio
    grp["flash"] = {"start": current_time, "color": GLOBAL_COLOR_BULL}
    
    # Audio de Meta Máxima
    audio_manager.set_force_pause(True)
    audio_manager.play(f"{g_dir.lower().replace('sell', 'sel')}_tp{int(lvl['rr'])}.mp3", pausar_mercado=True)
    
    # Flash de pantalla si es el bando principal o trade de viewers
    if is_viewer or g_dir == bot_decision:
        flash_active = True
        flash_start_time = current_time
        flash_color = GLOBAL_COLOR_BULL
        flash_text = f"+{int(lvl['rr']) * 100} FXP"
        total_operations += 1
        
        # Voces de victoria (solo si no hay viewers operando para no saturar)
        if not is_viewer and voz_win_voices and viewer_trade_active is None:
            audio_manager.play(f"VOZ_WIN_{random.randint(1, 7)}.mp3")
        elif is_viewer:
            luvvoice_tts.play_on_max_tp()

    # 4. Limpieza Inmediata (opcional, pero marcamos para borrado en el siguiente frame)
    
    print(f"[SISTEMA] META MÁXIMA ALCANZADA (RR {lvl['rr']}). Posición cerrada y PnL congelado.")

pygame.font.init()
font_price = pygame.font.SysFont("Arial", 16, bold=True)
font_hud_title = pygame.font.SysFont("Arial", 18, bold=True)
font_hud_val = pygame.font.SysFont("Arial", 22, bold=True)
font_bos = pygame.font.SysFont("Arial", 16, bold=True)
font_ob = pygame.font.SysFont("Consolas", 13, bold=True)
# --- CARGAR AVATAR DEL STREAMER ---
# Nota: window_streamer.py carga esta misma imagen por su cuenta (es un
# proceso separado); main.py ya no dibuja el panel del streamer, pero
# mantenemos avatar_img aquí por si en el futuro se necesita en el gráfico.
avatar_img = None
_profile_path = find_profile_image()
if _profile_path:
    avatar_img = pygame.image.load(_profile_path).convert_alpha()
    avatar_img = pygame.transform.smoothscale(avatar_img, (200, 200))
else:
    print(f"[AVISO] Avatar no encontrado en: {PROFILE_DIR}")

# get_viewer_avatar() ahora viene de avatar_utils.py (compartido con window_ranking.py)

# --- TOP 5 VIEWERS (desde base de datos) ---
font_top = pygame.font.SysFont("Arial", 14, bold=True)
# Verificar reset mensual
check_monthly_reset()
# Crear jugadores de prueba si la DB está vacía
db_top = get_all_players_ranked()
# Solo crear jugadores si la DB está vacía
# Solo viewers reales - no crear jugadores de prueba
db_top = get_all_players_ranked()

top_viewers = load_top_viewers()
# --- SONIDO LEVELUP cuando alguien sube en el TOP 5 ---
# (El dibujo visual del TOP 5 y sus flechitas +/- ahora vive en window_ranking.py,
# ese proceso no tiene audio propio, así que main.py sigue chequeando el orden
# solo para decidir cuándo reproducir el sonido)
top5_prev_order = [v["name"] for v in top_viewers]
top5_last_refresh = 0
TOP5_REFRESH_INTERVAL = 3000  # Chequear cada 3 segundos

# --- ESTADO DE ANIMACIÓN DE LA GUÍA ---
guide_animation_start = 0

def check_top5_levelup_sound(current_time):
    """Refresca top_viewers y reproduce LEVELUP.mp3 si alguien subió de posición"""
    global top_viewers, top5_prev_order
    new_viewers = load_top_viewers()
    new_order = [v["name"] for v in new_viewers]
    someone_moved_up = False
    for name in new_order:
        if name in top5_prev_order:
            if new_order.index(name) < top5_prev_order.index(name):
                someone_moved_up = True
        else:
            someone_moved_up = True
    if someone_moved_up and sound_levelup is not None and game_started:
        play_sound(sound_levelup)
    top5_prev_order = new_order
    top_viewers = new_viewers
# Cargar stats del streamer desde DB
streamer_data = get_streamer_stats()
fxp_balance = streamer_data["balance"]
wins = streamer_data["wins"]
losses = streamer_data["losses"]
STREAMER_NAME = "LEAN FX"
candles = []
active_trade = None
price = 1000
# --- SISTEMA DE IMPULSO Y RETROCESO (Dinámico: 4-6 Impulsos, 2-3 Retrocesos) ---
trend_dir = random.choice([-1, 1])
market_state = "impulse"
wave_count = 1  # Mantenido por compatibilidad
trend_length = random.randint(4, 6)
trend_count = 0
trend_strength = random.uniform(10, 18)
current_dir = trend_dir
impulse_in_trend = 0

for _ in range(180):
    trend_count += 1
    
    if trend_count >= trend_length:
        trend_count = 0
        if market_state == "impulse":
            market_state = "retracement"
            trend_length = random.randint(2, 3)
            trend_strength = random.uniform(5, 9)
            current_dir = -trend_dir
            impulse_in_trend += 1
        else:
            market_state = "impulse"
            trend_length = random.randint(4, 6)
            trend_strength = random.uniform(10, 18)
            
            # Cambio de tendencia tras 1-2 impulsos (Ciclos Ágiles)
            if impulse_in_trend >= random.randint(1, 2):
                trend_dir *= -1
                impulse_in_trend = 0
            current_dir = trend_dir
    else:
        # Mantener la dirección de la sub-onda actual
        if market_state == "impulse":
            current_dir = trend_dir
        else: # retracement
            current_dir = -trend_dir

    # Sesgo del tick basado en el estado actual
    bias_prob = 0.82 if market_state == "impulse" else 0.65
    
    if random.random() < bias_prob:
        body = random.uniform(trend_strength * 0.4, trend_strength * 1.1) * current_dir
    else:
        body = random.uniform(0.1, trend_strength * 0.5) * -current_dir
        
    open_p = price
    close_p = open_p + body
    
    # --- MECHAS REALISTAS ---
    wick_base = trend_strength * 0.2
    wick_up = random.uniform(0.1, wick_base) if body > 0 else random.uniform(0.2, wick_base * 1.5)
    wick_down = random.uniform(0.2, wick_base * 1.5) if body > 0 else random.uniform(0.1, wick_base)
        
    high_p = max(open_p, close_p) + wick_up
    low_p = min(open_p, close_p) - wick_down
    
    candles.append({"open": open_p, "close": close_p, "high": high_p, "low": low_p})
    price = close_p
current_candle = candles[-1]
buttons_active = False
# --- SL/TP: se resuelve dentro del GAME LOOP usando OHLC real ---
  
# --- SISTEMA DE AGOTAMIENTO DE MERCADO ---
market_exhaustion_active = False
market_exhaustion_dir = 0
market_exhaustion_start = 0
MARKET_EXHAUSTION_DURATION = 8000  # 8 segundos de retroceso forzado
TRADE_RISK = 100  # Siempre pierdes 100 FXP, sin importar el tamaño del Riesgo
TP_MULTIPLIER = 3.0  # Meta:Riesgo 3:1
SL_BUFFER = 1.0  # Riesgo 1 pip debajo/encima de la zona
ZONE_PADDING = 3.5  # Margen extra para que las zonas sean más grandes y realistas
TIMER_DURATION = 10000  # 10 segundos en ms (temporal para pruebas)
trade_history = []
font_btn = pygame.font.SysFont("Arial", 20, bold=True)
font_trade = pygame.font.SysFont("Arial", 14, bold=True)
font_timer = pygame.font.SysFont("Arial", 48, bold=True)
# Estado del timer y zona
zone_frozen = False  # True cuando el gráfico está congelado
zone_timer_start = 0  # Momento en que se activó el timer
zone_detected = None  # Info de la zona detectada {"high", "low", "type"}
trade_decided = False  # Si ya eligió BUY o SELL durante el timer
zones_mitigated = set()  # Zonas ya mitigadas (no se repiten)
zones_mitigated_info = {}  # {"zone_id": {"index": candle_index, "bos_count": 0}} info de mitigación
# Flash al ganar/perder
flash_active = False
flash_start_time = 0
flash_color = (0, 0, 0)
flash_text = ""
FLASH_DURATION = 2000  # 2 segundos
# Tick-tock
last_tick_second = -1  # Para no repetir el tick en el mismo segundo
# Bot inteligente del streamer
BOT_ENABLED = True
BOT_WIN_RATE = 0.70  # 70% de probabilidad de ganar
BOT_COOLDOWN = 300000  # 5 minutos en ms
BOT_MAX_OPS_HOUR = 4
bot_last_trade_time = 0
bot_ops_this_hour = 0
bot_hour_start = 0
bot_bias_active = False  # True cuando el precio tiene sesgo a favor del bot
bot_bias_direction = 0  # 1 = arriba, -1 = abajo
# --- BOTS SIMULADOS (viewers falsos que operan para testear el ranking) ---
VIEWER_BOTS_ENABLED = False  # Desactivado: solo viewers reales de TikTok
VIEWER_BOT_INTERVAL = 8000  # (ya no se usa, operan en zona)
viewer_bot_last_time = 0

# --- SISTEMA DE LIQUIDEZ POR LIKES ---
# Cada 10 minutos se activa un evento donde el mercado "se queda sin
# liquidez" y hace falta que el chat de TikTok dé likes para reponerla.
# Rotan 3 tipos de evento en orden fijo: A (bloqueante) -> C (rondas por
# nivel) -> D (barra unica) -> A -> C -> D ...
LIQUIDITY_EVENT_TYPES = ["A", "C", "D"]
liquidity_event_index = 0  # Indice dentro de LIQUIDITY_EVENT_TYPES
liquidity_last_trigger = 0  # Momento (ms) del ultimo evento disparado (se fija al iniciar la partida)
liquidity_event_active = None  # None o dict con info del evento en curso
liquidity_particles = []  # Particulas cyan decorativas durante el evento
# Simulador de likes para pruebas sin estar en vivo (tecla L)
simulated_likes = 0
SIMULATED_LIKES_PER_PRESS = 10

# Config de cada tipo de evento - se cargan desde la base de datos (ajustables
# en vivo desde la pantalla de CONFIGURACION), con estos valores como default
# la primera vez que se corre el juego.
LIQUIDITY_EVENT_INTERVAL = int(get_config("liq_interval_min", "10")) * 60000  # minutos -> ms
LIQUIDITY_A_TARGET = int(get_config("liq_a_target", "100"))        # Likes necesarios para reanudar (evento bloqueante)
LIQUIDITY_A_TIMEOUT = 45000     # 45s: si no se llega a la meta, se reanuda igual (seguridad, no configurable)
LIQUIDITY_C_DURATION = 15000    # 15s de duracion (no configurable)
# Los 3 niveles del Evento C son totalmente independientes (cada uno con su
# propia meta de likes y su propio bono FXP, ajustables por separado)
LIQUIDITY_C_LEVELS = [
    (int(get_config("liq_c1_likes", "100")), int(get_config("liq_c1_bonus", "500"))),
    (int(get_config("liq_c2_likes", "200")), int(get_config("liq_c2_bonus", "1000"))),
    (int(get_config("liq_c3_likes", "400")), int(get_config("liq_c3_bonus", "2000"))),
]
LIQUIDITY_D_DURATION = 20000    # 20s de duracion (no configurable)
LIQUIDITY_D_TARGET = int(get_config("liq_d_target", "150"))        # Meta unica para llenar la barra
LIQUIDITY_D_BONUS = int(get_config("liq_d_bonus", "800"))          # Bono si se llena la barra
LIQUIDITY_MODE_DYNAMIC = get_config("liq_mode", "0") == "1"   # Modo dinámico de likes

# --- CONEXIÓN TIKTOK LIVE ---
TIKTOK_USERNAME = get_config("tiktok_username", "lean.fx1")
MAX_RR = int(get_config("max_rr", "3"))  # Límite máximo de Meta permitido (1:max_meta)

# Cargar colores personalizados
GLOBAL_COLOR_BG = parse_color(get_config("color_bg", "8,12,20"), (8, 12, 20))
GLOBAL_COLOR_BULL = parse_color(get_config("color_bull", "38,166,154"), (38, 166, 154))
GLOBAL_COLOR_BEAR = parse_color(get_config("color_bear", "239,83,80"), (239, 83, 80))

# --- MIGRACIÓN DE DATOS V2 (OPCIONAL) ---
V2_DB_PATH = r"C:\Users\leand\Desktop\LEAN FX GAME TODAS LAS VERSIONES\LEAN_FX_GAME_V2\lean_fx_game.db"
if os.path.exists(V2_DB_PATH):
    print(f"[MIGRACIÓN] Detectada base de datos V2 en: {V2_DB_PATH}")
    # Solo migramos si no se ha hecho antes (podemos guardar una marca en config)
    if get_config("v2_migrated", "0") == "0":
        success, msg = merge_v2_data(V2_DB_PATH)
        if success:
            set_config("v2_migrated", "1")
            print(f"[MIGRACIÓN] Éxito: {msg}")
        else:
            print(f"[MIGRACIÓN] Fallo: {msg}")
else:
    print("[MIGRACIÓN] No se encontró base de datos V2 para importar.")

tiktok_chat = TikTokChatReader(username=TIKTOK_USERNAME, max_rr=MAX_RR)
tiktok_chat.start()  # Inicia en hilo separado
# --- SISTEMA DE VOTOS DE VIEWERS ---
viewer_votes = []  # Lista de {"name": str, "vote": "BUY"/"SELL"} votos pendientes
viewer_votes_display = []  # Copia para mostrar incluso después de resolver
viewer_trade_active = None  # Trade activo de viewers: {"type", "entry", "sl", "tp", "entry_index"}

# --- FASE 2: ANALYTICS ---
current_session_id = None
last_analytics_update = 0
session_unique_participants = set()
session_total_messages = 0
session_total_likes = 0
last_tiktok_likes = 0
last_tiktok_comments_count = 0
viewer_trade_is_extremo = False  # Si la zona actual es EXTREMO (streamer también opera)
running = True
clock = pygame.time.Clock()
CANDLE_DURATION = 1000
last_candle_time = pygame.time.get_ticks()
TICK_DELAY = 60
last_tick_time = pygame.time.get_ticks()
bos_markers = []
initial_candle_count = len(candles)
range_phase = "buscando_high"
range_high = None
range_high_index = None
range_low = None
range_low_index = None
pullback_count = 0
prev_pullback_close = None
last_direction = None
prev_range_low = None
prev_range_low_index = None
prev_range_high = None
prev_range_high_index = None
confirmed_fractals = []
active_ob = None
prev_ob = None
active_decisional = None
active_fvg = None
current_visible_count = 100.0
target_visible_count = 100.0

def find_liquidity(candles_list, start_idx, end_idx, bos_type, price_floor, price_ceil):
    """
    Busca liquidez dentro del rango operativo.
    - BOS ALCISTA: busca equal highs entre price_floor (active_ob.high) y price_ceil (prev_range_high)
    - BOS BAJISTA: busca equal lows entre price_floor (prev_range_low) y price_ceil (active_ob.low)
    Fractal menor: high/low con 2 velas de retroceso despues.
    2+ fractales al mismo nivel (tolerancia 3 pts), separados 4+ velas = LIQ.
    Solo niveles NO mitigados. Maximo 3.
    """
    if price_floor >= price_ceil:
        return []
    tolerance = 3.0
    min_separation = 4
    fractals = []
    if bos_type == "ALCISTA":
        # Buscar fractal highs dentro de la zona
        for i in range(start_idx, end_idx - 2):
            c = candles_list[i]
            if (candles_list[i + 1]["high"] < c["high"] and candles_list[i + 2]["high"] < c["high"]):
                if price_floor <= c["high"] <= price_ceil:
                    fractals.append({"price": c["high"], "index": i})
        search_side = "high"
    else:
        # Buscar fractal lows dentro de la zona
        for i in range(start_idx, end_idx - 2):
            c = candles_list[i]
            if (candles_list[i + 1]["low"] > c["low"] and candles_list[i + 2]["low"] > c["low"]):
                if price_floor <= c["low"] <= price_ceil:
                    fractals.append({"price": c["low"], "index": i})
        search_side = "low"
    # Buscar pares al mismo nivel
    levels = []
    for i in range(len(fractals)):
        for j in range(i + 1, len(fractals)):
            if abs(fractals[j]["index"] - fractals[i]["index"]) >= min_separation:
                if abs(fractals[i]["price"] - fractals[j]["price"]) <= tolerance:
                    avg_price = (fractals[i]["price"] + fractals[j]["price"]) / 2
                    if avg_price < price_floor or avg_price > price_ceil:
                        continue
                    last_touch_idx = fractals[j]["index"]
                    # Verificar que NO fue mitigado despues del ultimo toque
                    mitigated = False
                    for k in range(last_touch_idx + 1, end_idx):
                        if search_side == "high" and candles_list[k]["close"] > avg_price:
                            mitigated = True
                            break
                        elif search_side == "low" and candles_list[k]["close"] < avg_price:
                            mitigated = True
                            break
                    if mitigated:
                        continue
                    found = False
                    for lv in levels:
                        if abs(lv["price"] - avg_price) <= tolerance:
                            lv["touches"] += 1
                            if last_touch_idx > lv["last_index"]:
                                lv["last_index"] = last_touch_idx
                            found = True
                            break
                    if not found:
                        levels.append({"side": search_side, "price": avg_price,
                                       "first_index": fractals[i]["index"],
                                       "last_index": last_touch_idx, "touches": 2})
    levels.sort(key=lambda x: x["touches"], reverse=True)
    return levels[:3]

def mitigate_liquidity(candles_list, liq_levels, candle_index):
    """
    Elimina niveles de liquidez mitigados: cuando una vela cierra pasando el nivel.
    """
    if not liq_levels or candle_index >= len(candles_list):
        return liq_levels
    c = candles_list[candle_index]
    remaining = []
    for lv in liq_levels:
        if lv["side"] == "high" and c["close"] > lv["price"]:
            continue  # mitigado
        if lv["side"] == "low" and c["close"] < lv["price"]:
            continue  # mitigado
        remaining.append(lv)
    return remaining
def find_decisional(candles_list, bos_index, bos_type, extreme_index):
    """
    El decisional es la vela que hizo el punto mas alto/bajo del ultimo retroceso
    antes de romper el BOS.
    Para BOS BAJISTA: busca el ultimo retroceso alcista (2 velas verdes, 2da cierra mas alto).
    El decisional es la vela con el high mas alto de ese retroceso (la 2da vela).
    Para BOS ALCISTA: busca el ultimo retroceso bajista (2 velas rojas, 2da cierra mas bajo).
    El decisional es la vela con el low mas bajo de ese retroceso (la 2da vela).
    """
    if extreme_index is None or bos_index is None:
        return None
    start = extreme_index + 1
    end = bos_index
    if end - start < 2:
        return None
    if bos_type == "ALCISTA":
        # Retroceso bajista: 2 velas rojas donde la 2da cierra mas bajo
        # El decisional es la 2da vela (la que hizo el low mas bajo)
        for i in range(end - 1, start, -1):
            c = candles_list[i]
            prev_c = candles_list[i - 1]
            if (c["close"] < c["open"] and prev_c["close"] < prev_c["open"]
                    and c["close"] < prev_c["close"]):
                return {"high": c["high"] + ZONE_PADDING, "low": c["low"] - ZONE_PADDING, "index": i}
    elif bos_type == "BAJISTA":
        # Retroceso alcista: 2 velas verdes donde la 2da cierra mas alto
        # El decisional es la 2da vela (la que hizo el high mas alto)
        for i in range(end - 1, start, -1):
            c = candles_list[i]
            prev_c = candles_list[i - 1]
            if (c["close"] > c["open"] and prev_c["close"] > prev_c["open"]
                    and c["close"] > prev_c["close"]):
                return {"high": c["high"] + ZONE_PADDING, "low": c["low"] - ZONE_PADDING, "index": i}
    return None

def zonas_se_solapan(zona_a, zona_b):
    """Devuelve True si los rangos de precio [low, high] de dos zonas se solapan/tocan."""
    if zona_a is None or zona_b is None:
        return False
    return zona_a["low"] <= zona_b["high"] and zona_b["low"] <= zona_a["high"]

def find_fvg(candles_list, start_idx, end_idx, bos_type):
    if end_idx - start_idx < 3:
        return None
    for i in range(start_idx, end_idx - 2):
        v1 = candles_list[i]
        v3 = candles_list[i + 2]
        if bos_type == "ALCISTA":
            if v3["low"] > v1["high"]:
                return {"high": v3["low"] + ZONE_PADDING, "low": v1["high"] - ZONE_PADDING, "index": i + 1}
        else:
            if v1["low"] > v3["high"]:
                return {"high": v1["low"] + ZONE_PADDING, "low": v3["high"] - ZONE_PADDING, "index": i + 1}
    return None

def process_new_candle(candles_list, new_index):
    global range_phase, range_high, range_high_index, range_low, range_low_index
    global pullback_count, prev_pullback_close, last_direction
    global prev_range_low, prev_range_low_index, prev_range_high, prev_range_high_index
    global active_ob, prev_ob, active_decisional, active_fvg
    if new_index < 1:
        return
    c = candles_list[new_index]
    is_bull = c["close"] > c["open"]
    is_bear = c["close"] < c["open"]
    # Mitigar FVG si el precio entra en la zona
    if active_fvg is not None:
        if "type" in active_fvg:
            if active_fvg["type"] == "ALCISTA" and c["close"] < active_fvg["high"]:
                active_fvg = None
            elif active_fvg["type"] == "BAJISTA" and c["close"] > active_fvg["low"]:
                active_fvg = None
        else:
            # Si no tiene type, verificar por posicion
            if c["close"] < active_fvg["high"] and c["close"] > active_fvg["low"]:
                active_fvg = None
    if prev_range_low is not None and is_bear and c["close"] < prev_range_low:
        bos_markers.append({"type": "BAJISTA", "price": prev_range_low, "level_index": prev_range_low_index, "break_index": new_index})
        play_sound(sound_bos)
        # Incrementar bos_count de zonas mitigadas
        for k in zones_mitigated_info:
            zones_mitigated_info[k]["bos_count"] = zones_mitigated_info[k].get("bos_count", 0) + 1
        if range_high is not None:
            confirmed_fractals.append({"price": range_high, "index": range_high_index, "type": "high"})
            play_sound(sound_fractal)
        if range_high_index is not None:
            ob_candle = candles_list[range_high_index]
            prev_ob = active_ob
            if prev_ob is not None:
                prev_ob["end_index"] = new_index
            active_ob = {"type": "BAJISTA", "high": ob_candle["high"] + ZONE_PADDING, "low": ob_candle["low"] - ZONE_PADDING, "index": range_high_index}
        dec = find_decisional(candles_list, new_index, "BAJISTA", range_high_index)
        if dec is not None:
            dec["type"] = "BAJISTA"
            if active_ob and (dec["index"] == active_ob["index"] or zonas_se_solapan(dec, active_ob)):
                dec = None
        active_decisional = dec
        active_fvg = find_fvg(candles_list, range_high_index, new_index, "BAJISTA")
        if active_fvg is not None:
            active_fvg["type"] = "BAJISTA"
        # Calcular liquidez en todas las velas visibles desde el BOS anterior
        lq_impulse_start = bos_markers[-2]["break_index"] if len(bos_markers) >= 2 else 0
        liquidity_levels = find_liquidity(candles_list, lq_impulse_start, new_index, "BAJISTA", prev_range_low if prev_range_low else -99999, active_ob["low"] if active_ob else 99999)
        prev_range_high = range_high
        prev_range_high_index = range_high_index
        prev_range_low = None
        prev_range_low_index = None
        range_low = c["low"]
        range_low_index = new_index
        range_high = None
        range_high_index = None
        range_phase = "buscando_low"
        pullback_count = 0
        prev_pullback_close = None
        last_direction = None
        return
    if prev_range_high is not None and is_bull and c["close"] > prev_range_high:
        bos_markers.append({"type": "ALCISTA", "price": prev_range_high, "level_index": prev_range_high_index, "break_index": new_index})
        play_sound(sound_bos)
        for k in zones_mitigated_info:
            zones_mitigated_info[k]["bos_count"] = zones_mitigated_info[k].get("bos_count", 0) + 1
        if range_low is not None:
            confirmed_fractals.append({"price": range_low, "index": range_low_index, "type": "low"})
            play_sound(sound_fractal)
        if range_low_index is not None:
            ob_candle = candles_list[range_low_index]
            prev_ob = active_ob
            if prev_ob is not None:
                prev_ob["end_index"] = new_index
            active_ob = {"type": "ALCISTA", "high": ob_candle["high"] + ZONE_PADDING, "low": ob_candle["low"] - ZONE_PADDING, "index": range_low_index}
        dec = find_decisional(candles_list, new_index, "ALCISTA", range_low_index)
        if dec is not None:
            dec["type"] = "ALCISTA"
            if active_ob and (dec["index"] == active_ob["index"] or zonas_se_solapan(dec, active_ob)):
                dec = None
        active_decisional = dec
        active_fvg = find_fvg(candles_list, range_low_index, new_index, "ALCISTA")
        if active_fvg is not None:
            active_fvg["type"] = "ALCISTA"
        # Calcular liquidez en todas las velas visibles desde el BOS anterior
        lq_impulse_start = bos_markers[-2]["break_index"] if len(bos_markers) >= 2 else 0
        liquidity_levels = find_liquidity(candles_list, lq_impulse_start, new_index, "ALCISTA", active_ob["high"] if active_ob else -99999, prev_range_high if prev_range_high else 99999)
        prev_range_low = range_low
        prev_range_low_index = range_low_index
        prev_range_high = None
        prev_range_high_index = None
        range_high = c["high"]
        range_high_index = new_index
        range_low = None
        range_low_index = None
        range_phase = "buscando_high"
        pullback_count = 0
        prev_pullback_close = None
        last_direction = None
        return
    if range_phase == "buscando_high":
        if range_high is None or c["high"] >= range_high:
            range_high = c["high"]
            range_high_index = new_index
            pullback_count = 0
            prev_pullback_close = None
        if range_high is not None and is_bear and new_index > range_high_index:
            if pullback_count == 0:
                pullback_count = 1
                prev_pullback_close = c["close"]
            elif prev_pullback_close is not None and c["close"] < prev_pullback_close:
                pullback_count = 2
                range_low = c["low"]
                range_low_index = new_index
                range_phase = "rango_definido"
                last_direction = "up"
                pullback_count = 0
                prev_pullback_close = None
                confirmed_fractals.append({"price": range_high, "index": range_high_index, "type": "high"})
                play_sound(sound_fractal)
            else:
                pullback_count = 1
                prev_pullback_close = c["close"]
        elif is_bull and range_high is not None and new_index > range_high_index:
            pullback_count = 0
            prev_pullback_close = None
    elif range_phase == "buscando_low":
        if range_low is None or c["low"] <= range_low:
            range_low = c["low"]
            range_low_index = new_index
            pullback_count = 0
            prev_pullback_close = None
        if range_low is not None and is_bull and new_index > range_low_index:
            if pullback_count == 0:
                pullback_count = 1
                prev_pullback_close = c["close"]
            elif prev_pullback_close is not None and c["close"] > prev_pullback_close:
                pullback_count = 2
                range_high = c["high"]
                range_high_index = new_index
                range_phase = "rango_definido"
                last_direction = "down"
                pullback_count = 0
                prev_pullback_close = None
                confirmed_fractals.append({"price": range_low, "index": range_low_index, "type": "low"})
                play_sound(sound_fractal)
            else:
                pullback_count = 1
                prev_pullback_close = c["close"]
        elif is_bear and range_low is not None and new_index > range_low_index:
            pullback_count = 0
            prev_pullback_close = None
    elif range_phase == "rango_definido":
        if last_direction == "up":
            if c["low"] < range_low:
                range_low = c["low"]
                range_low_index = new_index
        elif last_direction == "down":
            if c["high"] > range_high:
                range_high = c["high"]
                range_high_index = new_index
        if is_bull and c["close"] > range_high:
            bos_markers.append({"type": "ALCISTA", "price": range_high, "level_index": range_high_index, "break_index": new_index})
            play_sound(sound_bos)
            confirmed_fractals.append({"price": range_low, "index": range_low_index, "type": "low"})
            play_sound(sound_fractal)
            if range_low_index is not None:
                ob_candle = candles_list[range_low_index]
                prev_ob = active_ob
                if prev_ob is not None:
                    prev_ob["end_index"] = new_index
                active_ob = {"type": "ALCISTA", "high": ob_candle["high"] + ZONE_PADDING, "low": ob_candle["low"] - ZONE_PADDING, "index": range_low_index}
            dec = find_decisional(candles_list, new_index, "ALCISTA", range_low_index)
            if dec is not None:
                dec["type"] = "ALCISTA"
                if active_ob and (dec["index"] == active_ob["index"] or zonas_se_solapan(dec, active_ob)):
                    dec = None
            active_decisional = dec
            active_fvg = find_fvg(candles_list, range_low_index, new_index, "ALCISTA")
            if active_fvg is not None:
                active_fvg["type"] = "ALCISTA"
            # Calcular liquidez en todas las velas visibles desde el BOS anterior
            lq_impulse_start = bos_markers[-2]["break_index"] if len(bos_markers) >= 2 else 0
            liquidity_levels = find_liquidity(candles_list, lq_impulse_start, new_index, "ALCISTA", active_ob["high"] if active_ob else -99999, prev_range_high if prev_range_high else 99999)
            prev_range_low = range_low
            prev_range_low_index = range_low_index
            range_high = c["high"]
            range_high_index = new_index
            range_low = None
            range_low_index = None
            range_phase = "buscando_high"
            pullback_count = 0
            prev_pullback_close = None
            last_direction = None
        elif is_bear and c["close"] < range_low:
            bos_markers.append({"type": "BAJISTA", "price": range_low, "level_index": range_low_index, "break_index": new_index})
            play_sound(sound_bos)
            confirmed_fractals.append({"price": range_high, "index": range_high_index, "type": "high"})
            play_sound(sound_fractal)
            if range_high_index is not None:
                ob_candle = candles_list[range_high_index]
                prev_ob = active_ob
                if prev_ob is not None:
                    prev_ob["end_index"] = new_index
                active_ob = {"type": "BAJISTA", "high": ob_candle["high"] + ZONE_PADDING, "low": ob_candle["low"] - ZONE_PADDING, "index": range_high_index}
            dec = find_decisional(candles_list, new_index, "BAJISTA", range_high_index)
            if dec is not None:
                dec["type"] = "BAJISTA"
                if active_ob and (dec["index"] == active_ob["index"] or zonas_se_solapan(dec, active_ob)):
                    dec = None
            active_decisional = dec
            active_fvg = find_fvg(candles_list, range_high_index, new_index, "BAJISTA")
            if active_fvg is not None:
                active_fvg["type"] = "BAJISTA"
            # Calcular liquidez en todas las velas visibles desde el BOS anterior
            lq_impulse_start = bos_markers[-2]["break_index"] if len(bos_markers) >= 2 else 0
            liquidity_levels = find_liquidity(candles_list, lq_impulse_start, new_index, "BAJISTA", prev_range_low if prev_range_low else -99999, active_ob["low"] if active_ob else 99999)
            prev_range_high = range_high
            prev_range_high_index = range_high_index
            range_low = c["low"]
            range_low_index = new_index
            range_high = None
            range_high_index = None
            range_phase = "buscando_low"
            pullback_count = 0
            prev_pullback_close = None
            last_direction = None
last_checked_index = initial_candle_count
for i in range(1, len(candles)):
    process_new_candle(candles, i)

while len(bos_markers) < 2:
    bos_markers.clear()
    confirmed_fractals.clear()
    active_ob = None
    prev_ob = None
    active_decisional = None
    active_fvg = None
    range_phase = "buscando_high"
    range_high = None
    range_high_index = None
    range_low = None
    range_low_index = None
    prev_range_low = None
    prev_range_low_index = None
    prev_range_high = None
    prev_range_high_index = None
    pullback_count = 0
    prev_pullback_close = None
    last_direction = None
    candles.clear()
    price = 1000
    # --- SISTEMA DE IMPULSO Y RETROCESO (Dinámico: 4-6 Impulsos, 2-3 Retrocesos) ---
    trend_dir = random.choice([-1, 1])
    market_state = "impulse"
    wave_count = 1  # Mantenido por compatibilidad
    trend_length = random.randint(4, 6)
    trend_count = 0
    trend_strength = random.uniform(10, 18)
    current_dir = trend_dir
    impulse_in_trend = 0

    for _ in range(180):
        trend_count += 1
        
        if trend_count >= trend_length:
            trend_count = 0
            if market_state == "impulse":
                market_state = "retracement"
                trend_length = random.randint(2, 3)
                trend_strength = random.uniform(5, 9)
                current_dir = -trend_dir
                impulse_in_trend += 1
            else:
                market_state = "impulse"
                trend_length = random.randint(4, 6)
                trend_strength = random.uniform(10, 18)
                
                # Cambio de tendencia tras 1-2 impulsos (Ciclos Ágiles)
                if impulse_in_trend >= random.randint(1, 2):
                    trend_dir *= -1
                    impulse_in_trend = 0
                current_dir = trend_dir

        # Sesgo del tick basado en el estado actual
        bias_prob = 0.82 if market_state == "impulse" else 0.65
        
        if random.random() < bias_prob:
            body = random.uniform(trend_strength * 0.4, trend_strength * 1.1) * current_dir
        else:
            body = random.uniform(0.1, trend_strength * 0.5) * -current_dir
            
        open_p = price
        close_p = open_p + body
        
        # --- MECHAS REALISTAS ---
        wick_base = trend_strength * 0.2
        wick_up = random.uniform(0.1, wick_base) if body > 0 else random.uniform(0.2, wick_base * 1.5)
        wick_down = random.uniform(0.2, wick_base * 1.5) if body > 0 else random.uniform(0.1, wick_base)
            
        high_p = max(open_p, close_p) + wick_up
        low_p = min(open_p, close_p) - wick_down
        
        candles.append({"open": open_p, "close": close_p, "high": high_p, "low": low_p})
        price = close_p
    for i in range(1, len(candles)):
        process_new_candle(candles, i)

current_candle = {"open": candles[-1]["close"], "close": candles[-1]["close"], "high": candles[-1]["close"], "low": candles[-1]["close"]}

# === MENÚ DE INICIO ===
font_menu_title = pygame.font.SysFont("Arial", 60, bold=True)
font_menu_btn = pygame.font.SysFont("Arial", 28, bold=True)
in_menu = True
menu_selection = None

# Cargar imagen de fondo del menú
menu_bg_path = os.path.join(BASE_DIR, "assets", "menu_bg.png")
if not os.path.exists(menu_bg_path):
    menu_bg_path = os.path.join(BASE_DIR, "assets", "menu_bg.jpg")
menu_bg = None
if os.path.exists(menu_bg_path):
    menu_bg = pygame.image.load(menu_bg_path).convert()
    menu_bg = pygame.transform.smoothscale(menu_bg, (SCREEN_W, SCREEN_H))
else:
    print("[AVISO] menu_bg no encontrado")

# Efecto click
menu_click_btn = None  # Nombre del botón clickeado
menu_click_time = 0
MENU_CLICK_DURATION = 150  # ms


# === PANTALLA DE CARGA (LOADING SCREEN) ===
def show_loading_screen():
    """
    Pantalla de carga animada con estética de trading futurista.
    Se muestra justo al abrir el juego, antes del menú principal.

    Simula: conexión con el servidor de la bolsa, carga de algoritmos y
    sincronización de velas. Barra de progreso con gradiente + glow, textos
    que cambian rápido, velas japonesas de fondo (marca de agua) y mini-velas
    que "cargan" según el avance.

    Dura ~6.5 segundos. Devuelve True si completó normalmente, o False si
    el usuario cerró (QUIT/ESC) durante la carga.
    """
    loading_start = pygame.time.get_ticks()
    LOADING_DURATION = 6500  # 6.5 segundos (carga más lenta y fluida)

    # Textos de simulación que cambian rápido según el progreso
    loading_messages = {
        0: 'Iniciando LEAN FX GAME...',
        10: 'Conectando con API de Binance...',
        20: 'Estableciendo canal seguro de datos...',
        30: 'Sincronizando Libro de Órdenes (Order Book)...',
        40: 'Cargando algoritmos de trading...',
        50: 'Calculando Medias Móviles (EMA 20/200)...',
        60: 'Calibrando indicadores de liquidez...',
        70: 'Inicializando motores de mercado...',
        75: 'Inyectando Liquidez al Simulador...',
        80: 'Optimizando zona de operaciones...',
        90: 'Verificando Conexión con TikTok Live...',
        95: 'Preparando interfaz de usuario...',
        100: 'Listo para operar.'
    }
    current_log_message = ""
    last_log_update_time = 0
    log_display_duration = 500 # Duración mínima de cada log en pantalla (legible)
    log_fade_alpha = 255
    log_fade_speed = 3 # Velocidad de desvanecimiento (más suave)

    # --- Feed de precios en vivo (simulado) ---
    btc_price = random.uniform(61000, 64000)
    eth_price = random.uniform(2900, 3100)
    btc_prev = btc_price
    eth_prev = eth_price
    last_price_update = 0
    PRICE_UPDATE_INTERVAL = 120  # ms entre actualizaciones (cambia rápido)
    font_load_price = pygame.font.SysFont("Consolas", int(SCREEN_H * 0.018), bold=True)

    # --- Reloj simulado para logs (formato consola [HH:MM:SS]) ---
    sim_clock_seconds = 12 * 3600  # Arranca a las 12:00:00

    # Partículas decorativas de fondo (cyan futurista)
    load_particles = [
        {"x": random.uniform(0, SCREEN_W), "y": random.uniform(0, SCREEN_H),
         "speed": random.uniform(0.3, 1.0), "size": random.randint(1, 3),
         "alpha": random.randint(60, 160)}
        for _ in range(25)
    ]

    # Velas japonesas de fondo (marca de agua, opacidad muy baja 10-15%)
    load_candles = []
    for _ in range(18):
        load_candles.append({
            "x": random.uniform(0, SCREEN_W),
            "y": random.uniform(0, SCREEN_H),
            "w": random.randint(10, 22),
            "h": random.randint(40, 160),
            "bull": random.random() < 0.5,  # True = verde, False = roja
            "speed": random.uniform(0.1, 0.4),
        })

    # Fuentes
    font_load_msg = pygame.font.SysFont("Arial", int(SCREEN_H * 0.022), bold=True)
    font_load_title = pygame.font.SysFont("Arial", int(SCREEN_H * 0.08), bold=True)
    font_load_pct = pygame.font.SysFont("Arial", int(SCREEN_H * 0.03), bold=True)
    font_load_small = pygame.font.SysFont("Consolas", int(SCREEN_H * 0.016), bold=True)

    while True:
        current_time = pygame.time.get_ticks()
        elapsed = current_time - loading_start
        progress = min(1.0, elapsed / LOADING_DURATION)

        # Fondo
        screen.fill((8, 12, 20))

        # --- Velas japonesas de fondo (marca de agua, opacidad 10-15%) ---
        candle_bg = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        for c in load_candles:
            c["x"] -= c["speed"]
            if c["x"] < -30:
                c["x"] = SCREEN_W + 30
                c["y"] = random.uniform(0, SCREEN_H)
                c["h"] = random.randint(40, 160)
                c["bull"] = random.random() < 0.5
            # Color base con alpha bajo (marca de agua)
            if c["bull"]:
                base = (38, 166, 154)
            else:
                base = (239, 83, 80)
            body_alpha = 35  # ~14% de opacidad
            wick_alpha = 25  # ~10% de opacidad
            cx = int(c["x"])
            cy = int(c["y"])
            cw = c["w"]
            ch = c["h"]
            # Cuerpo de la vela
            pygame.draw.rect(candle_bg, (base[0], base[1], base[2], body_alpha), (cx, cy, cw, ch))
            # Mechas (superior e inferior)
            pygame.draw.line(candle_bg, (base[0], base[1], base[2], wick_alpha),
                             (cx + cw // 2, cy - 20), (cx + cw // 2, cy), 2)
            pygame.draw.line(candle_bg, (base[0], base[1], base[2], wick_alpha),
                             (cx + cw // 2, cy + ch), (cx + cw // 2, cy + ch + 20), 2)
        screen.blit(candle_bg, (0, 0))

        # --- Partículas de fondo ---
        for p in load_particles:
            p["y"] -= p["speed"]
            if p["y"] < -5:
                p["y"] = SCREEN_H + 5
                p["x"] = random.uniform(0, SCREEN_W)
            ps = pygame.Surface((p["size"] * 2, p["size"] * 2), pygame.SRCALPHA)
            pygame.draw.circle(ps, (0, 200, 255, p["alpha"]), (p["size"], p["size"]), p["size"])
            screen.blit(ps, (int(p["x"]), int(p["y"])))

        # --- Feed de precios en vivo (esquina superior derecha) ---
        if not audio_manager.juego_pausado and current_time - last_price_update >= PRICE_UPDATE_INTERVAL:
            btc_prev = btc_price
            eth_prev = eth_price
            btc_price += random.uniform(-150, 150)
            eth_price += random.uniform(-10, 10)
            last_price_update = current_time

        # BTC (verde neón)
        btc_color = (0, 255, 120) if btc_price >= btc_prev else (0, 200, 90)
        btc_txt = font_load_price.render(f"BTC  ${btc_price:,.2f}", True, btc_color)
        btc_glow = font_load_price.render(f"BTC  ${btc_price:,.2f}", True, (0, 120, 60))
        btc_rect = btc_txt.get_rect(topright=(SCREEN_W - 30, int(SCREEN_H * 0.06)))
        for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
            screen.blit(btc_glow, btc_rect.move(dx, dy))
        screen.blit(btc_txt, btc_rect)

        # ETH (rojo neón)
        eth_color = (255, 70, 70) if eth_price >= eth_prev else (255, 40, 40)
        eth_txt = font_load_price.render(f"ETH  ${eth_price:,.2f}", True, eth_color)
        eth_glow = font_load_price.render(f"ETH  ${eth_price:,.2f}", True, (120, 20, 20))
        eth_rect = eth_txt.get_rect(topright=(SCREEN_W - 30, btc_rect.bottom + 6))
        for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
            screen.blit(eth_glow, eth_rect.move(dx, dy))
        screen.blit(eth_txt, eth_rect)

        # --- Título con sombra ---
        title_shadow = font_load_title.render("LEAN FX", True, (0, 80, 100))
        screen.blit(title_shadow, title_shadow.get_rect(center=(SCREEN_W // 2 + 2, int(SCREEN_H * 0.18) + 2)))
        title_txt = font_load_title.render("LEAN FX", True, (0, 220, 255))
        screen.blit(title_txt, title_txt.get_rect(center=(SCREEN_W // 2, int(SCREEN_H * 0.18))))
        sub_txt = font_load_small.render("TERMINAL DE TRADING EN TIEMPO REAL", True, (120, 160, 180))
        screen.blit(sub_txt, sub_txt.get_rect(center=(SCREEN_W // 2, int(SCREEN_H * 0.24))))

        # --- Mensaje de simulación (Logs dinámicos) ---
        current_percentage = int(progress * 100)
        for pct_threshold in sorted(loading_messages.keys()):
            if current_percentage >= pct_threshold:
                if loading_messages[pct_threshold] != current_log_message:
                    current_log_message = loading_messages[pct_threshold]
                    last_log_update_time = current_time
                    log_fade_alpha = 255 # Reset fade
            else:
                break
        
        if current_time - last_log_update_time < log_display_duration:
            log_fade_alpha = 255
        else:
            log_fade_alpha = max(0, log_fade_alpha - log_fade_speed)

        if current_log_message:
            pulse = int(180 + 75 * math.sin(current_time / 300.0))
            log_color = (0, min(255, pulse), 255, log_fade_alpha)
            # Timestamp simulado en formato consola: [12:00:03]
            sim_total = sim_clock_seconds + int(elapsed / 1000)
            sim_h = (sim_total // 3600) % 24
            sim_m = (sim_total // 60) % 60
            sim_s = sim_total % 60
            sim_timestamp = f"[{sim_h:02d}:{sim_m:02d}:{sim_s:02d}]"
            # Timestamp en gris/cyan tenue + mensaje en cyan brillante
            ts_surf = font_load_msg.render(sim_timestamp, True, (110, 170, 200, log_fade_alpha))
            msg_surf = font_load_msg.render(current_log_message, True, log_color)
            total_w = ts_surf.get_width() + 8 + msg_surf.get_width()
            start_x = SCREEN_W // 2 - total_w // 2
            msg_y = int(SCREEN_H * 0.55)
            screen.blit(ts_surf, (start_x, msg_y))
            screen.blit(msg_surf, (start_x + ts_surf.get_width() + 8, msg_y))

        # --- Barra de progreso futurista ---
        bar_w = int(SCREEN_W * 0.55)
        bar_h = int(SCREEN_H * 0.035)
        bar_x = SCREEN_W // 2 - bar_w // 2
        bar_y = int(SCREEN_H * 0.62)
        # Fondo de la barra
        pygame.draw.rect(screen, (25, 30, 42), (bar_x, bar_y, bar_w, bar_h), border_radius=8)
        # Relleno con gradiente cyan
        fill_w = int(bar_w * progress)
        if fill_w > 0:
            bar_surf = pygame.Surface((fill_w, bar_h), pygame.SRCALPHA)
            for bx in range(fill_w):
                t = bx / max(fill_w - 1, 1)
                g = int(180 + (220 - 180) * t)
                b = int(220 + (255 - 220) * t)
                pygame.draw.line(bar_surf, (0, g, b, 230), (bx, 0), (bx, bar_h))
            screen.blit(bar_surf, (bar_x, bar_y))
            # Glow
            glow_surf = pygame.Surface((fill_w + 6, bar_h + 6), pygame.SRCALPHA)
            glow_surf.fill((0, 200, 255, 25))
            screen.blit(glow_surf, (bar_x - 3, bar_y - 3))
        # Borde pulsante
        border_pulse = int(180 + 60 * math.sin(current_time / 200.0))
        pygame.draw.rect(screen, (0, min(255, border_pulse), 255), (bar_x, bar_y, bar_w, bar_h), 2, border_radius=8)
        # Marcas de progreso
        for i in range(1, 9):
            mx = bar_x + int(bar_w * (i / 9))
            pygame.draw.line(screen, (40, 50, 65), (mx, bar_y + 2), (mx, bar_y + bar_h - 2), 1)

        # --- Porcentaje ---
        pct_txt = font_load_pct.render(f"{int(progress * 100)}%", True, (255, 255, 255))
        screen.blit(pct_txt, pct_txt.get_rect(center=(SCREEN_W // 2, bar_y + bar_h + int(SCREEN_H * 0.04))))

        # --- Mini-velas que "cargan" según el avance ---
        mini_candles_x = int(SCREEN_W * 0.12)
        mini_candles_y = int(SCREEN_H * 0.62)
        for ci in range(6):
            cx = mini_candles_x + ci * 25
            ch = int(bar_h * (0.3 + 0.7 * min(1.0, progress * 1.5 - ci * 0.1)))
            if ch <= 0:
                continue
            is_bull = (ci % 2 == 0)
            color = GLOBAL_COLOR_BULL if is_bull else GLOBAL_COLOR_BEAR
            cy = mini_candles_y + bar_h - ch
            pygame.draw.rect(screen, color, (cx, cy, 10, ch))
            pygame.draw.line(screen, color, (cx + 5, cy - 6), (cx + 5, cy + ch + 6), 1)

        # --- Texto status abajo ---
        status_txt = font_load_small.render("v3.0 - MODO SIMULADOR EN VIVO", True, (60, 90, 110))
        screen.blit(status_txt, status_txt.get_rect(center=(SCREEN_W // 2, int(SCREEN_H * 0.92))))

        # --- Procesar eventos (permitir salir durante la carga) ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return False

        pygame.display.flip()
        clock.tick(60)

        if elapsed >= LOADING_DURATION:
            return True


# === LOOP PRINCIPAL ===
app_running = show_loading_screen()
while app_running:
    # --- AUTO-INICIO DE SESIÓN GLOBAL ---
    # Si TikTok se conecta, iniciamos sesión inmediatamente (incluso en el menú)
    if current_session_id is None and tiktok_chat.is_connected():
        try:
            current_session_id = start_session()
            tiktok_chat.reset_session_totals()
            print(f"[ANALYTICS] Sesión detectada/iniciada globalmente ID: {current_session_id}")
        except Exception as e:
            print(f"[ANALYTICS] Error auto-iniciando sesión global: {e}")

    # Reset variables para volver al menú
    in_menu = True
    menu_click_btn = None
    menu_selection = None
    game_started = False
    guide_animation_start = 0

    # Animaciones del menú
    import math
    # Partículas flotantes
    menu_particles = []
    for _ in range(30):
        menu_particles.append({
            "x": random.randint(0, SCREEN_W),
            "y": random.randint(0, SCREEN_H),
            "speed": random.uniform(0.3, 1.2),
            "size": random.randint(1, 3),
            "color": random.choice([(0, 220, 255), (255, 200, 0), (0, 180, 200), (200, 170, 0)]),
            "alpha": random.randint(80, 200),
        })
    # Velas japonesas de fondo
    menu_candles = []
    for i in range(15):
        h = random.randint(30, 120)
        menu_candles.append({
            "x": random.randint(0, SCREEN_W),
            "y": random.randint(int(SCREEN_H * 0.2), int(SCREEN_H * 0.8)),
            "w": random.randint(8, 14),
            "h": h,
            "color": random.choice([GLOBAL_COLOR_BULL, GLOBAL_COLOR_BEAR]),
            "speed": random.uniform(0.2, 0.6),
        })
    # Línea de precio animada (tipo chart)
    menu_price_points = []
    price_val = SCREEN_H * 0.5
    for i in range(int(SCREEN_W * 0.8)):
        price_val += random.uniform(-2, 2)
        price_val = max(SCREEN_H * 0.3, min(SCREEN_H * 0.7, price_val))
        menu_price_points.append(price_val)
    menu_price_offset = 0
    # Definir áreas de botones (para glow y clicks)
    btn_w = int(SCREEN_W * 0.28)
    btn_h = int(SCREEN_H * 0.08)
    btn_iniciar = pygame.Rect(int(SCREEN_W * (681/1366)) - btn_w // 2, int(SCREEN_H * (341/768)) - btn_h // 2, btn_w, btn_h)
    btn_ranking = pygame.Rect(int(SCREEN_W * (686/1366)) - btn_w // 2, int(SCREEN_H * (476/768)) - btn_h // 2, btn_w, btn_h)
    btn_config = pygame.Rect(int(SCREEN_W * (681/1366)) - btn_w // 2, int(SCREEN_H * (607/768)) - btn_h // 2, btn_w, btn_h)

    # --- MENÚ ---
    # Reproducir música ambient en loop
    if sound_ambient is not None:
        sound_ambient.play(loops=-1)
    while in_menu and app_running:
        clock.tick(60)
        current_time = pygame.time.get_ticks()
        # Fondo
        if menu_bg is not None:
            screen.blit(menu_bg, (0, 0))
        else:
            screen.fill((15, 15, 25))
        # --- ANIMACIONES DEL MENÚ ---
        # Velas japonesas de fondo (opacidad baja)
        candle_surface = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        for c in menu_candles:
            c["x"] -= c["speed"]
            if c["x"] < -20:
                c["x"] = SCREEN_W + 20
                c["y"] = random.randint(int(SCREEN_H * 0.2), int(SCREEN_H * 0.8))
            col = (c["color"][0], c["color"][1], c["color"][2], 35)
            pygame.draw.rect(candle_surface, col, (int(c["x"]), int(c["y"]), c["w"], c["h"]))
            # Mecha
            wick_col = (c["color"][0], c["color"][1], c["color"][2], 25)
            pygame.draw.line(candle_surface, wick_col, (int(c["x"]) + c["w"] // 2, int(c["y"]) - 15), (int(c["x"]) + c["w"] // 2, int(c["y"])), 1)
            pygame.draw.line(candle_surface, wick_col, (int(c["x"]) + c["w"] // 2, int(c["y"]) + c["h"]), (int(c["x"]) + c["w"] // 2, int(c["y"]) + c["h"] + 15), 1)
        screen.blit(candle_surface, (0, 0))
        # Partículas flotantes
        for p in menu_particles:
            p["y"] -= p["speed"]
            if p["y"] < -5:
                p["y"] = SCREEN_H + 5
                p["x"] = random.randint(0, SCREEN_W)
            ps = pygame.Surface((p["size"] * 2, p["size"] * 2), pygame.SRCALPHA)
            pygame.draw.circle(ps, (p["color"][0], p["color"][1], p["color"][2], p["alpha"]), (p["size"], p["size"]), p["size"])
            screen.blit(ps, (int(p["x"]), int(p["y"])))
        # Línea de precio animada (se mueve de derecha a izquierda)
        menu_price_offset += 1
        if menu_price_offset >= len(menu_price_points):
            menu_price_offset = 0
            # Generar nuevos puntos
            price_val = SCREEN_H * 0.5
            for i in range(len(menu_price_points)):
                price_val += random.uniform(-2, 2)
                price_val = max(SCREEN_H * 0.3, min(SCREEN_H * 0.7, price_val))
                menu_price_points[i] = price_val
        price_line_surface = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        visible_points = menu_price_points[menu_price_offset:] + menu_price_points[:menu_price_offset]
        step = max(1, len(visible_points) // SCREEN_W)
        for i in range(1, SCREEN_W - 1):
            idx1 = min((i - 1) * step, len(visible_points) - 1)
            idx2 = min(i * step, len(visible_points) - 1)
            y1 = int(visible_points[idx1])
            y2 = int(visible_points[idx2])
            pygame.draw.line(price_line_surface, (0, 200, 220, 40), (i - 1, y1), (i, y2), 2)
        screen.blit(price_line_surface, (0, 0))
        # Niebla sutil (nubes transparentes que se mueven)
        fog_surface = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        fog_time = current_time / 3000.0
        for fi in range(3):
            fog_x = int((fog_time * 20 + fi * 400) % (SCREEN_W + 300)) - 150
            fog_y = int(SCREEN_H * (0.7 + fi * 0.08))
            fog_w = 300 + fi * 50
            fog_h = 40
            for fy in range(fog_h):
                fog_alpha = int(12 * (1 - abs(fy - fog_h // 2) / (fog_h // 2)))
                pygame.draw.line(fog_surface, (100, 150, 180, fog_alpha), (fog_x, fog_y + fy), (fog_x + fog_w, fog_y + fy))
        screen.blit(fog_surface, (0, 0))
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                # Diálogo ¿Cerrar juego?
                confirming = True
                pygame.event.clear()
                pygame.time.wait(100)
                while confirming:
                    confirm_overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                    confirm_overlay.fill((0, 0, 0, 150))
                    screen.blit(confirm_overlay, (0, 0))
                    confirm_txt = font_timer.render("¿CERRAR EL JUEGO?", True, (255, 255, 255))
                    screen.blit(confirm_txt, confirm_txt.get_rect(center=(SCREEN_W // 2, int(SCREEN_H * 0.35))))
                    btn_si = pygame.Rect(SCREEN_W // 2 - 150, int(SCREEN_H * 0.50), 120, 50)
                    btn_no = pygame.Rect(SCREEN_W // 2 + 30, int(SCREEN_H * 0.50), 120, 50)
                    pygame.draw.rect(screen, (239, 83, 80), btn_si, border_radius=8)
                    pygame.draw.rect(screen, (38, 166, 154), btn_no, border_radius=8)
                    si_txt = font_btn.render("SI", True, (255, 255, 255))
                    no_txt = font_btn.render("NO", True, (255, 255, 255))
                    screen.blit(si_txt, si_txt.get_rect(center=btn_si.center))
                    screen.blit(no_txt, no_txt.get_rect(center=btn_no.center))
                    pygame.display.flip()
                    for c_event in pygame.event.get():
                        if c_event.type == pygame.QUIT:
                            confirming = False
                            app_running = False
                            in_menu = False
                        elif c_event.type == pygame.KEYDOWN:
                            if c_event.key == pygame.K_ESCAPE:
                                confirming = False
                        elif c_event.type == pygame.MOUSEBUTTONDOWN and c_event.button == 1:
                            cmx, cmy = c_event.pos
                            if btn_si.collidepoint(cmx, cmy):
                                confirming = False
                                app_running = False
                                in_menu = False
                            elif btn_no.collidepoint(cmx, cmy):
                                confirming = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                print(f"[MENU CLICK] x={mx}, y={my}")
                if btn_iniciar.collidepoint(mx, my):
                    menu_click_btn = "iniciar"
                    menu_click_time = current_time
                elif btn_ranking.collidepoint(mx, my):
                    menu_click_btn = "ranking"
                    menu_click_time = current_time
                elif btn_config.collidepoint(mx, my):
                    menu_click_btn = "config"
                    menu_click_time = current_time
        # Verificar si el efecto click terminó
        if menu_click_btn and current_time - menu_click_time > MENU_CLICK_DURATION:
            if menu_click_btn == "iniciar":
                in_menu = False
                game_started = True
                guide_animation_start = pygame.time.get_ticks()  # Iniciar animación de la guía
                liquidity_last_trigger = pygame.time.get_ticks()
                liquidity_event_active = None
                
                # La sesión se inicia automáticamente al conectar con TikTok (ver actualización de analytics)
                # o manualmente si el usuario inicia el juego sin conexión activa.
                if current_session_id is None:
                    try:
                        current_session_id = start_session()
                        tiktok_chat.reset_session_totals()
                        print(f"[ANALYTICS] Sesión iniciada manualmente ID: {current_session_id}")
                    except Exception as e:
                        print(f"[ANALYTICS] Error iniciando sesión: {e}")

                if sound_ambient is not None:
                    sound_ambient.stop()
                # Iniciar playlist de música
                if music_playlist:
                    random.shuffle(music_playlist)
                    music_current_index = 0
                    pygame.mixer.music.load(music_playlist[music_current_index])
                    vol = int(get_config("vol_music", "30")) / 100.0
                    pygame.mixer.music.set_volume(vol)
                    pygame.mixer.music.play()
                    music_playing = True
                elif sound_game_music is not None:
                    sound_game_music.set_volume(cfg_vol_music / 100.0)
                    sound_game_music.play(loops=-1)
            elif menu_click_btn == "ranking":
                # Pantalla de RANKING MEJORADA
                in_ranking = True
                ranking_scroll = 0
                ranking_enter_time = pygame.time.get_ticks()
                # Partículas del ranking
                rank_particles = []
                for _ in range(25):
                    rank_particles.append({
                        "x": random.randint(0, SCREEN_W),
                        "y": random.randint(0, SCREEN_H),
                        "speed": random.uniform(0.2, 0.8),
                        "size": random.randint(1, 3),
                        "alpha": random.randint(40, 120),
                    })
                # Velas japonesas de fondo (animadas)
                rank_candles = []
                for _ in range(12):
                    rank_candles.append({
                        "x": random.randint(0, SCREEN_W),
                        "y": random.randint(int(SCREEN_H * 0.2), int(SCREEN_H * 0.9)),
                        "w": random.randint(8, 14),
                        "h": random.randint(30, 100),
                        "color": random.choice([GLOBAL_COLOR_BULL, GLOBAL_COLOR_BEAR]),
                        "speed": random.uniform(0.3, 0.8),
                    })
                while in_ranking:
                    clock.tick(60)
                    current_time = pygame.time.get_ticks()
                    time_in_ranking = current_time - ranking_enter_time
                    screen.fill(GLOBAL_COLOR_BG)
                    # --- PARTICULAS DE FONDO ---
                    for p in rank_particles:
                        p["y"] -= p["speed"]
                        if p["y"] < -5:
                            p["y"] = SCREEN_H + 5
                            p["x"] = random.randint(0, SCREEN_W)
                        ps = pygame.Surface((p["size"] * 2, p["size"] * 2), pygame.SRCALPHA)
                        pygame.draw.circle(ps, (0, 180, 220, p["alpha"]), (p["size"], p["size"]), p["size"])
                        screen.blit(ps, (int(p["x"]), int(p["y"])))
                    # --- VELAS JAPONESAS DE FONDO (baja opacidad) ---
                    candle_bg_surface = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                    for rc in rank_candles:
                        rc["x"] -= rc["speed"]
                        if rc["x"] < -20:
                            rc["x"] = SCREEN_W + 20
                            rc["y"] = random.randint(int(SCREEN_H * 0.2), int(SCREEN_H * 0.9))
                            rc["h"] = random.randint(30, 100)
                        col = (rc["color"][0], rc["color"][1], rc["color"][2], 30)
                        pygame.draw.rect(candle_bg_surface, col, (int(rc["x"]), int(rc["y"]), rc["w"], rc["h"]))
                        # Mecha
                        wick_col = (rc["color"][0], rc["color"][1], rc["color"][2], 20)
                        cx = int(rc["x"]) + rc["w"] // 2
                        pygame.draw.line(candle_bg_surface, wick_col, (cx, int(rc["y"]) - 12), (cx, int(rc["y"])), 1)
                        pygame.draw.line(candle_bg_surface, wick_col, (cx, int(rc["y"]) + rc["h"]), (cx, int(rc["y"]) + rc["h"] + 12), 1)
                    screen.blit(candle_bg_surface, (0, 0))
                    # --- TITULO con sombra/glow ---
                    font_rank_title = pygame.font.SysFont("Arial", int(SCREEN_H * 0.055), bold=True)
                    # Sombra
                    title_shadow = font_rank_title.render("RANKING GENERAL", True, (0, 80, 100))
                    screen.blit(title_shadow, title_shadow.get_rect(center=(SCREEN_W // 2 + 2, int(SCREEN_H * 0.04) + 2)))
                    # Texto principal
                    rank_title = font_rank_title.render("RANKING GENERAL", True, (0, 220, 255))
                    screen.blit(rank_title, rank_title.get_rect(center=(SCREEN_W // 2, int(SCREEN_H * 0.04))))
                    # Total jugadores arriba derecha (pegado como EN VIVO)
                    all_players = get_all_players_ranked()
                    font_total = pygame.font.SysFont("Arial", int(SCREEN_H * 0.020), bold=True)
                    total_txt = font_total.render(f"{len(all_players)} jugadores activos", True, (0, 200, 220))
                    screen.blit(total_txt, (SCREEN_W - total_txt.get_width() - int(SCREEN_W * 0.03), int(SCREEN_H * 0.03)))
                    # --- INDICADOR EN VIVO (más grande) ---
                    live_x = int(SCREEN_W * 0.03)
                    live_y = int(SCREEN_H * 0.04)
                    live_pulse = int(8 + 3 * math.sin(current_time / 300.0))
                    live_alpha = int(180 + 75 * math.sin(current_time / 300.0))
                    live_glow = pygame.Surface((live_pulse * 4, live_pulse * 4), pygame.SRCALPHA)
                    pygame.draw.circle(live_glow, (0, 255, 80, 40), (live_pulse * 2, live_pulse * 2), live_pulse * 2)
                    screen.blit(live_glow, (live_x - live_pulse * 2, live_y - live_pulse * 2))
                    pygame.draw.circle(screen, (0, min(255, live_alpha + 50), 80), (live_x, live_y), live_pulse)
                    font_live = pygame.font.SysFont("Arial", int(SCREEN_H * 0.020), bold=True)
                    live_txt = font_live.render("EN VIVO", True, (0, 220, 100))
                    screen.blit(live_txt, (live_x + 14, live_y - live_txt.get_height() // 2))
                    # --- PANEL STREAMER PROFESIONAL ---
                    streamer_now = get_streamer_stats()
                    st_total = streamer_now["wins"] + streamer_now["losses"]
                    st_wr = int((streamer_now["wins"] / st_total * 100)) if st_total > 0 else 0
                    st_panel_w = int(SCREEN_W * 0.62)
                    st_panel_h = int(SCREEN_H * 0.09)
                    st_bg_x = SCREEN_W // 2 - st_panel_w // 2
                    st_bg_y = int(SCREEN_H * 0.08)
                    # Fondo
                    st_bg = pygame.Surface((st_panel_w, st_panel_h), pygame.SRCALPHA)
                    for row in range(st_panel_h):
                        alpha = int(130 + 30 * (row / st_panel_h))
                        pygame.draw.line(st_bg, (0, 20, 40, alpha), (0, row), (st_panel_w, row))
                    screen.blit(st_bg, (st_bg_x, st_bg_y))
                    glow_alpha = int(180 + 60 * math.sin(current_time / 500.0))
                    pygame.draw.rect(screen, (0, min(255, glow_alpha), 220), (st_bg_x, st_bg_y, st_panel_w, st_panel_h), 2, border_radius=6)
                    # Avatar + Nombre (centro-izquierda)
                    if avatar_img is not None:
                        av_size = int(st_panel_h * 0.60)
                        av_small = pygame.transform.smoothscale(avatar_img, (av_size, av_size))
                        screen.blit(av_small, (st_bg_x + 10, st_bg_y + (st_panel_h - av_size) // 2))
                        name_x = st_bg_x + 10 + av_size + 8
                    else:
                        name_x = st_bg_x + 12
                    font_st_name = pygame.font.SysFont("Arial", int(SCREEN_H * 0.022), bold=True)
                    st_name = font_st_name.render("LEAN FX", True, (0, 220, 255))
                    screen.blit(st_name, (name_x, st_bg_y + (st_panel_h - st_name.get_height()) // 2))
                    # Cajitas de stats (al lado derecho del nombre)
                    font_st_label = pygame.font.SysFont("Arial", int(SCREEN_H * 0.013), bold=True)
                    font_st_val = pygame.font.SysFont("Arial", int(SCREEN_H * 0.018), bold=True)
                    box_h = int(st_panel_h * 0.75)
                    box_w = int(st_panel_w * 0.12)
                    box_gap = int(st_panel_w * 0.01)
                    box_start_x = name_x + st_name.get_width() + 20
                    box_y = st_bg_y + (st_panel_h - box_h) // 2
                    st_profit_fxp = streamer_now['balance'] - 10000
                    stats_boxes = [
                        ("BALANCE", f"{int(streamer_now['balance'])}", (0, 220, 255)),
                        ("+/- FXP", f"{int(st_profit_fxp):+d} FXP", (38, 200, 154) if st_profit_fxp >= 0 else GLOBAL_COLOR_BEAR),
                        ("WINS", f"{streamer_now['wins']}", GLOBAL_COLOR_BULL),
                        ("LOSSES", f"{streamer_now['losses']}", GLOBAL_COLOR_BEAR),
                        ("WIN RATE", f"{st_wr}%", (200, 200, 220)),
                    ]
                    for i, (label, value, color) in enumerate(stats_boxes):
                        bx = box_start_x + i * (box_w + box_gap)
                        box_surf = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
                        box_surf.fill((0, 20, 35, 150))
                        screen.blit(box_surf, (bx, box_y))
                        pygame.draw.rect(screen, (0, 80, 100), (bx, box_y, box_w, box_h), 1, border_radius=3)
                        lbl = font_st_label.render(label, True, (100, 140, 160))
                        screen.blit(lbl, lbl.get_rect(center=(bx + box_w // 2, box_y + 10)))
                        val = font_st_val.render(value, True, color)
                        screen.blit(val, val.get_rect(center=(bx + box_w // 2, box_y + box_h // 2 + 4)))
                    # --- LINEA SEPARADORA con gradiente ---
                    sep_y = int(SCREEN_H * 0.20)
                    sep_surface = pygame.Surface((int(SCREEN_W * 0.90), 2), pygame.SRCALPHA)
                    for sx in range(int(SCREEN_W * 0.90)):
                        dist = abs(sx - int(SCREEN_W * 0.45)) / (SCREEN_W * 0.45)
                        alpha = int(150 * (1 - dist))
                        pygame.draw.line(sep_surface, (0, 180, 220, alpha), (sx, 0), (sx, 1))
                    screen.blit(sep_surface, (int(SCREEN_W * 0.05), sep_y))
                    # Headers
                    headers = ["#", "JUGADOR", "BALANCE (FXP)", "+/- FXP", "W", "L", "WIN RATE"]
                    hx_positions = [0.05, 0.10, 0.30, 0.42, 0.52, 0.59, 0.67]
                    font_header = pygame.font.SysFont("Arial", int(SCREEN_H * 0.016), bold=True)
                    header_y = int(SCREEN_H * 0.22)
                    for i, h in enumerate(headers):
                        h_txt = font_header.render(h, True, (120, 160, 180))
                        screen.blit(h_txt, (int(SCREEN_W * hx_positions[i]), header_y))
                    # Underline debajo de headers
                    underline_y = header_y + int(SCREEN_H * 0.022)
                    underline_surf = pygame.Surface((int(SCREEN_W * 0.92), 1), pygame.SRCALPHA)
                    for ux in range(int(SCREEN_W * 0.92)):
                        dist = abs(ux - int(SCREEN_W * 0.46)) / (SCREEN_W * 0.46)
                        alpha = int(100 * (1 - dist))
                        pygame.draw.line(underline_surf, (0, 150, 180, alpha), (ux, 0), (ux, 0))
                    screen.blit(underline_surf, (int(SCREEN_W * 0.04), underline_y))
                    # --- BARRA LATERAL DECORATIVA CYAN con glow ---
                    bar_deco_x = int(SCREEN_W * 0.035)
                    bar_deco_y1 = int(SCREEN_H * 0.25)
                    bar_deco_y2 = int(SCREEN_H * 0.93)
                    # Glow (barra ancha semitransparente)
                    glow_bar = pygame.Surface((8, bar_deco_y2 - bar_deco_y1), pygame.SRCALPHA)
                    glow_bar.fill((0, 180, 220, 25))
                    screen.blit(glow_bar, (bar_deco_x - 3, bar_deco_y1))
                    # Barra fina principal
                    pygame.draw.line(screen, (0, 180, 220, 180), (bar_deco_x, bar_deco_y1), (bar_deco_x, bar_deco_y2), 2)
                    # --- DIBUJAR FILAS (mejoradas v2) ---
                    row_h = int(SCREEN_H * 0.065)
                    visible_rows = 10
                    start_y = int(SCREEN_H * 0.26)
                    font_row_name = pygame.font.SysFont("Arial", int(SCREEN_H * 0.024), bold=True)
                    font_row_stat = pygame.font.SysFont("Arial", int(SCREEN_H * 0.020), bold=True)
                    for idx in range(min(visible_rows, len(all_players) - ranking_scroll)):
                        p_idx = idx + ranking_scroll
                        if p_idx >= len(all_players):
                            break
                        p = all_players[p_idx]
                        # Animación cascada: cada fila aparece con delay
                        row_delay = idx * 80
                        row_alpha_factor = min(1.0, max(0.0, (time_in_ranking - row_delay) / 300.0))
                        if row_alpha_factor <= 0:
                            continue
                        ry = start_y + (idx * row_h)
                        # Slide desde la derecha
                        slide_offset = int((1.0 - row_alpha_factor) * 60)
                        row_x_base = int(SCREEN_W * 0.045) + slide_offset
                        row_width = int(SCREEN_W * 0.92)
                        # Fondo de fila
                        row_bg = pygame.Surface((row_width, row_h - 3), pygame.SRCALPHA)
                        # Degradado de opacidad: filas más abajo se ven más tenues
                        fade_factor = max(0.4, 1.0 - (p_idx * 0.06)) if p_idx >= 3 else 1.0
                        if p_idx == 0:
                            for ry_line in range(row_h - 3):
                                g_alpha = int(row_alpha_factor * (70 + 40 * (ry_line / (row_h - 3))))
                                pygame.draw.line(row_bg, (60, 50, 0, g_alpha), (0, ry_line), (row_width, ry_line))
                        elif p_idx == 1:
                            row_bg.fill((30, 30, 40, int(row_alpha_factor * 100)))
                        elif p_idx == 2:
                            row_bg.fill((35, 25, 15, int(row_alpha_factor * 90)))
                        elif idx % 2 == 0:
                            row_bg.fill((18, 22, 35, int(row_alpha_factor * 100 * fade_factor)))
                        else:
                            row_bg.fill((12, 15, 25, int(row_alpha_factor * 70 * fade_factor)))
                        screen.blit(row_bg, (row_x_base, ry))
                        # --- HIGHLIGHT #1: borde dorado completo + brillo ---
                        if p_idx == 0:
                            # Borde dorado completo alrededor de la fila
                            gold_pulse = int(200 + 55 * math.sin(current_time / 400.0))
                            pygame.draw.rect(screen, (gold_pulse, int(gold_pulse * 0.84), 0), (row_x_base, ry, row_width, row_h - 3), 2, border_radius=3)
                            # Glow exterior
                            glow_s = pygame.Surface((row_width + 6, row_h + 1), pygame.SRCALPHA)
                            glow_s.fill((255, 215, 0, 15))
                            screen.blit(glow_s, (row_x_base - 3, ry - 2))
                        elif p_idx == 1:
                            pygame.draw.rect(screen, (192, 192, 192), (row_x_base, ry, 4, row_h - 3))
                        elif p_idx == 2:
                            pygame.draw.rect(screen, (205, 127, 50), (row_x_base, ry, 4, row_h - 3))
                        # --- MEDALLA: circulo dorado para #1, numeros para el resto ---
                        medal_cx = int(SCREEN_W * hx_positions[0]) + slide_offset + 12
                        medal_cy = ry + (row_h - 3) // 2
                        if p_idx == 0:
                            # Circulo dorado con "1" adentro
                            pygame.draw.circle(screen, (255, 215, 0), (medal_cx, medal_cy), int(SCREEN_H * 0.014))
                            pygame.draw.circle(screen, (200, 160, 0), (medal_cx, medal_cy), int(SCREEN_H * 0.014), 2)
                            one_font = pygame.font.SysFont("Arial", int(SCREEN_H * 0.016), bold=True)
                            one_txt = one_font.render("1", True, (40, 20, 0))
                            screen.blit(one_txt, one_txt.get_rect(center=(medal_cx, medal_cy)))
                        elif p_idx == 1:
                            pygame.draw.circle(screen, (192, 192, 192), (medal_cx, medal_cy), int(SCREEN_H * 0.012))
                            two_font = pygame.font.SysFont("Arial", int(SCREEN_H * 0.015), bold=True)
                            two_txt = two_font.render("2", True, (30, 30, 30))
                            screen.blit(two_txt, two_txt.get_rect(center=(medal_cx, medal_cy)))
                        elif p_idx == 2:
                            pygame.draw.circle(screen, (205, 127, 50), (medal_cx, medal_cy), int(SCREEN_H * 0.012))
                            three_font = pygame.font.SysFont("Arial", int(SCREEN_H * 0.015), bold=True)
                            three_txt = three_font.render("3", True, (30, 15, 0))
                            screen.blit(three_txt, three_txt.get_rect(center=(medal_cx, medal_cy)))
                        else:
                            num_font = pygame.font.SysFont("Arial", int(SCREEN_H * 0.017), bold=True)
                            num_txt = num_font.render(str(p_idx + 1), True, (140, 140, 160))
                            screen.blit(num_txt, num_txt.get_rect(center=(medal_cx, medal_cy)))
                        # Nombre con avatar
                        if p_idx < 3:
                            name_color = (255, 255, 255)
                        else:
                            nc = int(200 * fade_factor)
                            name_color = (nc, nc, min(255, nc + 10))
                        # Avatar circulito
                        r_avatar = get_viewer_avatar(p["username"], 30)
                        name_x_pos = int(SCREEN_W * hx_positions[1]) + slide_offset
                        if r_avatar is not None:
                            screen.blit(r_avatar, (name_x_pos, ry + (row_h - 3) // 2 - 15))
                            name_x_pos += 36
                        name_txt = font_row_name.render(p["username"], True, name_color)
                        screen.blit(name_txt, (name_x_pos, ry + (row_h - 3) // 2 - name_txt.get_height() // 2))
                        # Balance (gris para los que están en negativo)
                        if p['balance'] < 10000:
                            bal_color = (140, 140, 150)
                        elif p_idx < 3:
                            bal_color = (0, 220, 255)
                        else:
                            bal_color = (0, int(180 * fade_factor), int(200 * fade_factor))
                        bal_txt = font_row_name.render(f"{int(p['balance'])} FXP", True, bal_color)
                        screen.blit(bal_txt, (int(SCREEN_W * hx_positions[2]) + slide_offset, ry + (row_h - 3) // 2 - bal_txt.get_height() // 2))
                        # PROFIT (diferencia desde 10,000 FXP iniciales)
                        profit_fxp = p['balance'] - 10000
                        if profit_fxp >= 0:
                            profit_color = (38, 200, 154)
                            profit_str = f"+{int(profit_fxp)} FXP"
                        else:
                            profit_color = GLOBAL_COLOR_BEAR
                            profit_str = f"{int(profit_fxp)} FXP"
                        profit_txt = font_row_stat.render(profit_str, True, profit_color)
                        screen.blit(profit_txt, (int(SCREEN_W * hx_positions[3]) + slide_offset, ry + (row_h - 3) // 2 - profit_txt.get_height() // 2))
                        # W
                        w_txt = font_row_stat.render(str(p["wins"]), True, GLOBAL_COLOR_BULL)
                        screen.blit(w_txt, (int(SCREEN_W * hx_positions[4]) + slide_offset, ry + (row_h - 3) // 2 - w_txt.get_height() // 2))
                        # L
                        l_txt = font_row_stat.render(str(p["losses"]), True, GLOBAL_COLOR_BEAR)
                        screen.blit(l_txt, (int(SCREEN_W * hx_positions[5]) + slide_offset, ry + (row_h - 3) // 2 - l_txt.get_height() // 2))
                        # --- WIN RATE con barra gradiente + glow ---
                        total = p["wins"] + p["losses"]
                        wr = int((p["wins"] / total * 100)) if total > 0 else 0
                        wr_x = int(SCREEN_W * hx_positions[6]) + slide_offset
                        bar_w_wr = int(SCREEN_W * 0.14)
                        bar_h_wr = int(SCREEN_H * 0.013)
                        bar_y_wr = ry + (row_h - 3) // 2 - bar_h_wr // 2
                        pygame.draw.rect(screen, (25, 25, 35), (wr_x, bar_y_wr, bar_w_wr, bar_h_wr), border_radius=7)
                        fill_w = int(bar_w_wr * (wr / 100))
                        if fill_w > 0:
                            bar_surf = pygame.Surface((fill_w, bar_h_wr), pygame.SRCALPHA)
                            if wr >= 50:
                                c1 = (20, 120, 100)
                                c2 = (38, 220, 180)
                            else:
                                c1 = (180, 40, 40)
                                c2 = (255, 100, 100)
                            for bx in range(fill_w):
                                t = bx / max(fill_w - 1, 1)
                                r_c = int(c1[0] + (c2[0] - c1[0]) * t)
                                g_c = int(c1[1] + (c2[1] - c1[1]) * t)
                                b_c = int(c1[2] + (c2[2] - c1[2]) * t)
                                pygame.draw.line(bar_surf, (r_c, g_c, b_c, 220), (bx, 0), (bx, bar_h_wr))
                            screen.blit(bar_surf, (wr_x, bar_y_wr))
                            if p_idx < 3:
                                glow_surf = pygame.Surface((fill_w + 4, bar_h_wr + 4), pygame.SRCALPHA)
                                glow_surf.fill((c2[0], c2[1], c2[2], 30))
                                screen.blit(glow_surf, (wr_x - 2, bar_y_wr - 2))
                        pygame.draw.rect(screen, (50, 50, 60), (wr_x, bar_y_wr, bar_w_wr, bar_h_wr), 1, border_radius=7)
                        wr_txt = font_row_stat.render(f"{wr}%", True, (220, 220, 230))
                        screen.blit(wr_txt, (wr_x + bar_w_wr + 10, ry + (row_h - 3) // 2 - wr_txt.get_height() // 2))
                    # --- SCROLL INDICATOR (barrita fina a la derecha) ---
                    if len(all_players) > visible_rows:
                        scroll_track_x = int(SCREEN_W * 0.97)
                        scroll_track_y = start_y
                        scroll_track_h = int(SCREEN_H * 0.65)
                        # Track (fondo)
                        pygame.draw.line(screen, (30, 40, 50), (scroll_track_x, scroll_track_y), (scroll_track_x, scroll_track_y + scroll_track_h), 3)
                        # Thumb (posicion actual)
                        thumb_h = max(20, int(scroll_track_h * (visible_rows / len(all_players))))
                        thumb_y = scroll_track_y + int((scroll_track_h - thumb_h) * (ranking_scroll / max(1, len(all_players) - visible_rows)))
                        pygame.draw.line(screen, (0, 180, 220), (scroll_track_x, thumb_y), (scroll_track_x, thumb_y + thumb_h), 4)
                    # --- FOOTER mejorado (sutil, sin ESC para viewers) ---
                    from datetime import datetime
                    now = datetime.now()
                    if now.month == 12:
                        next_month = f"1 Enero {now.year + 1}"
                    else:
                        months = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
                        next_month = f"1 {months[now.month + 1]} {now.year}"
                    font_footer = pygame.font.SysFont("Arial", int(SCREEN_H * 0.018), bold=True)
                    reset_txt = font_footer.render(f"Reset mensual: {next_month}", True, (80, 120, 150))
                    screen.blit(reset_txt, reset_txt.get_rect(center=(SCREEN_W // 2, int(SCREEN_H * 0.95))))
                    pygame.display.flip()
                    for r_event in pygame.event.get():
                        if r_event.type == pygame.QUIT:
                            in_ranking = False
                            in_menu = False
                            app_running = False
                        elif r_event.type == pygame.KEYDOWN:
                            if r_event.key == pygame.K_ESCAPE:
                                in_ranking = False
                            elif r_event.key == pygame.K_DOWN:
                                if ranking_scroll < max(0, len(all_players) - visible_rows):
                                    ranking_scroll += 1
                            elif r_event.key == pygame.K_UP:
                                if ranking_scroll > 0:
                                    ranking_scroll -= 1
                menu_click_btn = None
            elif menu_click_btn == "config":
                # === PANTALLA DE CONFIGURACIÓN ===
                in_config = True
                # Cargar valores actuales
                cfg_timer = int(get_config("timer_duration", "10000")) // 1000  # en segundos
                cfg_risk = int(get_config("trade_risk", "100"))
                cfg_tp_mult = float(get_config("tp_multiplier", "3.0"))
                cfg_bot_enabled = get_config("bot_enabled", "1") == "1"
                cfg_bot_wr = int(float(get_config("bot_win_rate", "0.70")) * 100)
                cfg_viewers_enabled = get_config("viewers_enabled", "1") == "1"
                cfg_vol_music = int(get_config("vol_music", "30"))
                cfg_vol_fx = int(get_config("vol_fx", "100"))
                cfg_max_rr = int(get_config("max_rr", "3"))
                # --- Sistema de liquidez por likes ---
                cfg_liq_interval = int(get_config("liq_interval_min", "10"))
                cfg_liq_a_target = int(get_config("liq_a_target", "100"))
                cfg_liq_c1_likes = int(get_config("liq_c1_likes", "100"))
                cfg_liq_c1_bonus = int(get_config("liq_c1_bonus", "500"))
                cfg_liq_c2_likes = int(get_config("liq_c2_likes", "200"))
                cfg_liq_c2_bonus = int(get_config("liq_c2_bonus", "1000"))
                cfg_liq_c3_likes = int(get_config("liq_c3_likes", "400"))
                cfg_liq_c3_bonus = int(get_config("liq_c3_bonus", "2000"))
                cfg_liq_d_target = int(get_config("liq_d_target", "150"))
                cfg_liq_d_bonus = int(get_config("liq_d_bonus", "800"))
                cfg_liq_mode = get_config("liq_mode", "0") == "1"
                cfg_liq_dyn_sens = int(get_config("liq_dyn_sens", "2"))
                cfg_liq_dyn_mult = float(get_config("liq_dyn_mult", "1.5"))
                # Colores
                cfg_color_bg = get_config("color_bg", "8,12,20")
                cfg_color_bull = get_config("color_bull", "38,166,154")
                cfg_color_bear = get_config("color_bear", "239,83,80")
                
                # Definición modular de la configuración
                config_modules = [
                    {
                        "title": "Parámetros Principales",
                        "tag": "Módulo 1",
                        "tabs": ["Operación", "Automatización"],
                        "sections": [
                            {"title": "Parámetros de Operación", "icon": "timer", "items": ["timer", "risk", "tp_mult"]},
                            {"title": "Automatización & Bots", "icon": "bot", "items": ["bot_enabled", "bot_wr", "viewers_enabled"]}
                        ]
                    },
                    {
                        "title": "Audio y Gestión de Audiencia",
                        "tag": "Módulo 2",
                        "tabs": ["Audio", "Resumen"],
                        "sections": [
                            {"title": "Configuración de Audio", "icon": "audio", "items": ["vol_music", "vol_fx", "max_rr"]},
                            {"title": "Resumen de Parámetros", "icon": "summary", "items": ["sys_status", "audio_latency", "sync"]}
                        ]
                    },
                    {
                        "title": "Liquidez por Likes",
                        "tag": "Módulo 3",
                        "tabs": ["Evento A", "Evento C", "Evento D", "Dinámico"],
                        "sections": [
                            {"title": "Configuración de Meta", "icon": "meta", "items": []}, # Dinámico según sub-tab
                            {"title": "Opciones Específicas", "icon": "settings", "items": []}
                        ]
                    },
                    {
                        "title": "Colores Visuales y Acciones",
                        "tag": "Módulo Final",
                        "tabs": ["Paleta", "Sistema"],
                        "sections": [
                            {"title": "Paleta de Gráficos", "icon": "palette", "items": ["color_bg", "color_bull", "color_bear"]},
                            {"title": "Restablecer Sistema", "icon": "warning", "items": ["reset"]}
                        ]
                    }
                ]

                # Diccionario de opciones para fácil acceso
                config_items = {
                    "timer": {"label": "Timer (segundos)", "type": "number", "min": 3, "max": 30, "step": 1},
                    "risk": {"label": "Riesgo por trade (FXP)", "type": "number", "min": 50, "max": 500, "step": 50},
                    "tp_mult": {"label": "Multiplicador FXP", "type": "number", "min": 1.0, "max": 5.0, "step": 0.5},
                    "bot_enabled": {"label": "Bot LEAN FX", "type": "toggle"},
                    "bot_wr": {"label": "Bot Win Rate %", "type": "number", "min": 50, "max": 90, "step": 5},
                    "viewers_enabled": {"label": "Bots Viewers", "type": "toggle"},
                    "vol_music": {"label": "Volumen Música %", "type": "number", "min": 0, "max": 100, "step": 10},
                    "vol_fx": {"label": "Volumen Efectos %", "type": "number", "min": 0, "max": 100, "step": 10},
                    "max_rr": {"label": "Meta Máxima Viewers", "type": "number", "min": 1, "max": 10, "step": 1},
                    "liq_interval": {"label": "Evento cada (minutos)", "type": "number", "min": 2, "max": 30, "step": 1},
                    "liq_a_target": {"label": "Meta likes (Evento A)", "type": "number", "min": 20, "max": 500, "step": 10},
                    "liq_c1_likes": {"label": "Nivel 1: likes requeridos", "type": "number", "min": 20, "max": 500, "step": 10},
                    "liq_c1_bonus": {"label": "Bono FXP (Nivel 1)", "type": "number", "min": 100, "max": 3000, "step": 100},
                    "liq_c2_likes": {"label": "Nivel 2: likes requeridos", "type": "number", "min": 20, "max": 800, "step": 10},
                    "liq_c2_bonus": {"label": "Bono FXP (Nivel 2)", "type": "number", "min": 100, "max": 5000, "step": 100},
                    "liq_c3_likes": {"label": "Nivel 3: likes requeridos", "type": "number", "min": 20, "max": 1500, "step": 10},
                    "liq_c3_bonus": {"label": "Bono FXP (Nivel 3)", "type": "number", "min": 100, "max": 8000, "step": 100},
                    "liq_d_target": {"label": "Meta likes (Evento D)", "type": "number", "min": 20, "max": 500, "step": 10},
                    "liq_d_bonus": {"label": "Bono FXP (Evento D)", "type": "number", "min": 100, "max": 3000, "step": 100},
                    "liq_mode": {"label": "Modo Dinámico Likes", "type": "toggle"},
                    "liq_dyn_sens": {"label": "Sensibilidad Meta", "type": "number", "min": 1, "max": 10, "step": 1},
                    "liq_dyn_mult": {"label": "Multiplicador Bono", "type": "number", "min": 1.0, "max": 5.0, "step": 0.5},
                    "color_bg": {"label": "Color de Fondo", "type": "color"},
                    "color_bull": {"label": "Color Vela Bull", "type": "color"},
                    "color_bear": {"label": "Color Vela Bear", "type": "color"},
                    "reset": {"label": "RESET RANKING", "type": "button"},
                    # Items informativos
                    "sys_status": {"label": "Estado del Sistema", "type": "info", "value": "Optimizado", "color": (38, 166, 154)},
                    "audio_latency": {"label": "Latencia de Audio", "type": "info", "value": "~12ms", "color": (200, 200, 200)},
                    "sync": {"label": "Sincronización", "type": "info", "value": "Activa", "color": (0, 220, 255)},
                }

                current_mod = 0
                current_tab = 0
                current_item_idx = 0
                config_confirm_reset = False

                while in_config:
                    clock.tick(60)
                    current_time = pygame.time.get_ticks()
                    screen.fill(GLOBAL_COLOR_BG)
                    
                    # --- CÁLCULOS DINÁMICOS SEGÚN EL MÓDULO Y SUB-TAB ---
                    mod = config_modules[current_mod]
                    
                    # Actualizar items de Módulo 3 según la sub-pestaña seleccionada
                    if current_mod == 2:
                        if current_tab == 0: # Evento A
                            mod["sections"][0]["items"] = ["liq_interval", "liq_a_target"]
                            mod["sections"][1]["items"] = []
                        elif current_tab == 1: # Evento C
                            mod["sections"][0]["items"] = ["liq_c1_likes", "liq_c1_bonus", "liq_c2_likes", "liq_c2_bonus"]
                            mod["sections"][1]["items"] = ["liq_c3_likes", "liq_c3_bonus"]
                        elif current_tab == 2: # Evento D
                            mod["sections"][0]["items"] = ["liq_d_target"]
                            mod["sections"][1]["items"] = ["liq_d_bonus"]
                        elif current_tab == 3: # Dinámico
                            mod["sections"][0]["items"] = ["liq_mode"]
                            mod["sections"][1]["items"] = ["liq_dyn_sens", "liq_dyn_mult"]

                    # --- DIBUJAR ENCABEZADO ---
                    font_title = pygame.font.SysFont("Arial", int(SCREEN_H * 0.06), bold=True)
                    font_tag = pygame.font.SysFont("Arial", int(SCREEN_H * 0.025), bold=True)
                    font_tabs = pygame.font.SysFont("Arial", int(SCREEN_H * 0.022), bold=True)
                    font_cfg_title = pygame.font.SysFont("Arial", int(SCREEN_H * 0.05), bold=True)
                    font_cfg_label = pygame.font.SysFont("Arial", int(SCREEN_H * 0.025), bold=True)
                    
                    # Título y Tag del Módulo
                    title_surf = font_title.render(mod["title"], True, (255, 255, 255))
                    screen.blit(title_surf, (int(SCREEN_W * 0.05), int(SCREEN_H * 0.06)))
                    
                    tag_surf = font_tag.render(mod["tag"], True, (0, 180, 220))
                    tag_rect = tag_surf.get_rect(midleft=(title_surf.get_width() + int(SCREEN_W * 0.07), title_surf.get_rect(top=int(SCREEN_H * 0.06)).centery))
                    pygame.draw.rect(screen, (0, 40, 60), tag_rect.inflate(20, 10), border_radius=15)
                    pygame.draw.rect(screen, (0, 180, 220), tag_rect.inflate(20, 10), 1, border_radius=15)
                    screen.blit(tag_surf, tag_rect)
                    
                    # Navegación de Pestañas (Top Right)
                    tab_x = int(SCREEN_W * 0.95)
                    for i, tname in enumerate(reversed(mod["tabs"])):
                        t_idx = len(mod["tabs"]) - 1 - i
                        is_sel = (t_idx == current_tab)
                        t_surf = font_tabs.render(tname, True, (255, 255, 255) if is_sel else (100, 100, 110))
                        t_rect = t_surf.get_rect(midright=(tab_x, int(SCREEN_H * 0.08)))
                        if is_sel:
                            pygame.draw.rect(screen, (0, 180, 220), t_rect.inflate(30, 15), border_radius=8)
                            # Efecto brillo
                            glow = pygame.Surface(t_rect.inflate(40, 25).size, pygame.SRCALPHA)
                            pygame.draw.rect(glow, (0, 180, 220, 50), glow.get_rect(), border_radius=10)
                            screen.blit(glow, t_rect.inflate(40, 25).topleft)
                        else:
                            pygame.draw.rect(screen, (20, 24, 35), t_rect.inflate(30, 15), border_radius=8)
                            pygame.draw.rect(screen, (40, 45, 60), t_rect.inflate(30, 15), 1, border_radius=8)
                        
                        screen.blit(t_surf, t_rect)
                        tab_x -= t_rect.width + 45

                    # --- DIBUJAR PANELES DE SECCIONES ---
                    panel_w = int(SCREEN_W * 0.44)
                    panel_h = int(SCREEN_H * 0.70)
                    panel_y = int(SCREEN_H * 0.16)
                    
                    for s_idx, section in enumerate(mod["sections"]):
                        px = int(SCREEN_W * 0.05) if s_idx == 0 else int(SCREEN_W * 0.51)
                        # Fondo del panel
                        panel_rect = pygame.Rect(px, panel_y, panel_w, panel_h)
                        pygame.draw.rect(screen, (15, 18, 28, 200), panel_rect, border_radius=12)
                        pygame.draw.rect(screen, (30, 35, 50), panel_rect, 1, border_radius=12)
                        
                        # Título de la sección
                        font_sec = pygame.font.SysFont("Arial", int(SCREEN_H * 0.024), bold=True)
                        sec_surf = font_sec.render(section["title"], True, (0, 180, 220))
                        screen.blit(sec_surf, (px + 45, panel_y + 30))
                        
                        # Icono (placeholder visual)
                        pygame.draw.circle(screen, (0, 180, 220), (px + 25, panel_y + 42), 4)
                        
                        # Dibujar Items
                        item_y = panel_y + 80
                        items_in_this_panel = section["items"]
                        
                        # En el Módulo Final, el panel derecho es especial (Reset)
                        if current_mod == 3 and s_idx == 1:
                            # Dibujar área de peligro
                            warning_icon_font = pygame.font.SysFont("Segoe UI Symbol", 80)
                            warn_surf = warning_icon_font.render("⚠", True, (239, 83, 80))
                            screen.blit(warn_surf, warn_surf.get_rect(center=(px + panel_w//2, panel_y + panel_h//3)))
                            
                            font_warn_title = pygame.font.SysFont("Arial", 30, bold=True)
                            font_warn_desc = pygame.font.SysFont("Arial", 20)
                            
                            w_title = font_warn_title.render("Restablecer Sistema", True, (239, 83, 80))
                            w_desc = font_warn_desc.render("Vuelve todos los valores y el ranking a su estado de fábrica.", True, (150, 150, 160))
                            
                            screen.blit(w_title, w_title.get_rect(center=(px + panel_w//2, panel_y + panel_h//2 + 20)))
                            screen.blit(w_desc, w_desc.get_rect(center=(px + panel_w//2, panel_y + panel_h//2 + 60)))
                            
                            # Botón Reset
                            btn_rect = pygame.Rect(0, 0, 200, 50)
                            btn_rect.center = (px + panel_w//2, panel_y + panel_h * 0.75)
                            is_sel = (current_item_idx == 0 and current_tab == 1) # Simplificado
                            pygame.draw.rect(screen, (239, 83, 80), btn_rect, border_radius=10)
                            if is_sel:
                                pygame.draw.rect(screen, (255, 255, 255), btn_rect, 2, border_radius=10)
                            
                            btn_txt = font_sec.render("RESET RANKING", True, (255, 255, 255))
                            screen.blit(btn_txt, btn_txt.get_rect(center=btn_rect.center))
                            continue

                        # Si no hay items (Módulo 3 tabs vacías), mostrar placeholder
                        if not items_in_this_panel and current_mod == 2:
                            font_empty = pygame.font.SysFont("Arial", 18, italic=True)
                            empty_txt = font_empty.render("Sin opciones adicionales", True, (60, 65, 80))
                            screen.blit(empty_txt, (px + 45, item_y))
                            continue

                        for i_idx, item_key in enumerate(items_in_this_panel):
                            opt = config_items[item_key]
                            # Detectar si este item está seleccionado
                            is_item_selected = False
                            if s_idx == 0 and current_item_idx == i_idx:
                                is_item_selected = True
                            elif s_idx == 1 and current_item_idx == i_idx + len(mod["sections"][0]["items"]):
                                is_item_selected = True
                            
                            # Fila de item
                            row_rect = pygame.Rect(px + 20, item_y, panel_w - 40, 55)
                            pygame.draw.rect(screen, (25, 30, 45, 150), row_rect, border_radius=8)
                            if is_item_selected:
                                pygame.draw.rect(screen, (0, 180, 220), row_rect, 1, border_radius=8)
                            
                            # Label
                            font_label = pygame.font.SysFont("Arial", 20, bold=True)
                            lbl_surf = font_label.render(opt["label"], True, (200, 200, 210))
                            screen.blit(lbl_surf, (row_rect.x + 20, row_rect.centery - lbl_surf.get_height() // 2))
                            
                            # Valor y controles
                            val_x = row_rect.right - 140
                            val_cy = row_rect.centery
                            
                            if opt["type"] == "number":
                                # Obtener valor
                                if item_key == "timer": val = cfg_timer
                                elif item_key == "risk": val = cfg_risk
                                elif item_key == "tp_mult": val = cfg_tp_mult
                                elif item_key == "bot_wr": val = cfg_bot_wr
                                elif item_key == "vol_music": val = cfg_vol_music
                                elif item_key == "vol_fx": val = cfg_vol_fx
                                elif item_key == "max_rr": val = cfg_max_rr
                                elif item_key == "liq_interval": val = cfg_liq_interval
                                elif item_key == "liq_a_target": val = cfg_liq_a_target
                                elif item_key == "liq_c1_likes": val = cfg_liq_c1_likes
                                elif item_key == "liq_c1_bonus": val = cfg_liq_c1_bonus
                                elif item_key == "liq_c2_likes": val = cfg_liq_c2_likes
                                elif item_key == "liq_c2_bonus": val = cfg_liq_c2_bonus
                                elif item_key == "liq_c3_likes": val = cfg_liq_c3_likes
                                elif item_key == "liq_c3_bonus": val = cfg_liq_c3_bonus
                                elif item_key == "liq_d_target": val = cfg_liq_d_target
                                elif item_key == "liq_d_bonus": val = cfg_liq_d_bonus
                                elif item_key == "liq_dyn_sens": val = cfg_liq_dyn_sens
                                elif item_key == "liq_dyn_mult": val = cfg_liq_dyn_mult
                                else: val = 0
                                
                                val_str = f"x{val:.1f}" if item_key == "liq_dyn_mult" else (f"1:{val:.1f}" if item_key == "tp_mult" else str(int(val)))
                                
                                # Control numérico con flechas
                                ctrl_rect = pygame.Rect(val_x, val_cy - 15, 120, 30)
                                pygame.draw.rect(screen, (15, 20, 30), ctrl_rect, border_radius=5)
                                pygame.draw.rect(screen, (40, 45, 60), ctrl_rect, 1, border_radius=5)
                                
                                font_val = pygame.font.SysFont("Arial", 18, bold=True)
                                v_surf = font_val.render(val_str, True, (255, 255, 255))
                                screen.blit(v_surf, v_surf.get_rect(center=ctrl_rect.center))
                                
                                # Flechas
                                arrow_font = pygame.font.SysFont("Arial", 18, bold=True)
                                a_color = (0, 180, 220) if is_item_selected else (60, 65, 80)
                                l_arr = arrow_font.render("<", True, a_color)
                                r_arr = arrow_font.render(">", True, a_color)
                                screen.blit(l_arr, (ctrl_rect.left + 8, ctrl_rect.centery - l_arr.get_height() // 2))
                                screen.blit(r_arr, (ctrl_rect.right - 18, ctrl_rect.centery - r_arr.get_height() // 2))
                                
                            elif opt["type"] == "toggle":
                                if item_key == "bot_enabled": val = cfg_bot_enabled
                                elif item_key == "viewers_enabled": val = cfg_viewers_enabled
                                elif item_key == "liq_mode": val = cfg_liq_mode
                                else: val = False
                                
                                t_rect = pygame.Rect(val_x + 50, val_cy - 12, 60, 24)
                                t_color = (38, 166, 154) if val else (239, 83, 80)
                                pygame.draw.rect(screen, t_color, t_rect, border_radius=12)
                                
                                font_t = pygame.font.SysFont("Arial", 14, bold=True)
                                t_surf = font_t.render("ON" if val else "OFF", True, (255, 255, 255))
                                screen.blit(t_surf, t_surf.get_rect(center=t_rect.center))
                                
                            elif opt["type"] == "color":
                                if item_key == "color_bg": val = parse_color(cfg_color_bg)
                                elif item_key == "color_bull": val = parse_color(cfg_color_bull)
                                elif item_key == "color_bear": val = parse_color(cfg_color_bear)
                                else: val = (255, 255, 255)
                                
                                c_rect = pygame.Rect(val_x + 50, val_cy - 12, 60, 24)
                                pygame.draw.rect(screen, val, c_rect, border_radius=6)
                                pygame.draw.rect(screen, (200, 200, 200), c_rect, 1, border_radius=6)
                                
                                # Flechas para color (visual)
                                a_color = (0, 180, 220) if is_item_selected else (60, 65, 80)
                                l_arr = arrow_font.render("<", True, a_color)
                                r_arr = arrow_font.render(">", True, a_color)
                                screen.blit(l_arr, (val_x + 20, val_cy - l_arr.get_height() // 2))
                                screen.blit(r_arr, (val_x + 120, val_cy - r_arr.get_height() // 2))
                                
                            elif opt["type"] == "info":
                                i_surf = font_label.render(opt["value"], True, opt["color"])
                                screen.blit(i_surf, i_surf.get_rect(midright=(row_rect.right - 20, row_rect.centery)))

                            item_y += 65

                    # --- INSTRUCCIONES ABAJO ---
                    font_hint = pygame.font.SysFont("Arial", 16)
                    hint_txt = font_hint.render("Pestañas = Filtrar Eventos    Izq/Der = Cambiar Valores    ENTER = Seleccionar", True, (80, 85, 100))
                    screen.blit(hint_txt, hint_txt.get_rect(center=(SCREEN_W // 2, int(SCREEN_H * 0.94))))
                    # Confirmación de reset
                    if config_confirm_reset:
                        confirm_overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                        confirm_overlay.fill((0, 0, 0, 180))
                        screen.blit(confirm_overlay, (0, 0))
                        confirm_txt = font_cfg_title.render("RESETEAR RANKING?", True, (255, 80, 80))
                        screen.blit(confirm_txt, confirm_txt.get_rect(center=(SCREEN_W // 2, int(SCREEN_H * 0.40))))
                        sub_txt = font_cfg_label.render("Todos los balances vuelven a 10000 FXP", True, (200, 200, 200))
                        screen.blit(sub_txt, sub_txt.get_rect(center=(SCREEN_W // 2, int(SCREEN_H * 0.48))))
                        hint2 = font_cfg_label.render("ENTER = Confirmar | ESC = Cancelar", True, (100, 150, 180))
                        screen.blit(hint2, hint2.get_rect(center=(SCREEN_W // 2, int(SCREEN_H * 0.56))))
                    pygame.display.flip()
                    for cfg_event in pygame.event.get():
                        if cfg_event.type == pygame.QUIT:
                            in_config = False
                            in_menu = False
                            app_running = False
                        elif cfg_event.type == pygame.KEYDOWN:
                            if config_confirm_reset:
                                if cfg_event.key == pygame.K_RETURN:
                                    from database import reset_all_players, DB_PATH
                                    import os
                                    try:
                                        # Verificar existencia de la DB antes de proceder
                                        if os.path.exists(DB_PATH):
                                            reset_all_players()
                                        else:
                                            print(f"[ERROR RESET] Base de datos no encontrada en: {DB_PATH}")
                                    except Exception as e:
                                        print(f"[ERROR RESET] Excepción durante el reinicio: {e}")
                                    
                                    # Restablecer valores locales de forma segura
                                    fxp_balance = 10000
                                    wins = 0
                                    losses = 0
                                    trade_history.clear()
                                    try:
                                        top_viewers = load_top_viewers()
                                    except Exception as e:
                                        print(f"[ERROR RESET] No se pudo recargar el ranking: {e}")
                                        top_viewers = []
                                    
                                    config_confirm_reset = False
                                elif cfg_event.key == pygame.K_ESCAPE:
                                    config_confirm_reset = False
                            else:
                                if cfg_event.key == pygame.K_ESCAPE:
                                    # Guardar config y salir
                                    from database import set_config as _set_cfg
                                    _set_cfg("timer_duration", str(cfg_timer * 1000))
                                    _set_cfg("trade_risk", str(cfg_risk))
                                    _set_cfg("tp_multiplier", str(cfg_tp_mult))
                                    _set_cfg("bot_enabled", "1" if cfg_bot_enabled else "0")
                                    _set_cfg("bot_win_rate", str(cfg_bot_wr / 100.0))
                                    _set_cfg("viewers_enabled", "1" if cfg_viewers_enabled else "0")
                                    _set_cfg("vol_music", str(cfg_vol_music))
                                    _set_cfg("vol_fx", str(cfg_vol_fx))
                                    _set_cfg("max_rr", str(cfg_max_rr))
                                    _set_cfg("liq_interval_min", str(cfg_liq_interval))
                                    _set_cfg("liq_a_target", str(cfg_liq_a_target))
                                    _set_cfg("liq_c1_likes", str(cfg_liq_c1_likes))
                                    _set_cfg("liq_c1_bonus", str(cfg_liq_c1_bonus))
                                    _set_cfg("liq_c2_likes", str(cfg_liq_c2_likes))
                                    _set_cfg("liq_c2_bonus", str(cfg_liq_c2_bonus))
                                    _set_cfg("liq_c3_likes", str(cfg_liq_c3_likes))
                                    _set_cfg("liq_c3_bonus", str(cfg_liq_c3_bonus))
                                    _set_cfg("liq_d_target", str(cfg_liq_d_target))
                                    _set_cfg("liq_d_bonus", str(cfg_liq_d_bonus))
                                    _set_cfg("liq_mode", "1" if cfg_liq_mode else "0")
                                    _set_cfg("liq_dyn_sens", str(cfg_liq_dyn_sens))
                                    _set_cfg("liq_dyn_mult", str(cfg_liq_dyn_mult))
                                    _set_cfg("color_bg", cfg_color_bg)
                                    _set_cfg("color_bull", cfg_color_bull)
                                    _set_cfg("color_bear", cfg_color_bear)
                                    
                                    # Aplicar al juego
                                    TIMER_DURATION = cfg_timer * 1000
                                    TRADE_RISK = cfg_risk
                                    TP_MULTIPLIER = cfg_tp_mult
                                    BOT_ENABLED = cfg_bot_enabled
                                    BOT_WIN_RATE = cfg_bot_wr / 100.0
                                    VIEWER_BOTS_ENABLED = cfg_viewers_enabled
                                    MAX_RR = cfg_max_rr
                                    tiktok_chat.max_rr = cfg_max_rr
                                    LIQUIDITY_EVENT_INTERVAL = cfg_liq_interval * 60000
                                    LIQUIDITY_A_TARGET = cfg_liq_a_target
                                    LIQUIDITY_C_LEVELS = [
                                        (cfg_liq_c1_likes, cfg_liq_c1_bonus),
                                        (cfg_liq_c2_likes, cfg_liq_c2_bonus),
                                        (cfg_liq_c3_likes, cfg_liq_c3_bonus),
                                    ]
                                    LIQUIDITY_D_TARGET = cfg_liq_d_target
                                    LIQUIDITY_D_BONUS = cfg_liq_d_bonus
                                    GLOBAL_COLOR_BG = parse_color(cfg_color_bg)
                                    GLOBAL_COLOR_BULL = parse_color(cfg_color_bull)
                                    GLOBAL_COLOR_BEAR = parse_color(cfg_color_bear)
                                    if sound_game_music is not None:
                                        sound_game_music.set_volume(cfg_vol_music / 100.0)
                                    if music_playing:
                                        pygame.mixer.music.set_volume(cfg_vol_music / 100.0)
                                    if sound_ambient is not None:
                                        sound_ambient.set_volume(cfg_vol_music / 100.0)
                                    
                                    # Aplicar volumen de efectos
                                    fx_vol = cfg_vol_fx / 100.0
                                    for s in [sound_bos, sound_fractal, sound_win, sound_loss, sound_zoom, sound_tick, sound_levelup]:
                                        if s is not None: s.set_volume(fx_vol)
                                    for s in zona_voices + lean_buy_voices + lean_sell_voices + voz_win_voices + voz_loss_voices:
                                        if s is not None: s.set_volume(fx_vol)
                                    in_config = False
                                
                                # Navegación Superior (Módulos 1-4)
                                elif cfg_event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                                    current_mod = cfg_event.key - pygame.K_1
                                    current_tab = 0
                                    current_item_idx = 0
                                
                                # Navegación de Pestañas/Eventos (Teclas Izquierda/Derecha en la barra superior o TAB)
                                elif cfg_event.key == pygame.K_TAB:
                                    mod = config_modules[current_mod]
                                    current_tab = (current_tab + 1) % len(mod["tabs"])
                                    current_item_idx = 0
                                
                                # Navegación entre Módulos con Flechas Izquierda/Derecha si no hay item seleccionado? 
                                # No, el usuario dijo Izq/Der para cambiar valores.
                                
                                # Navegación de Items (Flechas Arriba/Abajo)
                                elif cfg_event.key == pygame.K_DOWN:
                                    mod = config_modules[current_mod]
                                    total_items = len(mod["sections"][0]["items"]) + len(mod["sections"][1]["items"])
                                    if current_mod == 3 and current_tab == 1: # Caso Reset
                                        total_items = 1
                                    if total_items > 0:
                                        current_item_idx = (current_item_idx + 1) % total_items
                                elif cfg_event.key == pygame.K_UP:
                                    mod = config_modules[current_mod]
                                    total_items = len(mod["sections"][0]["items"]) + len(mod["sections"][1]["items"])
                                    if current_mod == 3 and current_tab == 1: # Caso Reset
                                        total_items = 1
                                    if total_items > 0:
                                        current_item_idx = (current_item_idx - 1) % total_items
                                
                                # Cambio de Valores (Flechas Izquierda/Derecha)
                                elif cfg_event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                                    mod = config_modules[current_mod]
                                    all_items = mod["sections"][0]["items"] + mod["sections"][1]["items"]
                                    
                                    if current_item_idx < len(all_items):
                                        item_key = all_items[current_item_idx]
                                        opt = config_items[item_key]
                                        direction = 1 if cfg_event.key == pygame.K_RIGHT else -1
                                        
                                        if opt["type"] == "number":
                                            if item_key == "timer": cfg_timer = max(opt["min"], min(opt["max"], cfg_timer + opt["step"] * direction))
                                            elif item_key == "risk": cfg_risk = max(opt["min"], min(opt["max"], cfg_risk + opt["step"] * direction))
                                            elif item_key == "tp_mult": cfg_tp_mult = max(opt["min"], min(opt["max"], cfg_tp_mult + opt["step"] * direction))
                                            elif item_key == "bot_wr": cfg_bot_wr = max(opt["min"], min(opt["max"], cfg_bot_wr + opt["step"] * direction))
                                            elif item_key == "vol_music": cfg_vol_music = max(opt["min"], min(opt["max"], cfg_vol_music + opt["step"] * direction))
                                            elif item_key == "vol_fx": cfg_vol_fx = max(opt["min"], min(opt["max"], cfg_vol_fx + opt["step"] * direction))
                                            elif item_key == "max_rr": cfg_max_rr = max(opt["min"], min(opt["max"], cfg_max_rr + opt["step"] * direction))
                                            elif item_key == "liq_interval": cfg_liq_interval = max(opt["min"], min(opt["max"], cfg_liq_interval + opt["step"] * direction))
                                            elif item_key == "liq_a_target": cfg_liq_a_target = max(opt["min"], min(opt["max"], cfg_liq_a_target + opt["step"] * direction))
                                            elif item_key == "liq_c1_likes": cfg_liq_c1_likes = max(opt["min"], min(opt["max"], cfg_liq_c1_likes + opt["step"] * direction))
                                            elif item_key == "liq_c1_bonus": cfg_liq_c1_bonus = max(opt["min"], min(opt["max"], cfg_liq_c1_bonus + opt["step"] * direction))
                                            elif item_key == "liq_c2_likes": cfg_liq_c2_likes = max(opt["min"], min(opt["max"], cfg_liq_c2_likes + opt["step"] * direction))
                                            elif item_key == "liq_c2_bonus": cfg_liq_c2_bonus = max(opt["min"], min(opt["max"], cfg_liq_c2_bonus + opt["step"] * direction))
                                            elif item_key == "liq_c3_likes": cfg_liq_c3_likes = max(opt["min"], min(opt["max"], cfg_liq_c3_likes + opt["step"] * direction))
                                            elif item_key == "liq_c3_bonus": cfg_liq_c3_bonus = max(opt["min"], min(opt["max"], cfg_liq_c3_bonus + opt["step"] * direction))
                                            elif item_key == "liq_d_target": cfg_liq_d_target = max(opt["min"], min(opt["max"], cfg_liq_d_target + opt["step"] * direction))
                                            elif item_key == "liq_d_bonus": cfg_liq_d_bonus = max(opt["min"], min(opt["max"], cfg_liq_d_bonus + opt["step"] * direction))
                                            elif item_key == "liq_dyn_sens": cfg_liq_dyn_sens = max(opt["min"], min(opt["max"], cfg_liq_dyn_sens + opt["step"] * direction))
                                            elif item_key == "liq_dyn_mult": cfg_liq_dyn_mult = max(opt["min"], min(opt["max"], cfg_liq_dyn_mult + opt["step"] * direction))
                                        
                                        elif opt["type"] == "toggle":
                                            if item_key == "bot_enabled": cfg_bot_enabled = not cfg_bot_enabled
                                            elif item_key == "viewers_enabled": cfg_viewers_enabled = not cfg_viewers_enabled
                                            elif item_key == "liq_mode": cfg_liq_mode = not cfg_liq_mode
                                            
                                        elif opt["type"] == "color":
                                            # Selector rápido de presets
                                            presets = []
                                            if item_key == "color_bg": presets = COLOR_PRESETS_BG
                                            elif item_key == "color_bull": presets = COLOR_PRESETS_BULL
                                            elif item_key == "color_bear": presets = COLOR_PRESETS_BEAR
                                            
                                            if presets:
                                                curr_rgb = parse_color(cfg_color_bg if item_key == "color_bg" else (cfg_color_bull if item_key == "color_bull" else cfg_color_bear))
                                                try:
                                                    idx = presets.index(curr_rgb)
                                                    new_idx = (idx + direction) % len(presets)
                                                except:
                                                    new_idx = 0
                                                
                                                new_rgb = presets[new_idx]
                                                new_val = f"{new_rgb[0]},{new_rgb[1]},{new_rgb[2]}"
                                                if item_key == "color_bg": cfg_color_bg = new_val
                                                elif item_key == "color_bull": cfg_color_bull = new_val
                                                elif item_key == "color_bear": cfg_color_bear = new_val

                                # Selección / Acción (ENTER)
                                elif cfg_event.key == pygame.K_RETURN:
                                    mod = config_modules[current_mod]
                                    all_items = mod["sections"][0]["items"] + mod["sections"][1]["items"]
                                    
                                    # Caso especial: Reset Ranking
                                    if current_mod == 3 and current_tab == 1:
                                        config_confirm_reset = True
                                        continue

                                    if current_item_idx < len(all_items):
                                        item_key = all_items[current_item_idx]
                                        opt = config_items[item_key]
                                        
                                        if opt["type"] == "color":
                                            curr_val = cfg_color_bg if item_key == "color_bg" else (cfg_color_bull if item_key == "color_bull" else cfg_color_bear)
                                            new_rgb = pick_color(parse_color(curr_val))
                                            if new_rgb:
                                                new_val = f"{new_rgb[0]},{new_rgb[1]},{new_rgb[2]}"
                                                if item_key == "color_bg": cfg_color_bg = new_val
                                                elif item_key == "color_bull": cfg_color_bull = new_val
                                                elif item_key == "color_bear": cfg_color_bear = new_val
                        
                        elif cfg_event.type == pygame.MOUSEBUTTONDOWN and cfg_event.button == 1:
                            mx, my = cfg_event.pos
                            
                            # Click en Pestañas (Top Right)
                            tab_x = int(SCREEN_W * 0.95)
                            mod = config_modules[current_mod]
                            for i, tname in enumerate(reversed(mod["tabs"])):
                                t_idx = len(mod["tabs"]) - 1 - i
                                t_surf = font_tabs.render(tname, True, (255, 255, 255))
                                t_rect = t_surf.get_rect(midright=(tab_x, int(SCREEN_H * 0.08)))
                                click_rect = t_rect.inflate(30, 15)
                                if click_rect.collidepoint(mx, my):
                                    current_tab = t_idx
                                    current_item_idx = 0
                                    break
                                tab_x -= t_rect.width + 45
                            
                            # Click en Módulos (Top Left)
                            mod_x = int(SCREEN_W * 0.05)
                            for i, m in enumerate(config_modules):
                                # Aproximación del área del título/tag para click (Módulo 1, 2, 3, 4)
                                m_title_surf = font_title.render(m["title"], True, (255, 255, 255))
                                m_rect = m_title_surf.get_rect(topleft=(int(SCREEN_W * 0.05), int(SCREEN_H * 0.06)))
                                if m_rect.inflate(20, 20).collidepoint(mx, my):
                                    current_mod = (current_mod + 1) % len(config_modules)
                                    current_tab = 0
                                    current_item_idx = 0
                                    break
                            
                            # Click en Items para seleccionar
                            all_items = mod["sections"][0]["items"] + mod["sections"][1]["items"]
                            panel_y = int(SCREEN_H * 0.16)
                            panel_w = int(SCREEN_W * 0.44)
                            
                            for s_idx, section in enumerate(mod["sections"]):
                                px = int(SCREEN_W * 0.05) if s_idx == 0 else int(SCREEN_W * 0.51)
                                item_y = panel_y + 80
                                for i_idx, item_key in enumerate(section["items"]):
                                    row_rect = pygame.Rect(px + 20, item_y, panel_w - 40, 55)
                                    if row_rect.collidepoint(mx, my):
                                        if s_idx == 0:
                                            current_item_idx = i_idx
                                        else:
                                            current_item_idx = i_idx + len(mod["sections"][0]["items"])
                                        
                                        opt = config_items[item_key]
                                        if opt["type"] == "toggle":
                                            if item_key == "bot_enabled": cfg_bot_enabled = not cfg_bot_enabled
                                            elif item_key == "viewers_enabled": cfg_viewers_enabled = not cfg_viewers_enabled
                                            elif item_key == "liq_mode": cfg_liq_mode = not cfg_liq_mode
                                        break
                                    item_y += 65

                    pygame.display.flip()

                # Al salir de la configuración, volver al menú principal
                pygame.event.clear()
                pygame.time.wait(200)
                menu_click_btn = None

        # --- DIBUJAR MENÚ PRINCIPAL ---
        # Botones del menú principal
        btn_w = int(SCREEN_W * 0.28)
        btn_h = int(SCREEN_H * 0.08)
        btn_iniciar = pygame.Rect(int(SCREEN_W * (681/1366)) - btn_w // 2, int(SCREEN_H * (341/768)) - btn_h // 2, btn_w, btn_h)
        btn_ranking = pygame.Rect(int(SCREEN_W * (686/1366)) - btn_w // 2, int(SCREEN_H * (476/768)) - btn_h // 2, btn_w, btn_h)
        btn_config = pygame.Rect(int(SCREEN_W * (952/1920)) - btn_w // 2, int(SCREEN_H * (862/1080)) - btn_h // 2, btn_w, btn_h)
        
        # Dibujar efecto click (oscurecer en el centro del botón)
        buttons = [("iniciar", btn_iniciar), ("ranking", btn_ranking), ("config", btn_config)]
        for btn_name, btn_rect in buttons:
            if menu_click_btn == btn_name:
                dark_surface = pygame.Surface((btn_rect.width, btn_rect.height), pygame.SRCALPHA)
                dark_surface.fill((0, 0, 0, 80))
                screen.blit(dark_surface, (btn_rect.x, btn_rect.y))
        pygame.display.flip()

    # --- GAME LOOP ---
    running = True
    # === GAME LOOP ===
    while running and app_running:
        clock.tick(60)
        current_time = pygame.time.get_ticks()
        curr_ticks = current_time
        
        # --- DEFINICIÓN DE VARIABLES DE DISEÑO (LAYOUT) ---
        guide_w = int(SCREEN_W * 0.18)
        guide_h = int(SCREEN_H * 0.62)
        guide_x = int(SCREEN_W * 0.80)
        guide_y = int(SCREEN_H * 0.32)
        tel_box_x, tel_box_y = guide_x - 6, int(SCREEN_H * 0.02)
        tel_box_w, tel_box_h = guide_w, 80

        screen.fill(GLOBAL_COLOR_BG)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    # Diálogo de pausa: ¿Volver al menú o cerrar?
                    paused = True
                    pygame.event.clear()
                    pygame.time.wait(100)
                    while paused:
                        # Fondo oscuro semi-transparente
                        pause_overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                        pause_overlay.fill((0, 0, 0, 150))
                        screen.blit(pause_overlay, (0, 0))
                        # Texto
                        pause_title = font_timer.render("PAUSA", True, (255, 255, 0))
                        screen.blit(pause_title, pause_title.get_rect(center=(SCREEN_W // 2, int(SCREEN_H * 0.30))))
                        # Botones
                        btn_resume = pygame.Rect(SCREEN_W // 2 - 140, int(SCREEN_H * 0.42), 280, 50)
                        btn_menu = pygame.Rect(SCREEN_W // 2 - 140, int(SCREEN_H * 0.52), 280, 50)
                        btn_quit = pygame.Rect(SCREEN_W // 2 - 140, int(SCREEN_H * 0.62), 280, 50)
                        pygame.draw.rect(screen, (38, 166, 154), btn_resume, border_radius=8)
                        pygame.draw.rect(screen, (100, 100, 100), btn_menu, border_radius=8)
                        pygame.draw.rect(screen, (239, 83, 80), btn_quit, border_radius=8)
                        res_txt = font_btn.render("CONTINUAR", True, (255, 255, 255))
                        menu_txt = font_btn.render("VOLVER AL MENU", True, (255, 255, 255))
                        quit_txt = font_btn.render("CERRAR JUEGO", True, (255, 255, 255))
                        screen.blit(res_txt, res_txt.get_rect(center=btn_resume.center))
                        screen.blit(menu_txt, menu_txt.get_rect(center=btn_menu.center))
                        screen.blit(quit_txt, quit_txt.get_rect(center=btn_quit.center))
                        pygame.display.flip()
                        for p_event in pygame.event.get():
                            if p_event.type == pygame.QUIT:
                                paused = False
                                running = False
                            elif p_event.type == pygame.KEYDOWN:
                                if p_event.key == pygame.K_ESCAPE:
                                    paused = False  # Continuar
                            elif p_event.type == pygame.MOUSEBUTTONDOWN and p_event.button == 1:
                                pmx, pmy = p_event.pos
                                if btn_resume.collidepoint(pmx, pmy):
                                    paused = False
                                elif btn_menu.collidepoint(pmx, pmy):
                                        paused = False
                                        running = False
                                        if sound_game_music is not None:
                                            sound_game_music.stop()
                                elif btn_quit.collidepoint(pmx, pmy):
                                    paused = False
                                    running = False
                                    app_running = False
                elif event.key == pygame.K_PLUS or event.key == pygame.K_KP_PLUS or event.key == pygame.K_EQUALS:
                    TIMER_DURATION = min(30000, TIMER_DURATION + 1000)
                elif event.key == pygame.K_MINUS or event.key == pygame.K_KP_MINUS:
                    TIMER_DURATION = max(3000, TIMER_DURATION - 1000)
                elif event.key == pygame.K_l:
                    # Simular likes con la tecla L (solo para pruebas sin estar en vivo)
                    simulated_likes += SIMULATED_LIKES_PER_PRESS
                    print(f"[LIKES SIMULADOS] +{SIMULATED_LIKES_PER_PRESS} (total sim: {simulated_likes})")
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                print(f"[CLICK] x={mx}, y={my}")
        # --- LOGICA DEL TIMER ---
        # --- LOGICA DEL TIMER ---
        if zone_frozen:
            elapsed = current_time - zone_timer_start
            # Delay de voz: el timer no cuenta hasta que la voz termine (4 seg aprox)
            VOICE_DELAY = 4000
            timer_elapsed = max(0, elapsed - VOICE_DELAY)
            if timer_elapsed >= TIMER_DURATION:
                # Timer terminó, reanudar gráfico
                # Si nadie eligió, el bot decide automáticamente
                if not trade_decided and BOT_ENABLED and active_trade is None:
                    can_trade = True
                    # Verificar cooldown
                    if current_time - bot_last_trade_time < BOT_COOLDOWN and bot_last_trade_time > 0:
                        can_trade = False
                    # Verificar máx ops/hora
                    if current_time - bot_hour_start > 3600000:
                        bot_ops_this_hour = 0
                        bot_hour_start = current_time
                    if bot_ops_this_hour >= BOT_MAX_OPS_HOUR:
                        can_trade = False
                    if can_trade and zone_detected is not None and zone_detected.get("source") == "EXTREMO":
                        entry_price = current_candle["close"]
                        # Bot LEAN FX: DUAL TRADE (BUY & SELL simultáneos)
                        # Cada bando se crea como un objeto independiente dentro de 'groups'
                        base_sl_dist = max(0.01, (zone_detected["high"] - zone_detected["low"]) + SL_BUFFER)
                        
                        active_trade = {
                            "entry": entry_price,
                            "entry_index": len(candles),
                            "groups": {
                                "BUY": {
                                    "entry": entry_price,
                                    "entry_index": len(candles),
                                    "dir": "BUY",
                                    "tipo": "BUY",
                                    "sl": entry_price - base_sl_dist,
                                    "rr": 1.0, # Base RR
                                    "levels": [
                                        {"rr": float(rr), "tp": entry_price + base_sl_dist * rr, "resolved": False, "users": []}
                                        for rr in range(1, MAX_RR + 1)
                                    ],
                                    "resolved": False,
                                    "flash": None,
                                    "max_rr": float(MAX_RR),
                                    "be_armed": False
                                },
                                "SELL": {
                                    "entry": entry_price,
                                    "entry_index": len(candles),
                                    "dir": "SELL",
                                    "tipo": "SELL",
                                    "sl": entry_price + base_sl_dist,
                                    "rr": 1.0, # Base RR
                                    "levels": [
                                        {"rr": float(rr), "tp": entry_price - base_sl_dist * rr, "resolved": False, "users": []}
                                        for rr in range(1, MAX_RR + 1)
                                    ],
                                    "resolved": False,
                                    "flash": None,
                                    "max_rr": float(MAX_RR),
                                    "be_armed": False
                                }
                            }
                        }
                        
                        # Bot decision para el sesgo y audios
                        if zone_detected["type"] == "ALCISTA":
                            bot_decision = "BUY"
                        else:
                            bot_decision = "SELL"
                        
                        # El sesgo artificial ha sido eliminado para un mercado 100% natural
                        bot_last_trade_time = current_time
                        bot_ops_this_hour += 1
                        trade_decided = True
                        play_sound(sound_bos)
                        # Reproducir audio de apertura
                        audio_manager.play("apertura.mp3", pausar_mercado=True)
                        # Voz LEAN FX anuncia su trade
                        if bot_decision == "BUY" and lean_buy_voices:
                            audio_manager.play(f"LEAN_BUY_{random.randint(1, 3)}.mp3")
                        elif bot_decision == "SELL" and lean_sell_voices:
                            audio_manager.play(f"LEAN_SELL_{random.randint(1, 3)}.mp3")
                zone_frozen = False
                # Crear o actualizar trade de viewers ahora que terminó el timer
                if viewer_votes and zone_detected is not None:
                    entry_price = current_candle["close"]
                    base_sl_distance = max(0.01, (zone_detected["high"] - zone_detected["low"]) + SL_BUFFER)
                    
                    # 1. Validación de RR Máximo (Límite de Configuración)
                    for v in viewer_votes:
                        v["rr"] = min(float(v.get("rr", 1.0)), float(MAX_RR))

                    if viewer_trade_active is None:
                        if active_trade is not None:
                            viewer_trade_active = active_trade
                        else:
                            viewer_trade_active = {
                                "groups": {},
                                "sl_dist": base_sl_distance,
                                "entry": entry_price,
                                "entry_index": len(candles)
                            }
                            audio_manager.play("apertura.mp3", pausar_mercado=True)
                    
                    # 2. Evitar Duplicidad de Cajas (Consolidar en una sola por Bando)
                    groups = viewer_trade_active["groups"]
                    v_sl_dist = viewer_trade_active.get("sl_dist", base_sl_distance)
                    
                    for v in viewer_votes:
                        g_dir = v["vote"]
                        rr = round(float(v["rr"]), 1)
                        # group_id es ahora solo el bando (BUY o SELL) para asegurar UNICIDAD DE CAJA
                        group_id = g_dir
                        
                        if group_id not in groups:
                            # Cada posición de viewer es independiente con su propia entrada
                            tp_price = entry_price + (v_sl_dist * rr) if g_dir == "BUY" else entry_price - (v_sl_dist * rr)
                            sl_price = entry_price - v_sl_dist if g_dir == "BUY" else entry_price + v_sl_dist
                            
                            groups[group_id] = {
                                "dir": g_dir,
                                "tipo": g_dir,
                                "entry": entry_price,
                                "entry_index": len(candles),
                                "sl": sl_price,
                                "rr": rr,
                                "levels": [
                                    {"rr": rr, "tp": tp_price, "users": [v["name"]], "resolved": False}
                                ],
                                "resolved": False,
                                "flash": None,
                                "max_rr": rr,
                                "be_armed": False,
                            }
                        else:
                            # Si el bando ya existe, añadimos este RR como un nuevo nivel de TP si no existe
                            # O sumamos el usuario al nivel de RR correspondiente
                            found_lvl = False
                            for lvl in groups[group_id]["levels"]:
                                if abs(lvl["rr"] - rr) < 0.05:
                                    if v["name"] not in lvl["users"]:
                                        lvl["users"].append(v["name"])
                                    found_lvl = True
                                    break
                            
                            if not found_lvl:
                                tp_price = entry_price + (v_sl_dist * rr) if g_dir == "BUY" else entry_price - (v_sl_dist * rr)
                                groups[group_id]["levels"].append({
                                    "rr": rr, "tp": tp_price, "users": [v["name"]], "resolved": False
                                })
                                # Actualizar max_rr para que la caja se dibuje hasta el nivel más lejano
                                groups[group_id]["max_rr"] = max(groups[group_id]["max_rr"], rr)
                    
                    # Si no hay votos después de procesar, cajas por defecto (una por bando)
                    if not groups:
                        for d in ["BUY", "SELL"]:
                            gid = d
                            rr_def = min(2.0, float(MAX_RR)) # RR por defecto
                            tp = entry_price + (v_sl_dist * rr_def) if d == "BUY" else entry_price - (v_sl_dist * rr_def)
                            sl = entry_price - v_sl_dist if d == "BUY" else entry_price + v_sl_dist
                            groups[gid] = {
                                "dir": d,
                                "tipo": d,
                                "entry": entry_price,
                                "entry_index": len(candles),
                                "sl": sl,
                                "rr": rr_def,
                                "resolved": False,
                                "flash": None,
                                "max_rr": rr_def,
                                "be_armed": False,
                                "levels": [{"rr": rr_def, "tp": tp, "users": [], "resolved": False}]
                            }

                    # Actualizar el contador superior con todos los votantes acumulados
                    all_voters = []
                    for g in groups.values():
                        for uname in g["levels"][0]["users"]:
                            all_voters.append({"name": uname, "vote": g["dir"]})
                    viewer_votes_display = all_voters
                    
                    # LIMPIAR VOTOS PROCESADOS para evitar duplicidad en el siguiente ciclo
                    viewer_votes = []
                
                zone_detected = None
                trade_decided = False
                last_tick_second = -1
        # --- Descongelar voice freeze (OBSOLETO, ahora lo maneja AudioManager) ---

        # --- SISTEMA DE LIQUIDEZ POR LIKES ---
        if (game_started and liquidity_event_active is None and not zone_frozen
                and active_trade is None and viewer_trade_active is None and not audio_manager.is_playing()
                and current_time - liquidity_last_trigger >= LIQUIDITY_EVENT_INTERVAL):
            liquidity_last_trigger = current_time
            event_type = LIQUIDITY_EVENT_TYPES[liquidity_event_index % len(LIQUIDITY_EVENT_TYPES)]
            liquidity_event_index += 1
            simulated_likes = 0
            if tiktok_chat is not None:
                tiktok_chat.reset_like_count()
            liquidity_particles = [
                {"x": random.uniform(0, SCREEN_W), "y": random.uniform(0, SCREEN_H),
                 "speed": random.uniform(0.4, 1.4), "size": random.randint(2, 5),
                 "alpha": random.randint(60, 160)}
                for _ in range(35)
            ]
            play_sound(sound_liquidity_start)
            if event_type == "A":
                liquidity_event_active = {"type": "A", "start_time": current_time}
            elif event_type == "C":
                liquidity_event_active = {"type": "C", "start_time": current_time, "reached_level": -1}
            elif event_type == "D":
                liquidity_event_active = {"type": "D", "start_time": current_time}
            
            # Fase 2: Registrar evento en Analytics
            if current_session_id is not None:
                add_session_event(current_session_id, f"LIQUIDITY_{event_type}")

        if liquidity_event_active is not None:
            _ev = liquidity_event_active
            _elapsed = current_time - _ev["start_time"]
            _real_likes = tiktok_chat.get_like_count() if tiktok_chat is not None else 0
            _current_likes = _real_likes + simulated_likes

            if _ev["type"] == "A":
                # Evento bloqueante: nada de trading hasta juntar la meta o hasta el timeout de seguridad
                if _current_likes >= LIQUIDITY_A_TARGET:
                    play_sound(sound_liquidity_success)
                    liquidity_event_active = None
                    last_candle_time = current_time
                elif _elapsed >= LIQUIDITY_A_TIMEOUT:
                    liquidity_event_active = None
                    last_candle_time = current_time
            elif _ev["type"] == "C":
                # Rondas por nivel: se paga el nivel mas alto alcanzado, se reanuda siempre al terminar el tiempo
                for lvl_idx, (lvl_likes, lvl_bonus) in enumerate(LIQUIDITY_C_LEVELS):
                    if _current_likes >= lvl_likes and lvl_idx > _ev["reached_level"]:
                        _ev["reached_level"] = lvl_idx
                        _ev["flash_start"] = current_time  # Para el flash visual del nivel nuevo
                        play_sound(sound_like_milestone)
                if _elapsed >= LIQUIDITY_C_DURATION:
                    if _ev["reached_level"] >= 0:
                        _bonus = LIQUIDITY_C_LEVELS[_ev["reached_level"]][1]
                        add_bonus_to_all_players(_bonus)
                        # Fase 2: Analytics FXP
                        if current_session_id is not None:
                            add_session_fxp(current_session_id, _bonus)
                        top_viewers = load_top_viewers()
                        play_sound(sound_liquidity_success)
                    liquidity_event_active = None
                    last_candle_time = current_time
            elif _ev["type"] == "D":
                # Barra unica: si se llena antes de que termine el tiempo, bono y corta ahi
                if _current_likes >= LIQUIDITY_D_TARGET:
                    add_bonus_to_all_players(LIQUIDITY_D_BONUS)
                    # Fase 2: Analytics FXP
                    if current_session_id is not None:
                        add_session_fxp(current_session_id, LIQUIDITY_D_BONUS)
                    top_viewers = load_top_viewers()
                    play_sound(sound_liquidity_success)
                    liquidity_event_active = None
                    last_candle_time = current_time
                elif _elapsed >= LIQUIDITY_D_DURATION:
                    liquidity_event_active = None
                    last_candle_time = current_time
        # --- PLAYLIST: pasar a siguiente canción cuando termina ---
        if music_playing and not pygame.mixer.music.get_busy():
            music_current_index = (music_current_index + 1) % len(music_playlist)
            try:
                pygame.mixer.music.load(music_playlist[music_current_index])
                pygame.mixer.music.play()
            except:
                pass
        # --- VOZ ENTRE TRADES (mantener atención) ---
        if game_started and not zone_frozen and not audio_manager.is_playing() and active_trade is None and viewer_trade_active is None:
            if not hasattr(pygame, '_idle_voice_last'):
                pygame._idle_voice_last = current_time
            if current_time - pygame._idle_voice_last > 35000:  # Cada 35 segundos
                pygame._idle_voice_last = current_time
                idle_voices = []
                for i in range(1, 8):
                    sv = load_sound(f"IDLE_VOZ_{i}.mp3")
                    if sv is not None:
                        idle_voices.append(sv)
                if idle_voices:
                    audio_manager.play(f"IDLE_VOZ_{random.randint(1, 14)}.mp3")

                    
        # --- MOVER PRECIO (solo si NO está pausado, NO está congelado, NO hay voice freeze, NO hay evento de liquidez y NO hay audio sonando) ---
        if audio_manager.juego_pausado:
            # Liberar la pausa forzada si el audio terminó y pasó el tiempo de gracia
            if not audio_manager.is_playing() and current_time - voice_freeze_start > 2000:
                audio_manager.set_force_pause(False)
            pass # Pausa absoluta: el precio no se mueve si hay audio sonando
        elif not zone_frozen and liquidity_event_active is None:
            if current_time - last_tick_time >= TICK_DELAY:
                # --- MOVER PRECIO (EURUSD Forex Style) ---
                # Step size basado en el estado del mercado
                if market_state == "retracement":
                    step_size = random.uniform(0.05, 0.15) * trend_strength
                else:
                    step_size = random.uniform(0.12, 0.35) * trend_strength
                
                # Sesgo dinámico basado en Ondas de Elliott
                current_candle_stretch = abs(current_candle["close"] - current_candle["open"])
                max_natural_stretch = trend_strength * 1.2
                stretch_factor = min(1.0, current_candle_stretch / max_natural_stretch)
                
                # Determinar dirección actual de la sub-onda
                if market_state == "impulse":
                    sub_wave_dir = trend_dir
                elif market_state == "retracement":
                    sub_wave_dir = -trend_dir
                else: 
                    sub_wave_dir = random.choice([-1, 1])
                
                # Probabilidad base según el estado (Ciclos Dinámicos)
                base_bias = 0.82 if market_state == "impulse" else 0.65
                
                dynamic_bias = base_bias - (stretch_factor * 0.35)
                
                if random.random() < dynamic_bias:
                    # Movimiento a favor: variar velocidad
                    tick_move = step_size * random.uniform(0.7, 1.3) * sub_wave_dir
                else:
                    # Movimiento en contra: retroceso de tick (ruido de mercado)
                    tick_move = -step_size * random.uniform(0.6, 1.2) * sub_wave_dir
                
                current_candle["close"] += tick_move
                current_candle["high"] = max(current_candle["high"], current_candle["close"])
                current_candle["low"] = min(current_candle["low"], current_candle["close"])
                last_tick_time = current_time
                # --- EVALUAR TRADE ACTIVO (DUAL INDEPENDIENTE) ---
                # Usa HIGH/LOW reales de la vela: SL/TP no dependen del cierre.
                if active_trade is not None and "groups" in active_trade:
                    c_high = current_candle.get("high")
                    c_low = current_candle.get("low")
                    current_time = pygame.time.get_ticks()

                    if c_high is not None and c_low is not None:
                        to_remove = []

                        for g_dir, grp in list(active_trade["groups"].items()):
                            if grp.get("resolved") or active_trade.get("cerrada"):
                                continue

                            # 1. SL tiene prioridad absoluta dentro del grupo.
                            sl_hit = (g_dir == "BUY" and c_low <= grp["sl"]) or (g_dir == "SELL" and c_high >= grp["sl"])

                            if sl_hit:
                                grp["resolved"] = True
                                grp["_closed_by"] = "SL"
                                for lvl in grp.get("levels", []):
                                    lvl["resolved"] = True
                                    lvl["_skipped_by_sl"] = True

                                grp["flash"] = {"start": current_time, "color": GLOBAL_COLOR_BEAR}
                                SL_HIT_AUDIO_FLAG = True
                                audio_manager.set_force_pause(True)
                                audio_manager.play(f"{g_dir.lower().replace('sell', 'sel')}_sl.mp3", pausar_mercado=True)
                                voice_freeze_start = current_time
                                trade_loss(TRADE_RISK, 1.0)
                                trade_history.append({"type": g_dir, "result": "LOSS", "pnl": -TRADE_RISK})

                                if g_dir == bot_decision:
                                    flash_active = True
                                    flash_start_time = current_time
                                    flash_color = GLOBAL_COLOR_BEAR
                                    flash_text = "-100 FXP"
                                    total_operations += 1
                                    if voz_loss_voices and viewer_trade_active is None:
                                        audio_manager.play(f"VOZ_LOSS_{random.randint(1, 7)}.mp3")
                                continue

                            # 2. TP: HIGH para BUY, LOW para SELL.
                            for lvl in grp.get("levels", []):
                                if lvl.get("resolved") or lvl.get("_skipped_by_sl"):
                                    continue

                                tp_hit = (g_dir == "BUY" and c_high >= lvl["tp"]) or (g_dir == "SELL" and c_low <= lvl["tp"])
                                if not tp_hit:
                                    continue

                                lvl["resolved"] = True
                                rr = lvl["rr"]
                                grp["flash"] = {"start": current_time, "color": GLOBAL_COLOR_BULL}
                                gain = TRADE_RISK * rr
                                trade_win(gain, rr)
                                trade_history.append({"type": g_dir, "result": "WIN", "pnl": gain})

                                max_configured_rr = grp.get("max_rr", MAX_RR)
                                if rr >= max_configured_rr:
                                    grp["resolved"] = True
                                    grp["_closed_by"] = "TP"
                                    close_position(active_trade, g_dir, grp, lvl, is_viewer=False)
                                    voice_freeze_start = current_time
                                    break

                                audio_manager.set_force_pause(True)
                                audio_manager.play(f"{g_dir.lower().replace('sell', 'sel')}_tp{int(rr)}.mp3", pausar_mercado=True)
                                voice_freeze_start = current_time
                                if g_dir == bot_decision:
                                    flash_active = True
                                    flash_start_time = current_time
                                    flash_color = GLOBAL_COLOR_BULL
                                    flash_text = f"+{int(rr) * 100} FXP"
                                    total_operations += 1

                            # Un grupo solo termina cuando todos sus niveles fueron resueltos.
                            if not grp.get("resolved") and grp.get("levels"):
                                if all(lvl.get("resolved") or lvl.get("_skipped_by_sl") for lvl in grp["levels"]):
                                    grp["resolved"] = True
                                    grp["_closed_by"] = "TP"

                        # 3. Limpieza independiente de BUY/SELL después del flash.
                        for g_dir, grp in list(active_trade["groups"].items()):
                            if not grp.get("resolved"):
                                continue
                            flash = grp.get("flash")
                            if flash is None or current_time - flash.get("start", current_time) > 1500:
                                to_remove.append(g_dir)

                        for g_dir in to_remove:
                            active_trade["groups"].pop(g_dir, None)

                        if active_trade is not None and not active_trade["groups"]:
                            active_trade = None
                            viewer_votes_display = []
                            trade_decided = False

                # --- DETECTAR SI PRECIO LLEGA A UNA ZONA (solo 1 vez por zona) ---
                if active_trade is None and not zone_frozen and viewer_trade_active is None and not audio_manager.is_playing() and liquidity_event_active is None:
                    price_now = current_candle["close"]
                    # Verificar Order Block activo
                    if active_ob is not None:
                        zone_id = f"ob_{active_ob['index']}"
                        # También verificar por precio (evitar reactivar zona similar)
                        zone_price_id = f"ob_{int(active_ob['high']*10)}_{int(active_ob['low']*10)}"
                        if zone_id not in zones_mitigated and zone_price_id not in zones_mitigated and active_ob["low"] <= price_now <= active_ob["high"]:
                            zone_frozen = True
                            zone_timer_start = current_time
                            zone_detected = {"high": active_ob["high"], "low": active_ob["low"], "type": active_ob["type"], "source": "EXTREMO"}
                            zones_mitigated.add(zone_id)
                            zones_mitigated.add(zone_price_id)
                            zones_mitigated_info[zone_id] = {"index": len(candles), "bos_count": 0}
                            zones_mitigated_info[zone_price_id] = {"index": len(candles), "bos_count": 0}
                            # Si el Decisional se superpone, mitigarlo también (no activar 2 entradas)
                            if active_decisional is not None:
                                dec_id = f"dec_{active_decisional['index']}"
                                dec_price_id = f"dec_{int(active_decisional['high']*10)}_{int(active_decisional['low']*10)}"
                                if active_decisional["low"] <= price_now <= active_decisional["high"]:
                                    zones_mitigated.add(dec_id)
                                    zones_mitigated.add(dec_price_id)
                                    zones_mitigated_info[dec_id] = {"index": len(candles), "bos_count": 0}
                                    zones_mitigated_info[dec_price_id] = {"index": len(candles), "bos_count": 0}
                            # Reproducir voz aleatoria de zona
                            if zona_voices:
                                vi = random.randint(0, len(zona_voices) - 1)
                                while vi == zona_voice_last and len(zona_voices) > 1:
                                    vi = random.randint(0, len(zona_voices) - 1)
                                zona_voice_last = vi
                                audio_manager.play(f"ZONA_VOZ_{vi+1}.mp3")
                    # Verificar Decisional
                    if not zone_frozen and active_decisional is not None:
                        zone_id = f"dec_{active_decisional['index']}"
                        zone_price_id = f"dec_{int(active_decisional['high']*10)}_{int(active_decisional['low']*10)}"
                        if zone_id not in zones_mitigated and zone_price_id not in zones_mitigated and active_decisional["low"] <= price_now <= active_decisional["high"]:
                            zone_frozen = True
                            zone_timer_start = current_time
                            zone_detected = {"high": active_decisional["high"], "low": active_decisional["low"], "type": active_decisional["type"], "source": "DECISIONAL"}
                            zones_mitigated.add(zone_id)
                            zones_mitigated.add(zone_price_id)
                            zones_mitigated_info[zone_id] = {"index": len(candles), "bos_count": 0}
                            zones_mitigated_info[zone_price_id] = {"index": len(candles), "bos_count": 0}
                            # Reproducir voz aleatoria de zona
                            if zona_voices:
                                vi = random.randint(0, len(zona_voices) - 1)
                                while vi == zona_voice_last and len(zona_voices) > 1:
                                    vi = random.randint(0, len(zona_voices) - 1)
                                zona_voice_last = vi
                                audio_manager.play(f"ZONA_VOZ_{vi+1}.mp3")
                    # FVG NO se opera por ahora (solo se dibuja)
                    # if not zone_frozen and active_fvg is not None:
                    #     zone_id = f"fvg_{active_fvg['index']}"
                    #     if zone_id not in zones_mitigated and active_fvg["low"] <= price_now <= active_fvg["high"]:
                    #         zone_frozen = True
                    #         zone_timer_start = current_time
                    #         zone_detected = {"high": active_fvg["high"], "low": active_fvg["low"], "type": active_fvg["type"]}
                    #         zones_mitigated.add(zone_id)
        # --- VIEWERS: TikTok Live real O bots simulados ---
        if game_started and zone_frozen and not getattr(pygame, '_viewers_voted_this_zone', False):
            pygame._viewers_voted_this_zone = True
            # Abrir votación en TikTok
            tiktok_chat.open_voting()

        # Recoger votos de TikTok (se actualizan en tiempo real)
        if game_started and zone_frozen and tiktok_chat.is_connected():
            tiktok_votes = tiktok_chat.get_votes()
            if tiktok_votes:
                # Usar votos reales de TikTok
                viewer_votes = []
                for tv in tiktok_votes:
                    viewer_votes.append({"name": tv["name"], "vote": tv["vote"], "rr": tv.get("rr", 1.0)})
                    # Fase 2: Registrar voto en Analytics
                    if current_session_id is not None:
                        add_session_vote(current_session_id, 'SUBE' if tv["vote"] == "BUY" else 'BAJA')
                    # Crear jugador en DB si no existe
                    from database import get_player
                    if not get_player(tv["name"]):
                        create_player(tv["name"])
                viewer_votes_display = viewer_votes.copy()
        # Bots de backup (solo si TikTok no está conectado o no hay votos reales)
        elif VIEWER_BOTS_ENABLED and game_started and zone_frozen and not tiktok_chat.is_connected():
            if not viewer_votes:
                num_voters = random.randint(2, 4)
                all_viewer_names = [v["name"] for v in load_top_viewers()]
                if all_viewer_names:
                    voters = random.sample(all_viewer_names, min(num_voters, len(all_viewer_names)))
                    viewer_votes = []
                    for chosen in voters:
                        vote = random.choice(["BUY", "SELL"])
                        viewer_votes.append({"name": chosen, "vote": vote, "rr": random.choice([1.0, 2.0, 3.0])})
                    viewer_votes_display = viewer_votes.copy()
        # Cerrar votación cuando se descongela
        if not zone_frozen:
            pygame._viewers_voted_this_zone = False
            tiktok_chat.close_voting()
        # --- RESOLVER TRADE DE VIEWERS (por grupo BUY/SELL y nivel R:R) ---
        if viewer_trade_active is not None and not zone_frozen and viewer_trade_active.get("groups"):
            vt_price = current_candle["close"]
            entry_price = viewer_trade_active["entry"]
            # Almacenar el evento de voz final (solo un TTS por resolución)
            pending_tts = None
            for g_key, grp in viewer_trade_active["groups"].items():
                if grp.get("resolved") or viewer_trade_active.get("cerrada"):
                    continue
                g_dir = grp.get("dir", "BUY")
                grp_sl = grp["sl"]
                grp_max_rr = grp.get("max_rr", 1.0)
                # --- ARMAR BREAK EVEN (BE) ---
                if not grp.get("be_armed"):
                    if any(lvl.get("resolved") for lvl in grp["levels"]):
                        grp["be_armed"] = True
                # --- VERIFICAR BREAK EVEN (BE) ---
                if grp.get("be_armed"):
                    be_hit = (vt_price <= entry_price) if g_dir == "BUY" else (vt_price >= entry_price)
                    if be_hit:
                        grp["resolved"] = True
                        grp["flash"] = {"color": (255, 200, 50), "start": current_time}
                        flash_active = True
                        flash_start_time = current_time
                        flash_color = (255, 200, 50)
                        flash_text = "-50 FXP"
                        pending_tts = "BE"
                        continue
                # Verificar SL del grupo
                sl_hit = (vt_price <= grp_sl) if g_dir == "BUY" else (vt_price >= grp_sl)
                if sl_hit:
                    for lvl in grp["levels"]:
                        for uname in lvl["users"]:
                            pl = get_player(uname)
                            if pl:
                                update_player_balance(uname, max(8000, pl["balance"] - TRADE_RISK), loss=True)
                                add_trade_history(uname, g_dir, "LOSS", -TRADE_RISK, 1.0)
                                # Fase 2: Analytics RR
                                if current_session_id is not None:
                                    add_session_rr_result(current_session_id, 1.0, win=False)
                                add_ticker_event(f"{uname} LOSS: -{TRADE_RISK} FXP")
                            viewer_streaks[uname] = 0
                    grp["resolved"] = True
                    SL_HIT_AUDIO_FLAG = True
                    audio_manager.set_force_pause(True)
                    audio_manager.play(f"{g_dir.lower().replace('sell', 'sel')}_sl.mp3", pausar_mercado=True)
                    voice_freeze_start = current_time
                    grp["flash"] = {"color": (239, 83, 80), "start": current_time}
                    flash_active = True
                    flash_start_time = current_time
                    flash_color = (239, 83, 80)
                    flash_text = "-100 FXP"
                    total_operations += 1
                    pending_tts = "SL"
                    continue # Permitir procesar otros grupos
                # Verificar Meta de cada nivel R:R
                for lvl in grp["levels"]:
                    if lvl.get("resolved"):
                        continue
                    tp_hit = (vt_price >= lvl["tp"]) if g_dir == "BUY" else (vt_price <= lvl["tp"])
                    if tp_hit:
                        is_max_tp = (lvl["rr"] >= grp_max_rr)
                        for uname in lvl["users"]:
                            pl = get_player(uname)
                            if pl:
                                gain = int(TRADE_RISK * lvl["rr"])
                                update_player_balance(uname, pl["balance"] + gain, win=True)
                                add_trade_history(uname, g_dir, "WIN", gain, lvl["rr"])

                                # Fase 2: Analytics FXP
                                if current_session_id is not None:
                                    add_session_fxp(current_session_id, gain)

                                # Fase 2: Analytics RR
                                if current_session_id is not None:
                                    add_session_rr_result(current_session_id, lvl["rr"], win=True)
                                add_ticker_event(f"{uname} WIN: +{gain} FXP (RR {lvl['rr']})")
                            viewer_streaks[uname] = viewer_streaks.get(uname, 0) + 1
                            if viewer_streaks[uname] >= STREAK_MIN:
                                streak_display = {"name": uname, "streak": viewer_streaks[uname], "start_time": current_time}
                        lvl["resolved"] = True
                        tp_num = int(lvl["rr"])
                        
                        if is_max_tp:
                            # Cierre forzoso inmediato para viewers
                            close_position(viewer_trade_active, g_dir, grp, lvl, is_viewer=True)
                            pending_tts = "MAX_TP"
                            voice_freeze_start = current_time
                        else:
                            audio_manager.set_force_pause(True)
                            if 1 <= tp_num <= 10:
                                audio_manager.play(f"{g_dir.lower().replace('sell', 'sel')}_tp{tp_num}.mp3", pausar_mercado=True)
                            voice_freeze_start = current_time
                            grp["flash"] = {"color": (38, 200, 154), "start": current_time}
                            flash_active = True
                            flash_start_time = current_time
                            flash_color = (38, 200, 154)
                            flash_text = f"+{int(lvl['rr']) * 100} FXP"
                            if lvl["rr"] >= 1.0:
                                grp["be_armed"] = True
                        
                        total_operations += 1
            # Disparar el TTS Luvvoice del evento final (solo uno por resolución)
            if pending_tts is not None:
                audio_manager.set_force_pause(True) # Asegurar pausa durante TTS
                if pending_tts == "MAX_TP":
                    luvvoice_tts.play_on_max_tp()
                elif pending_tts == "SL":
                    luvvoice_tts.play_on_stop_loss()
                elif pending_tts == "BE":
                    audio_manager.play("neutro.mp3", pausar_mercado=True)
                    luvvoice_tts.play_on_break_even()
                voice_freeze_start = current_time
            # Limpieza Quirúrgica (Viewers): Eliminar cada caja de forma independiente tras su flash
            if viewer_trade_active is not None and "groups" in viewer_trade_active:
                to_remove_v = []
                for g_id, grp in viewer_trade_active["groups"].items():
                    if grp.get("resolved"):
                        if grp.get("flash"):
                            if current_time - grp["flash"]["start"] > 1500:
                                to_remove_v.append(g_id)
                        else:
                            to_remove_v.append(g_id)
                
                for g_id in to_remove_v:
                    del viewer_trade_active["groups"][g_id]
                
                if not viewer_trade_active["groups"]:
                    check_top5_levelup_sound(current_time)
                    viewer_trade_active = None
                    viewer_votes = []
                    # Fase 2: Registrar ronda finalizada
                    if current_session_id is not None:
                        add_session_round(current_session_id)
                    if active_trade is None:
                        viewer_votes_display = []
        if not audio_manager.juego_pausado and not zone_frozen and liquidity_event_active is None and current_time - last_candle_time >= CANDLE_DURATION:
            # --- ACTUALIZAR ESTRUCTURA DE IMPULSO/RETROCESO (Dinámico: 4-6 Impulsos, 2-3 Retrocesos) ---
            trend_count += 1
            if trend_count >= trend_length:
                trend_count = 0
                if market_state == "impulse":
                    market_state = "retracement"
                    trend_length = random.randint(2, 3)
                    trend_strength = random.uniform(6, 10)
                    current_dir = -trend_dir
                    impulse_in_trend += 1
                else:
                    market_state = "impulse"
                    trend_length = random.randint(4, 6)
                    trend_strength = random.uniform(11, 19)
                    
                    # Cambio de tendencia tras 1-2 impulsos (Ciclos Ágiles)
                    if impulse_in_trend >= random.randint(1, 2):
                        trend_dir *= -1
                        impulse_in_trend = 0
                    current_dir = trend_dir
            
            # Aplicar mechas realistas al cierre
            wick_ratio = 0.25 if market_state == "retracement" else 0.15
            wick_up = random.uniform(0.1, trend_strength * wick_ratio)
            wick_down = random.uniform(0.1, trend_strength * wick_ratio)
            
            # Si la vela es de rechazo (mecha larga en contra), aumentamos una
            if (current_candle["close"] > current_candle["open"] and current_dir < 0) or \
               (current_candle["close"] < current_candle["open"] and current_dir > 0):
                if random.random() < 0.5:
                    wick_up *= 2.2
                else:
                    wick_down *= 2.2
            
            current_candle["high"] = max(current_candle["high"], max(current_candle["open"], current_candle["close"]) + wick_up)
            current_candle["low"] = min(current_candle["low"], min(current_candle["open"], current_candle["close"]) - wick_down)
            
            candles.append(current_candle.copy())
            # Resetear cooldown de spam por vela en el chat de TikTok
            tiktok_chat.reset_candle_cooldown()
            if len(candles) > 1000:
                candles.pop(0)
                for bos in bos_markers:
                    bos["level_index"] -= 1
                    bos["break_index"] -= 1
                bos_markers[:] = [b for b in bos_markers if b["break_index"] >= 0]
                for f in confirmed_fractals:
                    f["index"] -= 1
                confirmed_fractals[:] = [f for f in confirmed_fractals if f["index"] >= 0]
                last_checked_index -= 1
                if range_high_index is not None:
                    range_high_index -= 1
                if range_low_index is not None:
                    range_low_index -= 1
                if prev_range_low_index is not None:
                    prev_range_low_index -= 1
                if prev_range_high_index is not None:
                    prev_range_high_index -= 1
                if active_ob is not None:
                    active_ob["index"] -= 1
                    if "end_index" in active_ob:
                        active_ob["end_index"] -= 1
                    if active_ob["index"] < 0:
                        active_ob = None
                if prev_ob is not None:
                    prev_ob["index"] -= 1
                    if "end_index" in prev_ob:
                        prev_ob["end_index"] -= 1
                    if prev_ob["index"] < 0:
                        prev_ob = None
                if active_decisional is not None:
                    active_decisional["index"] -= 1
                    if active_decisional["index"] < 0:
                        active_decisional = None
                if active_fvg is not None:
                    active_fvg["index"] -= 1
                    if active_fvg["index"] < 0:
                        active_fvg = None
                if active_trade is not None and "entry_index" in active_trade:
                    active_trade["entry_index"] -= 1
                if viewer_trade_active is not None and "entry_index" in viewer_trade_active:
                    viewer_trade_active["entry_index"] -= 1
            current_len = len(candles)
            bos_markers[:] = [b for b in bos_markers if current_len - b["break_index"] <= 999]
            confirmed_fractals[:] = [f for f in confirmed_fractals if current_len - f["index"] <= 999]
            process_new_candle(candles, len(candles) - 1)
            last_checked_index = len(candles)
            current_candle = {"open": candles[-1]["close"], "close": candles[-1]["close"], "high": candles[-1]["close"], "low": candles[-1]["close"]}
            last_candle_time = current_time
        # Solo incluimos la vela actual en el renderizado si ha tenido algún movimiento (evita vela fantasma estática)
        all_candles = candles + [current_candle] if current_candle["high"] != current_candle["low"] else candles
        total_len = len(all_candles)
        needed_count = 60  # Base: mostrar últimas 60 velas
        # Solo mirar el último rango (no ir tan atrás)
        if prev_range_low_index is not None:
            distance = total_len - prev_range_low_index
            if distance > needed_count and distance < 120:
                needed_count = distance + 10
        if prev_range_high_index is not None:
            distance = total_len - prev_range_high_index
            if distance > needed_count and distance < 120:
                needed_count = distance + 10
        if range_phase == "rango_definido":
            if range_high_index is not None:
                distance = total_len - range_high_index
                if distance > needed_count and distance < 120:
                    needed_count = distance + 10
            if range_low_index is not None:
                distance = total_len - range_low_index
                if distance > needed_count and distance < 120:
                    needed_count = distance + 10
        needed_count = max(50, min(needed_count, 100))
        new_target = float(needed_count)
        # Sonido de ZOOM cuando el zoom cambia significativamente
        if abs(new_target - target_visible_count) > 15:
            play_sound(sound_zoom)
        target_visible_count = new_target
        current_visible_count += (target_visible_count - current_visible_count) * 0.08
        num_visible = int(current_visible_count)
        visible_candles = all_candles[-num_visible:]
        if visible_candles:
            all_highs = [c["high"] for c in visible_candles]
            all_lows = [c["low"] for c in visible_candles]
            max_p = max(all_highs)
            min_p = min(all_lows)
            price_range = max_p - min_p
            if price_range == 0:
                price_range = 1.0
            vertical_zoom = (SCREEN_H * 0.75) / price_range
            view_center_price = min_p + price_range / 2
            center_y = int(SCREEN_H * 0.55)
            chart_start_x = 0
            chart_end_x = int(SCREEN_W * 0.75)
            # Velas ocupan hasta 70%
            available_width = int(SCREEN_W * 0.67) - chart_start_x
            spacing = available_width / max(num_visible - 1, 1)
            candle_width = max(3, int(spacing * 0.65))
            start_x = chart_start_x
            total_candles = len(all_candles)
            visible_start_global = total_candles - len(visible_candles)
            # --- RENDERIZAR ORDER BLOCKS, DECISIONAL, FVG ---
            ob_surface = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            
            # Solo dibujamos el bloque activo (EXTREMO) para una interfaz limpia
            for ob_data, ob_opacity, ob_label in [(active_ob, 45, "EXTREMO")]:
                if ob_data is None:
                    continue
                # No dibujar si ya fue mitigada
                ob_zone_id = f"ob_{ob_data['index']}"
                ob_price_id = f"ob_{int(ob_data['high']*10)}_{int(ob_data['low']*10)}"
                # Si fue mitigada, dibujar solo hasta el punto de mitigación
                mitigated = ob_zone_id in zones_mitigated or ob_price_id in zones_mitigated
                if mitigated:
                    info = zones_mitigated_info.get(ob_zone_id) or zones_mitigated_info.get(ob_price_id)
                    if info and info.get("bos_count", 0) >= 2:
                        continue  # Ya pasaron 2 BOS, borrar
                ob_vis = ob_data["index"] - visible_start_global
                if ob_vis >= len(visible_candles):
                    continue
                if ob_vis < 0:
                    ob_x_start = 0
                else:
                    ob_x_start = int(start_x + (ob_vis * spacing))
                if "end_index" in ob_data:
                    ob_end_vis = ob_data["end_index"] - visible_start_global
                    if ob_end_vis < 0:
                        continue
                    ob_x_end = int(start_x + (ob_end_vis * spacing)) + candle_width
                else:
                    ob_x_end = int(start_x + ((len(visible_candles) - 1) * spacing)) + candle_width
                # Si fue mitigada, limitar hasta el punto de mitigación
                if mitigated:
                    info = zones_mitigated_info.get(ob_zone_id) or zones_mitigated_info.get(ob_price_id)
                    if info:
                        mit_vis = info["index"] - visible_start_global
                        if 0 <= mit_vis < len(visible_candles):
                            ob_x_end = int(start_x + (mit_vis * spacing)) + candle_width
                ob_y_high = center_y - int((ob_data["high"] - view_center_price) * vertical_zoom)
                ob_y_low = center_y - int((ob_data["low"] - view_center_price) * vertical_zoom)
                ob_height = max(1, ob_y_low - ob_y_high)
                ob_width = max(1, ob_x_end - ob_x_start)
                if ob_data["type"] == "ALCISTA":
                    ob_color = (*GLOBAL_COLOR_BULL, ob_opacity)
                else:
                    ob_color = (*GLOBAL_COLOR_BEAR, ob_opacity)
                
                # Dibujo de la caja limpia de la zona
                pygame.draw.rect(ob_surface, ob_color, (ob_x_start, ob_y_high, ob_width, ob_height))
                # Borde sutil para definir la zona
                pygame.draw.rect(ob_surface, (*ob_color[:3], 150), (ob_x_start, ob_y_high, ob_width, ob_height), 1)

                if ob_label:
                    # Determinar etiqueta de operación activa si existe
                    display_label = ob_label
                    if active_trade and not active_trade.get("cerrada"):
                        for g_dir, grp in active_trade.get("groups", {}).items():
                            if not grp.get("resolved"):
                                display_label = f"{ob_label} - {g_dir.replace('BUY', 'COMPRA').replace('SELL', 'VENTA')}"
                                break
                    
                    label_txt = font_ob.render(display_label, True, (255, 255, 255))
                    label_rect = label_txt.get_rect(center=(ob_x_start + ob_width // 2, ob_y_high + ob_height // 2))
                    
                    # Realce estético: Cuadro con fondo oscuro y borde cian brillante (glow)
                    padding_h, padding_v = 10, 5
                    bg_rect = label_rect.inflate(padding_h * 2, padding_v * 2)
                    pygame.draw.rect(ob_surface, (5, 12, 25, 230), bg_rect, border_radius=4)
                    
                    # Efecto de resplandor (glow) cian eléctrico intenso
                    glow_color = (0, 255, 255)
                    for i in range(2):
                        alpha = 150 // (i + 1)
                        pygame.draw.rect(ob_surface, (*glow_color, alpha), bg_rect.inflate(i*2, i*2), 1, border_radius=4+i)
                    
                    ob_surface.blit(label_txt, label_rect)
            
            if active_decisional is not None:
                # Lógica para DECISIONAL similar a EXTREMO
                dec_zone_id = f"dec_{active_decisional['index']}"
                dec_price_id = f"dec_{int(active_decisional['high']*10)}_{int(active_decisional['low']*10)}"
                is_mitigated = dec_zone_id in zones_mitigated or dec_price_id in zones_mitigated
                
                info = zones_mitigated_info.get(dec_zone_id) or zones_mitigated_info.get(dec_price_id)
                if not (is_mitigated and info and info.get("bos_count", 0) >= 2):
                    dec_vis = active_decisional["index"] - visible_start_global
                    if 0 <= dec_vis < len(visible_candles):
                        dec_x_start = int(start_x + (dec_vis * spacing))
                        if is_mitigated and info:
                            mit_vis = info["index"] - visible_start_global
                            dec_x_end = int(start_x + (mit_vis * spacing)) + candle_width if 0 <= mit_vis < len(visible_candles) else int(start_x + ((len(visible_candles) - 1) * spacing)) + candle_width
                        else:
                            dec_x_end = int(start_x + ((len(visible_candles) - 1) * spacing)) + candle_width
                            
                        dec_y_high = center_y - int((active_decisional["high"] - view_center_price) * vertical_zoom)
                        dec_y_low = center_y - int((active_decisional["low"] - view_center_price) * vertical_zoom)
                        dec_height = max(1, dec_y_low - dec_y_high)
                        dec_width = max(1, dec_x_end - dec_x_start)
                        
                        dec_opacity = 30 if not is_mitigated else 15
                        if active_decisional["type"] == "ALCISTA":
                            dec_color = (*GLOBAL_COLOR_BULL, dec_opacity)
                        else:
                            dec_color = (*GLOBAL_COLOR_BEAR, dec_opacity)
                        
                        pygame.draw.rect(ob_surface, dec_color, (dec_x_start, dec_y_high, dec_width, dec_height))
                        pygame.draw.rect(ob_surface, (*dec_color[:3], 100), (dec_x_start, dec_y_high, dec_width, dec_height), 1)
                        
                        dec_label = "DECISIONAL"
                        if active_trade and not active_trade.get("cerrada"):
                             for g_dir, grp in active_trade.get("groups", {}).items():
                                if not grp.get("resolved"):
                                    dec_label = f"DECISIONAL - {g_dir.replace('BUY', 'COMPRA').replace('SELL', 'VENTA')}"
                                    break
                                    
                        dec_txt = font_ob.render(dec_label, True, (255, 255, 255))
                        dec_rect = dec_txt.get_rect(center=(dec_x_start + dec_width // 2, dec_y_high + dec_height // 2))
                        
                        # Fondo oscuro para legibilidad
                        pygame.draw.rect(ob_surface, (5, 12, 25, 200), dec_rect.inflate(12, 6), border_radius=3)
                        ob_surface.blit(dec_txt, dec_rect)
            
            screen.blit(ob_surface, (0, 0))
            for index, candle in enumerate(visible_candles):
                x_pos = int(start_x + (index * spacing))
                y_open = center_y - int((candle["open"] - view_center_price) * vertical_zoom)
                y_close = center_y - int((candle["close"] - view_center_price) * vertical_zoom)
                y_high = center_y - int((candle["high"] - view_center_price) * vertical_zoom)
                y_low = center_y - int((candle["low"] - view_center_price) * vertical_zoom)
                is_bullish = candle["close"] >= candle["open"]
                color = GLOBAL_COLOR_BULL if is_bullish else GLOBAL_COLOR_BEAR
                center_x = x_pos + (candle_width // 2)
                top_body = min(y_open, y_close)
                bottom_body = max(y_open, y_close)
                body_height = max(1, bottom_body - top_body)
                pygame.draw.line(screen, color, (center_x, y_high), (center_x, top_body), 1)
                pygame.draw.line(screen, color, (center_x, bottom_body), (center_x, y_low), 1)
                pygame.draw.rect(screen, color, (x_pos, top_body, candle_width, body_height))
            fractal_surface = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            total_fractals = len(confirmed_fractals)
            for idx, frac in enumerate(confirmed_fractals):
                vis_f = frac["index"] - visible_start_global
                if vis_f < 0 or vis_f >= len(visible_candles):
                    continue
                age = (total_fractals - 1 - idx) // 2
                if age == 0:
                    opacity = 204
                elif age == 1:
                    opacity = 128
                elif age == 2:
                    opacity = 90
                else:
                    opacity = 64
                fx = int(start_x + (vis_f * spacing)) + (candle_width // 2)
                fy = center_y - int((frac["price"] - view_center_price) * vertical_zoom)
                if frac["type"] == "high":
                    pygame.draw.circle(fractal_surface, (255, 255, 0, opacity), (fx, fy - 10), 8)
                else:
                    pygame.draw.circle(fractal_surface, (255, 255, 0, opacity), (fx, fy + 10), 8)
            screen.blit(fractal_surface, (0, 0))
            for bos in bos_markers:
                vis_level = bos["level_index"] - visible_start_global
                vis_break = bos["break_index"] - visible_start_global
                if vis_break < 0 or vis_break >= len(visible_candles):
                    continue
                if vis_level >= len(visible_candles):
                    continue
                if vis_level < 0:
                    x_bos_start = start_x
                else:
                    x_bos_start = int(start_x + (vis_level * spacing)) + (candle_width // 2)
                x_bos_end = int(start_x + (vis_break * spacing)) + (candle_width // 2)
                y_level = center_y - int((bos["price"] - view_center_price) * vertical_zoom)
                bos_text = font_bos.render("BOS", True, (255, 255, 255))
                text_rect = bos_text.get_rect(center=((x_bos_start + x_bos_end) // 2, y_level))
                text_margin = 6
                left_end = text_rect.left - text_margin
                for x in range(x_bos_start, left_end, 10):
                    seg_end = min(x + 5, left_end)
                    pygame.draw.line(screen, (255, 255, 255), (x, y_level), (seg_end, y_level), 1)
                right_start = text_rect.right + text_margin
                for x in range(right_start, x_bos_end, 10):
                    seg_end = min(x + 5, x_bos_end)
                    pygame.draw.line(screen, (255, 255, 255), (x, y_level), (seg_end, y_level), 1)
                screen.blit(bos_text, text_rect)
            # --- PANEL VIEWERS (arriba centro, donde estaban los botones) ---
            btn_x = int(SCREEN_W * 0.35)
            btn_y = int(SCREEN_H * 0.03)
            if zone_frozen:
                # Timer activo - mostrar panel de votación
                elapsed = current_time - zone_timer_start
                timer_elapsed_render = max(0, elapsed - 4000)  # VOICE_DELAY
                remaining = max(0, TIMER_DURATION - timer_elapsed_render)
                seconds_left = remaining / 1000.0
                # Tick-tock en los últimos 5 segundos
                current_second = int(seconds_left)
                if seconds_left <= 5.0 and current_second != last_tick_second and seconds_left > 0:
                    play_sound(sound_tick)
                    last_tick_second = current_second
                # === ELIMINADO: Panel lateral antiguo (Reposicionado al centro) ===
                """
                slide_progress = min(1.0, (elapsed) / 200.0)  # 200ms slide rápido
                panel_w = int(SCREEN_W * 0.20)
                panel_h = int(SCREEN_H * 0.14)
                panel_x_final = int(SCREEN_W * 0.02)
                panel_x = int(panel_x_final - (1.0 - slide_progress) * (panel_w + 20))
                panel_y = int(SCREEN_H * 0.02)
                # Fondo oscuro
                panel_bg = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
                panel_bg.fill((5, 10, 20, 230))
                screen.blit(panel_bg, (panel_x, panel_y))
                # Borde dorado pulsante
                border_pulse = int(200 + 55 * math.sin(current_time / 200.0))
                pygame.draw.rect(screen, (border_pulse, int(border_pulse * 0.75), 0), (panel_x, panel_y, panel_w, panel_h), 2, border_radius=6)
                # Barra cyan izquierda (más gruesa, glow)
                pygame.draw.rect(screen, (0, 220, 255), (panel_x, panel_y, 4, panel_h))
                glow_bar = pygame.Surface((8, panel_h), pygame.SRCALPHA)
                glow_bar.fill((0, 200, 255, 40))
                screen.blit(glow_bar, (panel_x, panel_y))
                # Timer grande con glow
                font_timer_mix = pygame.font.SysFont("Arial", int(SCREEN_H * 0.042), bold=True)
                timer_txt = font_timer_mix.render(f"{seconds_left:.1f}s", True, (255, 255, 255))
                # Sombra del timer
                timer_shadow = font_timer_mix.render(f"{seconds_left:.1f}s", True, (0, 100, 130))
                # screen.blit(timer_shadow, (panel_x + 14, panel_y + int(panel_h * 0.10) + 2))
                # screen.blit(timer_txt, (panel_x + 12, panel_y + int(panel_h * 0.10)))
                # Barra de progreso (más ancha, con glow)
                bar_w_m = int(panel_w * 0.85)
                bar_h_m = 8
                bar_x_m = panel_x + 12
                bar_y_m = panel_y + int(panel_h * 0.58)
                progress = remaining / TIMER_DURATION
                pygame.draw.rect(screen, (20, 25, 35), (bar_x_m, bar_y_m, bar_w_m, bar_h_m), border_radius=4)
                if progress > 0.5:
                    bar_color = (0, 220, 255)
                elif progress > 0.25:
                    bar_color = (255, 220, 0)
                else:
                    bar_color = (255, 50, 50)
                fill_w = int(bar_w_m * progress)
                if fill_w > 0:
                    pygame.draw.rect(screen, bar_color, (bar_x_m, bar_y_m, fill_w, bar_h_m), border_radius=4)
                    # Glow de la barra
                    bar_glow = pygame.Surface((fill_w, bar_h_m + 6), pygame.SRCALPHA)
                    bar_glow.fill((bar_color[0], bar_color[1], bar_color[2], 30))
                    screen.blit(bar_glow, (bar_x_m, bar_y_m - 3))
                # "ESCRIBE SUBE O BAJA" más grande
                font_escribe_m = pygame.font.SysFont("Arial", int(SCREEN_H * 0.022), bold=True)
                escribe_txt = font_escribe_m.render("ESCRIBE SUBE O BAJA", True, (0, 200, 220))
                screen.blit(escribe_txt, (panel_x + 12, panel_y + int(panel_h * 0.78)))
                """

                # === NUEVO TEMPORIZADOR CENTRAL FLOTANTE (ESTILO CYBERPUNK HUD) ===
                if seconds_left > 0:
                    # Configuración de colores según tensión (crítico < 3s)
                    is_critical = seconds_left < 3.0
                    accent_color = (255, 50, 50) if is_critical else (0, 255, 255)
                    glow_color = (150, 0, 0) if is_critical else (0, 150, 200)
                    
                    # Efecto de parpadeo rápido en estado crítico
                    if is_critical and (curr_ticks // 200) % 2 == 0:
                        accent_color = (255, 255, 255)
                    
                    timer_w = int(SCREEN_W * 0.28)
                    timer_h = int(SCREEN_H * 0.12)
                    timer_x = (SCREEN_W - timer_w) // 2
                    timer_y = int(SCREEN_H * 0.005)
                    
                    # 1. FONDO HUD (Translúcido y oscuro)
                    timer_rect = pygame.Rect(timer_x, timer_y, timer_w, timer_h)
                    s_bg = pygame.Surface((timer_w, timer_h), pygame.SRCALPHA)
                    pygame.draw.rect(s_bg, (5, 10, 20, 210), (0, 0, timer_w, timer_h), border_radius=4)
                    screen.blit(s_bg, (timer_x, timer_y))
                    
                    # 2. BORDES TÉCNICOS Y ESQUINAS CYBER
                    pygame.draw.rect(screen, (*accent_color, 80), timer_rect, 1, border_radius=4)
                    
                    # Esquinas reforzadas (L-shapes)
                    c_len = 15
                    # Arriba-Izquierda
                    pygame.draw.line(screen, accent_color, (timer_x, timer_y), (timer_x + c_len, timer_y), 3)
                    pygame.draw.line(screen, accent_color, (timer_x, timer_y), (timer_x, timer_y + c_len), 3)
                    # Arriba-Derecha
                    pygame.draw.line(screen, accent_color, (timer_x + timer_w, timer_y), (timer_x + timer_w - c_len, timer_y), 3)
                    pygame.draw.line(screen, accent_color, (timer_x + timer_w, timer_y), (timer_x + timer_w, timer_y + c_len), 3)
                    # Abajo-Izquierda
                    pygame.draw.line(screen, accent_color, (timer_x, timer_y + timer_h), (timer_x + c_len, timer_y + timer_h), 3)
                    pygame.draw.line(screen, accent_color, (timer_x, timer_y + timer_h), (timer_x, timer_y + timer_h - c_len), 3)
                    # Abajo-Derecha
                    pygame.draw.line(screen, accent_color, (timer_x + timer_w, timer_y + timer_h), (timer_x + timer_w - c_len, timer_y + timer_h), 3)
                    pygame.draw.line(screen, accent_color, (timer_x + timer_w, timer_y + timer_h), (timer_x + timer_w, timer_y + timer_h - c_len), 3)

                    # 3. TEXTO TEMPORIZADOR GIGANTE
                    font_huge = pygame.font.SysFont("Consolas", int(SCREEN_H * 0.075), bold=True)
                    timer_str = f"{seconds_left:.1f}s"
                    
                    # Resplandor dinámico
                    pulse_val = (math.sin(curr_ticks * 0.01) + 1) / 2
                    glow_a = int(50 + 100 * pulse_val)
                    for off in [(-2,0), (2,0), (0,-2), (0,2)]:
                        glow_surf = font_huge.render(timer_str, True, (*glow_color, glow_a))
                        glow_rect = glow_surf.get_rect(center=(timer_x + timer_w//2 + off[0], timer_y + timer_h//2 - 10 + off[1]))
                        screen.blit(glow_surf, glow_rect)
                    
                    t_surf = font_huge.render(timer_str, True, (255, 255, 255))
                    t_rect = t_surf.get_rect(center=(timer_x + timer_w//2, timer_y + timer_h//2 - 10))
                    screen.blit(t_surf, t_rect)
                    
                    # 4. BARRA DE PROGRESO INFERIOR (DINÁMICA)
                    bar_w = timer_w - 40
                    bar_h = 6
                    bar_x = timer_x + 20
                    bar_y = timer_y + timer_h - 42
                    progress = remaining / TIMER_DURATION
                    
                    # Fondo de la barra
                    pygame.draw.rect(screen, (30, 40, 50), (bar_x, bar_y, bar_w, bar_h), border_radius=3)
                    # Relleno de la barra
                    fill_w = int(bar_w * progress)
                    if fill_w > 0:
                        pygame.draw.rect(screen, accent_color, (bar_x, bar_y, fill_w, bar_h), border_radius=3)
                        # Glow en la punta de la barra
                        if fill_w > 4:
                            pygame.draw.circle(screen, (255, 255, 255), (bar_x + fill_w, bar_y + bar_h//2), 3)

                    # 5. SUBTEXTO DE INSTRUCCIÓN
                    font_sub = pygame.font.SysFont("Consolas", int(SCREEN_H * 0.020), bold=True)
                    sub_txt = font_sub.render("ESCRIBE SUBE O BAJA", True, accent_color)
                    sub_rect = sub_txt.get_rect(center=(timer_x + timer_w//2, timer_y + timer_h - 20))
                    
                    # Parpadeo de instrucción
                    if (curr_ticks // 400) % 2 == 0:
                        screen.blit(sub_txt, sub_rect)

                # --- PANEL VIEWERS (REPOSICIONADO Y REDISEÑADO) ---
                if viewer_votes:
                    buy_count = sum(1 for v in viewer_votes if v["vote"] == "BUY")
                    sell_count = sum(1 for v in viewer_votes if v["vote"] == "SELL")
                    total_votes = buy_count + sell_count
                    
                    vbox_w = guide_w
                    vbox_h = int(SCREEN_H * 0.11)
                    vbox_x = guide_x - 6
                    vbox_y = tel_box_y + tel_box_h + 15
                    
                    # 1. FONDO HUD CYBERPUNK
                    vote_bg = pygame.Surface((vbox_w, vbox_h), pygame.SRCALPHA)
                    pygame.draw.rect(vote_bg, (5, 10, 20, 225), (0, 0, vbox_w, vbox_h), border_radius=6)
                    
                    # Borde Neón Pulsante
                    pulse_io = (math.sin(current_time * 0.005) + 1) / 2
                    neon_a = int(150 + 105 * pulse_io)
                    pygame.draw.rect(vote_bg, (0, 255, 255, neon_a), (0, 0, vbox_w, vbox_h), 2, border_radius=6)
                    
                    # Brillo exterior sutil
                    for i in range(3):
                        pygame.draw.rect(vote_bg, (0, 200, 255, 30 // (i+1)), (-i, -i, vbox_w+i*2, vbox_h+i*2), 1, border_radius=6+i)
                    
                    screen.blit(vote_bg, (vbox_x, vbox_y))
                    
                    # 2. TÍTULO Y TOTAL
                    font_vw_label = pygame.font.SysFont("Consolas", int(SCREEN_H * 0.016), bold=True)
                    vw_lbl = font_vw_label.render(f"VOTOS EN VIVO: {total_votes}", True, (0, 220, 255))
                    screen.blit(vw_lbl, vw_lbl.get_rect(center=(vbox_x + vbox_w // 2, vbox_y + int(vbox_h * 0.20))))
                    
                    # 3. CONTADORES SUBE / BAJA
                    font_vote_big = pygame.font.SysFont("Consolas", int(SCREEN_H * 0.038), bold=True)
                    font_sub = pygame.font.SysFont("Consolas", int(SCREEN_H * 0.014), bold=True)
                    
                    # SUBE (Verde Neón)
                    buy_txt = font_vote_big.render(f"{buy_count}", True, (0, 255, 127))
                    buy_lbl = font_sub.render("SUBE", True, (0, 255, 127))
                    
                    # BAJA (Rojo Neón)
                    sell_txt = font_vote_big.render(f"{sell_count}", True, (255, 49, 49))
                    sell_lbl = font_sub.render("BAJA", True, (255, 49, 49))
                    
                    # Renderizado de textos
                    screen.blit(buy_txt, buy_txt.get_rect(center=(vbox_x + int(vbox_w * 0.28), vbox_y + int(vbox_h * 0.58))))
                    screen.blit(buy_lbl, buy_lbl.get_rect(center=(vbox_x + int(vbox_w * 0.28), vbox_y + int(vbox_h * 0.85))))
                    
                    screen.blit(sell_txt, sell_txt.get_rect(center=(vbox_x + int(vbox_w * 0.72), vbox_y + int(vbox_h * 0.58))))
                    screen.blit(sell_lbl, sell_lbl.get_rect(center=(vbox_x + int(vbox_w * 0.72), vbox_y + int(vbox_h * 0.85))))
                    
                    # Separador vertical técnico
                    pygame.draw.line(screen, (0, 100, 130), 
                                     (vbox_x + vbox_w // 2, vbox_y + int(vbox_h * 0.40)), 
                                     (vbox_x + vbox_w // 2, vbox_y + int(vbox_h * 0.90)), 2)
            elif active_trade is not None and "groups" in active_trade:
                # LEAN FX operando - mostrar info del trade
                info_x = int(SCREEN_W * 0.05)
                info_y = int(SCREEN_H * 0.03)
                trade_color = (0, 200, 220) # Color neutral/cian para DUAL
                trade_txt = font_hud_val.render("LEAN FX: DUAL POS", True, trade_color)
                screen.blit(trade_txt, (info_x, info_y))
                
                # PnL del bando principal (bot_decision)
                current_price = current_candle["close"]
                # Buscar el bando principal en los grupos independientes
                p_grp = active_trade["groups"].get(bot_decision)
                if not p_grp: # Si ya se cerró, buscar el primero que quede
                    p_grp = next(iter(active_trade["groups"].values())) if active_trade["groups"] else None
                
                if p_grp:
                    v_entry = p_grp["entry"]
                    if p_grp["dir"] == "BUY":
                        pnl_points = current_price - v_entry
                    else:
                        pnl_points = v_entry - current_price
                    
                    pnl_color = GLOBAL_COLOR_BULL if pnl_points >= 0 else GLOBAL_COLOR_BEAR
                    pnl_txt = font_timer.render(f"{int(pnl_points):+d} FXP", True, pnl_color)
                    screen.blit(pnl_txt, (info_x, info_y + 25))
                # Viewers también operan al mismo tiempo - panel centrado arriba
                if viewer_votes_display:
                    buy_count = sum(1 for v in viewer_votes_display if v["vote"] == "BUY")
                    sell_count = sum(1 for v in viewer_votes_display if v["vote"] == "SELL")
                    total_votes = buy_count + sell_count
                    
                    vbox_w = guide_w
                    vbox_h = int(SCREEN_H * 0.11)
                    vbox_x = guide_x - 6
                    vbox_y = tel_box_y + tel_box_h + 15
                    
                    # 1. FONDO HUD CYBERPUNK
                    vote_bg = pygame.Surface((vbox_w, vbox_h), pygame.SRCALPHA)
                    pygame.draw.rect(vote_bg, (5, 10, 20, 225), (0, 0, vbox_w, vbox_h), border_radius=6)
                    
                    # Borde Neón Pulsante
                    pulse_io = (math.sin(current_time * 0.005) + 1) / 2
                    neon_a = int(150 + 105 * pulse_io)
                    pygame.draw.rect(vote_bg, (0, 255, 255, neon_a), (0, 0, vbox_w, vbox_h), 2, border_radius=6)
                    
                    # Brillo exterior sutil
                    for i in range(3):
                        pygame.draw.rect(vote_bg, (0, 200, 255, 30 // (i+1)), (-i, -i, vbox_w+i*2, vbox_h+i*2), 1, border_radius=6+i)
                    
                    screen.blit(vote_bg, (vbox_x, vbox_y))
                    
                    # 2. TÍTULO Y TOTAL
                    font_vw_label = pygame.font.SysFont("Consolas", int(SCREEN_H * 0.016), bold=True)
                    vw_lbl = font_vw_label.render(f"VOTOS EN VIVO: {total_votes}", True, (0, 220, 255))
                    screen.blit(vw_lbl, vw_lbl.get_rect(center=(vbox_x + vbox_w // 2, vbox_y + int(vbox_h * 0.20))))
                    
                    # 3. CONTADORES SUBE / BAJA
                    font_vote_big = pygame.font.SysFont("Consolas", int(SCREEN_H * 0.038), bold=True)
                    font_sub = pygame.font.SysFont("Consolas", int(SCREEN_H * 0.014), bold=True)
                    
                    # SUBE (Verde Neón)
                    buy_txt = font_vote_big.render(f"{buy_count}", True, (0, 255, 127))
                    buy_lbl = font_sub.render("SUBE", True, (0, 255, 127))
                    
                    # BAJA (Rojo Neón)
                    sell_txt = font_vote_big.render(f"{sell_count}", True, (255, 49, 49))
                    sell_lbl = font_sub.render("BAJA", True, (255, 49, 49))
                    
                    # Renderizado de textos
                    screen.blit(buy_txt, buy_txt.get_rect(center=(vbox_x + int(vbox_w * 0.28), vbox_y + int(vbox_h * 0.58))))
                    screen.blit(buy_lbl, buy_lbl.get_rect(center=(vbox_x + int(vbox_w * 0.28), vbox_y + int(vbox_h * 0.85))))
                    
                    screen.blit(sell_txt, sell_txt.get_rect(center=(vbox_x + int(vbox_w * 0.72), vbox_y + int(vbox_h * 0.58))))
                    screen.blit(sell_lbl, sell_lbl.get_rect(center=(vbox_x + int(vbox_w * 0.72), vbox_y + int(vbox_h * 0.85))))
                    
                    # Separador vertical técnico
                    pygame.draw.line(screen, (0, 100, 130), 
                                     (vbox_x + vbox_w // 2, vbox_y + int(vbox_h * 0.40)), 
                                     (vbox_x + vbox_w // 2, vbox_y + int(vbox_h * 0.90)), 2)
            elif viewer_trade_active is not None:
                # Viewers operando - Cuadro resumen (REPOSICIONADO Y REDISEÑADO)
                if viewer_votes:
                    buy_count = sum(1 for v in viewer_votes if v["vote"] == "BUY")
                    sell_count = sum(1 for v in viewer_votes if v["vote"] == "SELL")
                    total_votes = buy_count + sell_count
                    
                    vbox_w = guide_w
                    vbox_h = int(SCREEN_H * 0.11)
                    vbox_x = guide_x - 6
                    vbox_y = tel_box_y + tel_box_h + 15
                    
                    # 1. FONDO HUD CYBERPUNK
                    vote_bg = pygame.Surface((vbox_w, vbox_h), pygame.SRCALPHA)
                    pygame.draw.rect(vote_bg, (5, 10, 20, 225), (0, 0, vbox_w, vbox_h), border_radius=6)
                    
                    # Borde Neón Pulsante
                    pulse_io = (math.sin(current_time * 0.005) + 1) / 2
                    neon_a = int(150 + 105 * pulse_io)
                    pygame.draw.rect(vote_bg, (0, 255, 255, neon_a), (0, 0, vbox_w, vbox_h), 2, border_radius=6)
                    
                    # Brillo exterior sutil
                    for i in range(3):
                        pygame.draw.rect(vote_bg, (0, 200, 255, 30 // (i+1)), (-i, -i, vbox_w+i*2, vbox_h+i*2), 1, border_radius=6+i)
                    
                    screen.blit(vote_bg, (vbox_x, vbox_y))
                    
                    # 2. TÍTULO Y TOTAL
                    font_vw_label = pygame.font.SysFont("Consolas", int(SCREEN_H * 0.016), bold=True)
                    vw_lbl = font_vw_label.render(f"VOTOS EN VIVO: {total_votes}", True, (0, 220, 255))
                    screen.blit(vw_lbl, vw_lbl.get_rect(center=(vbox_x + vbox_w // 2, vbox_y + int(vbox_h * 0.20))))
                    
                    # 3. CONTADORES SUBE / BAJA
                    font_vote_big = pygame.font.SysFont("Consolas", int(SCREEN_H * 0.038), bold=True)
                    font_sub = pygame.font.SysFont("Consolas", int(SCREEN_H * 0.014), bold=True)
                    
                    # SUBE (Verde Neón)
                    buy_txt = font_vote_big.render(f"{buy_count}", True, (0, 255, 127))
                    buy_lbl = font_sub.render("SUBE", True, (0, 255, 127))
                    
                    # BAJA (Rojo Neón)
                    sell_txt = font_vote_big.render(f"{sell_count}", True, (255, 49, 49))
                    sell_lbl = font_sub.render("BAJA", True, (255, 49, 49))
                    
                    # Renderizado de textos
                    screen.blit(buy_txt, buy_txt.get_rect(center=(vbox_x + int(vbox_w * 0.28), vbox_y + int(vbox_h * 0.58))))
                    screen.blit(buy_lbl, buy_lbl.get_rect(center=(vbox_x + int(vbox_w * 0.28), vbox_y + int(vbox_h * 0.85))))
                    
                    screen.blit(sell_txt, sell_txt.get_rect(center=(vbox_x + int(vbox_w * 0.72), vbox_y + int(vbox_h * 0.58))))
                    screen.blit(sell_lbl, sell_lbl.get_rect(center=(vbox_x + int(vbox_w * 0.72), vbox_y + int(vbox_h * 0.85))))
                    
                    # Separador vertical técnico
                    pygame.draw.line(screen, (0, 100, 130), 
                                     (vbox_x + vbox_w // 2, vbox_y + int(vbox_h * 0.40)), 
                                     (vbox_x + vbox_w // 2, vbox_y + int(vbox_h * 0.90)), 2)
            # --- DIBUJAR POSICIONES EN EL GRAFICO ---
            # Trade del streamer (EXTREMO) - DUAL RENDERING
            if active_trade is not None and "groups" in active_trade:
                entry_y = center_y - int((active_trade["entry"] - view_center_price) * vertical_zoom)
                entry_vis = active_trade["entry_index"] - visible_start_global
                if entry_vis < 0:
                    line_start_x = 0
                else:
                    line_start_x = int(start_x + (entry_vis * spacing)) + (candle_width // 2)
                last_candle_x = int(start_x + ((len(visible_candles) - 1) * spacing)) + candle_width
                label_offset = max(int(3 * spacing), 80)
                line_end_x = last_candle_x + label_offset
                
                # Renderizar ambas cajas lado a lado (BUY/SELL)
                v_box_w = max(int(spacing * 3.2), 55)
                
                for g_dir, grp in active_trade["groups"].items():
                    # BORRADO QUIRÚRGICO: Si ya se resolvió y no está en flash, no se dibuja
                    is_flashing = False
                    if grp.get("flash"):
                        elapsed_flash = current_time - grp["flash"]["start"]
                        if elapsed_flash < 1000:
                            is_flashing = True
                    
                    if grp.get("resolved") and not is_flashing:
                        continue

                    entry_y = center_y - int((grp["entry"] - view_center_price) * vertical_zoom)
                    entry_vis = grp["entry_index"] - visible_start_global
                    if entry_vis < 0:
                        line_start_x = 0
                    else:
                        line_start_x = int(start_x + (entry_vis * spacing)) + (candle_width // 2)

                    if g_dir == "BUY":
                        box_start_x = line_start_x - v_box_w - 3
                        box_end_x = box_start_x + v_box_w
                    else:
                        box_start_x = line_start_x + 3
                        box_end_x = box_start_x + v_box_w
                    rect_width = box_end_x - box_start_x
                    tp_levels_y = [center_y - int((lvl["tp"] - view_center_price) * vertical_zoom) for lvl in grp.get("levels", [])]
                    
                    # Definición de grp_sl_y y validación de seguridad
                    grp_sl_y = center_y - int((grp.get("sl", 0) - view_center_price) * vertical_zoom) if "sl" in grp else None
                    
                    if grp_sl_y is not None and entry_y is not None:
                        if g_dir == "BUY":
                            grp_tp_y = min(tp_levels_y) if tp_levels_y else entry_y
                            tp_top = grp_tp_y
                            tp_height = entry_y - grp_tp_y
                            sl_top = entry_y
                            sl_height = grp_sl_y - entry_y
                        else:
                            grp_tp_y = max(tp_levels_y) if tp_levels_y else entry_y
                            tp_top = entry_y
                            tp_height = grp_tp_y - entry_y
                            sl_top = grp_sl_y
                            sl_height = entry_y - grp_sl_y
                    else:
                        continue # Evitar crash si no hay coordenadas válidas
                        
                    box_visual_top = min(tp_top, sl_top)
                    box_visual_bottom = max(tp_top + max(0, tp_height), sl_top + max(0, sl_height))
                    box_height = box_visual_bottom - box_visual_top
                    
                    # --- RENDERIZADO DE POSICIÓN DINÁMICA (image_9.png) ---
                    # Los bloques geométricos aparecen solo cuando el trade está activo
                    
                    if visible_candles:
                        current_price = visible_candles[-1]["close"]
                        current_price_y = center_y - int((current_price - view_center_price) * vertical_zoom)
                        
                        # --- RENDERIZADO ESTILO TRADINGVIEW (CAPAS) ---
                        # Colores Neón con Transparencia
                        base_alpha = 45   # ~18-20% Opacidad base fija
                        prog_alpha = 130  # Opacidad más alta para el progreso dinámico
                        
                        color_profit = (0, 255, 120)  # Verde Neón
                        color_loss = (255, 30, 30)    # Rojo Neón
                        color_divider = (80, 80, 80)  # Gris medio nítido
                        
                        # 1. CAPA BASE FIJA (Estructura completa del trade)
                        base_surf = pygame.Surface((rect_width, box_height), pygame.SRCALPHA)
                        
                        # Dibujar bloque de Profit proyectado (TP)
                        pygame.draw.rect(base_surf, (*color_profit, base_alpha), 
                                       (0, tp_top - box_visual_top, rect_width, tp_height))
                        
                        # Dibujar bloque de Riesgo proyectado (SL)
                        pygame.draw.rect(base_surf, (*color_loss, base_alpha), 
                                       (0, sl_top - box_visual_top, rect_width, sl_height))
                        
                        screen.blit(base_surf, (box_start_x, box_visual_top))
                        
                        # 2. CAPA DINÁMICA DE PROGRESO (Desde entrada hasta precio actual)
                        prog_h = abs(current_price_y - entry_y)
                        if prog_h > 0:
                            prog_y = min(entry_y, current_price_y)
                            # Determinar si el progreso es Profit o Loss según dirección
                            is_profit = (g_dir == "BUY" and current_price_y <= entry_y) or (g_dir == "SELL" and current_price_y >= entry_y)
                            p_color = color_profit if is_profit else color_loss
                            
                            prog_surf = pygame.Surface((rect_width, prog_h), pygame.SRCALPHA)
                            prog_surf.fill((*p_color, prog_alpha))
                            screen.blit(prog_surf, (box_start_x, prog_y))
                        
                        # Línea de Entrada Divisoria (Nítida y Fija al trade)
                        pygame.draw.line(screen, color_divider, (box_start_x, entry_y), (box_start_x + rect_width, entry_y), 2)

                    # 1. Línea Horizontal de Entrada Extendida (Cian Neón Dotted)
                    entry_line_color = (0, 255, 255, 120)
                    for x in range(line_start_x, int(SCREEN_W * 0.72), 15):
                        pygame.draw.line(screen, entry_line_color, (x, entry_y), (min(x + 8, int(SCREEN_W * 0.72)), entry_y), 1)

                    # 2. Flecha de Entrada y Ratio (Cian Neón Intenso con Glow)
                    arrow_color = (0, 255, 255) # Cian Neón Puro
                    arrow_size = 18
                    if entry_vis >= 0 and entry_vis < len(visible_candles):
                        # Efecto de resplandor para la flecha
                        glow_color = (0, 255, 255, 80)
                        glow_surf = pygame.Surface((arrow_size + 10, arrow_size + 10), pygame.SRCALPHA)
                        
                        if g_dir == "BUY":
                            # Glow flecha arriba
                            points_glow = [(arrow_size//2 + 5, 0), (0, arrow_size + 5), (arrow_size + 10, arrow_size + 5)]
                            pygame.draw.polygon(glow_surf, glow_color, points_glow)
                            screen.blit(glow_surf, (line_start_x - arrow_size//2 - 5, entry_y - 2))
                            
                            # Flecha sólida
                            points = [(line_start_x, entry_y + 3), (line_start_x - arrow_size//2, entry_y + 20), (line_start_x + arrow_size//2, entry_y + 20)]
                            pygame.draw.polygon(screen, arrow_color, points)
                        else:
                            # Glow flecha abajo
                            points_glow = [(arrow_size//2 + 5, arrow_size + 5), (0, 0), (arrow_size + 10, 0)]
                            pygame.draw.polygon(glow_surf, glow_color, points_glow)
                            screen.blit(glow_surf, (line_start_x - arrow_size//2 - 5, entry_y - arrow_size - 3))
                            
                            # Flecha sólida
                            points = [(line_start_x, entry_y - 3), (line_start_x - arrow_size//2, entry_y - 20), (line_start_x + arrow_size//2, entry_y - 20)]
                            pygame.draw.polygon(screen, arrow_color, points)
                        
                        # Etiqueta de Ratio (Eliminada a petición del usuario)
                        pass

                    # 3. Línea de Stop Loss (Rojo Neón Intenso con Glow)
                    sl_color = (255, 30, 30) # Rojo Neón Intenso
                    sl_glow_color = (255, 30, 30, 60)
                    sl_line_alpha = 180 if grp.get("resolved") else 255
                    
                    # Dibujar resplandor de la línea
                    sl_glow_surf = pygame.Surface((box_end_x - box_start_x, 6), pygame.SRCALPHA)
                    pygame.draw.line(sl_glow_surf, sl_glow_color, (0, 3), (box_end_x - box_start_x, 3), 4)
                    screen.blit(sl_glow_surf, (box_start_x, grp_sl_y - 3))
                    
                    # Línea principal sólida y brillante
                    for x in range(box_start_x, box_end_x, 12):
                        pygame.draw.line(screen, sl_color, (x, grp_sl_y), (min(x + 8, box_end_x), grp_sl_y), 2)
                        
                    # 4. Niveles de Meta (Etiquetas Jerárquicas META 1, META 2, LÍMITE)
                    for idx, (lvl, lvl_y) in enumerate(zip(grp["levels"], tp_levels_y)):
                        rr_val = int(lvl['rr'])
                        if rr_val in [1, 2, 3, MAX_RR]:
                            tp_line_alpha = 30 if grp.get("resolved") or lvl.get("resolved") else 60
                            dotted = (200, 200, 200, tp_line_alpha)
                            for x in range(box_start_x, box_end_x, 20):
                                pygame.draw.line(screen, dotted, (x, lvl_y), (min(x + 4, box_end_x), lvl_y), 1)
                            
                            # Etiquetas de Meta
                            meta_text = "LÍMITE" if rr_val == MAX_RR else f"META {idx + 1}"
                            meta_surf = font_trade.render(meta_text, True, (200, 200, 200))
                            meta_surf.set_alpha(150)
                            meta_rect = meta_surf.get_rect()
                            
                            # Posicionamiento simétrico en el borde de la caja
                            if g_dir == "BUY":
                                meta_rect.bottomright = (box_end_x - 5, lvl_y - 2)
                            else:
                                meta_rect.topright = (box_end_x - 5, lvl_y + 2)
                            screen.blit(meta_surf, meta_rect)

                    # Línea de entrada corta (sobre la caja)
                    for x in range(box_start_x, box_end_x, 12):
                        pygame.draw.line(screen, (255, 255, 255, 80), (x, entry_y), (x + 6, entry_y), 1)
                        
                    # Destello (flash) local y limpio
                    if grp.get("flash"):
                        f = grp["flash"]
                        elapsed_flash = current_time - f["start"]
                        if elapsed_flash < 1000:
                            # Efecto de pulso y fade
                            glow_alpha = int(180 * (1.0 - elapsed_flash / 1000.0))
                            if f["color"] == GLOBAL_COLOR_BEAR: # SL
                                flash_y = entry_y if g_dir == "BUY" else grp_sl_y
                                flash_h = max(1, abs(grp_sl_y - entry_y))
                            else: # TP
                                flash_y = box_visual_top
                                flash_h = max(1, box_height)
                            
                            # Relleno de color flash
                            glow_surf = pygame.Surface((rect_width, flash_h), pygame.SRCALPHA)
                            glow_surf.fill((*f["color"], glow_alpha))
                            screen.blit(glow_surf, (box_start_x, flash_y))
                            
                            # Borde de impacto
                            pygame.draw.rect(screen, (*f["color"], glow_alpha), (box_start_x, flash_y, rect_width, flash_h), 3)

            if viewer_trade_active is not None and viewer_trade_active is not active_trade and viewer_trade_active.get("groups"):
                # Renderizar cajas simultáneas BUY y SELL independientes (solo si no es el mismo objeto que active_trade)
                last_candle_x = int(start_x + ((len(visible_candles) - 1) * spacing)) + candle_width
                label_offset = max(int(3 * spacing), 80)
                line_end_x = last_candle_x + label_offset
                
                v_box_w = max(int(spacing * 3.2), 55)
                
                # Obtener listas de RRs activos para calcular offsets
                buy_ids = sorted([k for k in viewer_trade_active["groups"].keys() if k.startswith("BUY")])
                sell_ids = sorted([k for k in viewer_trade_active["groups"].keys() if k.startswith("SELL")])

                for g_id, grp in viewer_trade_active["groups"].items():
                    # BORRADO QUIRÚRGICO: Si ya se resolvió y no está en flash, no se dibuja
                    is_flashing = False
                    if grp.get("flash"):
                        elapsed_flash = current_time - grp["flash"]["start"]
                        if elapsed_flash < 1000:
                            is_flashing = True
                    
                    if grp.get("resolved") and not is_flashing:
                        continue
                    
                    # Cada grupo tiene su propia entrada independiente
                    entry_y = center_y - int((grp["entry"] - view_center_price) * vertical_zoom)
                    entry_vis = grp["entry_index"] - visible_start_global
                    if entry_vis < 0:
                        line_start_x = 0
                    else:
                        line_start_x = int(start_x + (entry_vis * spacing)) + (candle_width // 2)
                    
                    g_dir = grp.get("dir", "BUY")
                    if g_dir == "BUY":
                        group_label_color = (38, 200, 154)
                        glow_color = (38, 255, 160)
                        # Offset basado en el índice del RR entre las compras
                        idx = buy_ids.index(g_id)
                        # Offset basado en el índice del RR entre las compras (Apilamiento compacto a la izquierda)
                        box_start_x = line_start_x - (idx + 2) * v_box_w - (idx + 1) * 5 - 3
                        box_end_x = box_start_x + v_box_w
                    else:
                        group_label_color = GLOBAL_COLOR_BEAR
                        glow_color = (255, 90, 40)
                        # Offset basado en el índice del RR entre las ventas (Apilamiento compacto a la derecha)
                        idx = sell_ids.index(g_id)
                        box_start_x = line_start_x + (idx + 1) * (v_box_w + 5) + 3
                        box_end_x = box_start_x + v_box_w
                    grp_sl_y = center_y - int((grp.get("sl", 0) - view_center_price) * vertical_zoom) if "sl" in grp else None
                    rect_width = box_end_x - box_start_x
                    tp_levels_y = [center_y - int((lvl["tp"] - view_center_price) * vertical_zoom) for lvl in grp.get("levels", [])]
                    
                    if grp_sl_y is not None and entry_y is not None:
                        if g_dir == "BUY":
                            grp_tp_y = min(tp_levels_y) if tp_levels_y else entry_y
                            tp_top = grp_tp_y
                            tp_height = entry_y - grp_tp_y
                            sl_top = entry_y
                            sl_height = grp_sl_y - entry_y
                        else:
                            grp_tp_y = max(tp_levels_y) if tp_levels_y else entry_y
                            tp_top = entry_y
                            tp_height = grp_tp_y - entry_y
                            sl_top = grp_sl_y
                            sl_height = entry_y - grp_sl_y
                    else:
                        continue # Protección contra valores None o no inicializados
                    box_visual_top = min(tp_top, sl_top)
                    box_visual_bottom = max(tp_top + max(0, tp_height), sl_top + max(0, sl_height))
                    box_height = box_visual_bottom - box_visual_top
                    # --- RENDERIZADO ESTILO TRADINGVIEW (CAPAS - VIEWERS) ---
                    if visible_candles:
                        current_price = visible_candles[-1]["close"]
                        current_price_y = center_y - int((current_price - view_center_price) * vertical_zoom)
                        
                        base_alpha = 40   # Opacidad base fija ligeramente menor para viewers
                        prog_alpha = 110  # Opacidad progreso dinámica para viewers
                        
                        color_profit = (0, 255, 120)  # Verde Neón
                        color_loss = (255, 30, 30)    # Rojo Neón
                        color_divider = (70, 70, 70)  # Gris oscuro nítido
                        
                        # 1. CAPA BASE FIJA (Estructura completa del trade)
                        base_surf = pygame.Surface((rect_width, box_height), pygame.SRCALPHA)
                        
                        # Dibujar bloque de Profit proyectado (TP)
                        pygame.draw.rect(base_surf, (*color_profit, base_alpha), 
                                       (0, tp_top - box_visual_top, rect_width, tp_height))
                        
                        # Dibujar bloque de Riesgo proyectado (SL)
                        pygame.draw.rect(base_surf, (*color_loss, base_alpha), 
                                       (0, sl_top - box_visual_top, rect_width, sl_height))
                        
                        screen.blit(base_surf, (box_start_x, box_visual_top))
                        
                        # 2. CAPA DINÁMICA DE PROGRESO (Desde entrada hasta precio actual)
                        prog_h = abs(current_price_y - entry_y)
                        if prog_h > 0:
                            prog_y = min(entry_y, current_price_y)
                            # Determinar si el progreso es Profit o Loss según dirección
                            is_profit = (g_dir == "BUY" and current_price_y <= entry_y) or (g_dir == "SELL" and current_price_y >= entry_y)
                            p_color = color_profit if is_profit else color_loss
                            
                            prog_surf = pygame.Surface((rect_width, prog_h), pygame.SRCALPHA)
                            prog_surf.fill((*p_color, prog_alpha))
                            screen.blit(prog_surf, (box_start_x, prog_y))
                        
                        pygame.draw.line(screen, color_divider, (box_start_x, entry_y), (box_start_x + rect_width, entry_y), 2)

                    # 1. Línea Horizontal de Entrada Extendida (Cian Neón Dotted)
                    entry_line_color = (0, 255, 255, 100)
                    for x in range(line_start_x, int(SCREEN_W * 0.72), 20):
                        pygame.draw.line(screen, entry_line_color, (x, entry_y), (min(x + 10, int(SCREEN_W * 0.72)), entry_y), 1)

                    # 2. Flecha de Entrada y Ratio (Cian Neón Intenso con Glow)
                    arrow_color = (0, 255, 255)
                    arrow_size = 16
                    if entry_vis >= 0 and entry_vis < len(visible_candles):
                        # Glow para flecha viewers
                        glow_color = (0, 255, 255, 60)
                        glow_surf = pygame.Surface((arrow_size + 8, arrow_size + 8), pygame.SRCALPHA)
                        
                        if g_dir == "BUY":
                            points_glow = [(arrow_size//2 + 4, 0), (0, arrow_size + 4), (arrow_size + 8, arrow_size + 4)]
                            pygame.draw.polygon(glow_surf, glow_color, points_glow)
                            screen.blit(glow_surf, (line_start_x - arrow_size//2 - 4, entry_y - 2))
                            
                            points = [(line_start_x, entry_y + 3), (line_start_x - arrow_size//2, entry_y + 18), (line_start_x + arrow_size//2, entry_y + 18)]
                            pygame.draw.polygon(screen, arrow_color, points)
                        else:
                            points_glow = [(arrow_size//2 + 4, arrow_size + 4), (0, 0), (arrow_size + 8, 0)]
                            pygame.draw.polygon(glow_surf, glow_color, points_glow)
                            screen.blit(glow_surf, (line_start_x - arrow_size//2 - 4, entry_y - arrow_size - 3))
                            
                            points = [(line_start_x, entry_y - 3), (line_start_x - arrow_size//2, entry_y - 18), (line_start_x + arrow_size//2, entry_y - 18)]
                            pygame.draw.polygon(screen, arrow_color, points)
                        
                        # Etiqueta Ratio para Viewers (Eliminada a petición del usuario)
                        pass

                    # 3. Línea de Stop Loss (Rojo Neón Intenso con Glow)
                    sl_color = (255, 30, 30) # Rojo Neón Intenso
                    sl_glow_color = (255, 30, 30, 50)
                    sl_line_alpha = 180 if grp.get("resolved") else 255
                    
                    sl_glow_surf = pygame.Surface((box_end_x - box_start_x, 6), pygame.SRCALPHA)
                    pygame.draw.line(sl_glow_surf, sl_glow_color, (0, 3), (box_end_x - box_start_x, 3), 4)
                    screen.blit(sl_glow_surf, (box_start_x, grp_sl_y - 3))
                    
                    for x in range(box_start_x, box_end_x, 12):
                        pygame.draw.line(screen, sl_color, (x, grp_sl_y), (min(x + 8, box_end_x), grp_sl_y), 2)
                        
                    # 4. Niveles de Meta (Etiquetas Jerárquicas META 1, META 2, LÍMITE - VIEWERS)
                    for idx, (lvl, lvl_y) in enumerate(zip(grp["levels"], tp_levels_y)):
                        tp_line_alpha = 30 if grp.get("resolved") or lvl.get("resolved") else 60
                        dotted = (200, 200, 200, tp_line_alpha)
                        for x in range(box_start_x, box_end_x, 20):
                            pygame.draw.line(screen, dotted, (x, lvl_y), (min(x + 4, box_end_x), lvl_y), 1)
                        
                        # Etiquetas de Meta para Viewers
                        rr_val = int(lvl['rr'])
                        if rr_val in [1, 2, 3, MAX_RR]:
                            meta_text = "LÍMITE" if rr_val == MAX_RR else f"META {idx + 1}"
                            meta_surf = font_trade.render(meta_text, True, (200, 200, 200))
                            meta_surf.set_alpha(120)
                            meta_rect = meta_surf.get_rect()
                            
                            # Posicionamiento simétrico
                            if g_dir == "BUY":
                                meta_rect.bottomright = (box_end_x - 5, lvl_y - 2)
                            else:
                                meta_rect.topright = (box_end_x - 5, lvl_y + 2)
                            screen.blit(meta_surf, meta_rect)

                    # Línea de entrada corta
                    for x in range(box_start_x, box_end_x, 12):
                        pygame.draw.line(screen, (200, 200, 200, 80), (x, entry_y), (x + 4, entry_y), 1)
                    # Destello (flash) local y limpio sobre la caja
                    if grp.get("flash"):
                        f = grp["flash"]
                        elapsed_flash = current_time - f["start"]
                        if elapsed_flash < 1000:
                            # Efecto de pulso y fade
                            glow_alpha = int(180 * (1.0 - elapsed_flash / 1000.0))
                            
                            if f["color"] == GLOBAL_COLOR_BEAR: # SL
                                flash_y = entry_y if g_dir == "BUY" else grp_sl_y
                                flash_h = max(1, abs(grp_sl_y - entry_y))
                            else: # TP
                                flash_y = box_visual_top
                                flash_h = max(1, box_height)

                            # Relleno de color flash
                            glow_surf = pygame.Surface((rect_width, flash_h), pygame.SRCALPHA)
                            glow_surf.fill((*f["color"], glow_alpha))
                            screen.blit(glow_surf, (box_start_x, flash_y))
                            
                            # Borde de impacto
                            pygame.draw.rect(screen, (*f["color"], glow_alpha), (box_start_x, flash_y, rect_width, flash_h), 3)
            # (Contador de viewers ya está integrado en el panel de arriba)
        # --- INDICADOR RECONEXIÓN TIKTOK ---
        if tiktok_chat.is_reconnecting():
            font_recon = pygame.font.SysFont("Arial", int(SCREEN_H * 0.014), bold=True)
            dots = "." * (1 + (current_time // 500) % 3)
            recon_txt = font_recon.render(f"RECONECTANDO{dots}", True, (255, 200, 0))
            screen.blit(recon_txt, (int(SCREEN_W * 0.02), int(SCREEN_H * 0.96)))
        # --- STREAK INDICATOR ---
        if streak_display and current_time - streak_display["start_time"] < STREAK_DISPLAY_DURATION:
            s_name = streak_display["name"]
            s_count = streak_display["streak"]
            s_elapsed = current_time - streak_display["start_time"]
            s_alpha = max(0.4, 1.0 - (s_elapsed / STREAK_DISPLAY_DURATION) * 0.6)
            # Notificación grande abajo centrada
            font_streak = pygame.font.SysFont("Arial", int(SCREEN_H * 0.030), bold=True)
            streak_txt = font_streak.render(f"{s_name} lleva {s_count} wins seguidos!", True, (255, 220, 50))
            # Cargar imagen fuego (cache)
            if not hasattr(pygame, '_fire_img_loaded'):
                pygame._fire_img_loaded = True
                fire_path = os.path.join(BASE_DIR, "assets", "fire.png")
                if os.path.exists(fire_path):
                    pygame._fire_img = pygame.image.load(fire_path).convert_alpha()
                    fire_size = int(SCREEN_H * 0.035)
                    pygame._fire_img = pygame.transform.smoothscale(pygame._fire_img, (fire_size, fire_size))
                else:
                    pygame._fire_img = None
            fire_img = pygame._fire_img
            fire_w = fire_img.get_width() if fire_img else 0
            streak_w = streak_txt.get_width() + fire_w * 2 + 50
            streak_h = streak_txt.get_height() + 20
            s_x = SCREEN_W // 2 - streak_w // 2
            s_y = int(SCREEN_H * 0.88)
            # Fondo con gradiente dorado
            streak_bg = pygame.Surface((streak_w, streak_h), pygame.SRCALPHA)
            for row in range(streak_h):
                a = int(200 * s_alpha * (0.8 + 0.2 * (row / streak_h)))
                pygame.draw.line(streak_bg, (40, 25, 0, a), (0, row), (streak_w, row))
            screen.blit(streak_bg, (s_x, s_y))
            # Borde dorado pulsante
            pulse = int(220 + 35 * math.sin(current_time / 150.0))
            pygame.draw.rect(screen, (pulse, int(pulse * 0.75), 0), (s_x, s_y, streak_w, streak_h), 2, border_radius=6)
            # Glow exterior
            glow_s = pygame.Surface((streak_w + 8, streak_h + 8), pygame.SRCALPHA)
            glow_s.fill((255, 180, 0, int(25 * s_alpha)))
            screen.blit(glow_s, (s_x - 4, s_y - 4))
            # Fuego izquierdo + texto + fuego derecho
            content_x = s_x + 15
            content_y = s_y + (streak_h - streak_txt.get_height()) // 2
            if fire_img:
                screen.blit(fire_img, (content_x, s_y + (streak_h - fire_w) // 2))
                content_x += fire_w + 8
            screen.blit(streak_txt, (content_x, content_y))
            if fire_img:
                screen.blit(fire_img, (content_x + streak_txt.get_width() + 8, s_y + (streak_h - fire_w) // 2))
        elif streak_display and current_time - streak_display["start_time"] >= STREAK_DISPLAY_DURATION:
            streak_display = None
        # --- TEXTO DE RESULTADO (SIN FLASH GLOBAL) ---
        if flash_active:
            flash_elapsed = current_time - flash_start_time
            if flash_elapsed >= FLASH_DURATION:
                flash_active = False
            else:
                # Fade out (opacidad disminuye)
                alpha = max(0, 200 - int(200 * (flash_elapsed / FLASH_DURATION)))
                
                # Texto grande en el centro, sin fondo de color en toda la pantalla
                font_flash = pygame.font.SysFont("Arial", int(SCREEN_H * 0.09), bold=True)
                # Sombra del texto para legibilidad
                flash_shadow = font_flash.render(flash_text, True, (0, 0, 0))
                flash_shadow.set_alpha(alpha // 2)
                flash_txt = font_flash.render(flash_text, True, flash_color)
                flash_txt.set_alpha(alpha)
                
                flash_rect = flash_txt.get_rect(center=(int(SCREEN_W * 0.50), int(SCREEN_H * 0.45)))
                screen.blit(flash_shadow, (flash_rect.x + 4, flash_rect.y + 4))
                screen.blit(flash_txt, flash_rect)

        # --- OVERLAY: EVENTOS DE LIQUIDEZ POR LIKES ---
        if liquidity_event_active is not None:
            _ev = liquidity_event_active
            _elapsed = current_time - _ev["start_time"]
            _real_likes = tiktok_chat.get_like_count() if tiktok_chat is not None else 0
            _current_likes = _real_likes + simulated_likes

            # Fondo casi solido (oscurece bastante mas que antes para que el texto resalte)
            liq_overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            liq_overlay.fill((3, 5, 10, 235))
            screen.blit(liq_overlay, (0, 0))

            # --- Particulas cyan decorativas (le dan vida al fondo negro) ---
            for p in liquidity_particles:
                p["y"] -= p["speed"]
                if p["y"] < -5:
                    p["y"] = SCREEN_H + 5
                    p["x"] = random.uniform(0, SCREEN_W)
                ps = pygame.Surface((p["size"] * 2, p["size"] * 2), pygame.SRCALPHA)
                pygame.draw.circle(ps, (0, 210, 255, p["alpha"]), (p["size"], p["size"]), p["size"])
                screen.blit(ps, (int(p["x"]), int(p["y"])))

            # --- Logo / marca LEAN FX arriba del cartel ---
            font_liq_brand = pygame.font.SysFont("Arial", int(SCREEN_H * 0.024), bold=True)
            brand_y = int(SCREEN_H * 0.10)
            if avatar_img is not None:
                brand_av_size = int(SCREEN_H * 0.07)
                brand_av = pygame.transform.smoothscale(avatar_img, (brand_av_size, brand_av_size))
                brand_txt = font_liq_brand.render("LEAN FX", True, (0, 220, 255))
                total_w = brand_av_size + 10 + brand_txt.get_width()
                bx = SCREEN_W // 2 - total_w // 2
                screen.blit(brand_av, (bx, brand_y - brand_av_size // 2))
                screen.blit(brand_txt, (bx + brand_av_size + 10, brand_y - brand_txt.get_height() // 2))
            else:
                brand_txt = font_liq_brand.render("LEAN FX", True, (0, 220, 255))
                screen.blit(brand_txt, brand_txt.get_rect(center=(SCREEN_W // 2, brand_y)))

            font_liq_title = pygame.font.SysFont("Arial", int(SCREEN_H * 0.048), bold=True)
            font_liq_sub = pygame.font.SysFont("Arial", int(SCREEN_H * 0.022), bold=True)
            font_liq_count = pygame.font.SysFont("Arial", int(SCREEN_H * 0.11), bold=True)  # Contador de likes: mas grande, legible en vertical
            font_liq_levels = pygame.font.SysFont("Arial", int(SCREEN_H * 0.032), bold=True)  # Niveles/meta: mas grande, legible en vertical

            if _ev["type"] == "A":
                title_txt = font_liq_title.render("SIN LIQUIDEZ EN EL MERCADO", True, (255, 60, 60))
                screen.blit(title_txt, title_txt.get_rect(center=(SCREEN_W // 2, int(SCREEN_H * 0.30))))
                sub_txt = font_liq_sub.render("PARA CONTINUAR, DEN LIKES A LA PANTALLA", True, (255, 220, 0))
                screen.blit(sub_txt, sub_txt.get_rect(center=(SCREEN_W // 2, int(SCREEN_H * 0.38))))
                count_txt = font_liq_count.render(f"{_current_likes} / {LIQUIDITY_A_TARGET}", True, (255, 255, 255))
                screen.blit(count_txt, count_txt.get_rect(center=(SCREEN_W // 2, int(SCREEN_H * 0.49))))
                # Barra mas grande (era 0.4 ancho x 0.03 alto, ahora 0.55 x 0.05 - foco visual principal)
                bar_w = int(SCREEN_W * 0.55)
                bar_h = int(SCREEN_H * 0.05)
                bar_x = SCREEN_W // 2 - bar_w // 2
                bar_y = int(SCREEN_H * 0.58)
                pygame.draw.rect(screen, (30, 32, 42), (bar_x, bar_y, bar_w, bar_h), border_radius=10)
                fill_pct = min(1.0, _current_likes / LIQUIDITY_A_TARGET)
                if fill_pct > 0:
                    pygame.draw.rect(screen, (0, 220, 255), (bar_x, bar_y, int(bar_w * fill_pct), bar_h), border_radius=10)
                pygame.draw.rect(screen, (255, 255, 255), (bar_x, bar_y, bar_w, bar_h), 2, border_radius=10)
                remaining_s = max(0, (LIQUIDITY_A_TIMEOUT - _elapsed) // 1000)
                timeout_txt = font_liq_sub.render(f"Reanuda automaticamente en {remaining_s}s", True, (150, 150, 160))
                screen.blit(timeout_txt, timeout_txt.get_rect(center=(SCREEN_W // 2, int(SCREEN_H * 0.68))))

            elif _ev["type"] == "C":
                title_txt = font_liq_title.render("RONDA DE LIKES", True, (0, 220, 255))
                screen.blit(title_txt, title_txt.get_rect(center=(SCREEN_W // 2, int(SCREEN_H * 0.26))))
                count_txt = font_liq_count.render(f"{_current_likes}", True, (255, 255, 255))
                screen.blit(count_txt, count_txt.get_rect(center=(SCREEN_W // 2, int(SCREEN_H * 0.38))))
                lvl_y = int(SCREEN_H * 0.50)
                _flash_start = _ev.get("flash_start")
                for lvl_idx, (lvl_likes, lvl_bonus) in enumerate(LIQUIDITY_C_LEVELS):
                    reached = lvl_idx <= _ev["reached_level"]
                    # Flash: el nivel recien alcanzado crece y brilla un instante
                    is_new = reached and lvl_idx == _ev["reached_level"] and _flash_start is not None and current_time - _flash_start < 600
                    lvl_color = (38, 220, 170) if reached else (150, 150, 165)
                    lvl_size = int(SCREEN_H * (0.038 if is_new else 0.032))
                    font_lvl = pygame.font.SysFont("Arial", lvl_size, bold=True)
                    prefix = "\u2713 " if reached else ""
                    lvl_txt = font_lvl.render(f"{prefix}{lvl_likes} likes -> +{lvl_bonus} FXP", True, lvl_color)
                    screen.blit(lvl_txt, lvl_txt.get_rect(center=(SCREEN_W // 2, lvl_y + lvl_idx * int(SCREEN_H * 0.06))))
                remaining_s = max(0, (LIQUIDITY_C_DURATION - _elapsed) / 1000)
                timer_txt = font_liq_sub.render(f"{remaining_s:.1f}s", True, (255, 220, 0))
                screen.blit(timer_txt, timer_txt.get_rect(center=(SCREEN_W // 2, int(SCREEN_H * 0.70))))

            elif _ev["type"] == "D":
                title_txt = font_liq_title.render("LLENEN LA BARRA DE LIKES", True, (255, 220, 0))
                screen.blit(title_txt, title_txt.get_rect(center=(SCREEN_W // 2, int(SCREEN_H * 0.28))))
                sub_txt = font_liq_levels.render(f"Meta: {LIQUIDITY_D_TARGET} likes -> +{LIQUIDITY_D_BONUS} FXP", True, (0, 220, 255))
                screen.blit(sub_txt, sub_txt.get_rect(center=(SCREEN_W // 2, int(SCREEN_H * 0.37))))
                # Barra mas grande (era 0.5 ancho x 0.05 alto, ahora 0.6 x 0.07)
                bar_w = int(SCREEN_W * 0.6)
                bar_h = int(SCREEN_H * 0.07)
                bar_x = SCREEN_W // 2 - bar_w // 2
                bar_y = int(SCREEN_H * 0.46)
                pygame.draw.rect(screen, (30, 32, 42), (bar_x, bar_y, bar_w, bar_h), border_radius=12)
                fill_pct = min(1.0, _current_likes / LIQUIDITY_D_TARGET)
                bar_color = (38, 220, 170) if fill_pct >= 1.0 else (255, 180, 0)
                if fill_pct > 0:
                    pygame.draw.rect(screen, bar_color, (bar_x, bar_y, int(bar_w * fill_pct), bar_h), border_radius=12)
                pygame.draw.rect(screen, (255, 255, 255), (bar_x, bar_y, bar_w, bar_h), 2, border_radius=12)
                count_txt = font_liq_sub.render(f"{_current_likes} / {LIQUIDITY_D_TARGET}", True, (255, 255, 255))
                screen.blit(count_txt, count_txt.get_rect(center=(SCREEN_W // 2, bar_y + bar_h + int(SCREEN_H * 0.045))))
                remaining_s = max(0, (LIQUIDITY_D_DURATION - _elapsed) / 1000)
                timer_txt = font_liq_sub.render(f"{remaining_s:.1f}s", True, (200, 200, 210))
                screen.blit(timer_txt, timer_txt.get_rect(center=(SCREEN_W // 2, int(SCREEN_H * 0.68))))

        # --- GUÍA VISUAL DE COMANDOS (Margen Derecho - HUD SUPREMO) ---
        if game_started and liquidity_event_active is None:
            if guide_animation_start == 0:
                guide_animation_start = pygame.time.get_ticks()
            
            elapsed = curr_ticks - guide_animation_start
            anim_progress = min(1.0, elapsed / 1000.0) 
            
            # 1. PANEL HUD CIBERNÉTICO (Fondo con Matriz de Puntos y Rejilla)
            panel_surf = pygame.Surface((guide_w, guide_h), pygame.SRCALPHA)
            # Fondo ultra-profundo translúcido con desenfoque simulado
            pygame.draw.rect(panel_surf, (5, 8, 15, 235), (0, 0, guide_w, guide_h), border_radius=6)
            
            # Matriz de Puntos (Cyber Grid)
            dot_color = (0, 200, 255, 30)
            for dx in range(0, guide_w, 18):
                for dy in range(0, guide_h, 18):
                    pygame.draw.circle(panel_surf, dot_color, (dx, dy), 1)
            
            # Rejilla de Coordenadas (Más sutil)
            grid_color = (0, 220, 255, 10)
            for i in range(0, guide_w, 40):
                pygame.draw.line(panel_surf, grid_color, (i, 0), (i, guide_h), 1)
            for i in range(0, guide_h, 40):
                pygame.draw.line(panel_surf, grid_color, (0, i), (guide_w, i), 1)

            # 2. ESQUINAS TÉCNICAS (Corner Brackets)
            bracket_color = (0, 255, 255)
            b_len = 15
            b_thick = 2
            # Top-Left
            pygame.draw.lines(panel_surf, bracket_color, False, [(0, b_len), (0, 0), (b_len, 0)], b_thick)
            # Top-Right
            pygame.draw.lines(panel_surf, bracket_color, False, [(guide_w-b_len, 0), (guide_w, 0), (guide_w, b_len)], b_thick)
            # Bottom-Left
            pygame.draw.lines(panel_surf, bracket_color, False, [(0, guide_h-b_len), (0, guide_h), (b_len, guide_h)], b_thick)
            # Bottom-Right
            pygame.draw.lines(panel_surf, bracket_color, False, [(guide_w-b_len, guide_h), (guide_w, guide_h), (guide_w, guide_h-b_len)], b_thick)
            
            # Brillo de Borde Neón (Refinado)
            for i in range(2):
                glow_a = 100 // (i + 1)
                pygame.draw.rect(panel_surf, (0, 220, 255, glow_a), (-i, -i, guide_w + i*2, guide_h + i*2), 1, border_radius=6 + i)
            
            panel_surf.set_alpha(int(255 * anim_progress))
            screen.blit(panel_surf, (guide_x - 6, guide_y - 6))
            
            # 3. TÍTULO TERMINAL HACKING
            font_guide_title = pygame.font.SysFont("Consolas", int(SCREEN_H * 0.028), bold=True)
            font_guide_subtitle = pygame.font.SysFont("Consolas", int(SCREEN_H * 0.016))
            font_deco = pygame.font.SysFont("Consolas", 9)
            
            # 0. TELEMETRÍA DE RONDAS Y VELA (Minimapa de tiempo)
            if anim_progress > 0.1:
                round_num = len(candles) - initial_candle_count + 1
                font_tel = pygame.font.SysFont("Consolas", int(SCREEN_H * 0.016), bold=True)
                
                # --- NUEVA TELEMETRÍA SUPERIOR DERECHA (RONDA Y TIMER) ---
                
                # Fondo translúcido para Telemetría
                tel_bg = pygame.Surface((tel_box_w, tel_box_h), pygame.SRCALPHA)
                pygame.draw.rect(tel_bg, (5, 10, 20, 200), (0, 0, tel_box_w, tel_box_h), border_radius=6)
                pygame.draw.rect(tel_bg, (0, 255, 255, 50), (0, 0, tel_box_w, tel_box_h), 1, border_radius=6)
                screen.blit(tel_bg, (tel_box_x, tel_box_y))

                # Texto de Ronda
                ronda_txt = font_tel.render(f"RONDA: #{round_num:02d}", True, (0, 255, 255))
                screen.blit(ronda_txt, (tel_box_x + 6, tel_box_y + 6))
                
                # Barra de tiempo de vela (Minimapa)
                candle_elapsed = curr_ticks - last_candle_time
                candle_pct = min(1.0, candle_elapsed / CANDLE_DURATION)
                
                # --- TENSIÓN EN EL TEMPORIZADOR (ÚLTIMO SEGUNDO) ---
                rem_ms = max(0, CANDLE_DURATION - candle_elapsed)
                is_tense = rem_ms < 1000 and rem_ms > 0
                
                if is_tense:
                    # Parpadeo agresivo y sacudida
                    blink = (curr_ticks // 100) % 2 == 0
                    bar_color = (255, 50, 50) if blink else (0, 220, 255)
                    rem_color = (255, 100, 100) if blink else (150, 180, 200)
                    shake_x = random.randint(-1, 1)
                    shake_y = random.randint(-1, 1)
                else:
                    bar_color = (0, 220, 255)
                    rem_color = (150, 180, 200)
                    shake_x, shake_y = 0, 0

                bar_w = tel_box_w - 16
                bar_h = 6
                pygame.draw.rect(screen, (20, 30, 50), (tel_box_x + 8 + shake_x, tel_box_y + 45 + shake_y, bar_w, bar_h), border_radius=3)
                pygame.draw.rect(screen, bar_color, (tel_box_x + 8 + shake_x, tel_box_y + 45 + shake_y, int(bar_w * candle_pct), bar_h), border_radius=3)
                
                # Tiempo restante
                rem_txt = font_tel.render(f"NEXT: {rem_ms/1000:.1f}s", True, rem_color)
                screen.blit(rem_txt, (tel_box_x + 8 + shake_x, tel_box_y + 60 + shake_y))

                # --- INDICADOR CIRCULAR DE CICLO ---
                circle_x = tel_box_x + 8 + rem_txt.get_width() + 10 + shake_x
                circle_y = tel_box_y + 70 + shake_y
                radius = 6
                pygame.draw.circle(screen, (30, 45, 60), (circle_x, circle_y), radius, 1)
                # Arco de progreso (0 a 360 grados)
                angle = 360 * candle_pct
                rect_arc = pygame.Rect(circle_x - radius, circle_y - radius, radius * 2, radius * 2)
                pygame.draw.arc(screen, (0, 255, 255), rect_arc, math.radians(-90), math.radians(-90 + angle), 2)

            if anim_progress > 0.2:
                # Efecto Parpadeo Cursor Terminal
                title_text = "PARA JUGAR"
                cursor = "_" if (curr_ticks // 600) % 2 == 0 else " "
                
                # Resplandor de Título
                for off in [(-1,0), (1,0), (0,-1), (0,1)]:
                    glow_t = font_guide_title.render(title_text + cursor, True, (0, 100, 150))
                    screen.blit(glow_t, (guide_x, guide_y + off[1]))
                
                guide_title_txt = font_guide_title.render(title_text + cursor, True, (255, 255, 255))
                screen.blit(guide_title_txt, (guide_x, guide_y))
                
                # Subtítulo con prefijo de sistema y efecto resplandor
                status_text = "> CMD_LINK: ACTIVE"
                for off in [(-1,0), (1,0), (0,-1), (0,1)]:
                    glow_s = font_guide_subtitle.render(status_text, True, (0, 150, 100))
                    screen.blit(glow_s, (guide_x + off[0], guide_y + int(SCREEN_H * 0.055) + off[1]))
                
                guide_subtitle_txt = font_guide_subtitle.render(status_text, True, (0, 255, 150))
                screen.blit(guide_subtitle_txt, (guide_x, guide_y + int(SCREEN_H * 0.055)))

                # Nueva línea: Guía de interacción para espectadores
                interaction_text = "> USA EL CHAT"
                for off in [(-1,0), (1,0), (0,-1), (0,1)]:
                    glow_i = font_guide_subtitle.render(interaction_text, True, (0, 150, 100))
                    screen.blit(glow_i, (guide_x + off[0], guide_y + int(SCREEN_H * 0.085) + off[1]))
                
                interaction_txt = font_guide_subtitle.render(interaction_text, True, (0, 255, 150))
                screen.blit(interaction_txt, (guide_x, guide_y + int(SCREEN_H * 0.085)))
                
                # Decoración Hexadecimal diminuta
                hex_deco = font_deco.render("ID:" + hex(curr_ticks % 0xFFFF)[2:].upper() + " L_VER:3.8", True, (0, 150, 180))
                screen.blit(hex_deco, (guide_x, guide_y - 18))

            # 4. TARJETAS DE DATOS (Cyber Cards)
            if anim_progress > 0.4:
                commands = [
                    ("SUBE 1", "1:1 R:R", (0, 255, 200)),
                    ("SUBE 2", "1:2 R:R", (0, 255, 200)),
                    ("SUBE 3", "1:3 R:R", (0, 255, 200)),
                    ("BAJA 1", "1:1 R:R", (255, 50, 80)),
                    ("BAJA 2", "1:2 R:R", (255, 50, 80)),
                    ("BAJA 3", "1:3 R:R", (255, 50, 80)),
                ]
                
                font_cmd = pygame.font.SysFont("Consolas", int(SCREEN_H * 0.030), bold=True)
                font_target = pygame.font.SysFont("Consolas", int(SCREEN_H * 0.016), bold=True)
                
                item_y = guide_y + int(SCREEN_H * 0.11)
                card_w = guide_w - 16
                card_h = int(SCREEN_H * 0.052)  # Tarjetas más altas
                card_spacing = int(SCREEN_H * 0.062)  # Mayor separación vertical
                
                for i, (cmd, target, color) in enumerate(commands):
                    if anim_progress < 0.4 + (i * 0.07): continue
                    
                    # Mini-Tarjeta translúcida con bordes técnicos
                    card_rect = pygame.Rect(guide_x - 4, item_y - 4, card_w, card_h)
                    pygame.draw.rect(screen, (15, 25, 45, 120), card_rect, border_radius=4)
                    pygame.draw.rect(screen, (*color, 40), card_rect, 1, border_radius=4)
                    
                    # Marcas de Telemetría diminutas en esquinas de tarjeta
                    pygame.draw.line(screen, (*color, 100), (card_rect.x, card_rect.y), (card_rect.x+4, card_rect.y), 1)
                    pygame.draw.line(screen, (*color, 100), (card_rect.x, card_rect.y), (card_rect.x, card_rect.y+4), 1)
                    
                    # Icono Hexagonal Brillante (Centrado verticalmente)
                    hx_points = []
                    hx_size = 6
                    cy = card_rect.centery
                    for angle in range(0, 360, 60):
                        rad = math.radians(angle)
                        hx_points.append((guide_x + 8 + hx_size * math.cos(rad), cy + hx_size * math.sin(rad)))
                    pygame.draw.polygon(screen, color, hx_points, 0)
                    pygame.draw.polygon(screen, (255, 255, 255), hx_points, 1)
                    
                    # Texto Comando con sutil Glow
                    cmd_txt = font_cmd.render(cmd, True, color)
                    cmd_y = card_rect.centery - cmd_txt.get_height() // 2
                    
                    for off in [(-1,0), (1,0)]:
                        glow_c = font_cmd.render(cmd, True, (*color, 50))
                        screen.blit(glow_c, (guide_x + 24 + off[0], cmd_y))
                    
                    screen.blit(cmd_txt, (guide_x + 24, cmd_y))
                    
                    # R:R alineado a la DERECHA EXTREMA
                    rr_txt = font_target.render(target, True, (200, 220, 240))
                    rr_y = card_rect.centery - rr_txt.get_height() // 2
                    screen.blit(rr_txt, (card_rect.right - rr_txt.get_width() - 40, rr_y))

                    # Código de telemetría diminuto (falso)
                    tel_txt = font_deco.render(f"TK-{i}0{i}", True, (*color, 80))
                    screen.blit(tel_txt, (card_rect.right - tel_txt.get_width() - 5, card_rect.y + 4))

                    item_y += card_spacing
                
                # 5. INDICADOR DE ESCALABILIDAD R:R (ACTUALIZADO 1:10 - MÁXIMA VISIBILIDAD)
                if anim_progress > 0.7:
                    # Tipografía más grande para impacto en móviles
                    font_scaling = pygame.font.SysFont("Consolas", int(SCREEN_H * 0.022), bold=True)
                    rr_scale_text = "> ESCALA HASTA 1:10 R:R"
                    
                    # Banner de fondo translúcido tipo alerta
                    banner_w = guide_w - 4
                    banner_h = int(SCREEN_H * 0.045)
                    banner_rect = pygame.Rect(guide_x - 4, item_y - 8, banner_w, banner_h)
                    
                    # Fondo oscuro con borde amarillo neón pulsante
                    pygame.draw.rect(screen, (10, 20, 35, 220), banner_rect, border_radius=6)
                    pulse = (math.sin(curr_ticks * 0.01) + 1) / 2
                    glow_val = int(100 + 155 * pulse)
                    pygame.draw.rect(screen, (255, 215, 0, glow_val), banner_rect, 2, border_radius=6)
                    
                    # Efecto de resplandor para el texto central
                    for off in [(-1,0), (1,0), (0,-1), (0,1)]:
                        glow_rr = font_scaling.render(rr_scale_text, True, (180, 120, 0))
                        screen.blit(glow_rr, (guide_x + 6 + off[0], banner_rect.centery - glow_rr.get_height() // 2 + off[1]))
                    
                    rr_scale_surf = font_scaling.render(rr_scale_text, True, (255, 255, 0))
                    # Alineado a la izquierda dentro del banner con pequeño margen
                    screen.blit(rr_scale_surf, (guide_x + 6, banner_rect.centery - rr_scale_surf.get_height() // 2))
                
                # 6. INDICADOR DE COOLDOWN / ESTADO DE PARTICIPACIÓN
                if anim_progress > 0.8:
                    # Ajuste de posición para que el HUD respire (borde inferior)
                    # Bajar el texto de telemetría y estado para evitar solapamiento con la tarjeta BAJA 3
                    status_y = guide_y + guide_h - 35
                    
                    # --- TELEMETRÍA DE VOLATILIDAD DINÁMICA (NUEVO) ---
                    if len(candles) > 5:
                        avg_vol = sum(c["high"] - c["low"] for c in candles[-5:]) / 5
                    else:
                        avg_vol = 8.0
                    
                    curr_vol = current_candle["high"] - current_candle["low"]
                    
                    if curr_vol > avg_vol * 1.6:
                        vol_label, vol_color = "RIESGO: ACTIVO", (255, 80, 80)
                    elif curr_vol > avg_vol * 0.9:
                        vol_label, vol_color = "VOLATILIDAD: ALTA", (255, 180, 50)
                    else:
                        vol_label, vol_color = "MERCADO: ESTABLE", (0, 255, 150)
                    
                    font_vol = pygame.font.SysFont("Consolas", int(SCREEN_H * 0.014), bold=True)
                    vol_surf = font_vol.render(vol_label, True, vol_color)
                    
                    # Contenedor inferior para volatilidad (Cyber Box)
                    vol_bg_rect = pygame.Rect(guide_x - 4, status_y - 45, guide_w - 4, 28)
                    pygame.draw.rect(screen, (5, 10, 20, 180), vol_bg_rect, border_radius=4)
                    
                    # --- EFECTO NEÓN DINÁMICO PARA VOLATILIDAD ALTA ---
                    pulse = (math.sin(curr_ticks * 0.01) + 1) / 2
                    if vol_label == "RIESGO: ACTIVO":
                        glow_a = int(100 + 155 * pulse)
                        pygame.draw.rect(screen, (*vol_color, glow_a), vol_bg_rect, 2, border_radius=4)
                    elif vol_label == "VOLATILIDAD: ALTA":
                        glow_a = int(50 + 100 * pulse)
                        pygame.draw.rect(screen, (*vol_color, glow_a), vol_bg_rect, 1, border_radius=4)
                    else:
                        pygame.draw.rect(screen, (*vol_color, 80), vol_bg_rect, 1, border_radius=4)
                    
                    # Punto de estado parpadeante sutil
                    if (curr_ticks // 500) % 2 == 0:
                        pygame.draw.circle(screen, vol_color, (guide_x + 8, status_y - 31), 2)
                    
                    # Alineación del texto centrada y con aire dentro de su tarjeta
                    vol_rect = vol_surf.get_rect(center=(vol_bg_rect.centerx, vol_bg_rect.centery))
                    screen.blit(vol_surf, vol_rect)

                    # Lógica de estado
                    if zone_frozen:
                        status_msg = "VOTACIÓN ABIERTA"
                        status_color = (0, 255, 150)
                    elif active_trade or viewer_trade_active:
                        status_msg = "OPERACIÓN EN CURSO"
                        status_color = (255, 150, 0)
                    elif curr_ticks - bot_last_trade_time < BOT_COOLDOWN and bot_last_trade_time > 0:
                        status_msg = "SISTEMA EN COOLDOWN"
                        status_color = (255, 50, 50)
                    else:
                        status_msg = "SISTEMA: LISTO"
                        status_color = (0, 255, 255)
                    
                    # Renderizar barra de estado
                    font_status = pygame.font.SysFont("Consolas", int(SCREEN_H * 0.018), bold=True)
                    # Fondo sutil para el estado
                    status_bg = pygame.Rect(guide_x - 4, status_y - 12, guide_w - 4, 26)
                    pygame.draw.rect(screen, (5, 15, 30, 180), status_bg, border_radius=4)
                    
                    # Texto de estado parpadeante si es crítico
                    show_status = True
                    if status_msg in ["VOTACIÓN ABIERTA", "SISTEMA EN COOLDOWN"]:
                        show_status = (curr_ticks // 400) % 2 == 0
                    
                    if show_status:
                        status_txt = font_status.render(status_msg, True, status_color)
                        screen.blit(status_txt, status_txt.get_rect(center=(guide_x + (guide_w-16)//2, status_y + 1)))
                    
                    # --- TICKER DE EVENTOS ESTILO CONSOLA (NUEVO) ---
                    ticker_h = 24
                    ticker_y = status_y + 18
                    ticker_bg = pygame.Rect(guide_x - 4, ticker_y, guide_w - 4, ticker_h)
                    pygame.draw.rect(screen, (2, 5, 10, 220), ticker_bg, border_radius=4)
                    pygame.draw.rect(screen, (0, 255, 255, 30), ticker_bg, 1, border_radius=4)
                    
                    if ticker_events:
                        # Mostrar solo el último evento con efecto de scroll/fade
                        last_event = ticker_events[-1]
                        time_since = curr_ticks - last_event["time"]
                        
                        if time_since < 5000: # Mostrar por 5 segundos
                            # Efecto de "escritura" tipo terminal
                            chars_to_show = int(time_since / 30)
                            display_msg = "> " + last_event["msg"][:chars_to_show]
                            
                            # Cursor parpadeante al final
                            if (curr_ticks // 300) % 2 == 0:
                                display_msg += "_"
                                
                            font_ticker = pygame.font.SysFont("Consolas", int(SCREEN_H * 0.014))
                            ticker_surf = font_ticker.render(display_msg, True, (0, 255, 255))
                            screen.blit(ticker_surf, (ticker_bg.x + 8, ticker_bg.y + 2))
                        else:
                            # Si no hay eventos recientes, mostrar un mensaje de sistema
                            font_ticker = pygame.font.SysFont("Consolas", int(SCREEN_H * 0.020))
                            idle_msg = f"> SYSTEM_IDLE_{hex(curr_ticks//1000)[2:].upper()}"
                            ticker_surf = font_ticker.render(idle_msg, True, (0, 100, 120))
                            screen.blit(ticker_surf, (ticker_bg.x + 10, ticker_bg.y + 4))
                    else:
                        font_ticker = pygame.font.SysFont("Consolas", int(SCREEN_H * 0.020))
                        screen.blit(font_ticker.render("> WAITING FOR EVENTS...", True, (0, 100, 120)), (ticker_bg.x + 10, ticker_bg.y + 4))
            
            # 5. SCANLINE Y EFECTO VISUAL CINEMATOGRÁFICO
            # Línea de escaneo más lenta y sutil
            scan_time = (curr_ticks % 6000) / 6000.0  # Mucho más lento (6 segundos por ciclo)
            scan_y = guide_y + (guide_h * scan_time)
            pygame.draw.line(screen, (0, 255, 255, 20), (guide_x - 10, scan_y), (guide_x + guide_w - 10, scan_y), 1)
            
            # Línea de animación de entrada (solo al inicio)
            if anim_progress < 1.0:
                entry_y = guide_y + (guide_h * anim_progress)
                pygame.draw.line(screen, (255, 255, 255, 120), (guide_x - 10, entry_y), (guide_x + guide_w - 10, entry_y), 2)

            # --- ACTUALIZACIÓN DE ANALYTICS (FASE 2) ---
            # Iniciar sesión automáticamente si TikTok se conecta y no hay una activa
            # (Eliminado de aquí y movido a nivel global)
            
            if current_session_id is not None and current_time - last_analytics_update > 10000: # Cada 10 segundos
                last_analytics_update = current_time
                try:
                    viewers = tiktok_chat.get_viewer_count() if tiktok_chat.connected else 0
                    # Si no hay conexión real, podemos usar un valor simulado si el usuario quiere,
                    # pero por ahora dejamos 0 o lo que devuelva el cliente.
                    likes = tiktok_chat.session_total_likes + simulated_likes
                    msgs = tiktok_chat.session_total_messages
                    parts = len(tiktok_chat.session_unique_participants)
                    update_session_metrics(current_session_id, viewers, likes, msgs, parts)
                except Exception as e:
                    print(f"[ANALYTICS] Error actualizando métricas: {e}")

        pygame.display.flip()

    # --- FINALIZACIÓN DE LA APP ---
    # Finalizar sesión de Analytics solo al cerrar la aplicación definitivamente
    if current_session_id is not None:
        try:
            end_session(current_session_id)
            print(f"[ANALYTICS] Sesión finalizada definitivamente ID: {current_session_id}")
            current_session_id = None
        except Exception as e:
            print(f"[ANALYTICS] Error finalizando sesión: {e}")

    if sound_game_music is not None:
        sound_game_music.stop()
    if music_playing:
        pygame.mixer.music.stop()
        music_playing = False

pygame.quit()
