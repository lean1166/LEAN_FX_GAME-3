import pygame
import sys
import os
import tkinter as tk
from tkinter import colorchooser
from database import get_config, set_config

# Configuración de la ventana
WIDTH, HEIGHT = 1280, 720
FPS = 60

def parse_color(c_str, default=(255, 255, 255)):
    try:
        r, g, b = map(int, c_str.split(","))
        return (r, g, b)
    except:
        return default

def pick_color(initial_color=(255, 255, 255), title="Seleccionar Color"):
    """Abre un selector de color de sistema y devuelve (r, g, b) o None."""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    color = colorchooser.askcolor(color=initial_color, title=title)
    root.destroy()
    if color[0]:
        return tuple(map(int, color[0]))
    return None

def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("LEAN FX - BANNER INFORMATIVO")
    clock = pygame.time.Clock()

    # Cargar colores desde DB o usar defaults
    bg_color_str = get_config("banner_color_bg", "10,15,25")
    text_color_str = get_config("banner_color_text", "0,220,255")
    
    color_bg = parse_color(bg_color_str, (10, 15, 25))
    color_text = parse_color(text_color_str, (0, 220, 255))

    # Texto a mostrar
    message = "Simulador lúdico de análisis técnico • Puntos ficticios (FXP) • No constituye asesoramiento financiero"
    
    # Cargar fuentes
    try:
        font_size = 64
        font = pygame.font.SysFont(["segoeui", "arial"], font_size, bold=True)
        font_hint = pygame.font.SysFont(["arial"], 20, bold=True)
    except:
        font = pygame.font.Font(None, 64)
        font_hint = pygame.font.Font(None, 20)

    def render_text():
        return font.render(message, True, color_text)

    text_surface = render_text()
    text_width = text_surface.get_width()
    text_height = text_surface.get_height()

    # Espacio entre repeticiones del texto
    gap = 300
    x_pos = WIDTH

    running = True
    show_hints = True
    hint_timer = 0

    while running:
        current_time = pygame.time.get_ticks()
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_b:
                    new_color = pick_color(color_bg, "Color de Fondo")
                    if new_color:
                        color_bg = new_color
                        set_config("banner_color_bg", f"{new_color[0]},{new_color[1]},{new_color[2]}")
                elif event.key == pygame.K_t:
                    new_color = pick_color(color_text, "Color de Texto")
                    if new_color:
                        color_text = new_color
                        set_config("banner_color_text", f"{new_color[0]},{new_color[1]},{new_color[2]}")
                        text_surface = render_text() # Re-renderizar con el nuevo color
                elif event.key == pygame.K_h:
                    show_hints = not show_hints

        # Actualizar posición
        x_pos -= 3
        if x_pos < -text_width:
            x_pos = gap

        # Dibujar
        screen.fill(color_bg)
        
        # Dibujar el texto
        screen.blit(text_surface, (x_pos, (HEIGHT - text_height) // 2))
        screen.blit(text_surface, (x_pos + text_width + gap, (HEIGHT - text_height) // 2))

        # Dibujar ayudas visuales (subtítulos de control)
        if show_hints:
            hint_bg = pygame.Surface((400, 40), pygame.SRCALPHA)
            hint_bg.fill((0, 0, 0, 100))
            screen.blit(hint_bg, (10, HEIGHT - 50))
            
            hint_txt = font_hint.render("[B] Color Fondo  [T] Color Texto  [H] Ocultar", True, (255, 255, 255))
            screen.blit(hint_txt, (20, HEIGHT - 40))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
