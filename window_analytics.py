"""
LEAN FX GAME - Ventana de ANALYTICS (Fase 2)

Proceso pygame independiente para mostrar estadísticas y métricas detalladas.
Incluye filtros de tiempo y visualizaciones de rendimiento del canal.
"""
import os
import sys
import pygame
import math
from datetime import datetime, timedelta

from shared_paths import find_asset
from database import get_analytics_data

# --- CONFIGURACIÓN DE VENTANA ---
WINDOW_W, WINDOW_H = 1200, 800
REFRESH_INTERVAL_MS = 5000  # Refrescar datos cada 5 segundos
FPS = 30

# --- COLORES CYBERPUNK ---
COLOR_BG = (8, 12, 20)
COLOR_PANEL = (15, 20, 30, 180)
COLOR_NEON_CYAN = (0, 220, 255)
COLOR_NEON_GREEN = (0, 255, 150)
COLOR_NEON_RED = (255, 50, 50)
COLOR_NEON_YELLOW = (255, 200, 0)
COLOR_TEXT_DIM = (120, 140, 160)
COLOR_TEXT_BRIGHT = (220, 230, 240)

pygame.init()
pygame.font.init()

# Posicionamiento inicial
os.environ['SDL_VIDEO_WINDOW_POS'] = "100,100"
screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
pygame.display.set_caption("LEAN FX - ANALYTICS DASHBOARD")

# Fuentes
font_title = pygame.font.SysFont("Consolas", 32, bold=True)
font_header = pygame.font.SysFont("Consolas", 24, bold=True)
font_main = pygame.font.SysFont("Consolas", 18, bold=True)
font_small = pygame.font.SysFont("Consolas", 14)
font_huge = pygame.font.SysFont("Consolas", 48, bold=True)

# --- ESTADO ---
current_filter = 'hoy' # 'hoy', 'ayer', '3d', '7d', 'mes', 'custom'
analytics_data = None
last_refresh = -REFRESH_INTERVAL_MS
scroll_y = 0
content_height = 1500 # Altura virtual inicial

# Fechas personalizadas (inicializadas a la última semana)
custom_start_date = (datetime.now() - timedelta(days=7)).date()
custom_end_date = datetime.now().date()
date_editing = None # 'start' o 'end'

# Filtros disponibles
FILTERS = [
    {'id': 'hoy', 'label': 'HOY'},
    {'id': 'ayer', 'label': 'AYER'},
    {'id': '3d', 'label': 'ÚLT. 3 DÍAS'},
    {'id': '7d', 'label': 'ÚLT. 7 DÍAS'},
    {'id': 'mes', 'label': 'ESTE MES'},
    {'id': 'custom', 'label': 'PERSONALIZADO'}
]

def draw_neon_rect(surf, rect, color, width=2, glow=True, corners=False):
    """Dibuja un rectángulo con efecto neón y esquinas opcionales"""
    pygame.draw.rect(surf, color, rect, width, border_radius=4)
    if glow:
        for i in range(1, 3):
            alpha = 80 // (i * 2)
            glow_color = (*color[:3], alpha)
            glow_rect = rect.inflate(i * 2, i * 2)
            s = pygame.Surface((glow_rect.width, glow_rect.height), pygame.SRCALPHA)
            pygame.draw.rect(s, glow_color, (0, 0, glow_rect.width, glow_rect.height), width, border_radius=4 + i)
            surf.blit(s, glow_rect.topleft)
    
    if corners:
        # Esquinas tipo bracket
        l = 15
        # Top Left
        pygame.draw.line(surf, color, rect.topleft, (rect.x + l, rect.y), width + 1)
        pygame.draw.line(surf, color, rect.topleft, (rect.x, rect.y + l), width + 1)
        # Top Right
        pygame.draw.line(surf, color, rect.topright, (rect.right - l, rect.y), width + 1)
        pygame.draw.line(surf, color, rect.topright, (rect.right, rect.y + l), width + 1)
        # Bottom Left
        pygame.draw.line(surf, color, rect.bottomleft, (rect.x + l, rect.bottom), width + 1)
        pygame.draw.line(surf, color, rect.bottomleft, (rect.x, rect.bottom - l), width + 1)
        # Bottom Right
        pygame.draw.line(surf, color, rect.bottomright, (rect.right - l, rect.bottom), width + 1)
        pygame.draw.line(surf, color, rect.bottomright, (rect.right, rect.bottom - l), width + 1)

def draw_stat_card(surf, x, y, w, h, label, value, color=COLOR_NEON_CYAN):
    """Dibuja una tarjeta de estadística compacta y estilizada"""
    card_rect = pygame.Rect(x, y, w, h)
    
    # Fondo translúcido con gradiente sutil
    bg = pygame.Surface((w, h), pygame.SRCALPHA)
    for i in range(h):
        alpha = 40 + (i / h) * 40
        pygame.draw.line(bg, (5, 15, 30, int(alpha)), (0, i), (w, i))
    surf.blit(bg, (x, y))
    
    # Borde neón sutil y esquinas
    draw_neon_rect(surf, card_rect, (*color, 120), 1, glow=True, corners=True)
    
    # Label (más pequeño y centrado arriba)
    lbl_txt = font_small.render(label.upper(), True, COLOR_TEXT_DIM)
    surf.blit(lbl_txt, (x + (w - lbl_txt.get_width()) // 2, y + 10))
    
    # Value (Grande y centrado)
    val_txt = font_header.render(str(value), True, color)
    surf.blit(val_txt, (x + (w - val_txt.get_width()) // 2, y + 35))

def render_dashboard(target_surf):
    global content_height
    if not analytics_data:
        return

    summary = analytics_data['summary']
    
    # --- 1. RESUMEN GENERAL (GRID COMPACTO) ---
    start_y = 20
    card_w, card_h = 180, 80 # Más pequeñas
    gap_x, gap_y = 15, 15
    grid_x = 50
    
    metrics = [
        ("Sesiones", summary.get('sessions_count', 0), COLOR_NEON_CYAN),
        ("Rondas", summary.get('rounds', 0), COLOR_NEON_GREEN),
        ("Voters", summary.get('participants', 0), COLOR_NEON_YELLOW),
        ("Pico Viewers", summary.get('max_peak', 0), COLOR_NEON_CYAN),
        ("Avg Viewers", f"{summary.get('global_avg_viewers', 0) or 0:.1f}", COLOR_NEON_CYAN),
        ("Total Likes", summary.get('likes', 0), COLOR_NEON_GREEN),
        ("Mensajes", summary.get('messages', 0), COLOR_NEON_CYAN),
        ("FXP Total", f"{int(summary.get('fxp', 0) or 0)}", COLOR_NEON_CYAN),
    ]

    dur_secs = summary.get('total_duration_secs', 0) or 0
    dur_str = f"{dur_secs // 3600}h {(dur_secs % 3600) // 60}m"
    metrics.append(("Tiempo", dur_str, COLOR_NEON_YELLOW))
    metrics.append(("Eventos", len(analytics_data['events']), COLOR_NEON_RED))

    # Dibujar métricas en grid de 6 columnas
    cols = 6
    for i, (lbl, val, col) in enumerate(metrics):
        row = i // cols
        col_idx = i % cols
        draw_stat_card(target_surf, grid_x + col_idx * (card_w + gap_x), start_y + row * (card_h + gap_y), card_w, card_h, lbl, val, col)

    start_y += (len(metrics) // cols + 1) * (card_h + gap_y) + 20
    
    # --- 2. SECCIONES DETALLADAS ---
    
    # Panel Votos y RR en la misma fila para ahorrar espacio
    row_h = 180
    panel_v_w = 400
    
    # Panel Votos
    votos = analytics_data['votes']
    sube = votos.get('SUBE', 0)
    baja = votos.get('BAJA', 0)
    total_v = sube + baja
    
    v_rect = pygame.Rect(grid_x, start_y, panel_v_w, row_h)
    pygame.draw.rect(target_surf, (10, 20, 35, 150), v_rect, border_radius=8)
    draw_neon_rect(target_surf, v_rect, (0, 100, 120), 1, False, corners=True)
    target_surf.blit(font_main.render("PARTICIPACIÓN", True, COLOR_NEON_CYAN), (grid_x + 20, start_y + 15))
    
    bar_x, bar_y, bar_w, bar_h = grid_x + 20, start_y + 80, panel_v_w - 40, 30
    if total_v > 0:
        pct_sube = sube / total_v
        pygame.draw.rect(target_surf, COLOR_NEON_GREEN, (bar_x, bar_y, int(bar_w * pct_sube), bar_h), border_radius=4)
        pygame.draw.rect(target_surf, COLOR_NEON_RED, (bar_x + int(bar_w * pct_sube), bar_y, bar_w - int(bar_w * pct_sube), bar_h), border_radius=4)
        
        s_txt = font_small.render(f"SUBE: {sube} ({int(pct_sube*100)}%)", True, COLOR_NEON_GREEN)
        b_txt = font_small.render(f"BAJA: {baja} ({int((1-pct_sube)*100)}%)", True, COLOR_NEON_RED)
        target_surf.blit(s_txt, (bar_x, bar_y - 20))
        target_surf.blit(b_txt, (bar_x + bar_w - b_txt.get_width(), bar_y - 20))
    else:
        pygame.draw.rect(target_surf, (30, 40, 50), (bar_x, bar_y, bar_w, bar_h), border_radius=4)
        target_surf.blit(font_small.render("SIN DATOS", True, COLOR_TEXT_DIM), (bar_x + bar_w//2 - 30, bar_y + 7))

    # Panel RR Stats (Al lado de votos)
    panel_rr_x = grid_x + panel_v_w + 20
    panel_rr_w = WINDOW_W - panel_rr_x - 50
    rr_rect = pygame.Rect(panel_rr_x, start_y, panel_rr_w, row_h)
    
    pygame.draw.rect(target_surf, (10, 20, 35, 150), rr_rect, border_radius=8)
    draw_neon_rect(target_surf, rr_rect, (0, 100, 120), 1, False, corners=True)
    target_surf.blit(font_main.render("TOP R:R RATIOS", True, COLOR_NEON_CYAN), (panel_rr_x + 20, start_y + 15))
    
    rr_stats = analytics_data['rr_stats'][:4]
    header_rr = font_small.render("RATIO      WINS    LOSSES    WR%", True, COLOR_TEXT_DIM)
    target_surf.blit(header_rr, (panel_rr_x + 20, start_y + 45))
    
    for i, rr in enumerate(rr_stats):
        ry = start_y + 70 + i * 22
        total_rr = rr['wins'] + rr['losses']
        wr = (rr['wins'] / total_rr * 100) if total_rr > 0 else 0
        txt_rr = font_small.render(f"1:{rr['rr_ratio']:.1f}", True, COLOR_NEON_YELLOW)
        txt_w = font_small.render(str(rr['wins']), True, COLOR_NEON_GREEN)
        txt_l = font_small.render(str(rr['losses']), True, COLOR_NEON_RED)
        txt_wr = font_small.render(f"{wr:.1f}%", True, COLOR_NEON_CYAN)
        target_surf.blit(txt_rr, (panel_rr_x + 20, ry))
        target_surf.blit(txt_w, (panel_rr_x + 100, ry))
        target_surf.blit(txt_l, (panel_rr_x + 160, ry))
        target_surf.blit(txt_wr, (panel_rr_x + 230, ry))

    # --- 3. MEJOR HORARIO Y EVENTOS (Fila 2) ---
    start_y += row_h + 20
    
    # Mejor Horario
    h_rect = pygame.Rect(grid_x, start_y, panel_v_w, row_h)
    pygame.draw.rect(target_surf, (10, 20, 35, 150), h_rect, border_radius=8)
    draw_neon_rect(target_surf, h_rect, (0, 100, 120), 1, False, corners=True)
    target_surf.blit(font_main.render("MEJOR HORARIO", True, COLOR_NEON_YELLOW), (grid_x + 20, start_y + 15))
    
    best_hours = analytics_data.get('best_hours', [])[:5]
    if best_hours:
        for i, bh in enumerate(best_hours):
            hy = start_y + 50 + i * 22
            txt_h = font_small.render(f"{bh['hour']}:00 HS", True, COLOR_TEXT_BRIGHT)
            txt_v = font_small.render(f"{bh['avg_viewers']:.1f} AVG", True, COLOR_NEON_CYAN)
            target_surf.blit(txt_h, (grid_x + 20, hy))
            target_surf.blit(txt_v, (grid_x + 150, hy))
    else:
        target_surf.blit(font_small.render("SIN DATOS", True, COLOR_TEXT_DIM), (grid_x + 20, start_y + 60))

    # Eventos Activados
    ev_rect = pygame.Rect(panel_rr_x, start_y, panel_rr_w, row_h)
    pygame.draw.rect(target_surf, (10, 20, 35, 150), ev_rect, border_radius=8)
    draw_neon_rect(target_surf, ev_rect, (0, 100, 120), 1, False, corners=True)
    target_surf.blit(font_main.render("EVENTOS", True, COLOR_NEON_RED), (panel_rr_x + 20, start_y + 15))
    
    events = analytics_data.get('events', [])
    if events:
        for i, ev in enumerate(events[:5]):
            ey = start_y + 50 + i * 22
            txt_en = font_small.render(ev['event_name'], True, COLOR_TEXT_BRIGHT)
            txt_ec = font_small.render(f"x{ev['count']}", True, COLOR_NEON_RED)
            target_surf.blit(txt_en, (panel_rr_x + 20, ey))
            target_surf.blit(txt_ec, (panel_rr_x + panel_rr_w - 50, ey))
    else:
        target_surf.blit(font_small.render("NINGUNO", True, COLOR_TEXT_DIM), (panel_rr_x + 20, start_y + 60))

    # --- 4. EVOLUCIÓN DIARIA (Fila 3) ---
    start_y += row_h + 20
    evolution = analytics_data['evolution']
    panel_ev_w = WINDOW_W - 100
    ev_chart_rect = pygame.Rect(grid_x, start_y, panel_ev_w, 200)
    pygame.draw.rect(target_surf, (10, 20, 35, 150), ev_chart_rect, border_radius=8)
    draw_neon_rect(target_surf, ev_chart_rect, (0, 100, 120), 1, False, corners=True)
    target_surf.blit(font_main.render("EVOLUCIÓN DE LIKES", True, COLOR_NEON_CYAN), (grid_x + 20, start_y + 15))
    
    chart_x, chart_y, chart_w, chart_h = grid_x + 50, start_y + 60, panel_ev_w - 100, 100
    if evolution:
        max_likes = max([d['likes'] for d in evolution]) if evolution else 1
        if max_likes == 0: max_likes = 1
        
        if len(evolution) > 1:
            points = []
            for i, d in enumerate(evolution):
                px = chart_x + (i * (chart_w / (len(evolution) - 1)))
                py = chart_y + chart_h - (d['likes'] / max_likes * chart_h)
                points.append((px, py))
            
            pygame.draw.lines(target_surf, COLOR_NEON_GREEN, False, points, 2)
            for i, p in enumerate(points):
                pygame.draw.circle(target_surf, COLOR_NEON_GREEN, (int(p[0]), int(p[1])), 4)
                if i % max(1, len(evolution)//10) == 0:
                    date_txt = font_small.render(evolution[i]['day'][5:], True, COLOR_TEXT_DIM)
                    target_surf.blit(date_txt, (int(p[0]) - 15, chart_y + chart_h + 10))
        else:
            d = evolution[0]
            pygame.draw.circle(target_surf, COLOR_NEON_GREEN, (chart_x + chart_w//2, chart_y + chart_h//2), 6)
            target_surf.blit(font_small.render(f"Likes: {d['likes']}", True, COLOR_NEON_GREEN), (chart_x + chart_w//2 + 10, chart_y + chart_h//2 - 10))

    content_height = start_y + 250

clock = pygame.time.Clock()
running = True

while running:
    current_time = pygame.time.get_ticks()
    
    # Eventos
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1: # Click izquierdo
                mx, my = event.pos
                
                # --- Click en Filtros ---
                for i, f in enumerate(FILTERS):
                    f_rect = pygame.Rect(50 + i * 165, 80, 160, 40)
                    if f_rect.collidepoint(mx, my):
                        current_filter = f['id']
                        if current_filter != 'custom':
                            last_refresh = -REFRESH_INTERVAL_MS
                        scroll_y = 0
                
                # --- Click en Controles Custom ---
                if current_filter == 'custom':
                    # Botones Start
                    start_rect = pygame.Rect(120, 130, 250, 35)
                    btn_s_m = pygame.Rect(start_rect.right + 5, 130, 35, 35)
                    btn_s_p = pygame.Rect(start_rect.right + 45, 130, 35, 35)
                    btn_s_mm = pygame.Rect(start_rect.right + 85, 130, 35, 35)
                    btn_s_pp = pygame.Rect(start_rect.right + 125, 130, 35, 35)
                    
                    if btn_s_m.collidepoint(mx, my):
                        custom_start_date -= timedelta(days=1)
                    elif btn_s_p.collidepoint(mx, my):
                        custom_start_date += timedelta(days=1)
                    elif btn_s_mm.collidepoint(mx, my):
                        custom_start_date -= timedelta(days=30)
                    elif btn_s_pp.collidepoint(mx, my):
                        custom_start_date += timedelta(days=30)
                    
                    if custom_start_date > custom_end_date:
                        custom_start_date = custom_end_date
                    
                    # Botones End
                    end_rect = pygame.Rect(WINDOW_W // 2 + 80, 130, 200, 35)
                    btn_e_m = pygame.Rect(end_rect.right + 5, 130, 35, 35)
                    btn_e_p = pygame.Rect(end_rect.right + 45, 130, 35, 35)
                    btn_e_mm = pygame.Rect(end_rect.right + 85, 130, 35, 35)
                    btn_e_pp = pygame.Rect(end_rect.right + 125, 130, 35, 35)
                    
                    if btn_e_m.collidepoint(mx, my):
                        custom_end_date -= timedelta(days=1)
                    elif btn_e_p.collidepoint(mx, my):
                        custom_end_date += timedelta(days=1)
                    elif btn_e_mm.collidepoint(mx, my):
                        custom_end_date -= timedelta(days=30)
                    elif btn_e_pp.collidepoint(mx, my):
                        custom_end_date += timedelta(days=30)

                    if custom_end_date < custom_start_date:
                        custom_end_date = custom_start_date
                    
                    # Botón Aplicar
                    btn_apply = pygame.Rect(WINDOW_W - 180, 130, 130, 35)
                    if btn_apply.collidepoint(mx, my):
                        last_refresh = -REFRESH_INTERVAL_MS

            elif event.button == 4: # Scroll Up
                scroll_y = min(0, scroll_y + 40)
            elif event.button == 5: # Scroll Down
                header_h = 180 if current_filter == 'custom' else 140
                scroll_y = max(-(content_height - (WINDOW_H - header_h)), scroll_y - 40)

    # Refrescar datos
    if current_time - last_refresh >= REFRESH_INTERVAL_MS:
        try:
            if current_filter == 'custom':
                analytics_data = get_analytics_data('custom', [custom_start_date.isoformat(), custom_end_date.isoformat()])
            else:
                analytics_data = get_analytics_data(current_filter)
            last_refresh = current_time
        except Exception as e:
            print(f"[ANALYTICS] Error obteniendo datos: {e}")

    # Dibujar
    screen.fill(COLOR_BG)
    
    # --- CONTENIDO SCROLLEABLE ---
    header_h = 180 if current_filter == 'custom' else 140
    virtual_h = max(WINDOW_H, content_height)
    content_surf = pygame.Surface((WINDOW_W, virtual_h), pygame.SRCALPHA)
    render_dashboard(content_surf)
    screen.blit(content_surf, (0, header_h + scroll_y))

    # --- HEADER FIJO ---
    header_bg = pygame.Surface((WINDOW_W, header_h), pygame.SRCALPHA)
    header_bg.fill((5, 10, 20, 255))
    screen.blit(header_bg, (0, 0))
    pygame.draw.line(screen, COLOR_NEON_CYAN, (0, header_h), (WINDOW_W, header_h), 2)
    
    title_txt = font_title.render("LEAN FX - ANALYTICS DASHBOARD", True, COLOR_NEON_CYAN)
    screen.blit(title_txt, (50, 25))
    
    for i, f in enumerate(FILTERS):
        f_rect = pygame.Rect(50 + i * 165, 80, 160, 40)
        is_active = current_filter == f['id']
        
        btn_col = COLOR_NEON_CYAN if is_active else (40, 60, 80)
        pygame.draw.rect(screen, (20, 30, 50) if is_active else (10, 15, 25), f_rect, border_radius=6)
        draw_neon_rect(screen, f_rect, btn_col, 2 if is_active else 1, glow=is_active)
        
        lbl_col = COLOR_TEXT_BRIGHT if is_active else COLOR_TEXT_DIM
        lbl = font_main.render(f['label'], True, lbl_col)
        screen.blit(lbl, lbl.get_rect(center=f_rect.center))

    # --- SELECTOR DE FECHAS (Solo si es CUSTOM) ---
    if current_filter == 'custom':
        # Texto "DESDE"
        screen.blit(font_main.render("DESDE:", True, COLOR_TEXT_DIM), (50, 135))
        
        # Botones de fecha Start
        start_rect = pygame.Rect(120, 130, 250, 35)
        pygame.draw.rect(screen, (15, 25, 45), start_rect, border_radius=4)
        draw_neon_rect(screen, start_rect, COLOR_NEON_CYAN if date_editing == 'start' else (60, 80, 100), 1)
        txt_start = font_main.render(custom_start_date.strftime("%d / %m / %Y"), True, COLOR_TEXT_BRIGHT)
        screen.blit(txt_start, txt_start.get_rect(center=start_rect.center))
        
        # Controles Start (+ / -)
        btn_s_m = pygame.Rect(start_rect.right + 5, 130, 35, 35)
        btn_s_p = pygame.Rect(start_rect.right + 45, 130, 35, 35)
        btn_s_mm = pygame.Rect(start_rect.right + 85, 130, 35, 35)
        btn_s_pp = pygame.Rect(start_rect.right + 125, 130, 35, 35)
        
        for r, t in [(btn_s_m, "-D"), (btn_s_p, "+D"), (btn_s_mm, "-M"), (btn_s_pp, "+M")]:
            pygame.draw.rect(screen, (30, 40, 60), r, border_radius=4)
            txt = font_small.render(t, True, COLOR_TEXT_BRIGHT)
            screen.blit(txt, txt.get_rect(center=r.center))

        # Texto "HASTA"
        screen.blit(font_main.render("HASTA:", True, COLOR_TEXT_DIM), (WINDOW_W // 2 + 20, 135))
        
        # Botones de fecha End
        end_rect = pygame.Rect(WINDOW_W // 2 + 80, 130, 200, 35)
        pygame.draw.rect(screen, (15, 25, 45), end_rect, border_radius=4)
        draw_neon_rect(screen, end_rect, COLOR_NEON_CYAN if date_editing == 'end' else (60, 80, 100), 1)
        txt_end = font_main.render(custom_end_date.strftime("%d/%m/%Y"), True, COLOR_TEXT_BRIGHT)
        screen.blit(txt_end, txt_end.get_rect(center=end_rect.center))
        
        # Controles End (+ / -)
        btn_e_m = pygame.Rect(end_rect.right + 5, 130, 35, 35)
        btn_e_p = pygame.Rect(end_rect.right + 45, 130, 35, 35)
        btn_e_mm = pygame.Rect(end_rect.right + 85, 130, 35, 35)
        btn_e_pp = pygame.Rect(end_rect.right + 125, 130, 35, 35)
        
        for r, t in [(btn_e_m, "-D"), (btn_e_p, "+D"), (btn_e_mm, "-M"), (btn_e_pp, "+M")]:
            pygame.draw.rect(screen, (30, 40, 60), r, border_radius=4)
            txt = font_small.render(t, True, COLOR_TEXT_BRIGHT)
            screen.blit(txt, txt.get_rect(center=r.center))
        
        # Botón APLICAR
        btn_apply = pygame.Rect(WINDOW_W - 180, 130, 130, 35)
        pygame.draw.rect(screen, (0, 80, 60), btn_apply, border_radius=4)
        draw_neon_rect(screen, btn_apply, COLOR_NEON_GREEN, 2)
        txt_apply = font_main.render("APLICAR", True, COLOR_TEXT_BRIGHT)
        screen.blit(txt_apply, txt_apply.get_rect(center=btn_apply.center))
    
    # Indicador de carga
    if current_time - last_refresh < 500:
        pygame.draw.circle(screen, COLOR_NEON_CYAN, (WINDOW_W - 50, 40), 10, 2)
        angle = (current_time / 100) % (math.pi * 2)
        end_x = WINDOW_W - 50 + math.cos(angle) * 10
        end_y = 40 + math.sin(angle) * 10
        pygame.draw.line(screen, COLOR_NEON_CYAN, (WINDOW_W - 50, 40), (int(end_x), int(end_y)), 3)

    pygame.display.flip()
    clock.tick(FPS)

pygame.quit()
sys.exit(0)
