"""Módulo de síntesis de voz TTS usando la API de Luvvoice (luvvoice.com).

Integra la API de Luvvoice para generar audios de eventos de voz nuevos,
manteniendo intactos los audios y sonidos existentes del juego.
Las llamadas se ejecutan en un hilo secundario para no congelar el bucle
principal de Pygame.
"""

import os
import pygame

# `requests` es opcional: si no está instalado, el TTS simplemente no se genera
# y el juego sigue funcionando con los audios existentes.
try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

# Configuración TTS Luvvoice
LUVVOICE_URL = "https://luvvoice.com/api/v1/text-to-speech"
LUVVOICE_VOICE = "Jorge"  # Voz "Jorge" (Spanish)
LUVVOICE_RATE = "+10%"    # Velocidad +10%

# Directorio de salida para audios generados
TTS_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "sound", "tts_luvvoice")


def _ensure_output_dir():
    """Crea el directorio de salida si no existe."""
    os.makedirs(TTS_OUTPUT_DIR, exist_ok=True)


def _generate_tts_audio(text: str, filename: str):
    """Genera un audio TTS con Luvvoice y lo guarda en el directorio de salida.

    Devuelve la ruta del archivo generado, o None si falla.
    """
    _ensure_output_dir()
    filepath = os.path.join(TTS_OUTPUT_DIR, filename)
    if os.path.exists(filepath):
        return filepath

    if not _REQUESTS_AVAILABLE:
        print("[LUVVOICE TTS] Módulo 'requests' no instalado. Instalá requests para activar el TTS.")
        return None

    try:
        response = requests.post(
            LUVVOICE_URL,
            json={
                "text": text,
                "voice": LUVVOICE_VOICE,
                "rate": LUVVOICE_RATE,
            },
            timeout=30,
        )
        if response.status_code == 200:
            with open(filepath, "wb") as f:
                f.write(response.content)
            return filepath
        else:
            print(f"[LUVVOICE TTS] Error HTTP {response.status_code}: {response.text[:200]}")
            return None
    except Exception as e:
        print(f"[LUVVOICE TTS] Error generando audio: {e}")
        return None


# Callback para integrar con el gestor de audio externo (ej: AudioManager en main.py)
_audio_callback = None

def set_audio_callback(callback):
    """Establece la función que manejará la reproducción (ej: audio_manager.play)."""
    global _audio_callback
    _audio_callback = callback

def _play_tts_audio(text: str, filename: str, pausar_mercado: bool = False):
    """Genera y reproduce un audio TTS de forma sincrónica."""
    filepath = _generate_tts_audio(text, filename)
    if filepath:
        if _audio_callback:
            # Llamada sincrónica: bloqueará el bucle si pausar_mercado es True
            _audio_callback(filepath, pausar_mercado=pausar_mercado)
        else:
            # Fallback: reproducción directa
            try:
                sound = pygame.mixer.Sound(filepath)
                sound.play()
            except Exception as e:
                print(f"[LUVVOICE TTS] Error reproduciendo audio: {e}")


def play_on_max_tp():
    """Evento ON_MAX_TP: Solo al alcanzar la Meta Máxima."""
    _play_tts_audio(
        "¡Felicidades a los ganadores! Se alcanzó la meta máxima de la ronda. Excelente lectura de mercado.",
        "on_max_tp.mp3",
        pausar_mercado=True,
    )


def play_on_stop_loss():
    """Evento ON_STOP_LOSS: Al tocar el límite de pérdida de la zona."""
    _play_tts_audio(
        "Operación cerrada en límite de pérdida. El mercado barrió la zona, a gestionar el riesgo para la siguiente.",
        "on_stop_loss.mp3",
        pausar_mercado=True,
    )


def play_on_break_even():
    """Evento ON_BREAK_EVEN: Al regresar al precio de entrada."""
    _play_tts_audio(
        "Precio de vuelta a la entrada. Operación protegida y cerrada en Break Even sin pérdidas.",
        "on_break_even.mp3",
        pausar_mercado=True,
    )