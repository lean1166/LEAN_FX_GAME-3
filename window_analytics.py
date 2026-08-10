"""
LEAN FX GAME - Ventana de ANALYTICS (Fase 2)

Proceso de escritorio independiente (PyQt6) para mostrar estadísticas y métricas detalladas.
Incluye filtros de tiempo y visualizaciones de rendimiento del canal.
"""
import os
import sys
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QTabWidget, QScrollArea, 
                             QPushButton, QFrame, QGridLayout, QListWidget, QListWidgetItem,
                             QDateEdit)
from PyQt6.QtCore import Qt, QTimer, QDate
from PyQt6.QtGui import QFont, QColor, QPalette

# Integración de Matplotlib para PyQt6
import matplotlib
matplotlib.use('QtAgg')
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt

from shared_paths import find_asset
from database import (
    get_analytics_data, 
    get_sessions_history, 
    get_session_details, 
    get_best_time_analysis, 
    get_comparison_data
)
from analytics_export import export_session_to_csv, export_period_to_csv, export_history_to_csv

# --- CONFIGURACIÓN Y ESTILO CYBERPUNK ---
COLOR_BG = "#050505"  # Fondo oscuro absoluto
COLOR_PANEL = "rgba(10, 15, 25, 200)"
COLOR_NEON_CYAN = "#00DCFF"
COLOR_NEON_GREEN = "#00FF7F" # Verde Neón (0, 255, 127)
COLOR_NEON_RED = "#FF3131"   # Rojo Neón (255, 49, 49)
COLOR_NEON_YELLOW = "#FFD700"
COLOR_TEXT_DIM = "#506478"
COLOR_TEXT_BRIGHT = "#FFFFFF"

class AnalyticsWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LEAN FX - ANALYTICS HUD")
        self.resize(1100, 700)
        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {COLOR_BG}; }}
            QWidget {{ color: {COLOR_TEXT_BRIGHT}; font-family: 'Consolas'; }}
        """)
        
        # Estado
        self.current_filter = 'hoy'
        self.analytics_data = None
        
        self.init_ui()
        self.refresh_data()
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_data)
        self.timer.start(10000)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(5)
        
        # 1. HEADER HUD
        header_frame = QFrame()
        header_frame.setStyleSheet(f"border-bottom: 2px solid {COLOR_NEON_CYAN}; margin-bottom: 5px;")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(0, 0, 0, 5)
        
        title = QLabel("// LEAN FX ANALYTICS SYSTEM_v3.0")
        title.setStyleSheet(f"color: {COLOR_NEON_CYAN}; font-size: 16pt; font-weight: bold; letter-spacing: 2px;")
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        self.lbl_status = QLabel("ONLINE")
        self.lbl_status.setStyleSheet(f"color: {COLOR_NEON_GREEN}; font-weight: bold; font-size: 10pt;")
        header_layout.addWidget(self.lbl_status)
        
        main_layout.addWidget(header_frame)
        
        # 2. TABS BAR (DASHBOARD, COMPARAR, etc.)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: 1px solid #1A2533; background: {COLOR_BG}; top: -1px; }}
            QTabBar::tab {{ 
                background: #0A0F19; color: {COLOR_TEXT_DIM}; padding: 6px 20px; 
                border: 1px solid #1A2533; border-bottom: none; margin-right: 2px;
                font-size: 9pt; font-weight: bold;
            }}
            QTabBar::tab:selected {{ 
                background: #141E2D; color: {COLOR_NEON_CYAN}; 
                border: 1px solid {COLOR_NEON_CYAN}; border-bottom: none;
            }}
            QTabBar::tab:hover {{ background: #1A2533; color: {COLOR_TEXT_BRIGHT}; }}
        """)
        
        # 3. FILTERS BAR (Fixed top inside dashboard)
        self.tab_dashboard = QWidget()
        self.setup_dashboard_tab()
        
        self.tab_compare = QWidget()
        self.setup_compare_tab()
        
        self.tab_evolution = QWidget()
        self.setup_evolution_tab()
        
        self.tab_history = QWidget()
        self.setup_history_tab()
        
        self.tabs.addTab(self.tab_dashboard, "DASHBOARD")
        self.tabs.addTab(self.tab_compare, "COMPARAR")
        self.tabs.addTab(self.tab_evolution, "EVOLUCIÓN")
        self.tabs.addTab(self.tab_history, "HISTORIAL")
        
        main_layout.addWidget(self.tabs)

    def setup_dashboard_tab(self):
        layout = QVBoxLayout(self.tab_dashboard)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # Barra de Filtros (Fija arriba)
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(5)
        
        filters = [
            ('HOY', 'hoy'), 
            ('AYER', 'ayer'), 
            ('7 DÍAS', '7d'), 
            ('30 DÍAS', '30d'), 
            ('TODO', 'all'),
            ('PERSONALIZADO', 'custom')
        ]
        self.filter_buttons = {}
        
        for text, key in filters:
            btn = QPushButton(text)
            btn.setCheckable(True)
            if key == 'custom':
                btn.setFixedWidth(120)
            else:
                btn.setFixedWidth(80)
            btn.clicked.connect(lambda checked, k=key: self.change_filter(k))
            btn.setStyleSheet(self.get_filter_btn_style(key == self.current_filter))
            filter_bar.addWidget(btn)
            self.filter_buttons[key] = btn
            
        filter_bar.addStretch()
        
        btn_export = QPushButton("EXPORTAR CSV")
        btn_export.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: 1px solid {COLOR_NEON_YELLOW}; color: {COLOR_NEON_YELLOW}; padding: 5px 15px; font-weight: bold; }}
            QPushButton:hover {{ background: {COLOR_NEON_YELLOW}; color: black; }}
        """)
        btn_export.clicked.connect(self.export_current_data)
        filter_bar.addWidget(btn_export)
        
        layout.addLayout(filter_bar)

        # Barra de Fecha Personalizada (Nueva) - Ahora en un contenedor para toggle
        self.custom_date_container = QWidget()
        self.custom_date_container.setVisible(False)
        custom_date_bar = QHBoxLayout(self.custom_date_container)
        custom_date_bar.setContentsMargins(5, 0, 5, 5)
        custom_date_bar.setSpacing(10)
        
        lbl_desde = QLabel("DESDE")
        lbl_desde.setFixedWidth(45)
        lbl_desde.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-size: 8pt; font-weight: bold;")
        self.date_from = QDateEdit(QDate.currentDate().addDays(-7))
        self.date_from.setCalendarPopup(True)
        self.date_from.setFixedWidth(110)
        self.date_from.setStyleSheet(f"background: #0A0F19; border: 1px solid #1A2533; color: {COLOR_NEON_CYAN}; padding: 3px;")
        
        lbl_hasta = QLabel("HASTA")
        lbl_hasta.setFixedWidth(45)
        lbl_hasta.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-size: 8pt; font-weight: bold;")
        self.date_to = QDateEdit(QDate.currentDate())
        self.date_to.setCalendarPopup(True)
        self.date_to.setFixedWidth(110)
        self.date_to.setStyleSheet(f"background: #0A0F19; border: 1px solid #1A2533; color: {COLOR_NEON_CYAN}; padding: 3px;")
        
        btn_apply = QPushButton("APLICAR FILTRO")
        btn_apply.setFixedWidth(130)
        btn_apply.setStyleSheet(f"""
            QPushButton {{ background: #141E2D; border: 1px solid {COLOR_NEON_CYAN}; color: {COLOR_NEON_CYAN}; font-weight: bold; padding: 3px; }}
            QPushButton:hover {{ background: {COLOR_NEON_CYAN}; color: black; }}
        """)
        btn_apply.clicked.connect(self.refresh_data)
        
        custom_date_bar.addWidget(lbl_desde)
        custom_date_bar.addWidget(self.date_from)
        custom_date_bar.addWidget(lbl_hasta)
        custom_date_bar.addWidget(self.date_to)
        custom_date_bar.addWidget(btn_apply)
        custom_date_bar.addStretch()
        
        layout.addWidget(self.custom_date_container)

        # 4. ÁREA DE DESPLAZAMIENTO PARA CONTENIDO
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet(f"""
            QScrollArea {{ background-color: {COLOR_BG}; border: none; }}
            QScrollBar:vertical {{
                border: none; background: #0A0F19; width: 10px; margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {COLOR_NEON_CYAN}; min-height: 20px; border-radius: 5px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)

        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet(f"background-color: {COLOR_BG};")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(5, 5, 5, 5)
        self.scroll_layout.setSpacing(15)

        # Cuadrícula de Métricas Principales (Top 8)
        self.metrics_grid = QGridLayout()
        self.metrics_grid.setSpacing(8)
        self.scroll_layout.addLayout(self.metrics_grid)

        # Contenedores para nuevos paneles
        self.panels_layout = QVBoxLayout()
        self.panels_layout.setSpacing(15)
        self.scroll_layout.addLayout(self.panels_layout)

        self.scroll_layout.addStretch()
        self.scroll.setWidget(self.scroll_content)
        layout.addWidget(self.scroll)

    def get_filter_btn_style(self, active):
        if active:
            return f"background: {COLOR_NEON_CYAN}; color: black; border: 1px solid {COLOR_NEON_CYAN}; font-weight: bold; padding: 4px;"
        return f"background: transparent; color: {COLOR_TEXT_DIM}; border: 1px solid #1A2533; padding: 4px;"

    def change_filter(self, key):
        self.current_filter = key
        
        # Mostrar/Ocultar barra de fechas personalizada
        if hasattr(self, 'custom_date_container'):
            self.custom_date_container.setVisible(key == 'custom')
            
        for k, btn in self.filter_buttons.items():
            btn.setChecked(k == key)
            btn.setStyleSheet(self.get_filter_btn_style(k == key))
        self.refresh_data()

    def setup_compare_tab(self):
        layout = QVBoxLayout(self.tab_compare)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)
        
        # Panel de Selectores (Compacto y Profesional)
        selectors_frame = QFrame()
        selectors_frame.setStyleSheet(f"background: #0A0F19; border: 1px solid #1A2533; border-radius: 4px;")
        selectors_layout = QVBoxLayout(selectors_frame)
        selectors_layout.setContentsMargins(15, 10, 15, 10)
        selectors_layout.setSpacing(8)
        
        # Contenedor horizontal para ambos períodos
        periods_container = QHBoxLayout()
        periods_container.setSpacing(20)
        
        # --- PERÍODO A ---
        period_a_layout = QVBoxLayout()
        lbl_a = QLabel("PERÍODO A (REFERENCIA)")
        lbl_a.setStyleSheet(f"color: {COLOR_NEON_CYAN}; font-weight: bold; font-size: 8pt; letter-spacing: 1px;")
        period_a_layout.addWidget(lbl_a)
        
        dates_a = QHBoxLayout()
        lbl_desde_a = QLabel("DESDE")
        lbl_desde_a.setFixedWidth(45)
        lbl_desde_a.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-size: 7pt; font-weight: bold;")
        self.date_a_from = QDateEdit(QDate.currentDate().addDays(-7))
        self.date_a_from.setCalendarPopup(True)
        self.date_a_from.setFixedHeight(25)
        self.date_a_from.setFixedWidth(110)
        self.date_a_from.setStyleSheet(f"background: #141E2D; border: 1px solid #1A2533; color: white; padding: 2px;")
        
        lbl_hasta_a = QLabel("HASTA")
        lbl_hasta_a.setFixedWidth(45)
        lbl_hasta_a.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-size: 7pt; font-weight: bold;")
        self.date_a_to = QDateEdit(QDate.currentDate())
        self.date_a_to.setCalendarPopup(True)
        self.date_a_to.setFixedHeight(25)
        self.date_a_to.setFixedWidth(110)
        self.date_a_to.setStyleSheet(f"background: #141E2D; border: 1px solid #1A2533; color: white; padding: 2px;")
        
        dates_a.addWidget(lbl_desde_a)
        dates_a.addWidget(self.date_a_from)
        dates_a.addSpacing(10)
        dates_a.addWidget(lbl_hasta_a)
        dates_a.addWidget(self.date_a_to)
        dates_a.addStretch()
        period_a_layout.addLayout(dates_a)
        
        # --- PERÍODO B ---
        period_b_layout = QVBoxLayout()
        lbl_b = QLabel("PERÍODO B (COMPARAR CON)")
        lbl_b.setStyleSheet(f"color: {COLOR_NEON_YELLOW}; font-weight: bold; font-size: 8pt; letter-spacing: 1px;")
        period_b_layout.addWidget(lbl_b)
        
        dates_b = QHBoxLayout()
        lbl_desde_b = QLabel("DESDE")
        lbl_desde_b.setFixedWidth(45)
        lbl_desde_b.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-size: 7pt; font-weight: bold;")
        self.date_b_from = QDateEdit(QDate.currentDate().addDays(-14))
        self.date_b_from.setCalendarPopup(True)
        self.date_b_from.setFixedHeight(25)
        self.date_b_from.setFixedWidth(110)
        self.date_b_from.setStyleSheet(f"background: #141E2D; border: 1px solid #1A2533; color: white; padding: 2px;")
        
        lbl_hasta_b = QLabel("HASTA")
        lbl_hasta_b.setFixedWidth(45)
        lbl_hasta_b.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-size: 7pt; font-weight: bold;")
        self.date_b_to = QDateEdit(QDate.currentDate().addDays(-8))
        self.date_b_to.setCalendarPopup(True)
        self.date_b_to.setFixedHeight(25)
        self.date_b_to.setFixedWidth(110)
        self.date_b_to.setStyleSheet(f"background: #141E2D; border: 1px solid #1A2533; color: white; padding: 2px;")
        
        dates_b.addWidget(lbl_desde_b)
        dates_b.addWidget(self.date_b_from)
        dates_b.addSpacing(10)
        dates_b.addWidget(lbl_hasta_b)
        dates_b.addWidget(self.date_b_to)
        dates_b.addStretch()
        period_b_layout.addLayout(dates_b)
        
        periods_container.addLayout(period_a_layout)
        periods_container.addLayout(period_b_layout)

        # Nota Informativa
        lbl_info = QLabel(">> TIP: PARA COMPARAR UN DÍA ESPECÍFICO, SELECCIONA LA MISMA FECHA EN 'DESDE' Y 'HASTA'")
        lbl_info.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-size: 7pt; font-style: italic; letter-spacing: 1px; margin-top: 5px;")
        
        # Botón COMPARAR
        self.btn_run_compare = QPushButton("EJECUTAR ANÁLISIS COMPARATIVO")
        self.btn_run_compare.setFixedHeight(35)
        self.btn_run_compare.setStyleSheet(f"""
            QPushButton {{ 
                background: #141E2D; color: {COLOR_NEON_CYAN}; font-weight: bold; 
                border: 1px solid {COLOR_NEON_CYAN}; border-radius: 2px;
                letter-spacing: 2px;
            }}
            QPushButton:hover {{ background: {COLOR_NEON_CYAN}; color: black; }}
        """)
        self.btn_run_compare.clicked.connect(self.refresh_comparison)
        
        selectors_layout.addLayout(periods_container)
        selectors_layout.addWidget(lbl_info)
        selectors_layout.addWidget(self.btn_run_compare)
        
        layout.addWidget(selectors_frame)
        
        # Área de resultados
        self.scroll_compare = QScrollArea()
        self.scroll_compare.setWidgetResizable(True)
        self.scroll_compare.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_compare.setStyleSheet(f"background-color: {COLOR_BG}; border: none;")
        
        self.compare_content = QWidget()
        self.compare_layout = QVBoxLayout(self.compare_content)
        self.compare_layout.setContentsMargins(5, 5, 5, 5)
        self.scroll_compare.setWidget(self.compare_content)
        layout.addWidget(self.scroll_compare)

    def setup_evolution_tab(self):
        layout = QVBoxLayout(self.tab_evolution)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # 1. Barra de Filtros de Temporalidad
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(5)
        
        self.evolution_filter = 'diario'
        evo_filters = [
            ('DIARIO', 'diario'), 
            ('SEMANAL', 'semanal'), 
            ('MENSUAL', 'mensual'), 
            ('PERSONALIZADO', 'custom')
        ]
        self.evo_filter_buttons = {}
        
        for text, key in evo_filters:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setFixedWidth(120 if key == 'custom' else 90)
            btn.clicked.connect(lambda checked, k=key: self.change_evolution_filter(k))
            btn.setStyleSheet(self.get_filter_btn_style(key == self.evolution_filter))
            filter_bar.addWidget(btn)
            self.evo_filter_buttons[key] = btn
            
        filter_bar.addStretch()
        layout.addLayout(filter_bar)

        # 2. Selector de fechas personalizado (Toggle)
        self.evo_custom_date_container = QWidget()
        self.evo_custom_date_container.setVisible(False)
        evo_date_layout = QHBoxLayout(self.evo_custom_date_container)
        evo_date_layout.setContentsMargins(5, 0, 5, 5)
        evo_date_layout.setSpacing(10)
        
        lbl_desde = QLabel("DESDE")
        lbl_desde.setFixedWidth(45)
        lbl_desde.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-size: 8pt; font-weight: bold;")
        self.evo_date_from = QDateEdit(QDate.currentDate().addDays(-30))
        self.evo_date_from.setCalendarPopup(True)
        self.evo_date_from.setFixedWidth(110)
        self.evo_date_from.setStyleSheet(f"background: #0A0F19; border: 1px solid #1A2533; color: {COLOR_NEON_CYAN}; padding: 3px;")
        
        lbl_hasta = QLabel("HASTA")
        lbl_hasta.setFixedWidth(45)
        lbl_hasta.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-size: 8pt; font-weight: bold;")
        self.evo_date_to = QDateEdit(QDate.currentDate())
        self.evo_date_to.setCalendarPopup(True)
        self.evo_date_to.setFixedWidth(110)
        self.evo_date_to.setStyleSheet(f"background: #0A0F19; border: 1px solid #1A2533; color: {COLOR_NEON_CYAN}; padding: 3px;")
        
        btn_apply = QPushButton("APLICAR RANGO")
        btn_apply.setFixedWidth(130)
        btn_apply.setStyleSheet(f"""
            QPushButton {{ background: #141E2D; border: 1px solid {COLOR_NEON_CYAN}; color: {COLOR_NEON_CYAN}; font-weight: bold; padding: 3px; }}
            QPushButton:hover {{ background: {COLOR_NEON_CYAN}; color: black; }}
        """)
        btn_apply.clicked.connect(self.update_evolution)
        
        evo_date_layout.addWidget(lbl_desde)
        evo_date_layout.addWidget(self.evo_date_from)
        evo_date_layout.addWidget(lbl_hasta)
        evo_date_layout.addWidget(self.evo_date_to)
        evo_date_layout.addWidget(btn_apply)
        evo_date_layout.addStretch()
        
        layout.addWidget(self.evo_custom_date_container)
        
        # 3. Área de Gráficos
        self.scroll_evolution = QScrollArea()
        self.scroll_evolution.setWidgetResizable(True)
        self.scroll_evolution.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_evolution.setStyleSheet(f"background-color: {COLOR_BG}; border: none;")
        
        self.evolution_content = QWidget()
        self.evolution_layout = QVBoxLayout(self.evolution_content)
        self.evolution_layout.setContentsMargins(5, 5, 5, 5)
        self.scroll_evolution.setWidget(self.evolution_content)
        layout.addWidget(self.scroll_evolution)

    def change_evolution_filter(self, key):
        self.evolution_filter = key
        
        # Toggle de barra de fechas
        if hasattr(self, 'evo_custom_date_container'):
            self.evo_custom_date_container.setVisible(key == 'custom')
            
        for k, btn in self.evo_filter_buttons.items():
            btn.setChecked(k == key)
            btn.setStyleSheet(self.get_filter_btn_style(k == key))
            
        self.update_evolution()

    def setup_history_tab(self):
        layout = QHBoxLayout(self.tab_history)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)
        
        # Lista de sesiones (Izquierda)
        left_panel = QFrame()
        left_panel.setFixedWidth(350)
        left_panel.setStyleSheet(f"background: #0A0F19; border-right: 1px solid #1A2533;")
        left_layout = QVBoxLayout(left_panel)
        
        left_layout.addWidget(self.create_section_header("HISTORIAL DE LIVES"))
        
        self.list_sessions = QListWidget()
        self.list_sessions.setStyleSheet(f"""
            QListWidget {{ background: transparent; border: none; }}
            QListWidget::item {{ 
                padding: 10px; border-bottom: 1px solid #141E2D; color: {COLOR_TEXT_DIM};
            }}
            QListWidget::item:selected {{ 
                background: #141E2D; color: {COLOR_NEON_CYAN}; border-left: 3px solid {COLOR_NEON_CYAN};
            }}
        """)
        self.list_sessions.itemClicked.connect(self.load_session_detail)
        left_layout.addWidget(self.list_sessions)
        
        btn_export_history = QPushButton("EXPORTAR HISTORIAL")
        btn_export_history.setStyleSheet(f"border: 1px solid {COLOR_NEON_YELLOW}; color: {COLOR_NEON_YELLOW}; padding: 5px;")
        btn_export_history.clicked.connect(self.export_history_csv)
        left_layout.addWidget(btn_export_history)
        
        layout.addWidget(left_panel)
        
        # Detalle de sesión (Derecha)
        self.detail_panel = QScrollArea()
        self.detail_panel.setWidgetResizable(True)
        self.detail_panel.setFrameShape(QFrame.Shape.NoFrame)
        self.detail_panel.setStyleSheet(f"background-color: {COLOR_BG}; border: none;")
        
        self.detail_content = QWidget()
        self.detail_layout = QVBoxLayout(self.detail_content)
        self.detail_panel.setWidget(self.detail_content)
        
        layout.addWidget(self.detail_panel)

    def refresh_comparison(self):
        # Obtener rangos personalizados
        start_a = self.date_a_from.date().toString("yyyy-MM-dd")
        end_a = self.date_a_to.date().toString("yyyy-MM-dd")
        
        start_b = self.date_b_from.date().toString("yyyy-MM-dd")
        end_b = self.date_b_to.date().toString("yyyy-MM-dd")
        
        data = get_comparison_data('custom', [start_a, end_a], 'custom', [start_b, end_b])
        
        # Limpiar
        while self.compare_layout.count():
            item = self.compare_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        header_text = f"COMPARACIÓN: [{start_a} a {end_a}] VS [{start_b} a {end_b}]"
        self.compare_layout.addWidget(self.create_section_header(header_text))
        
        for m in data:
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{ 
                    background: #0A0F19; border: 1px solid #1A2533; 
                    border-radius: 4px; margin-bottom: 2px;
                }}
            """)
            l = QHBoxLayout(card)
            l.setContentsMargins(15, 10, 15, 10)
            
            lbl_name = QLabel(m['label'].upper())
            lbl_name.setStyleSheet(f"color: {COLOR_TEXT_BRIGHT}; font-weight: bold; font-size: 9pt; letter-spacing: 1px;")
            
            # Formatear valores según tipo (fxp, tiempo, etc.)
            v1, v2 = m['val1'], m['val2']
            if 'FXP' in m['label']:
                val_str = f"{int(v1)} vs {int(v2)}"
            elif 'Promedio' in m['label']:
                val_str = f"{v1:.1f} vs {v2:.1f}"
            else:
                val_str = f"{v1} vs {v2}"
                
            vals = QLabel(val_str)
            vals.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-family: 'Consolas'; font-size: 9pt;")
            
            diff = m['diff']
            pct = m['pct']
            
            # Estilo de diferencia
            if diff > 0:
                col = COLOR_NEON_GREEN
                prefix = "+"
                arrow = "▲"
            elif diff < 0:
                col = COLOR_NEON_RED
                prefix = ""
                arrow = "▼"
            else:
                col = COLOR_TEXT_DIM
                prefix = ""
                arrow = "="
            
            # Formatear diferencia numérica
            if 'FXP' in m['label']:
                diff_str = f"{prefix}{int(diff)}"
            elif 'Promedio' in m['label']:
                diff_str = f"{prefix}{diff:.1f}"
            else:
                diff_str = f"{prefix}{diff}"
                
            lbl_diff = QLabel(f"{arrow} {diff_str} ({prefix}{pct:.1f}%)")
            lbl_diff.setStyleSheet(f"color: {col}; font-weight: bold; font-family: 'Consolas'; font-size: 10pt;")
            
            l.addWidget(lbl_name)
            l.addStretch()
            l.addWidget(vals)
            l.addSpacing(30)
            l.addWidget(lbl_diff)
            
            self.compare_layout.addWidget(card)
        
        self.compare_layout.addStretch()
        self.lbl_status.setText("ANÁLISIS COMPLETADO")

    def update_evolution(self):
        if not self.analytics_data: return
        evolution = self.analytics_data.get('evolution', [])
        
        # Limpiar
        while self.evolution_layout.count():
            item = self.evolution_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        if not evolution:
            self.evolution_layout.addWidget(QLabel("SIN DATOS HISTÓRICOS SUFICIENTES"), alignment=Qt.AlignmentFlag.AlignCenter)
            return

        # --- Lógica de Agrupación ---
        processed_data = []
        filter_type = getattr(self, 'evolution_filter', 'diario')
        
        if filter_type == 'diario' or filter_type == 'custom':
            processed_data = evolution
        else:
            # Agrupar por Semana o Mes
            groups = {}
            for d in evolution:
                dt = datetime.strptime(d['day'], '%Y-%m-%d')
                if filter_type == 'semanal':
                    # Usar el lunes de esa semana como etiqueta
                    key = (dt - timedelta(days=dt.weekday())).strftime('%Y-%m-%d')
                else: # mensual
                    key = dt.strftime('%Y-%m-01')
                
                if key not in groups:
                    groups[key] = {
                        'day': key, 
                        'sessions': 0, 'likes': 0, 'rounds': 0, 
                        'max_peak': 0, 'avg_viewers_sum': 0, 'avg_viewers_count': 0,
                        'messages': 0, 'participants': 0, 'fxp': 0
                    }
                
                g = groups[key]
                g['sessions'] += d.get('sessions', 1)
                g['likes'] += d['likes']
                g['rounds'] += d['rounds']
                g['max_peak'] = max(g['max_peak'], d['max_peak'])
                g['avg_viewers_sum'] += d.get('avg_viewers', 0)
                g['avg_viewers_count'] += 1
                g['messages'] += d['messages']
                g['participants'] += d['participants']
                g['fxp'] += d['fxp']
            
            # Convertir a lista y calcular promedios
            for key in sorted(groups.keys()):
                g = groups[key]
                g['avg_viewers'] = g['avg_viewers_sum'] / max(1, g['avg_viewers_count'])
                processed_data.append(g)

        # 1. Crear Figure de Matplotlib
        fig = Figure(figsize=(10, 8), dpi=100)
        fig.patch.set_facecolor(COLOR_BG)
        canvas = FigureCanvas(fig)
        canvas.setStyleSheet(f"background-color: {COLOR_BG};")
        
        # Ajustar espaciado
        fig.subplots_adjust(hspace=0.4, wspace=0.3, top=0.9, bottom=0.1)
        
        # Datos para graficar
        days = [d['day'] for d in processed_data]
        viewers = [d['max_peak'] for d in processed_data]
        likes = [d['likes'] for d in processed_data]
        participants = [d['participants'] for d in processed_data]
        fxp = [d['fxp'] for d in processed_data]
        
        metrics = [
            (viewers, "VIEWERS (PICO)", COLOR_NEON_CYAN),
            (likes, "LIKES", COLOR_NEON_RED),
            (participants, "PARTICIPANTES", COLOR_NEON_YELLOW),
            (fxp, "FXP DISTRIBUIDO", COLOR_NEON_GREEN)
        ]
        
        for i, (data, title, color) in enumerate(metrics):
            ax = fig.add_subplot(2, 2, i + 1)
            ax.set_facecolor("#0A0F19")
            
            # Línea y puntos
            ax.plot(days, data, color=color, linewidth=2, marker='o', markersize=4, markerfacecolor=color, markeredgecolor='white')
            ax.fill_between(days, data, color=color, alpha=0.1)
            
            # Estilo de ejes
            ax.set_title(title, color=color, fontsize=10, fontweight='bold', pad=10)
            ax.tick_params(axis='x', colors=COLOR_TEXT_DIM, labelsize=7, rotation=45)
            ax.tick_params(axis='y', colors=COLOR_TEXT_DIM, labelsize=7)
            
            for spine in ax.spines.values():
                spine.set_color("#1A2533")
            
            ax.grid(True, linestyle='--', alpha=0.1, color=COLOR_TEXT_DIM)
            
        self.evolution_layout.addWidget(canvas)
        
        # Tabla debajo
        title_table = "TABLA DE DATOS (" + filter_type.upper() + ")"
        self.evolution_layout.addWidget(self.create_section_header(title_table))
        
        header_row = QFrame()
        header_row.setStyleSheet("background: #141E2D; font-weight: bold;")
        h_layout = QHBoxLayout(header_row)
        cols = ["PERÍODO", "VIEWERS", "LIKES", "VOTERS", "FXP"]
        for c in cols:
            lbl = QLabel(c)
            lbl.setStyleSheet(f"color: {COLOR_NEON_CYAN}; font-size: 8pt;")
            h_layout.addWidget(lbl)
        self.evolution_layout.addWidget(header_row)
        
        # Mostrar los últimos 15 períodos procesados
        for day in reversed(processed_data[-15:]):
            row = QFrame()
            row.setStyleSheet("border-bottom: 1px solid #1A2533;")
            r_layout = QHBoxLayout(row)
            
            r_layout.addWidget(QLabel(day['day']))
            r_layout.addWidget(QLabel(str(day['max_peak'])))
            r_layout.addWidget(QLabel(str(day['likes'])))
            r_layout.addWidget(QLabel(str(day['participants'])))
            r_layout.addWidget(QLabel(str(int(day['fxp']))))
            
            self.evolution_layout.addWidget(row)
        
        self.evolution_layout.addStretch()

    def update_history_list(self):
        history = get_sessions_history(30)
        self.list_sessions.clear()
        
        for s in history:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, s['id'])
            
            date_str = s['start_time'].split('.')[0]
            item.setText(f"SESIÓN #{s['id']} - {date_str}\n{s['rounds']} RONDAS | {s['max_viewers']} PEAK")
            self.list_sessions.addItem(item)

    def load_session_detail(self, item):
        session_id = item.data(Qt.ItemDataRole.UserRole)
        details = get_session_details(session_id)
        if not details: return
        
        # Optimización: Desactivar actualizaciones visuales durante la reconstrucción
        self.detail_panel.setUpdatesEnabled(False)
        
        # Limpiar detalle
        while self.detail_layout.count():
            item = self.detail_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    si = item.layout().takeAt(0)
                    if si.widget(): si.widget().deleteLater()

        summary = details['summary']
        
        # Cabecera de detalle
        header = QHBoxLayout()
        title = QLabel(f"// DETALLE SESIÓN #{session_id}")
        title.setStyleSheet(f"color: {COLOR_NEON_CYAN}; font-size: 14pt; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()
        
        btn_exp = QPushButton("EXPORTAR SESIÓN")
        btn_exp.setStyleSheet(f"""
            QPushButton {{ border: 1px solid {COLOR_NEON_YELLOW}; color: {COLOR_NEON_YELLOW}; padding: 5px 15px; font-weight: bold; background: transparent; }}
            QPushButton:hover {{ background: {COLOR_NEON_YELLOW}; color: black; }}
        """)
        btn_exp.clicked.connect(lambda: self.export_session_csv(details))
        header.addWidget(btn_exp)
        self.detail_layout.addLayout(header)
        
        # Grid de métricas de la sesión
        grid = QGridLayout()
        grid.setSpacing(10)
        
        # Formatear duración
        dur_secs = summary.get('duration_secs', 0) or 0
        h = dur_secs // 3600
        m = (dur_secs % 3600) // 60
        s = dur_secs % 60
        duration_str = f"{int(h):02d}:{int(m):02d}:{int(s):02d}"

        metrics = [
            ("INICIO", summary['start_time'], COLOR_TEXT_BRIGHT),
            ("FIN", summary['end_time'] or "N/A", COLOR_TEXT_BRIGHT),
            ("DURACIÓN", duration_str, COLOR_NEON_GREEN),
            ("RONDAS", summary['total_rounds'], COLOR_NEON_GREEN),
            ("VIEWERS PICO", summary['peak_viewers'], COLOR_NEON_CYAN),
            ("LIKES", summary['total_likes'], COLOR_NEON_RED),
            ("FXP TOTAL", int(summary['fxp_distributed'] or 0), COLOR_NEON_YELLOW),
            ("PARTICIPANTES", summary['unique_participants_count'], COLOR_NEON_CYAN),
            ("MENSAJES", summary['total_messages'], COLOR_NEON_YELLOW),
        ]
        
        for i, (l, v, c) in enumerate(metrics):
            card = self.create_stat_card(l, v, c)
            card.setFixedHeight(70)
            grid.addWidget(card, i // 3, i % 3)
        
        self.detail_layout.addLayout(grid)
        
        # Votos y eventos (estilo HUD)
        votes = details.get('votes', {})
        sube = votes.get('SUBE', 0)
        baja = votes.get('BAJA', 0)
        total_v = sube + baja
        
        self.detail_layout.addWidget(self.create_section_header("PARTICIPACIÓN EN ESTA SESIÓN"))
        
        vote_frame = QFrame()
        vote_frame.setStyleSheet(f"background: #0A0F19; border: 1px solid #1A2533; padding: 10px;")
        v_layout = QHBoxLayout(vote_frame)
        
        lbl_v = QLabel(f"TOTAL VOTOS: {total_v}  |  SUBE: {sube}  |  BAJA: {baja}")
        lbl_v.setStyleSheet(f"color: {COLOR_TEXT_BRIGHT}; font-weight: bold;")
        v_layout.addWidget(lbl_v)
        self.detail_layout.addWidget(vote_frame)
        
        # Eventos
        events = details.get('events', [])
        if events:
            self.detail_layout.addWidget(self.create_section_header("LÍNEA DE TIEMPO DE EVENTOS"))
            ev_scroll = QScrollArea()
            ev_scroll.setWidgetResizable(True)
            ev_scroll.setFixedHeight(150)
            ev_scroll.setStyleSheet("background: transparent; border: none;")
            ev_cont = QWidget()
            ev_lay = QVBoxLayout(ev_cont)
            for ev in events:
                e_row = QLabel(f"[{ev.get('timestamp', '')}] >> {ev.get('event_name', '')}")
                e_row.setStyleSheet(f"color: {COLOR_NEON_YELLOW}; font-size: 8pt; font-family: 'Consolas';")
                ev_lay.addWidget(e_row)
            ev_lay.addStretch()
            ev_scroll.setWidget(ev_cont)
            self.detail_layout.addWidget(ev_scroll)
        
        self.detail_layout.addStretch()
        
        # Reactivar actualizaciones
        self.detail_panel.setUpdatesEnabled(True)
        self.detail_panel.verticalScrollBar().setValue(0)

    def export_session_csv(self, details):
        path = export_session_to_csv(details)
        if path: self.lbl_status.setText(f"EXPORTADO: {os.path.basename(path)}")

    def export_history_csv(self):
        history = get_sessions_history(100)
        path = export_history_to_csv(history)
        if path: self.lbl_status.setText(f"EXPORTADO: {os.path.basename(path)}")

    def update_dashboard(self):
        if not self.analytics_data: return
        
        # 1. Limpiar Grid de Métricas Principales
        while self.metrics_grid.count():
            item = self.metrics_grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        # 2. Limpiar Paneles Inferiores
        while self.panels_layout.count():
            item = self.panels_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            elif item.layout():
                # Limpiar sub-layouts
                while item.layout().count():
                    sub_item = item.layout().takeAt(0)
                    if sub_item.widget(): sub_item.widget().deleteLater()
            
        summary = self.analytics_data.get('summary', {})
        
        # Formatear duración
        dur_secs = summary.get('total_duration_secs', 0) or 0
        h = dur_secs // 3600
        m = (dur_secs % 3600) // 60
        s = dur_secs % 60
        duration_str = f"{int(h):02d}:{int(m):02d}:{int(s):02d}"
        
        # 8 métricas solicitadas
        metrics = [
            ("SESIONES", summary.get('sessions_count', 0), COLOR_NEON_CYAN),
            ("RONDAS", summary.get('rounds', 0), COLOR_NEON_GREEN),
            ("VOTERS", summary.get('participants', 0), COLOR_NEON_YELLOW),
            ("PICO VIEWERS", summary.get('max_peak', 0), COLOR_NEON_CYAN),
            ("AVG VIEWERS", round(summary.get('global_avg_viewers', 0) or 0, 1), COLOR_NEON_CYAN),
            ("LIKES", summary.get('likes', 0), COLOR_NEON_RED),
            ("TOTAL FXP", int(summary.get('fxp', 0) or 0), COLOR_NEON_YELLOW),
            ("TIEMPO TOTAL", duration_str, COLOR_NEON_GREEN)
        ]
        
        for i, (lbl, val, col) in enumerate(metrics):
            card = self.create_stat_card(lbl, val, col)
            self.metrics_grid.addWidget(card, i // 4, i % 4)

        # 3. Integrar Bloques Analíticos Inferiores
        self.add_participation_block()
        
        # Fila para R:R y Horarios (Lado a lado)
        row2_layout = QHBoxLayout()
        row2_layout.setSpacing(15)
        
        rr_block = self.create_rr_block()
        hours_block = self.create_hours_block()
        
        row2_layout.addWidget(rr_block, 1)
        row2_layout.addWidget(hours_block, 1)
        self.panels_layout.addLayout(row2_layout)
        
        # Eventos
        self.add_events_block()
        
        # 4. Añadir Tarjetas de Análisis de Horarios y Mejores Métricas (Sección Solicitada)
        self.add_key_metrics_analysis()

    def add_key_metrics_analysis(self):
        self.panels_layout.addWidget(self.create_section_header("ANÁLISIS DE MEJORES MÉTRICAS HISTÓRICAS"))
        
        container = QFrame()
        container.setStyleSheet(f"background: #0A0F19; border: 1px solid #1A2533;")
        layout = QGridLayout(container)
        layout.setSpacing(10)
        
        # Obtener análisis de horarios desde DB
        best_time = get_best_time_analysis()
        summary = self.analytics_data.get('summary', {})
        
        # Si best_time es string, no hay datos
        best_day = best_time.get('best_day', 'N/A') if isinstance(best_time, dict) else 'N/A'
        best_hour = best_time.get('best_hour', 'N/A') if isinstance(best_time, dict) else 'N/A'
        
        analysis_metrics = [
            ("MEJOR DÍA", best_day, COLOR_NEON_CYAN),
            ("MEJOR HORARIO", best_hour, COLOR_NEON_GREEN),
            ("MÁX PICO", summary.get('max_peak', 0), COLOR_NEON_CYAN),
            ("AVG MÁXIMA", round(summary.get('global_avg_viewers', 0) or 0, 1), COLOR_NEON_CYAN),
            ("PARTICIPACIÓN CHAT", f"{summary.get('messages', 0)} MSG", COLOR_NEON_YELLOW)
        ]
        
        for i, (lbl, val, col) in enumerate(analysis_metrics):
            card = self.create_stat_card(lbl, val, col)
            card.setFixedHeight(70)
            layout.addWidget(card, 0, i)
            
        self.panels_layout.addWidget(container)

    def create_section_header(self, title):
        lbl = QLabel(f"// {title}")
        lbl.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-size: 9pt; font-weight: bold; margin-top: 5px;")
        return lbl

    def add_participation_block(self):
        self.panels_layout.addWidget(self.create_section_header("PARTICIPACIÓN: SUBE vs BAJA"))
        
        votes = self.analytics_data.get('votes', {})
        sube = votes.get('SUBE', 0)
        baja = votes.get('BAJA', 0)
        total = sube + baja
        
        pct_sube = (sube / total * 100) if total > 0 else 50
        pct_baja = (baja / total * 100) if total > 0 else 50
        
        container = QFrame()
        container.setStyleSheet(f"background: #0A0F19; border: 1px solid #1A2533; border-radius: 4px;")
        layout = QVBoxLayout(container)
        
        # Barra de progreso visual
        bar_layout = QHBoxLayout()
        bar_layout.setSpacing(0)
        
        lbl_sube = QLabel(f"SUBE {sube} ({pct_sube:.1f}%)")
        lbl_sube.setStyleSheet(f"color: {COLOR_NEON_GREEN}; font-weight: bold; padding: 10px;")
        
        lbl_baja = QLabel(f"BAJA {baja} ({pct_baja:.1f}%)")
        lbl_baja.setStyleSheet(f"color: {COLOR_NEON_RED}; font-weight: bold; padding: 10px;")
        
        bar_layout.addWidget(lbl_sube)
        bar_layout.addStretch()
        bar_layout.addWidget(lbl_baja)
        layout.addLayout(bar_layout)
        
        # Barra gráfica simple
        graph_bar = QFrame()
        graph_bar.setFixedHeight(8)
        graph_bar_layout = QHBoxLayout(graph_bar)
        graph_bar_layout.setContentsMargins(0, 0, 0, 0)
        graph_bar_layout.setSpacing(0)
        
        part_sube = QFrame()
        part_sube.setStyleSheet(f"background: {COLOR_NEON_GREEN}; border: none;")
        
        part_baja = QFrame()
        part_baja.setStyleSheet(f"background: {COLOR_NEON_RED}; border: none;")
        
        graph_bar_layout.addWidget(part_sube, max(1, int(pct_sube)))
        graph_bar_layout.addWidget(part_baja, max(1, int(pct_baja)))
        
        layout.addWidget(graph_bar)
        self.panels_layout.addWidget(container)

    def create_rr_block(self):
        container = QFrame()
        container.setStyleSheet(f"background: #0A0F19; border: 1px solid #1A2533; border-left: 2px solid {COLOR_NEON_CYAN};")
        layout = QVBoxLayout(container)
        
        layout.addWidget(self.create_section_header("TOP R:R RATIOS (RENDIMIENTO)"))
        
        rr_stats = self.analytics_data.get('rr_stats', [])[:5] # Top 5
        
        if not rr_stats:
            layout.addWidget(QLabel("SIN DATOS DE TRADES"), alignment=Qt.AlignmentFlag.AlignCenter)
        else:
            for rr in rr_stats:
                ratio = rr.get('rr_ratio', 0)
                wins = rr.get('wins', 0)
                losses = rr.get('losses', 0)
                total = wins + losses
                wr = (wins / total * 100) if total > 0 else 0
                
                row = QFrame()
                row.setStyleSheet("border: none; background: transparent; border-bottom: 1px solid #141E2D;")
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 5, 0, 5)
                
                lbl_ratio = QLabel(f"RR 1:{ratio}")
                lbl_ratio.setStyleSheet(f"color: {COLOR_NEON_CYAN}; font-weight: bold;")
                
                lbl_stats = QLabel(f"WR: {wr:.1f}% ({wins}W / {losses}L)")
                lbl_stats.setStyleSheet(f"color: {COLOR_TEXT_BRIGHT}; font-size: 8pt;")
                
                row_layout.addWidget(lbl_ratio)
                row_layout.addStretch()
                row_layout.addWidget(lbl_stats)
                layout.addWidget(row)
        
        return container

    def create_hours_block(self):
        container = QFrame()
        container.setStyleSheet(f"background: #0A0F19; border: 1px solid #1A2533; border-left: 2px solid {COLOR_NEON_GREEN};")
        layout = QVBoxLayout(container)
        
        layout.addWidget(self.create_section_header("MEJOR HORARIO Y RENDIMIENTO"))
        
        best_hours = self.analytics_data.get('best_hours', [])[:5]
        
        if not best_hours:
            layout.addWidget(QLabel("SIN DATOS DE HORARIOS"), alignment=Qt.AlignmentFlag.AlignCenter)
        else:
            for h_data in best_hours:
                hour = h_data.get('hour', '00')
                avg_v = round(h_data.get('avg_viewers', 0) or 0, 1)
                part = h_data.get('participants', 0)
                
                row = QFrame()
                row.setStyleSheet("border: none; background: transparent; border-bottom: 1px solid #141E2D;")
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 5, 0, 5)
                
                lbl_hour = QLabel(f"{hour}:00 HS")
                lbl_hour.setStyleSheet(f"color: {COLOR_NEON_GREEN}; font-weight: bold;")
                
                lbl_stats = QLabel(f"AVG: {avg_v} | VOTERS: {part}")
                lbl_stats.setStyleSheet(f"color: {COLOR_TEXT_BRIGHT}; font-size: 8pt;")
                
                row_layout.addWidget(lbl_hour)
                row_layout.addStretch()
                row_layout.addWidget(lbl_stats)
                layout.addWidget(row)
        
        return container

    def add_events_block(self):
        self.panels_layout.addWidget(self.create_section_header("EVENTOS ACTIVADOS"))
        
        events = self.analytics_data.get('events', [])
        
        container = QFrame()
        container.setStyleSheet(f"background: #0A0F19; border: 1px solid #1A2533;")
        layout = QGridLayout(container)
        layout.setSpacing(10)
        
        if not events:
            layout.addWidget(QLabel("NO SE ACTIVARON EVENTOS EN ESTE PERIODO"), 0, 0, alignment=Qt.AlignmentFlag.AlignCenter)
        else:
            for i, ev in enumerate(events):
                name = ev.get('event_name', 'EVENTO')
                count = ev.get('count', 0)
                
                ev_card = QFrame()
                ev_card.setStyleSheet(f"background: #141E2D; border: 1px solid {COLOR_NEON_YELLOW}; padding: 5px;")
                ev_layout = QVBoxLayout(ev_card)
                
                lbl_name = QLabel(name)
                lbl_name.setStyleSheet(f"color: {COLOR_NEON_YELLOW}; font-size: 8pt; font-weight: bold; border: none;")
                
                lbl_count = QLabel(f"x{count}")
                lbl_count.setStyleSheet(f"color: {COLOR_TEXT_BRIGHT}; font-size: 10pt; font-weight: bold; border: none;")
                
                ev_layout.addWidget(lbl_name)
                ev_layout.addWidget(lbl_count, alignment=Qt.AlignmentFlag.AlignCenter)
                
                layout.addWidget(ev_card, i // 4, i % 4)
        
        self.panels_layout.addWidget(container)

    def create_stat_card(self, label, value, color):
        card = QFrame()
        # Estilo HUD: bordes finos, fondo oscuro, esquinas rectas
        card.setStyleSheet(f"""
            QFrame {{ 
                background: #0A0F19; 
                border: 1px solid {color}; 
                border-left: 4px solid {color};
            }}
        """)
        card.setFixedHeight(80)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)
        
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-size: 8pt; font-weight: bold; border: none; background: transparent;")
        
        val = QLabel(str(value))
        val.setStyleSheet(f"color: {color}; font-size: 18pt; font-weight: bold; border: none; background: transparent;")
        
        layout.addWidget(lbl)
        layout.addWidget(val, alignment=Qt.AlignmentFlag.AlignLeft)
        
        return card

    def export_current_data(self):
        if self.analytics_data:
            label = self.current_filter
            if label == 'custom':
                label = f"CUSTOM_{self.date_from.date().toString('yyyyMMdd')}_TO_{self.date_to.date().toString('yyyyMMdd')}"
            export_period_to_csv(self.analytics_data, label)
            self.lbl_status.setText(f"EXPORTADO: {label}")

    def refresh_data(self):
        try:
            custom_dates = None
            if self.current_filter == 'custom':
                start = self.date_from.date().toString("yyyy-MM-dd")
                end = self.date_to.date().toString("yyyy-MM-dd")
                custom_dates = [start, end]
                
            self.analytics_data = get_analytics_data(self.current_filter, custom_dates)
            self.update_dashboard()
            self.update_evolution()
            self.update_history_list()
            self.lbl_status.setText(f"UPDATED: {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"[ANALYTICS] Error: {e}")
            self.lbl_status.setText("ERROR")
            self.lbl_status.setStyleSheet(f"color: {COLOR_NEON_RED};")

    def update_history(self):
        pass  # Se implementará en la pestaña historial


    def show_session_details(self, session_id):
        # Implementar vista de detalle
        pass

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AnalyticsWindow()
    window.show()
    sys.exit(app.exec())
