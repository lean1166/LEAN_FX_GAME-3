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
from database import (
    get_analytics_data, 
    get_sessions_history, 
    get_session_details, 
    get_best_time_analysis, 
    get_comparison_data
)
from analytics_export import export_session_to_csv, export_period_to_csv

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
current_tab = 'DASHBOARD' # 'DASHBOARD', 'COMPARAR', 'EVOLUCIÓN', 'HISTORIAL', 'RECOMENDACIÓN'
current_filter = 'hoy' # 'hoy', 'ayer', '3d', '7d', 'mes', 'custom'
analytics_data = None
comparison_data = None
sessions_history = []
selected_session = None
best_time_data = None
last_refresh = -REFRESH_INTERVAL_MS
scroll_y = 0
content_height = 1500 # Altura virtual inicial

# Filtros para comparación
comp_filter_1 = 'hoy'
comp_filter_2 = 'ayer'
comp_custom_1 = None
comp_custom_2 = None

# Pestañas
TABS = ['DASHBOARD', 'COMPARAR', 'EVOLUCIÓN', 'HISTORIAL', 'RECOMENDACIÓN']

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
    if not analytics_data and current_tab != 'RECOMENDACIÓN':
        return

    if current_tab == 'DASHBOARD':
        render_main_dashboard(target_surf)
    elif current_tab == 'COMPARAR':
        render_comparison(target_surf)
    elif current_tab == 'EVOLUCIÓN':
        render_evolution(target_surf)
    elif current_tab == 'HISTORIAL':
        render_history(target_surf)
    elif current_tab == 'RECOMENDACIÓN':
        render_recommendation(target_surf)

def render_main_dashboard(target_surf):
    global content_height
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
    
    # Botón Exportar al final del Dashboard
    export_rect = pygame.Rect(grid_x, content_height - 40, 200, 35)
    pygame.draw.rect(target_surf, (0, 60, 80), export_rect, border_radius=4)
    draw_neon_rect(target_surf, export_rect, COLOR_NEON_CYAN, 1)
    target_surf.blit(font_main.render("EXPORTAR CSV", True, COLOR_TEXT_BRIGHT), (export_rect.x + 35, export_rect.y + 7))

def render_comparison(target_surf):
    global content_height
    start_y = 20
    grid_x = 50
    
    target_surf.blit(font_header.render(f"COMPARACIÓN: {comp_filter_1.upper()} VS {comp_filter_2.upper()}", True, COLOR_NEON_CYAN), (grid_x, start_y))
    start_y += 50
    
    if not comparison_data:
        target_surf.blit(font_main.render("Cargando comparación...", True, COLOR_TEXT_DIM), (grid_x, start_y))
        return

    row_h = 45
    for i, item in enumerate(comparison_data):
        ry = start_y + i * (row_h + 10)
        row_rect = pygame.Rect(grid_x, ry, WINDOW_W - 100, row_h)
        pygame.draw.rect(target_surf, (15, 25, 40, 150), row_rect, border_radius=4)
        
        # Label
        target_surf.blit(font_main.render(item['label'], True, COLOR_TEXT_BRIGHT), (grid_x + 20, ry + 12))
        
        # Valores
        v1_str = f"{item['val1']:.1f}" if isinstance(item['val1'], float) else str(item['val1'])
        v2_str = f"{item['val2']:.1f}" if isinstance(item['val2'], float) else str(item['val2'])
        
        target_surf.blit(font_main.render(v1_str, True, COLOR_NEON_CYAN), (grid_x + 300, ry + 12))
        target_surf.blit(font_main.render("vs", True, COLOR_TEXT_DIM), (grid_x + 400, ry + 12))
        target_surf.blit(font_main.render(v2_str, True, COLOR_TEXT_BRIGHT), (grid_x + 450, ry + 12))
        
        # Diferencia
        diff_col = COLOR_NEON_GREEN if item['diff'] > 0 else (COLOR_NEON_RED if item['diff'] < 0 else COLOR_TEXT_DIM)
        diff_sign = "+" if item['diff'] > 0 else ""
        diff_str = f"{diff_sign}{item['diff']:.1f}" if isinstance(item['diff'], float) else f"{diff_sign}{item['diff']}"
        target_surf.blit(font_main.render(diff_str, True, diff_col), (grid_x + 600, ry + 12))
        
        # Porcentaje
        pct_str = f"{diff_sign}{item['pct']:.1f}%"
        target_surf.blit(font_main.render(pct_str, True, diff_col), (grid_x + 750, ry + 12))

    content_height = start_y + len(comparison_data) * (row_h + 10) + 50

def render_evolution(target_surf):
    global content_height
    start_y = 20
    grid_x = 50
    
    evolution = analytics_data.get('evolution', [])
    if not evolution:
        target_surf.blit(font_main.render("No hay datos de evolución para este período.", True, COLOR_TEXT_DIM), (grid_x, start_y))
        return

    metrics = [
        ('likes', 'EVOLUCIÓN DE LIKES', COLOR_NEON_CYAN),
        ('sessions', 'EVOLUCIÓN DE SESIONES', COLOR_NEON_GREEN),
        ('rounds', 'EVOLUCIÓN DE RONDAS', COLOR_NEON_YELLOW)
    ]
    
    for i, (key, title, col) in enumerate(metrics):
        chart_y = start_y + i * 250
        chart_rect = pygame.Rect(grid_x, chart_y, WINDOW_W - 100, 200)
        pygame.draw.rect(target_surf, (10, 20, 35, 150), chart_rect, border_radius=8)
        draw_neon_rect(target_surf, chart_rect, (0, 100, 120), 1, False, corners=True)
        target_surf.blit(font_main.render(title, True, col), (grid_x + 20, chart_y + 15))
        
        cx, cy, cw, ch = grid_x + 60, chart_y + 60, WINDOW_W - 220, 100
        max_val = max([d.get(key, 0) for d in evolution]) if evolution else 1
        if max_val == 0: max_val = 1
        
        if len(evolution) > 1:
            points = []
            for j, d in enumerate(evolution):
                px = cx + (j * (cw / (len(evolution) - 1)))
                py = cy + ch - (d.get(key, 0) / max_val * ch)
                points.append((px, py))
            pygame.draw.lines(target_surf, col, False, points, 2)
            for j, p in enumerate(points):
                pygame.draw.circle(target_surf, col, (int(p[0]), int(p[1])), 4)
                if j % max(1, len(evolution)//10) == 0:
                    date_txt = font_small.render(evolution[j]['day'][5:], True, COLOR_TEXT_DIM)
                    target_surf.blit(date_txt, (int(p[0]) - 15, cy + ch + 10))
        else:
            d = evolution[0]
            pygame.draw.circle(target_surf, col, (cx + cw//2, cy + ch//2), 6)
            target_surf.blit(font_small.render(f"{key.capitalize()}: {d.get(key, 0)}", True, col), (cx + cw//2 + 10, cy + ch//2 - 10))

    content_height = start_y + len(metrics) * 250 + 50

def render_history(target_surf):
    global content_height
    start_y = 20
    grid_x = 50
    
    if selected_session:
        render_session_details(target_surf)
        return

    target_surf.blit(font_header.render("HISTORIAL DE SESIONES", True, COLOR_NEON_CYAN), (grid_x, start_y))
    start_y += 50
    
    header_rect = pygame.Rect(grid_x, start_y, WINDOW_W - 100, 40)
    pygame.draw.rect(target_surf, (20, 40, 60), header_rect, border_radius=4)
    
    cols = [("FECHA", 20), ("DURACIÓN", 220), ("RONDAS", 350), ("MAX VIEWERS", 450), ("AVG VIEWERS", 600), ("FXP", 750)]
    for txt, ox in cols:
        target_surf.blit(font_small.render(txt, True, COLOR_TEXT_BRIGHT), (grid_x + ox, start_y + 12))
    
    start_y += 50
    for i, s in enumerate(sessions_history):
        ry = start_y + i * 45
        row_rect = pygame.Rect(grid_x, ry, WINDOW_W - 100, 40)
        is_hover = row_rect.collidepoint(pygame.mouse.get_pos()[0], pygame.mouse.get_pos()[1] - (230 + scroll_y)) # Ajuste manual de offset
        
        pygame.draw.rect(target_surf, (15, 30, 50) if is_hover else (10, 20, 35), row_rect, border_radius=4)
        if is_hover:
            pygame.draw.rect(target_surf, COLOR_NEON_CYAN, row_rect, 1, border_radius=4)
            
        dur = s['duration_secs']
        dur_str = f"{dur//3600}h {(dur%3600)//60}m"
        
        target_surf.blit(font_small.render(s['start_time'], True, COLOR_TEXT_BRIGHT), (grid_x + 20, ry + 12))
        target_surf.blit(font_small.render(dur_str, True, COLOR_TEXT_DIM), (grid_x + 220, ry + 12))
        target_surf.blit(font_small.render(str(s['rounds']), True, COLOR_NEON_GREEN), (grid_x + 350, ry + 12))
        target_surf.blit(font_small.render(str(s['max_viewers']), True, COLOR_NEON_CYAN), (grid_x + 450, ry + 12))
        target_surf.blit(font_small.render(f"{s['avg_viewers']:.1f}", True, COLOR_NEON_CYAN), (grid_x + 600, ry + 12))
        target_surf.blit(font_small.render(f"{int(s['fxp'])}", True, COLOR_NEON_YELLOW), (grid_x + 750, ry + 12))

    content_height = start_y + len(sessions_history) * 45 + 50

def render_session_details(target_surf):
    global content_height
    start_y = 20
    grid_x = 50
    
    # Botón Volver
    back_rect = pygame.Rect(grid_x, start_y, 100, 30)
    pygame.draw.rect(target_surf, (40, 50, 60), back_rect, border_radius=4)
    target_surf.blit(font_small.render("< VOLVER", True, COLOR_TEXT_BRIGHT), (grid_x + 15, start_y + 7))
    
    # Botón Exportar Sesión
    exp_rect = pygame.Rect(grid_x + 120, start_y, 150, 30)
    pygame.draw.rect(target_surf, (0, 80, 60), exp_rect, border_radius=4)
    target_surf.blit(font_small.render("EXPORTAR CSV", True, COLOR_TEXT_BRIGHT), (exp_rect.x + 25, exp_rect.y + 7))
    
    start_y += 50
    s = selected_session['summary']
    target_surf.blit(font_header.render(f"RESUMEN DE LIVE: {s['start_time']}", True, COLOR_NEON_CYAN), (grid_x, start_y))
    start_y += 50
    
    # Grid de métricas de la sesión
    metrics = [
        ("Duración", f"{s['duration_secs']//3600}h {(s['duration_secs']%3600)//60}m", COLOR_NEON_YELLOW),
        ("Rondas", s['total_rounds'], COLOR_NEON_GREEN),
        ("Participantes", s['unique_participants_count'], COLOR_NEON_YELLOW),
        ("Pico Viewers", s['peak_viewers'], COLOR_NEON_CYAN),
        ("Avg Viewers", f"{(s['avg_viewers_sum'] / max(1, s['avg_viewers_count'])):.1f}", COLOR_NEON_CYAN),
        ("Likes", s['total_likes'], COLOR_NEON_GREEN),
        ("Mensajes", s['total_messages'], COLOR_NEON_CYAN),
        ("FXP Repartido", int(s['fxp_distributed']), COLOR_NEON_CYAN),
    ]
    
    card_w, card_h = 180, 80
    cols = 4
    for i, (lbl, val, col) in enumerate(metrics):
        r, c = i // cols, i % cols
        draw_stat_card(target_surf, grid_x + c * (card_w + 20), start_y + r * (card_h + 20), card_w, card_h, lbl, val, col)
    
    start_y += (len(metrics)//cols) * (card_h + 20) + 40
    
    # Votos y RR de la sesión
    votos = selected_session['votes']
    sube, baja = votos.get('SUBE', 0), votos.get('BAJA', 0)
    total = sube + baja
    
    v_rect = pygame.Rect(grid_x, start_y, 400, 150)
    pygame.draw.rect(target_surf, (10, 20, 35, 150), v_rect, border_radius=8)
    target_surf.blit(font_main.render("VOTOS TOTALES", True, COLOR_NEON_CYAN), (grid_x + 20, start_y + 15))
    
    if total > 0:
        bar_w = 360
        pygame.draw.rect(target_surf, COLOR_NEON_GREEN, (grid_x + 20, start_y + 60, int(bar_w * (sube/total)), 30), border_radius=4)
        pygame.draw.rect(target_surf, COLOR_NEON_RED, (grid_x + 20 + int(bar_w * (sube/total)), start_y + 60, bar_w - int(bar_w * (sube/total)), 30), border_radius=4)
        target_surf.blit(font_small.render(f"SUBE: {sube}", True, COLOR_NEON_GREEN), (grid_x + 20, start_y + 100))
        target_surf.blit(font_small.render(f"BAJA: {baja}", True, COLOR_NEON_RED), (grid_x + 300, start_y + 100))

    # RR Stats de la sesión
    rr_stats = selected_session['rr_stats']
    if rr_stats:
        rr_panel_x = grid_x + 450
        rr_panel_w = WINDOW_W - rr_panel_x - 50
        rr_rect = pygame.Rect(rr_panel_x, start_y, rr_panel_w, 150)
        pygame.draw.rect(target_surf, (10, 20, 35, 150), rr_rect, border_radius=8)
        target_surf.blit(font_main.render("RENDIMIENTO R:R", True, COLOR_NEON_CYAN), (rr_panel_x + 20, start_y + 15))
        
        header_rr = font_small.render("RATIO      WINS    LOSSES    WR%", True, COLOR_TEXT_DIM)
        target_surf.blit(header_rr, (rr_panel_x + 20, start_y + 45))
        
        for i, rr in enumerate(rr_stats[:4]):
            ry = start_y + 70 + i * 20
            total_rr = rr['win_count'] + rr['loss_count']
            wr = (rr['win_count'] / total_rr * 100) if total_rr > 0 else 0
            txt_rr = font_small.render(f"1:{rr['rr_ratio']:.1f}", True, COLOR_NEON_YELLOW)
            txt_w = font_small.render(str(rr['win_count']), True, COLOR_NEON_GREEN)
            txt_l = font_small.render(str(rr['loss_count']), True, COLOR_NEON_RED)
            txt_wr = font_small.render(f"{wr:.1f}%", True, COLOR_NEON_CYAN)
            target_surf.blit(txt_rr, (rr_panel_x + 20, ry))
            target_surf.blit(txt_w, (rr_panel_x + 100, ry))
            target_surf.blit(txt_l, (rr_panel_x + 160, ry))
            target_surf.blit(txt_wr, (rr_panel_x + 230, ry))

    content_height = start_y + 200

def render_recommendation(target_surf):
    global content_height
    start_y = 20
    grid_x = 50
    
    target_surf.blit(font_header.render("MEJOR HORARIO PARA HACER LIVE", True, COLOR_NEON_YELLOW), (grid_x, start_y))
    start_y += 60
    
    if not best_time_data or isinstance(best_time_data, str):
        msg = best_time_data if best_time_data else "Calculando recomendación..."
        target_surf.blit(font_main.render(msg, True, COLOR_TEXT_DIM), (grid_x, start_y))
        return

    # Banner de recomendación
    rec_rect = pygame.Rect(grid_x, start_y, WINDOW_W - 100, 100)
    pygame.draw.rect(target_surf, (20, 35, 60, 200), rec_rect, border_radius=10)
    draw_neon_rect(target_surf, rec_rect, COLOR_NEON_YELLOW, 2, glow=True, corners=True)
    
    rec_txt = font_header.render(best_time_data['recommendation'], True, COLOR_TEXT_BRIGHT)
    target_surf.blit(rec_txt, rec_txt.get_rect(center=rec_rect.center))
    
    start_y += 130
    
    # Detalles del análisis
    details = [
        ("Día Recomendado", best_time_data['best_day'], COLOR_NEON_YELLOW),
        ("Hora Recomendada", best_time_data['best_hour'], COLOR_NEON_CYAN),
        ("Avg Viewers Esperados", f"{best_time_data['avg_viewers']:.1f}", COLOR_NEON_GREEN),
        ("Pico Viewers Histórico", best_time_data['peak_viewers'], COLOR_NEON_CYAN),
    ]
    
    for i, (lbl, val, col) in enumerate(details):
        ry = start_y + i * 40
        target_surf.blit(font_main.render(lbl + ":", True, COLOR_TEXT_DIM), (grid_x, ry))
        target_surf.blit(font_main.render(str(val), True, col), (grid_x + 350, ry))

    content_height = start_y + 200

clock = pygame.time.Clock()
running = True

while running:
    current_time = pygame.time.get_ticks()
    mx, my = pygame.mouse.get_pos()
    
    # Eventos
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if selected_session:
                    selected_session = None
                else:
                    running = False
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1: # Click izquierdo
                # --- Click en Pestañas ---
                for i, tab in enumerate(TABS):
                    tab_rect = pygame.Rect(50 + i * 180, 80, 175, 40)
                    if tab_rect.collidepoint(mx, my):
                        current_tab = tab
                        scroll_y = 0
                        last_refresh = -REFRESH_INTERVAL_MS # Forzar recarga
                
                # --- Click en Filtros (Solo Dashboard y Evolución) ---
                if current_tab in ['DASHBOARD', 'EVOLUCIÓN']:
                    for i, f in enumerate(FILTERS):
                        f_rect = pygame.Rect(50 + i * 165, 130, 160, 40)
                        if f_rect.collidepoint(mx, my):
                            current_filter = f['id']
                            if current_filter != 'custom':
                                last_refresh = -REFRESH_INTERVAL_MS
                            scroll_y = 0
                
                # --- Click en Historial ---
                if current_tab == 'HISTORIAL':
                    if selected_session:
                        # Botón Volver
                        header_h = 130
                        if pygame.Rect(50, 20 + header_h + scroll_y, 100, 30).collidepoint(mx, my):
                            selected_session = None
                        # Botón Exportar Sesión
                        elif pygame.Rect(170, 20 + header_h + scroll_y, 150, 30).collidepoint(mx, my):
                            export_session_to_csv(selected_session)
                    else:
                        # Click en fila de historial
                        header_h = 130
                        start_y_h = 20 + 100 + header_h + scroll_y
                        for i, s in enumerate(sessions_history):
                            if pygame.Rect(50, start_y_h + i * 45, WINDOW_W - 100, 40).collidepoint(mx, my):
                                selected_session = get_session_details(s['id'])
                                scroll_y = 0
                
                # --- Click en Dashboard (Exportar) ---
                if current_tab == 'DASHBOARD':
                    header_h = 230 if current_filter == 'custom' else 180
                    export_rect = pygame.Rect(50, content_height - 40 + header_h + scroll_y, 200, 35)
                    if export_rect.collidepoint(mx, my):
                        export_period_to_csv(analytics_data, current_filter)

                # --- Click en Controles Custom ---
                if current_tab in ['DASHBOARD', 'EVOLUCIÓN'] and current_filter == 'custom':
                    # Botones Start
                    start_rect = pygame.Rect(120, 180, 250, 35)
                    btn_s_m = pygame.Rect(start_rect.right + 5, 180, 35, 35)
                    btn_s_p = pygame.Rect(start_rect.right + 45, 180, 35, 35)
                    btn_s_mm = pygame.Rect(start_rect.right + 85, 180, 35, 35)
                    btn_s_pp = pygame.Rect(start_rect.right + 125, 180, 35, 35)
                    
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
                    end_rect = pygame.Rect(WINDOW_W // 2 + 80, 180, 200, 35)
                    btn_e_m = pygame.Rect(end_rect.right + 5, 180, 35, 35)
                    btn_e_p = pygame.Rect(end_rect.right + 45, 180, 35, 35)
                    btn_e_mm = pygame.Rect(end_rect.right + 85, 180, 35, 35)
                    btn_e_pp = pygame.Rect(end_rect.right + 125, 180, 35, 35)
                    
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
                    btn_apply = pygame.Rect(WINDOW_W - 180, 180, 130, 35)
                    if btn_apply.collidepoint(mx, my):
                        last_refresh = -REFRESH_INTERVAL_MS

            elif event.button == 4: # Scroll Up
                scroll_y = min(0, scroll_y + 40)
            elif event.button == 5: # Scroll Down
                header_h = 230 if current_tab in ['DASHBOARD', 'EVOLUCIÓN'] and current_filter == 'custom' else (180 if current_tab in ['DASHBOARD', 'EVOLUCIÓN'] else 130)
                scroll_y = max(-(content_height - (WINDOW_H - header_h)), scroll_y - 40)

    # Refrescar datos
    if current_time - last_refresh >= REFRESH_INTERVAL_MS:
        try:
            if current_tab == 'DASHBOARD' or current_tab == 'EVOLUCIÓN':
                if current_filter == 'custom':
                    analytics_data = get_analytics_data('custom', [custom_start_date.isoformat(), custom_end_date.isoformat()])
                else:
                    analytics_data = get_analytics_data(current_filter)
            elif current_tab == 'COMPARAR':
                comparison_data = get_comparison_data(comp_filter_1, None, comp_filter_2, None)
            elif current_tab == 'HISTORIAL':
                sessions_history = get_sessions_history()
            elif current_tab == 'RECOMENDACIÓN':
                best_time_data = get_best_time_analysis()
            
            last_refresh = current_time
        except Exception as e:
            print(f"[ANALYTICS] Error obteniendo datos: {e}")

    # Dibujar
    screen.fill(COLOR_BG)
    
    # --- HEADER FIJO ---
    header_h = 230 if current_tab in ['DASHBOARD', 'EVOLUCIÓN'] and current_filter == 'custom' else (180 if current_tab in ['DASHBOARD', 'EVOLUCIÓN'] else 130)
    header_bg = pygame.Surface((WINDOW_W, header_h), pygame.SRCALPHA)
    header_bg.fill((5, 10, 20, 255))
    screen.blit(header_bg, (0, 0))
    pygame.draw.line(screen, COLOR_NEON_CYAN, (0, header_h), (WINDOW_W, header_h), 2)
    
    title_txt = font_title.render("LEAN FX - ANALYTICS DASHBOARD", True, COLOR_NEON_CYAN)
    screen.blit(title_txt, (50, 25))
    
    # Dibujar Pestañas
    for i, tab in enumerate(TABS):
        tab_rect = pygame.Rect(50 + i * 180, 80, 175, 40)
        is_active = current_tab == tab
        btn_col = COLOR_NEON_CYAN if is_active else (40, 60, 80)
        pygame.draw.rect(screen, (20, 30, 50) if is_active else (10, 15, 25), tab_rect, border_radius=6)
        draw_neon_rect(screen, tab_rect, btn_col, 2 if is_active else 1, glow=is_active)
        lbl = font_small.render(tab, True, COLOR_TEXT_BRIGHT if is_active else COLOR_TEXT_DIM)
        screen.blit(lbl, lbl.get_rect(center=tab_rect.center))

    # Dibujar Filtros (Solo si aplica)
    if current_tab in ['DASHBOARD', 'EVOLUCIÓN']:
        for i, f in enumerate(FILTERS):
            f_rect = pygame.Rect(50 + i * 165, 130, 160, 40)
            is_active = current_filter == f['id']
            btn_col = COLOR_NEON_GREEN if is_active else (40, 60, 80)
            pygame.draw.rect(screen, (15, 35, 25) if is_active else (10, 15, 25), f_rect, border_radius=6)
            draw_neon_rect(screen, f_rect, btn_col, 2 if is_active else 1, glow=is_active)
            lbl = font_small.render(f['label'], True, COLOR_TEXT_BRIGHT if is_active else COLOR_TEXT_DIM)
            screen.blit(lbl, lbl.get_rect(center=f_rect.center))

        if current_filter == 'custom':
            screen.blit(font_small.render("DESDE:", True, COLOR_TEXT_DIM), (50, 185))
            start_rect = pygame.Rect(120, 180, 250, 35)
            pygame.draw.rect(screen, (15, 25, 45), start_rect, border_radius=4)
            txt_start = font_small.render(custom_start_date.strftime("%d / %m / %Y"), True, COLOR_TEXT_BRIGHT)
            screen.blit(txt_start, txt_start.get_rect(center=start_rect.center))
            
            screen.blit(font_small.render("HASTA:", True, COLOR_TEXT_DIM), (WINDOW_W // 2 + 20, 185))
            end_rect = pygame.Rect(WINDOW_W // 2 + 80, 180, 200, 35)
            pygame.draw.rect(screen, (15, 25, 45), end_rect, border_radius=4)
            txt_end = font_small.render(custom_end_date.strftime("%d/%m/%Y"), True, COLOR_TEXT_BRIGHT)
            screen.blit(txt_end, txt_end.get_rect(center=end_rect.center))

            btn_apply = pygame.Rect(WINDOW_W - 180, 180, 130, 35)
            pygame.draw.rect(screen, (0, 80, 60), btn_apply, border_radius=4)
            apply_txt = font_small.render("APLICAR", True, COLOR_TEXT_BRIGHT)
            screen.blit(apply_txt, apply_txt.get_rect(center=btn_apply.center))

    # --- CONTENIDO SCROLLEABLE ---
    virtual_h = max(WINDOW_H, content_height)
    content_surf = pygame.Surface((WINDOW_W, virtual_h), pygame.SRCALPHA)
    render_dashboard(content_surf)
    screen.blit(content_surf, (0, header_h + scroll_y))

    # Indicador de carga
    if current_time - last_refresh < 500:
        pygame.draw.circle(screen, COLOR_NEON_CYAN, (WINDOW_W - 50, 40), 10, 2)
        angle = (current_time / 100) % (math.pi * 2)
        pygame.draw.line(screen, COLOR_NEON_CYAN, (WINDOW_W - 50, 40), (int(WINDOW_W - 50 + math.cos(angle) * 10), int(40 + math.sin(angle) * 10)), 3)

    pygame.display.flip()
    clock.tick(FPS)

pygame.quit()
sys.exit(0)
