"""
Módulo de conexión a TikTok Live Chat
Lee mensajes del chat en tiempo real y detecta votos BUY/SELL

Requisito: pip install TikTokLive
"""
import threading
import asyncio
import time
import os
import re
import urllib.request

from shared_paths import AVATARS_DIR

def download_avatar(username, url):
    """Descarga avatar de TikTok y lo guarda localmente"""
    if not url:
        return
    filepath = os.path.join(AVATARS_DIR, f"{username}.jpg")
    if os.path.exists(filepath):
        return  # Ya lo tenemos
    try:
        urllib.request.urlretrieve(url, filepath)
        print(f"[AVATAR] Descargado: {username}")
    except Exception as e:
        print(f"[AVATAR] Error descargando {username}: {e}")

# Intentar importar TikTokLive
try:
    from TikTokLive import TikTokLiveClient
    from TikTokLive.events import CommentEvent, ConnectEvent, DisconnectEvent, LikeEvent
    TIKTOK_AVAILABLE = True
except ImportError:
    TIKTOK_AVAILABLE = False
    print("[AVISO] TikTokLive no instalado. Ejecutá: pip install TikTokLive")


def extract_like_count(event):
    """
    Extraer la cantidad de likes de un LikeEvent probando varios nombres de
    atributo posibles (la librería TikTokLive no documenta un nombre único
    y estable entre versiones). Devuelve 1 como fallback minimo si no se
    encuentra ningun atributo numerico (asi al menos se cuenta el evento).
    Loggea una sola vez que atributo funciono, para poder confirmarlo.
    """
    for attr in ("count", "likeCount", "like_count", "total"):
        if hasattr(event, attr):
            val = getattr(event, attr)
            if isinstance(val, (int, float)) and val > 0:
                if not getattr(extract_like_count, "_logged", False):
                    print(f"[LIKES] Usando atributo '{attr}' del LikeEvent (valor ejemplo: {val})")
                    extract_like_count._logged = True
                return int(val)
    return 1


def extract_avatar_url(user):
    """
    Extraer la URL de la foto de perfil de un usuario de TikTokLive probando
    varias rutas posibles. En V1 se usaba user.avatar_jpg / user.avatar_url,
    que NO EXISTEN en el modelo real de la librería (por eso nunca funcionó
    la foto de perfil) - la imagen en realidad viene en un objeto tipo
    "avatar_thumb" con una lista de URLs (m_urls / urls / url_list), del cual
    conviene tomar la última (suele ser la de mayor resolución).
    Loggea una sola vez qué ruta funcionó, para poder confirmarlo en un live real.
    """
    candidates = [
        ("avatar_thumb", ("m_urls", "urls", "url_list")),
        ("avatar_medium", ("m_urls", "urls", "url_list")),
        ("avatar_large", ("m_urls", "urls", "url_list")),
        ("profile_picture", ("m_urls", "urls", "url_list")),
    ]
    for obj_attr, list_attrs in candidates:
        obj = getattr(user, obj_attr, None)
        if obj is None:
            continue
        for list_attr in list_attrs:
            url_list = getattr(obj, list_attr, None)
            if url_list:
                try:
                    url = url_list[-1]
                except (IndexError, TypeError):
                    continue
                if url:
                    if not getattr(extract_avatar_url, "_logged", False):
                        print(f"[AVATAR] Usando user.{obj_attr}.{list_attr}[-1] (ejemplo: {url})")
                        extract_avatar_url._logged = True
                    return url
    # Fallbacks simples (por si en alguna version son strings directos)
    for attr in ("avatar_url", "avatar_jpg", "avatarUrl"):
        val = getattr(user, attr, None)
        if isinstance(val, str) and val:
            if not getattr(extract_avatar_url, "_logged", False):
                print(f"[AVATAR] Usando user.{attr} (string directo, ejemplo: {val})")
                extract_avatar_url._logged = True
            return val
    return ""


def parse_rr_command(comment, max_rr):
    """
    Extrae el ratio Riesgo:Beneficio (R:R) de un comando de chat.
    Soporta formatos flexibles: 1:2, 1-2, 1_2, 1.2, 3, 1.5, etc.
    """
    # 1. Intentar buscar patrón X[sep]Y donde [sep] es :, -, _, o .
    # Captura el segundo número como el beneficio (Reward)
    pair_match = re.search(r"(\d+)\s*[:\-\._]\s*(\d+(?:\.\d+)?)", comment)
    if pair_match:
        try:
            requested = float(pair_match.group(2))
        except (ValueError, IndexError):
            requested = 1.0
    else:
        # 2. Si no hay par, buscar un número solo (puede ser decimal)
        single_match = re.search(r"(\d+(?:\.\d+)?)", comment)
        if single_match:
            try:
                requested = float(single_match.group(1))
            except (ValueError, IndexError):
                requested = 1.0
        else:
            requested = 1.0

    if requested < 1:
        requested = 1.0
    return min(requested, float(max_rr))


class TikTokChatReader:
    """Lee el chat de TikTok Live en un hilo separado"""

    def __init__(self, username="lean.fx1", max_rr=3):
        self.username = username
        self.max_rr = max_rr  # Límite máximo de R:R permitido (1:max_rr)
        self.connected = False
        self.votes = []  # Lista de {"name": str, "vote": "BUY"/"SELL", "rr": float, "avatar_url": str}
        self.voting_open = False  # True cuando se puede votar (zona activa)
        self.voters_this_zone = set()  # Viewers que ya votaron en esta ronda/zona (cooldown por ronda)
        self.voters_this_candle = set() # Viewers que ya votaron en esta vela (anti-spam por vela)
        self.all_comments = []  # Todos los comentarios (para debug)
        self.thread = None
        self.loop = None
        self.client = None
        self.reconnect_attempts = 0
        self.max_reconnect = 999  # Reintentos infinitos
        self.reconnecting = False  # Indicador para mostrar en pantalla
        # --- Contador de likes (para el evento "liquidez por likes") ---
        self.like_count = 0  # Se resetea con reset_like_count() al iniciar cada evento
        # --- Totales de sesión (Analytics) ---
        self.session_total_likes = 0
        self.session_total_messages = 0
        self.session_unique_participants = set()

    def start(self):
        """Iniciar la conexión en un hilo separado"""
        if not TIKTOK_AVAILABLE:
            print("[TIKTOK] Librería no disponible. Usando bots simulados.")
            return False
        self.thread = threading.Thread(target=self._run_async, daemon=True)
        self.thread.start()
        return True

    def _run_async(self):
        """Correr el loop asyncio en el hilo"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._connect())

    async def _connect(self):
        """Conectar al live de TikTok"""
        while self.reconnect_attempts < self.max_reconnect:
            try:
                self.client = TikTokLiveClient(unique_id=self.username)

                @self.client.on(ConnectEvent)
                async def on_connect(event: ConnectEvent):
                    self.connected = True
                    self.reconnecting = False
                    self.reconnect_attempts = 0
                    print(f"[TIKTOK] Conectado al live de @{self.username}")

                @self.client.on(DisconnectEvent)
                async def on_disconnect(event: DisconnectEvent):
                    self.connected = False
                    print(f"[TIKTOK] Desconectado del live")

                @self.client.on(LikeEvent)
                async def on_like(event: LikeEvent):
                    try:
                        count = extract_like_count(event)
                        self.like_count += count
                        self.session_total_likes += count
                    except Exception as like_err:
                        print(f"[TIKTOK] Error procesando like: {like_err}")

                @self.client.on(CommentEvent)
                async def on_comment(event: CommentEvent):
                    try:
                        username = event.user.nickname or str(event.user.id)
                        unique_id = str(event.user.id)
                        comment = event.comment.strip().upper()
                        avatar_url = extract_avatar_url(event.user)

                        # Analytics
                        self.session_total_messages += 1
                        self.session_unique_participants.add(unique_id)

                        # Guardar todos los comentarios (debug)
                        self.all_comments.append({
                            "name": username,
                            "unique_id": unique_id,
                            "comment": comment,
                            "avatar_url": avatar_url,
                            "time": time.time()
                        })
                        # Solo mantener últimos 50
                        if len(self.all_comments) > 50:
                            self.all_comments.pop(0)

                        # Detectar voto BUY/SELL (Estricto: solo SUBE y BAJA)
                        if self.voting_open:
                            # 1. Validación de Cooldown por Ronda y Anti-Spam por Vela
                            if unique_id in self.voters_this_zone:
                                return # Ya votó en esta ronda, ignorar silenciosamente
                            
                            if unique_id in self.voters_this_candle:
                                return # Ya mandó comando en esta vela, evitar spam
                                
                            vote = None
                            # Bloquear palabras antiguas y solo permitir "SUBE" y "BAJA"
                            if "SUBE" in comment:
                                vote = "BUY"
                            elif "BAJA" in comment:
                                vote = "SELL"

                            if vote:
                                # Registrar al usuario para los bloqueos de cooldown y spam
                                self.voters_this_zone.add(unique_id)
                                self.voters_this_candle.add(unique_id)
                                
                                # Permitir múltiples votos (duplicados sin descartar a nadie)
                                rr = parse_rr_command(comment, self.max_rr)
                                self.votes.append({
                                    "name": username,
                                    "unique_id": unique_id,
                                    "vote": vote,
                                    "rr": rr,
                                    "avatar_url": avatar_url
                                })
                                # Descargar avatar en background
                                threading.Thread(target=download_avatar, args=(username, avatar_url), daemon=True).start()
                                print(f"[VOTO] {username} -> {vote} 1:{rr:.1f}")
                    except Exception as comment_err:
                        print(f"[TIKTOK] Error procesando comentario: {comment_err}")

                print(f"[TIKTOK] Conectando a @{self.username}...")
                await self.client.connect()

            except Exception as e:
                self.connected = False
                self.reconnecting = True
                self.reconnect_attempts += 1
                wait_time = min(30, 5 * self.reconnect_attempts)  # Espera progresiva: 5s, 10s, 15s... max 30s
                print(f"[TIKTOK] Error: {e}. Reintento en {wait_time}s (intento #{self.reconnect_attempts})")
                await asyncio.sleep(wait_time)

        print("[TIKTOK] Máximo de reintentos alcanzado. Usando bots simulados.")

    def open_voting(self):
        """Abrir votación (cuando se detecta zona)"""
        self.voting_open = True
        self.votes = []
        self.voters_this_zone = set()
        self.voters_this_candle = set()

    def close_voting(self):
        """Cerrar votación (cuando termina el timer)"""
        self.voting_open = False
        self.voters_this_candle = set()

    def reset_candle_cooldown(self):
        """Resetear anti-spam por vela (llamado desde main.py en cada vela nueva)"""
        self.voters_this_candle = set()

    def get_votes(self):
        """Obtener votos actuales"""
        return self.votes.copy()

    def get_vote_count(self):
        """Obtener conteo de votos"""
        buy = sum(1 for v in self.votes if v["vote"] == "BUY")
        sell = sum(1 for v in self.votes if v["vote"] == "SELL")
        return buy, sell

    def is_connected(self):
        """Verificar si está conectado"""
        return self.connected

    def is_reconnecting(self):
        """Verificar si está intentando reconectar"""
        return self.reconnecting and not self.connected

    def has_real_voters(self):
        """Verificar si hay voters reales (para desactivar bots)"""
        return len(self.votes) > 0

    def reset_like_count(self):
        """Reiniciar el contador de likes (al empezar un evento de liquidez)"""
        self.like_count = 0

    def reset_session_totals(self):
        """Reiniciar totales de sesión (Analytics)"""
        self.session_total_likes = 0
        self.session_total_messages = 0
        self.session_unique_participants = set()

    def get_like_count(self):
        """Obtener el conteo de likes acumulado desde el último reset"""
        return self.like_count
    
    def get_viewer_count(self):
        """Obtener el conteo de espectadores actual"""
        return self.viewer_count