import csv
import os
from datetime import datetime

def export_session_to_csv(session_details, folder="exports"):
    """Exporta los detalles de una sesión individual a CSV"""
    if not session_details:
        return None
        
    if not os.path.exists(folder):
        os.makedirs(folder)
        
    summary = session_details.get('summary', {})
    session_id = summary.get('id', 'unknown')
    start_time = summary.get('start_time', 'unknown').replace(":", "-").replace(" ", "_")
    filename = f"session_{session_id}_{start_time}.csv"
    filepath = os.path.join(folder, filename)
    
    with open(filepath, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # 1. Resumen General
        writer.writerow(["--- RESUMEN GENERAL ---"])
        for key, val in summary.items():
            writer.writerow([key, val])
        writer.writerow([])
        
        # 2. Votos
        votes = session_details.get('votes', {})
        if votes:
            writer.writerow(["--- VOTOS ---"])
            for v_type, count in votes.items():
                writer.writerow([v_type, count])
            writer.writerow([])
        
        # 3. RR Stats
        rr_stats = session_details.get('rr_stats', [])
        if rr_stats:
            writer.writerow(["--- RR STATS ---"])
            writer.writerow(["Ratio", "Wins", "Losses", "WinRate%"])
            for rr in rr_stats:
                total = rr.get('win_count', 0) + rr.get('loss_count', 0)
                wr = (rr.get('win_count', 0) / total * 100) if total > 0 else 0
                writer.writerow([f"1:{rr.get('rr_ratio', 0)}", rr.get('win_count', 0), rr.get('loss_count', 0), f"{wr:.2f}%"])
            writer.writerow([])
        
        # 4. Eventos
        events = session_details.get('events', [])
        if events:
            writer.writerow(["--- EVENTOS ---"])
            writer.writerow(["Evento", "Timestamp"])
            for ev in events:
                writer.writerow([ev.get('event_name', ''), ev.get('timestamp', '')])
            
    return filepath

def export_period_to_csv(analytics_data, period_label, folder="exports"):
    """Exporta los datos agregados de un período a CSV"""
    if not analytics_data:
        return None
        
    if not os.path.exists(folder):
        os.makedirs(folder)
        
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"analytics_{period_label.lower().replace(' ', '_')}_{date_str}.csv"
    filepath = os.path.join(folder, filename)
    
    with open(filepath, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # 1. Resumen
        writer.writerow([f"--- ANALYTICS PERIODO: {period_label} ---"])
        summary = analytics_data.get('summary', {})
        for key, val in summary.items():
            writer.writerow([key, val])
        writer.writerow([])
        
        # 2. Votos
        votes = analytics_data.get('votes', {})
        if votes:
            writer.writerow(["--- VOTOS ---"])
            for v_type, count in votes.items():
                writer.writerow([v_type, count])
            writer.writerow([])
        
        # 3. Evolución Diaria
        evolution = analytics_data.get('evolution', [])
        if evolution:
            writer.writerow(["--- EVOLUCIÓN DIARIA ---"])
            writer.writerow(["Fecha", "Sesiones", "Likes", "Rondas", "Peak Viewers", "Avg Viewers", "Messages", "Participants", "FXP"])
            for ev in evolution:
                writer.writerow([
                    ev.get('day', ''), 
                    ev.get('sessions', 0), 
                    ev.get('likes', 0), 
                    ev.get('rounds', 0),
                    ev.get('max_peak', 0),
                    f"{ev.get('avg_viewers', 0):.1f}" if isinstance(ev.get('avg_viewers'), (int, float)) else ev.get('avg_viewers', 0),
                    ev.get('messages', 0),
                    ev.get('participants', 0),
                    ev.get('fxp', 0)
                ])
            
    return filepath

def export_history_to_csv(history_list, folder="exports"):
    """Exporta la lista completa del historial de sesiones a CSV"""
    if not history_list:
        return None
        
    if not os.path.exists(folder):
        os.makedirs(folder)
        
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"history_sessions_{date_str}.csv"
    filepath = os.path.join(folder, filename)
    
    with open(filepath, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["--- HISTORIAL COMPLETO DE SESIONES ---"])
        writer.writerow(["ID", "Inicio", "Fin", "Rondas", "Max Viewers", "Avg Viewers", "Participantes", "FXP", "Duracion (seg)"])
        
        for s in history_list:
            writer.writerow([
                s.get('id', ''),
                s.get('start_time', ''),
                s.get('end_time', ''),
                s.get('rounds', 0),
                s.get('max_viewers', 0),
                f"{s.get('avg_viewers', 0):.1f}" if isinstance(s.get('avg_viewers'), (int, float)) else s.get('avg_viewers', 0),
                s.get('participants', 0),
                s.get('fxp', 0),
                s.get('duration_secs', 0)
            ])
            
    return filepath
