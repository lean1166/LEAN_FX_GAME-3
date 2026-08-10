import csv
import os
from datetime import datetime

def export_session_to_csv(session_details, folder="exports"):
    """Exporta los detalles de una sesión individual a CSV"""
    if not session_details:
        return None
        
    if not os.path.exists(folder):
        os.makedirs(folder)
        
    session_id = session_details['summary']['id']
    date_str = session_details['summary']['start_time'].replace(":", "-").replace(" ", "_")
    filename = f"session_{session_id}_{date_str}.csv"
    filepath = os.path.join(folder, filename)
    
    with open(filepath, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # 1. Resumen General
        writer.writerow(["--- RESUMEN GENERAL ---"])
        summary = session_details['summary']
        for key, val in summary.items():
            writer.writerow([key, val])
        writer.writerow([])
        
        # 2. Votos
        writer.writerow(["--- VOTOS ---"])
        votes = session_details['votes']
        for v_type, count in votes.items():
            writer.writerow([v_type, count])
        writer.writerow([])
        
        # 3. RR Stats
        writer.writerow(["--- RR STATS ---"])
        writer.writerow(["Ratio", "Wins", "Losses", "WinRate%"])
        for rr in session_details['rr_stats']:
            total = rr['win_count'] + rr['loss_count']
            wr = (rr['win_count'] / total * 100) if total > 0 else 0
            writer.writerow([f"1:{rr['rr_ratio']}", rr['win_count'], rr['loss_count'], f"{wr:.2f}%"])
        writer.writerow([])
        
        # 4. Eventos
        writer.writerow(["--- EVENTOS ---"])
        writer.writerow(["Evento", "Timestamp"])
        for ev in session_details['events']:
            writer.writerow([ev['event_name'], ev['timestamp']])
            
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
        summary = analytics_data['summary']
        for key, val in summary.items():
            writer.writerow([key, val])
        writer.writerow([])
        
        # 2. Votos
        writer.writerow(["--- VOTOS ---"])
        votes = analytics_data['votes']
        for v_type, count in votes.items():
            writer.writerow([v_type, count])
        writer.writerow([])
        
        # 3. Evolución Diaria
        writer.writerow(["--- EVOLUCIÓN DIARIA ---"])
        writer.writerow(["Fecha", "Sesiones", "Likes", "Rondas"])
        for ev in analytics_data['evolution']:
            writer.writerow([ev['day'], ev['sessions'], ev['likes'], ev['rounds']])
            
    return filepath
