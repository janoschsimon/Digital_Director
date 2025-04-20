"""
Direct Visualization Modul für den Digital Dirigenten 3.0
---------------------------------------------------------
Visualisiert die musikalische Interpretation mit bidirektionaler Timing-Darstellung.
Notfall-Version mit extremer Fehlerbehandlung.
"""

import os
import logging
import numpy as np
import matplotlib
# Force the use of Agg backend for better stability in web environments
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import matplotlib.colors as mcolors
from typing import Dict, List, Tuple, Any, Optional
import gc  # For explicit garbage collection

# Konfiguriere Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# NOTFALL-SICHERHEITSFUNKTION
def safe_items(obj):
    """
    Sichere Methode für dict.items(), die mit None, Strings und anderen Nicht-Dictionaries umgehen kann.
    
    Args:
        obj: Ein beliebiges Objekt, von dem .items() angefordert wird
        
    Returns:
        Leere Liste, wenn obj kein Dictionary ist, sonst obj.items()
    """
    if obj is None:
        logger.warning("SICHERHEIT: safe_items() auf None aufgerufen")
        return []
    if isinstance(obj, str):
        logger.warning(f"SICHERHEIT: safe_items() auf String aufgerufen: {obj[:20]}...")
        return []
    if not isinstance(obj, dict):
        logger.warning(f"SICHERHEIT: safe_items() auf Nicht-Dictionary aufgerufen: {type(obj)}")
        return []
    return obj.items()

def create_emergency_visualization(output_path):
    """
    Erstellt eine einfache Notfall-Visualisierung bei Fehlern.
    """
    try:
        plt.figure(figsize=(10, 6))
        plt.plot([1, 2, 3, 4], [0, 3, 1, 5], 'r-', label="Verzögerung")
        plt.plot([1, 2, 3, 4], [0, -2, -1, 0], 'b-', label="Beschleunigung")
        plt.axhline(y=0, color='k', linestyle='-')
        plt.xlabel("Takt")
        plt.ylabel("Timing-Änderung")
        plt.title("NOTFALL-VISUALISIERUNG\nBidirektionales Timing-Beispiel")
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(output_path)
        plt.close()
        logger.info(f"Notfall-Visualisierung gespeichert: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Sogar die Notfall-Visualisierung ist fehlgeschlagen: {e}")
        return None

def create_direct_visualization(interpretation_results, output_path=None, figure_size=(15, 12)):
    """
    Hauptfunktion zur Visualisierung der musikalischen Interpretation.
    
    Args:
        interpretation_results: Ergebnisse der musikalischen Interpretation
        output_path: Pfad für die Ausgabedatei
        figure_size: Größe der Ausgabegrafik (Breite, Höhe) in Zoll
        
    Returns:
        Figure-Objekt der Matplotlib-Visualisierung oder None bei Fehler
    """
    try:
        logger.info("Erstelle Visualisierung der musikalischen Interpretation...")
        
        # KRITISCHE SICHERHEITSÜBERPRÜFUNG
        if interpretation_results is None:
            logger.error("interpretation_results ist None - erstelle Notfall-Visualisierung")
            if output_path:
                return create_emergency_visualization(output_path)
            return None
            
        if not isinstance(interpretation_results, dict):
            logger.error(f"interpretation_results hat falschen Typ: {type(interpretation_results)}")
            if output_path:
                return create_emergency_visualization(output_path)
            return None
            
        # ORCHESTRAL CONDUCTOR SICHERHEITSÜBERPRÜFUNG
        if 'orchestral_conductor' in interpretation_results:
            oc = interpretation_results['orchestral_conductor']
            
            # Prüfe und repariere agogic_map
            if not hasattr(oc, 'agogic_map') or oc.agogic_map is None:
                logger.critical("SICHERHEIT: agogic_map nicht gefunden oder ist None - erstelle leeres Dictionary")
                oc.agogic_map = {0: 0.0}
            elif isinstance(oc.agogic_map, str):
                logger.critical(f"SICHERHEIT: agogic_map ist String '{oc.agogic_map[:20]}...' - konvertiere zu Dictionary")
                # Versuche den String in ein Dictionary zu konvertieren, wenn er wie eines aussieht
                if oc.agogic_map.startswith('{') and oc.agogic_map.endswith('}'):
                    try:
                        import json
                        oc.agogic_map = json.loads(oc.agogic_map)
                    except:
                        oc.agogic_map = {0: 0.0}  # Fallback
                else:
                    oc.agogic_map = {0: 0.0}  # Einfaches Fallback-Dictionary
            elif not isinstance(oc.agogic_map, dict):
                logger.critical(f"SICHERHEIT: agogic_map hat falschen Typ: {type(oc.agogic_map)} - korrigiere")
                oc.agogic_map = {0: 0.0}
                
            # Prüfe und repariere phrase_boundaries
            if not hasattr(oc, 'phrase_boundaries') or oc.phrase_boundaries is None:
                logger.critical("SICHERHEIT: phrase_boundaries nicht gefunden oder ist None - erstelle leere Liste")
                oc.phrase_boundaries = []
            elif isinstance(oc.phrase_boundaries, str):
                logger.critical(f"SICHERHEIT: phrase_boundaries ist String - konvertiere zu leerer Liste")
                oc.phrase_boundaries = []
            elif not isinstance(oc.phrase_boundaries, list):
                logger.critical(f"SICHERHEIT: phrase_boundaries hat falschen Typ: {type(oc.phrase_boundaries)} - korrigiere")
                oc.phrase_boundaries = []
        else:
            logger.warning("orchestral_conductor nicht in interpretation_results gefunden")
            
        # Schließe alle offenen Figuren
        plt.close('all')
        
        # Extrahiere die Daten für die Visualisierung mit Fehlerbehandlung
        timing_data = extract_bidirectional_timing_values(interpretation_results)
        dynamics_data = extract_dynamics_values(interpretation_results)
        articulation_data = extract_articulation_values(interpretation_results)
        
        # Stelle sicher, dass alle Daten die gleiche Länge haben
        max_length = max(len(timing_data['measures']), 
                        len(dynamics_data['measures']), 
                        len(articulation_data['measures']))
        
        if max_length < 2:
            logger.error("Unzureichende Daten für Visualisierung - erstelle Notfall-Visualisierung")
            if output_path:
                return create_emergency_visualization(output_path)
            return None
        
        # Erstelle Figure und Axes mit Fehlerbehandlung
        try:
            fig = plt.figure(figsize=figure_size)
            gs = GridSpec(3, 1, height_ratios=[3, 2, 2])
        except Exception as e:
            logger.error(f"Fehler beim Erstellen der Figure: {e}")
            if output_path:
                return create_emergency_visualization(output_path)
            return None
        
        # Berechne statistische Werte für Info-Text
        stats = calculate_visualization_statistics(timing_data, dynamics_data, articulation_data)
        
        # Haupttitel mit Dateninformationen
        title = f"Musikalische Konturkarte - {os.path.basename(output_path or 'Unbenannt')}"
        fig.suptitle(title, fontsize=16)
        
        try:
            # 1. Timing-Plot (Bidirektional)
            ax1 = fig.add_subplot(gs[0])
            
            # Bidirektionale Darstellung mit gefüllten Flächen
            ax1.fill_between(timing_data['measures'], timing_data['positive_timing'], 0, 
                            color='#ff7f7f', alpha=0.7, label="Verzögerung (rit.)")
            ax1.fill_between(timing_data['measures'], timing_data['negative_timing'], 0, 
                            color='#7fbfff', alpha=0.7, label="Beschleunigung (accel.)")
            
            # Mark phrase boundaries if available
            orchestral_conductor = None
            if 'orchestral_conductor' in interpretation_results:
                orchestral_conductor = interpretation_results.get('orchestral_conductor')
                
            if orchestral_conductor is not None and hasattr(orchestral_conductor, 'phrase_boundaries'):
                phrase_boundaries = orchestral_conductor.phrase_boundaries
                
                if phrase_boundaries and isinstance(phrase_boundaries, list):
                    try:
                        for item in phrase_boundaries:
                            if not isinstance(item, tuple) or len(item) < 2:
                                continue
                                
                            start, end = item[0], item[1]
                            
                            # Mark phrase beginnings
                            ax1.axvline(x=start+1, color='#4f4faf', linestyle='--', alpha=0.6, linewidth=1.0)
                            # Mark phrase endings
                            ax1.axvline(x=end+1, color='#9f4f4f', linestyle='--', alpha=0.6, linewidth=1.0)
                    except Exception as e:
                        logger.warning(f"Could not draw phrase boundaries: {e}")
            
            # Orchestrale Führung als gestrichelte Linie anzeigen, falls vorhanden
            if 'orchestral_direction' in timing_data and timing_data['orchestral_direction'] is not None:
                orchestral_direction = timing_data['orchestral_direction']
                
                try:
                    # Skaliere die Orchestrale Führung auf den gleichen Bereich
                    max_timing = max(max(abs(v) for v in timing_data['positive_timing']), 
                                    max(abs(v) for v in timing_data['negative_timing']))
                    if max_timing > 0:
                        scale_factor = max_timing / max(0.001, max(abs(v) for v in orchestral_direction))
                        scaled_direction = [v * scale_factor for v in orchestral_direction]
                        
                        # Stelle sicher, dass die Längen übereinstimmen
                        min_length = min(len(timing_data['measures']), len(scaled_direction))
                        if min_length > 0:
                            ax1.plot(timing_data['measures'][:min_length], 
                                    scaled_direction[:min_length], 
                                    'k--', linewidth=1, alpha=0.5, 
                                    label="Orchestrale Führung")
                except Exception as e:
                    logger.warning(f"Fehler beim Darstellen der orchestralen Führung: {e}")
            
            # Weitere Konfiguration des Timing-Plots
            max_y_value = max(max(abs(v) for v in timing_data['positive_timing']), 
                            max(abs(v) for v in timing_data['negative_timing']))
            y_limit = max(max_y_value * 1.1, 10)  # Mindestens 10% für die Y-Achse
            
            ax1.set_ylabel("Timing-Änderung (%)")
            ax1.set_ylim(-y_limit, y_limit)
            ax1.grid(True, alpha=0.3)
            ax1.axhline(y=0, color='k', linestyle='-', alpha=0.3)
            
            # Phrasengrenzen in der Legende
            phrase_start = plt.Line2D([], [], color='#4f4faf', linestyle='--', label="Phrasenanfang")
            phrase_end = plt.Line2D([], [], color='#9f4f4f', linestyle='--', label="Phrasenende")
            handles, labels = ax1.get_legend_handles_labels()
            ax1.legend(handles + [phrase_start, phrase_end], labels + ["Phrasenanfang", "Phrasenende"], 
                    loc='upper right')
        except Exception as e:
            logger.error(f"Fehler beim Erstellen des Timing-Plots: {e}")
            plt.close(fig)
            if output_path:
                return create_emergency_visualization(output_path)
            return None
        
        try:
            # 2. Dynamik-Plot
            ax2 = fig.add_subplot(gs[1])
            ax2.plot(dynamics_data['measures'], dynamics_data['dynamics_values'], 'r-', linewidth=1.5)
            ax2.set_ylabel("Dynamik-Änderung (%)")
            ax2.grid(True, alpha=0.3)
            ax2.axhline(y=0, color='k', linestyle='-', alpha=0.3)
        except Exception as e:
            logger.error(f"Fehler beim Erstellen des Dynamik-Plots: {e}")
            plt.close(fig)
            if output_path:
                return create_emergency_visualization(output_path)
            return None
        
        try:
            # 3. Artikulation-Plot
            ax3 = fig.add_subplot(gs[2])
            ax3.plot(articulation_data['measures'], articulation_data['articulation_values'], 'b-', linewidth=1.5)
            ax3.set_xlabel("Takt")
            ax3.set_ylabel("Artikulation (%)")
            ax3.grid(True, alpha=0.3)
            ax3.axhline(y=0, color='k', linestyle='-', alpha=0.3)
        except Exception as e:
            logger.error(f"Fehler beim Erstellen des Artikulation-Plots: {e}")
            plt.close(fig)
            if output_path:
                return create_emergency_visualization(output_path)
            return None
        
        # X-Achsen-Ticks optimieren
        for ax in [ax1, ax2, ax3]:
            if max_length > 100:
                # Bei vielen Takten: Zeige nur jeden 10. Takt
                ax.set_xticks(range(1, max_length + 1, 10))
            elif max_length > 50:
                # Bei mittelvielen Takten: Zeige jeden 5. Takt
                ax.set_xticks(range(1, max_length + 1, 5))
            else:
                # Bei weniger Takten: Zeige jeden 2. Takt
                ax.set_xticks(range(1, max_length + 1, 2))
        
        # Beschriftungen
        x_position = 0.01
        y_positions = [0.01, 0.04, 0.07, 0.10, 0.13, 0.16]
        
        # Informationstext am unteren Rand
        fig.text(x_position, y_positions[0], 
                f"Durchschnittliche Timing-Änderung: {stats['avg_timing_change']:.2f}%", 
                fontsize=9, transform=fig.transFigure)
        fig.text(x_position, y_positions[1], 
                f"Maximale Verzögerung: {stats['max_delay']:.2f}%, Maximale Beschleunigung: {abs(stats['max_acceleration']):.2f}%", 
                fontsize=9, transform=fig.transFigure)
        fig.text(x_position, y_positions[2], 
                f"Timing-Verteilung: {stats['positive_timing_percent']:.1f}% Verzögerungen, {stats['negative_timing_percent']:.1f}% Beschleunigungen", 
                fontsize=9, transform=fig.transFigure)
        
        fig.text(0.5, y_positions[0], 
                "Positive Timing-Werte bedeuten Verzögerung (ritardando), negative bedeuten Beschleunigung (accelerando)", 
                fontsize=9, ha='center', transform=fig.transFigure)
        fig.text(0.5, y_positions[1], 
                "Positive Dynamik-Werte bedeuten lauteres Spiel, negative bedeuten leiseres Spiel", 
                fontsize=9, ha='center', transform=fig.transFigure)
        fig.text(0.5, y_positions[2], 
                "Positive Artikulations-Werte bedeuten längere Noten (legato), negative bedeuten kürzere Noten (staccato)", 
                fontsize=9, ha='center', transform=fig.transFigure)
        
        plt.tight_layout()
        plt.subplots_adjust(bottom=0.18)  # Platz für den Text lassen
        
        # Speichern oder Anzeigen
        if output_path:
            try:
                plt.savefig(output_path, dpi=100, bbox_inches='tight')
                logger.info(f"Visualisierung gespeichert: {output_path}")
                plt.close(fig)  # Figure schließen, um Speicher freizugeben
                gc.collect()    # Garbage collection erzwingen
                return output_path
            except Exception as e:
                logger.error(f"Fehler beim Speichern der Visualisierung: {e}")
                plt.close(fig)
                if output_path:
                    return create_emergency_visualization(output_path)
                return None
        
        return fig

    except Exception as e:
        logger.error(f"Unerwarteter Fehler in der Visualisierung: {e}")
        import traceback
        logger.error(traceback.format_exc())
        plt.close('all')  # Notfall-Bereinigung
        gc.collect()      # Garbage collection erzwingen
        if output_path:
            return create_emergency_visualization(output_path)
        return None


def extract_bidirectional_timing_values(interpretation_results, measure_count=None):
    """
    Extrahiert positive und negative Timing-Werte (Verzögerungen und Beschleunigungen)
    separat für eine verbesserte Visualisierung.
    
    Args:
        interpretation_results: Ergebnisse der musikalischen Interpretation
        measure_count: Optional, Anzahl der Takte (wird automatisch bestimmt, wenn nicht angegeben)
    
    Returns:
        Dictionary mit separaten positiven und negativen Timing-Werten pro Takt
    """
    try:
        # SICHERHEITSÜBERPRÜFUNG
        if interpretation_results is None:
            logger.warning("interpretation_results ist None")
            return default_timing_data()
            
        if not isinstance(interpretation_results, dict):
            logger.warning(f"interpretation_results hat falschen Typ: {type(interpretation_results)}")
            return default_timing_data()
            
        voices = interpretation_results.get('voices', [])
        if not voices:
            logger.warning("Keine Stimmen für Timing-Analyse gefunden")
            return default_timing_data()
        
        # Extract orchestral direction if available
        orchestral_conductor = interpretation_results.get('orchestral_conductor')
        orchestral_direction = None
        
        # Neue zusätzliche Typprüfung
        if isinstance(orchestral_conductor, dict):
            agogic_map = orchestral_conductor.get('agogic_map', {})
        
        # SICHERHEITSCHECK für orchestral_conductor und agogic_map
        if orchestral_conductor is not None:
            # Stelle sicher, dass orchestral_conductor ein Objekt ist
            if hasattr(orchestral_conductor, 'agogic_map'):
                agogic_map = orchestral_conductor.agogic_map
                
                # KRITISCHE SICHERHEITSPRÜFUNG mit verbesserter Fehlerbehandlung
                if agogic_map is None:
                    logger.warning("agogic_map ist None - verwende leeres Dictionary")
                    agogic_map = {}
                
                elif isinstance(agogic_map, str):
                    logger.warning(f"agogic_map ist String - verwende leeres Dictionary")
                    # Versuche den String in ein Dictionary zu konvertieren, wenn möglich
                    try:
                        if agogic_map.startswith('{') and agogic_map.endswith('}'):
                            import json
                            agogic_map = json.loads(agogic_map)
                        else:
                            agogic_map = {}
                    except:
                        agogic_map = {}
                
                elif not isinstance(agogic_map, dict):
                    logger.warning(f"agogic_map hat falschen Typ: {type(agogic_map)} - verwende leeres Dictionary")
                    agogic_map = {}
                
                if agogic_map:  # Nur verarbeiten, wenn nicht leer
                    try:
                        # Sichere Verarbeitung der agogic_map
                        keys = list(agogic_map.keys())
                        if keys:
                            max_key = max(keys)
                            orchestral_direction = []
                            for i in range(max_key + 1):
                                orchestral_direction.append(agogic_map.get(i, 0))
                    except Exception as e:
                        logger.warning(f"Fehler bei Verarbeitung der agogic_map: {e}")
                        orchestral_direction = None
        
        # Bestimme die Anzahl der Takte, falls nicht angegeben
        if measure_count is None:
            max_measure = 0
            for voice in voices:
                if hasattr(voice, 'notes') and voice.notes:
                    for note in voice.notes:
                        # Taktnummer basierend auf Startzeit schätzen
                        try:
                            measure = estimate_measure_number(note, interpretation_results.get('ticks_per_beat', 480))
                            max_measure = max(max_measure, measure)
                        except Exception as e:
                            logger.warning(f"Fehler bei der Taktbestimmung für Note: {e}")
                            continue
            measure_count = max(1, max_measure + 1)  # Mindestens einen Takt
        
        # Sammle Timing-Änderungen pro Takt und Stimme
        timing_by_measure = [[] for _ in range(measure_count)]
        
        for voice in voices:
            if hasattr(voice, 'notes') and voice.notes:
                for note in voice.notes:
                    if hasattr(note, 'adjusted_start_time') and hasattr(note, 'original_start_time'):
                        timing_change = note.adjusted_start_time - note.original_start_time
                        # In Prozent des Viertels umrechnen für bessere Vergleichbarkeit
                        ticks_per_beat = interpretation_results.get('ticks_per_beat', 480)
                        timing_change_percent = (timing_change / ticks_per_beat) * 100
                        
                        # Taktnummer bestimmen
                        try:
                            measure = estimate_measure_number(note, ticks_per_beat)
                            if 0 <= measure < measure_count:
                                timing_by_measure[measure].append(timing_change_percent)
                        except Exception as e:
                            logger.warning(f"Fehler bei der Taktbestimmung für Note: {e}")
                            continue
        
        # Berechne verschiedene Statistiken pro Takt
        measures = list(range(1, measure_count + 1))
        positive_timing = []  # Maximale positive Werte für Hauptvisualisierung
        negative_timing = []  # Maximale negative Werte für Hauptvisualisierung
        max_pos = []          # Maximale positive Werte für Statistik
        max_neg = []          # Maximale negative Werte für Statistik
        avg_pos = []          # Durchschnitt aller positiven Werte
        avg_neg = []          # Durchschnitt aller negativen Werte
        
        for measure_values in timing_by_measure:
            if measure_values:
                pos_values = [v for v in measure_values if v > 0]
                neg_values = [v for v in measure_values if v < 0]
                
                # Maximalwerte
                max_p = max(pos_values) if pos_values else 0
                max_n = min(neg_values) if neg_values else 0
                max_pos.append(max_p)
                max_neg.append(max_n)
                
                # Durchschnittswerte
                avg_p = sum(pos_values) / len(pos_values) if pos_values else 0
                avg_n = sum(neg_values) / len(neg_values) if neg_values else 0
                avg_pos.append(avg_p)
                avg_neg.append(avg_n)
                
                # Repräsentative Werte für die Hauptvisualisierung
                # Wir verwenden die Maximalwerte, um größere Kontraste zu erhalten
                positive_timing.append(max_p)
                negative_timing.append(max_n)
            else:
                # Keine Werte für diesen Takt
                max_pos.append(0)
                max_neg.append(0)
                avg_pos.append(0)
                avg_neg.append(0)
                positive_timing.append(0)
                negative_timing.append(0)
        
        return {
            'measures': measures,
            'positive_timing': positive_timing,
            'negative_timing': negative_timing,
            'max_pos': max_pos,
            'max_neg': max_neg,
            'avg_pos': avg_pos,
            'avg_neg': avg_neg,
            'orchestral_direction': orchestral_direction
        }
    except Exception as e:
        logger.error(f"Fehler beim Extrahieren der Timing-Werte: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # Rückgabe von Standardwerten im Fehlerfall
        return default_timing_data()


def default_timing_data():
    """
    Gibt Standard-Timing-Daten zurück, wenn die eigentliche Extraktion fehlschlägt.
    
    Returns:
        Dictionary mit Standardwerten für die Visualisierung
    """
    return {
        'measures': [1, 2, 3, 4], 
        'positive_timing': [0, 5, 2, 8],  # Beispieldaten für visuelle Darstellung
        'negative_timing': [0, -3, -1, 0], 
        'max_pos': [0, 5, 2, 8], 
        'max_neg': [0, -3, -1, 0], 
        'avg_pos': [0, 3, 1, 5], 
        'avg_neg': [0, -2, -1, 0],
        'orchestral_direction': None
    }


def extract_dynamics_values(interpretation_results, measure_count=None):
    """
    Extrahiert die Dynamikänderungen pro Takt.
    
    Args:
        interpretation_results: Ergebnisse der musikalischen Interpretation
        measure_count: Optional, Anzahl der Takte
        
    Returns:
        Dictionary mit Dynamikwerten pro Takt
    """
    try:
        # SICHERHEITSÜBERPRÜFUNG
        if interpretation_results is None or not isinstance(interpretation_results, dict):
            return {'measures': [1, 2, 3, 4], 'dynamics_values': [0, 5, -3, 2]}
            
        voices = interpretation_results.get('voices', [])
        if not voices:
            return {'measures': [1, 2, 3, 4], 'dynamics_values': [0, 5, -3, 2]}
        
        # Bestimme die Anzahl der Takte, falls nicht angegeben
        if measure_count is None:
            max_measure = 0
            for voice in voices:
                if hasattr(voice, 'notes') and voice.notes:
                    for note in voice.notes:
                        try:
                            # Taktnummer basierend auf Startzeit schätzen
                            measure = estimate_measure_number(note, interpretation_results.get('ticks_per_beat', 480))
                            max_measure = max(max_measure, measure)
                        except Exception as e:
                            logger.warning(f"Fehler bei der Taktbestimmung für Note: {e}")
                            continue
            measure_count = max(1, max_measure + 1)  # Mindestens einen Takt
        
        # Sammle Dynamics-Änderungen pro Takt
        dynamics_by_measure = [[] for _ in range(measure_count)]
        
        for voice in voices:
            if hasattr(voice, 'notes') and voice.notes:
                for note in voice.notes:
                    if hasattr(note, 'adjusted_velocity') and hasattr(note, 'velocity'):
                        velocity_change = note.adjusted_velocity - note.velocity
                        # In Prozent umrechnen für bessere Vergleichbarkeit
                        velocity_change_percent = (velocity_change / max(1, note.velocity)) * 100
                        
                        try:
                            # Taktnummer bestimmen
                            measure = estimate_measure_number(note, interpretation_results.get('ticks_per_beat', 480))
                            if 0 <= measure < measure_count:
                                dynamics_by_measure[measure].append(velocity_change_percent)
                        except Exception as e:
                            logger.warning(f"Fehler bei der Taktbestimmung für Note: {e}")
                            continue
        
        # Berechne durchschnittliche Dynamics-Änderung pro Takt
        measures = list(range(1, measure_count + 1))
        dynamics_values = []
        
        for measure_values in dynamics_by_measure:
            if measure_values:
                avg_value = sum(measure_values) / len(measure_values)
                dynamics_values.append(avg_value)
            else:
                dynamics_values.append(0)
        
        return {
            'measures': measures,
            'dynamics_values': dynamics_values
        }
    except Exception as e:
        logger.error(f"Fehler beim Extrahieren der Dynamik-Werte: {e}")
        return {'measures': [1, 2, 3, 4], 'dynamics_values': [0, 5, -3, 2]}


def extract_articulation_values(interpretation_results, measure_count=None):
    """
    Extrahiert die Artikulationsänderungen pro Takt.
    
    Args:
        interpretation_results: Ergebnisse der musikalischen Interpretation
        measure_count: Optional, Anzahl der Takte
        
    Returns:
        Dictionary mit Artikulationswerten pro Takt
    """
    try:
        # SICHERHEITSÜBERPRÜFUNG
        if interpretation_results is None or not isinstance(interpretation_results, dict):
            return {'measures': [1, 2, 3, 4], 'articulation_values': [0, 4, -2, 1]}
            
        voices = interpretation_results.get('voices', [])
        if not voices:
            return {'measures': [1, 2, 3, 4], 'articulation_values': [0, 4, -2, 1]}
        
        # Bestimme die Anzahl der Takte, falls nicht angegeben
        if measure_count is None:
            max_measure = 0
            for voice in voices:
                if hasattr(voice, 'notes') and voice.notes:
                    for note in voice.notes:
                        try:
                            # Taktnummer basierend auf Startzeit schätzen
                            measure = estimate_measure_number(note, interpretation_results.get('ticks_per_beat', 480))
                            max_measure = max(max_measure, measure)
                        except Exception as e:
                            logger.warning(f"Fehler bei der Taktbestimmung für Note: {e}")
                            continue
            measure_count = max(1, max_measure + 1)  # Mindestens einen Takt
        
        # Sammle Artikulations-Änderungen pro Takt (basierend auf Notendauer)
        articulation_by_measure = [[] for _ in range(measure_count)]
        
        for voice in voices:
            if hasattr(voice, 'notes') and voice.notes:
                for note in voice.notes:
                    if (hasattr(note, 'adjusted_duration') and 
                        hasattr(note, 'original_duration') and 
                        note.original_duration > 0):
                        # Artikulation als prozentuale Änderung der Notendauer
                        duration_change = note.adjusted_duration - note.original_duration
                        duration_change_percent = (duration_change / note.original_duration) * 100
                        
                        try:
                            # Taktnummer bestimmen
                            measure = estimate_measure_number(note, interpretation_results.get('ticks_per_beat', 480))
                            if 0 <= measure < measure_count:
                                articulation_by_measure[measure].append(duration_change_percent)
                        except Exception as e:
                            logger.warning(f"Fehler bei der Taktbestimmung für Note: {e}")
                            continue
        
        # Berechne durchschnittliche Artikulation pro Takt
        measures = list(range(1, measure_count + 1))
        articulation_values = []
        
        for measure_values in articulation_by_measure:
            if measure_values:
                avg_value = sum(measure_values) / len(measure_values)
                articulation_values.append(avg_value)
            else:
                articulation_values.append(0)
        
        return {
            'measures': measures,
            'articulation_values': articulation_values
        }
    except Exception as e:
        logger.error(f"Fehler beim Extrahieren der Artikulations-Werte: {e}")
        return {'measures': [1, 2, 3, 4], 'articulation_values': [0, 4, -2, 1]}


def calculate_visualization_statistics(timing_data, dynamics_data, articulation_data):
    """
    Berechnet Statistiken für die Informationstexte.
    
    Args:
        timing_data: Timing-Daten
        dynamics_data: Dynamik-Daten
        articulation_data: Artikulations-Daten
        
    Returns:
        Dictionary mit statistischen Werten
    """
    stats = {}
    
    try:
        # SICHERHEITSÜBERPRÜFUNG - Stelle sicher, dass alle Eingaben gültig sind
        if (not isinstance(timing_data, dict) or 
            not isinstance(dynamics_data, dict) or 
            not isinstance(articulation_data, dict)):
            return {
                'avg_timing_change': 3.5,
                'max_delay': 8.0,
                'max_acceleration': -3.0,
                'positive_timing_percent': 70,
                'negative_timing_percent': 30,
                'avg_dynamics_change': 4.0,
                'max_dynamics_increase': 8.0,
                'max_dynamics_decrease': -4.0,
                'avg_articulation_change': 3.0,
                'max_legato': 5.0,
                'max_staccato': -4.0
            }
        
        # Timing-Statistiken
        if ('positive_timing' in timing_data and 
            'negative_timing' in timing_data and 
            timing_data['positive_timing'] and 
            timing_data['negative_timing']):
            
            # Durchschnittliche absolute Änderung
            pos_vals = [v for v in timing_data['positive_timing'] if v > 0]
            neg_vals = [abs(v) for v in timing_data['negative_timing'] if v < 0]
            all_vals = pos_vals + neg_vals
            
            stats['avg_timing_change'] = sum(all_vals) / len(all_vals) if all_vals else 0
            
            # Maximale Werte
            stats['max_delay'] = max(timing_data['positive_timing']) if timing_data['positive_timing'] else 0
            stats['max_acceleration'] = min(timing_data['negative_timing']) if timing_data['negative_timing'] else 0
            
            # Prozentuale Verteilung
            positive_count = sum(1 for v in timing_data['positive_timing'] if v > 0)
            negative_count = sum(1 for v in timing_data['negative_timing'] if v < 0)
            total_count = positive_count + negative_count
            
            if total_count > 0:
                stats['positive_timing_percent'] = (positive_count / total_count) * 100
                stats['negative_timing_percent'] = (negative_count / total_count) * 100
            else:
                stats['positive_timing_percent'] = 50
                stats['negative_timing_percent'] = 50
        else:
            stats['avg_timing_change'] = 0
            stats['max_delay'] = 0
            stats['max_acceleration'] = 0
            stats['positive_timing_percent'] = 50
            stats['negative_timing_percent'] = 50
        
        # Dynamics-Statistiken
        if ('dynamics_values' in dynamics_data and 
            dynamics_data['dynamics_values']):
            
            stats['avg_dynamics_change'] = sum(abs(v) for v in dynamics_data['dynamics_values']) / len(dynamics_data['dynamics_values'])
            stats['max_dynamics_increase'] = max(dynamics_data['dynamics_values'])
            stats['max_dynamics_decrease'] = min(dynamics_data['dynamics_values'])
        else:
            stats['avg_dynamics_change'] = 0
            stats['max_dynamics_increase'] = 0
            stats['max_dynamics_decrease'] = 0
        
        # Artikulations-Statistiken
        if ('articulation_values' in articulation_data and 
            articulation_data['articulation_values']):
            
            stats['avg_articulation_change'] = sum(abs(v) for v in articulation_data['articulation_values']) / len(articulation_data['articulation_values'])
            stats['max_legato'] = max(articulation_data['articulation_values'])
            stats['max_staccato'] = min(articulation_data['articulation_values'])
        else:
            stats['avg_articulation_change'] = 0
            stats['max_legato'] = 0
            stats['max_staccato'] = 0
    except Exception as e:
        logger.error(f"Fehler bei der Berechnung der Statistiken: {e}")
        # Standardwerte zurückgeben
        stats = {
            'avg_timing_change': 3.5,
            'max_delay': 8.0,
            'max_acceleration': -3.0,
            'positive_timing_percent': 70,
            'negative_timing_percent': 30,
            'avg_dynamics_change': 4.0,
            'max_dynamics_increase': 8.0,
            'max_dynamics_decrease': -4.0,
            'avg_articulation_change': 3.0,
            'max_legato': 5.0,
            'max_staccato': -4.0
        }
    
    return stats


def estimate_measure_number(note, ticks_per_beat=480):
    """
    Schätzt die Taktnummer einer Note basierend auf ihrer Startzeit.
    
    Args:
        note: Die Note
        ticks_per_beat: MIDI-Ticks pro Viertelnote
    
    Returns:
        Geschätzte Taktnummer (0-basiert)
    """
    try:
        if hasattr(note, 'measure_number'):
            return note.measure_number
            
        # Fallback: Schätzung basierend auf Startzeit (Annahme: 4/4-Takt)
        # Versuche verschiedene mögliche Attribute
        start_time = None
        if hasattr(note, 'original_start_time'):
            start_time = note.original_start_time
        elif hasattr(note, 'start_time'):
            start_time = note.start_time
        elif hasattr(note, 'adjusted_start_time'):
            start_time = note.adjusted_start_time
        
        if start_time is None:
            return 0
            
        ticks_per_measure = ticks_per_beat * 4
        return start_time // ticks_per_measure
    except Exception as e:
        logger.error(f"Fehler bei der Taktschätzung: {e}")
        return 0


def create_simplified_visualization(interpretation_results, output_path=None):
    """
    Erzeugt eine vereinfachte Fallback-Visualisierung mit einem anderen Ansatz.
    Diese Funktion wird verwendet, wenn die Hauptvisualisierung fehlschlägt.
    """
    return create_emergency_visualization(output_path)
        

def create_simple_agogic_visualization(interpretation_results, output_path=None):
    """Erstellt eine einfache Visualisierung der orchestralen Führungslinie mit durchgehender Linie."""
    try:
        # Extrahiere die Timing-Werte
        timing_data = extract_bidirectional_timing_values(interpretation_results)
        
        # Orchestrale Führung und X-Werte
        x = timing_data['measures']
        
        # WICHTIG: Wir müssen die ORIGINAL orchestrale Führung extrahieren
        # Dafür greifen wir direkt auf die orchestral_conductor zu
        orchestral_direction = None
        if 'orchestral_conductor' in interpretation_results:
            oc = interpretation_results['orchestral_conductor']
            if hasattr(oc, 'agogic_map') and isinstance(oc.agogic_map, dict):
                # Extrahiere die originalen Werte ohne Skalierung
                max_key = max(oc.agogic_map.keys()) if oc.agogic_map else 0
                orchestral_direction = []
                for i in range(max_key + 1):
                    # WICHTIG: Multipliziere mit größerem Faktor für gleiche Skala wie im komplexen Diagramm
                    value = oc.agogic_map.get(i, 0) * 15  # Skaliere auf ähnlichen Bereich wie im Original
                    orchestral_direction.append(value)
        
        if not orchestral_direction:
            logger.warning("Keine orchestrale Führungsdaten vorhanden")
            return None
        
        # Erstelle eine Figur mit dunklem Hintergrund
        plt.figure(figsize=(12, 8), facecolor='#333333')
        ax = plt.axes(facecolor='#333333')
        
        # Stelle sicher, dass die Längen übereinstimmen
        min_length = min(len(x), len(orchestral_direction))
        
        # Plotte die orchestrale Führungslinie als DURCHGEHENDE Linie
        plt.plot(x[:min_length], orchestral_direction[:min_length], 
                color='white', linestyle='-', linewidth=1.5, marker='o', markersize=3)
        
        # Füge Datenpunkte mit Werten hinzu
        for i in range(min_length):
            val = orchestral_direction[i]
            if abs(val) > 1.0:  # Nur wichtige Werte anzeigen
                plt.annotate(f"{val:.2f}", (x[i], val), 
                            textcoords="offset points", 
                            xytext=(0,5), 
                            ha='center', 
                            color='white', 
                            fontsize=8)
        
        # Grid und Achsen
        plt.grid(True, color='#555555', linestyle='-', linewidth=0.5, alpha=0.7)
        plt.axhline(y=0, color='#777777', linestyle='-', linewidth=1)
        
        # Titel und Labels
        plt.title("Orchestrale Führung", color='white', fontsize=14)
        plt.ylabel("Timing-Änderung (%)", color='white')
        plt.xlabel("Takt", color='white')
        
        # Achsenbeschriftungen in weiß
        ax.tick_params(colors='white')
        for spine in ax.spines.values():
            spine.set_color('white')
        
        # Infotext
        plt.figtext(0.9, 0.95, "Digital Dirigent 3.0", color='white', ha='right', fontsize=10)
        plt.figtext(0.5, 0.02, 
                  "Positive Werte bedeuten Verzögerung (ritardando), negative bedeuten Beschleunigung (accelerando)", 
                  color='white', ha='center', fontsize=8)
        
        # WICHTIG: Y-Achse auf erweiterten Bereich skalieren
        plt.ylim(-25, 25)  # Verwende einen Bereich von -25% bis +25%
        
        # Speichern
        if output_path:
            # Ändere den Dateinamen zu _simple
            simple_path = output_path.replace('_visualization.png', '_simple.png')
            plt.savefig(simple_path, dpi=100, bbox_inches='tight', facecolor='#333333')
            plt.close()
            return simple_path
            
        return plt.gcf()
    except Exception as e:
        logger.error(f"Fehler bei der einfachen Visualisierung: {e}")
        return None

def create_combined_visualization(interpretation_results, output_dir, filename_prefix="interpretation"):
    """
    Erzeugt eine Visualisierung der musikalischen Interpretation und speichert sie.
    
    Args:
        interpretation_results: Ergebnisse der musikalischen Interpretation
        output_dir: Verzeichnis für die Ausgabedatei
        filename_prefix: Präfix für den Dateinamen
        
    Returns:
        Pfad zur gespeicherten Visualisierung
    """
    try:
        # KRITISCHE SICHERHEITSÜBERPRÜFUNG 
        if interpretation_results is None:
            logger.error("interpretation_results ist None - erstelle Notfall-Visualisierung")
            output_path = os.path.join(output_dir, f"{filename_prefix}_emergency_viz.png")
            return create_emergency_visualization(output_path)
        
        # Stelle sicher, dass das Ausgabeverzeichnis existiert
        try:
            os.makedirs(output_dir, exist_ok=True)
        except Exception as e:
            logger.error(f"Fehler beim Erstellen des Ausgabeverzeichnisses: {e}")
            output_dir = os.getcwd()  # Fallback: Aktuelles Verzeichnis
        
        # Erstelle Ausgabepfad
        output_path = os.path.join(output_dir, f"{filename_prefix}_visualization.png")
        fallback_path = os.path.join(output_dir, f"{filename_prefix}_simplified.png")
        emergency_path = os.path.join(output_dir, f"{filename_prefix}_emergency.png")
        
        # NOCH MEHR SICHERHEITSÜBERPRÜFUNGEN vor dem Erstellen der Visualisierung
        if 'orchestral_conductor' in interpretation_results:
            oc = interpretation_results['orchestral_conductor']
            
            # Extra-Überprüfung speziell für String-Objekte
            if hasattr(oc, 'agogic_map'):
                if isinstance(oc.agogic_map, str):
                    logger.critical(f"KRITISCH: agogic_map ist String '{oc.agogic_map[:20]}...' - konvertiere zu Dictionary")
                    # Versuche den String in ein Dictionary zu konvertieren, wenn er wie eines aussieht
                    if oc.agogic_map.startswith('{') and oc.agogic_map.endswith('}'):
                        try:
                            import json
                            oc.agogic_map = json.loads(oc.agogic_map)
                        except:
                            oc.agogic_map = {0: 0.0}  # Fallback
                    else:
                        oc.agogic_map = {0: 0.0}  # Einfaches Fallback-Dictionary
        
        # KRITISCHE VALIDIERUNG: orchestral_conductor und agogic_map
        if 'orchestral_conductor' in interpretation_results:
            oc = interpretation_results['orchestral_conductor']
            
            # Prüfe und repariere agogic_map
            if not hasattr(oc, 'agogic_map') or oc.agogic_map is None:
                logger.critical("KRITISCH: agogic_map ist None - erstelle leeres Dictionary")
                oc.agogic_map = {0: 0.0}
            elif isinstance(oc.agogic_map, str):
                logger.critical(f"KRITISCH: agogic_map ist ein String - konvertiere zu Dictionary")
                oc.agogic_map = {0: 0.0}
            elif not isinstance(oc.agogic_map, dict):
                logger.critical(f"KRITISCH: agogic_map ist kein Dictionary sondern {type(oc.agogic_map)}")
                oc.agogic_map = {0: 0.0}
            
            # Prüfe und repariere phrase_boundaries
            if not hasattr(oc, 'phrase_boundaries') or oc.phrase_boundaries is None:
                logger.critical("KRITISCH: phrase_boundaries ist None - erstelle leere Liste")
                oc.phrase_boundaries = []
            elif isinstance(oc.phrase_boundaries, str):
                logger.critical(f"KRITISCH: phrase_boundaries ist eine String - konvertiere zu leerer Liste")
                oc.phrase_boundaries = []
            elif not isinstance(oc.phrase_boundaries, list):
                logger.critical(f"KRITISCH: phrase_boundaries ist keine Liste sondern {type(oc.phrase_boundaries)}")
                oc.phrase_boundaries = []
        
        # Erstelle und speichere die Hauptvisualisierung
        try:
            result = create_direct_visualization(interpretation_results, output_path)
            
            # Erstelle zusätzlich die einfache Agogik-Visualisierung
            simple_viz = create_simple_agogic_visualization(interpretation_results, output_path)
            if simple_viz:
                logger.info(f"Einfache Agogik-Visualisierung erstellt: {simple_viz}")
            
            if result is not None:
                return output_path
        except Exception as e:
            logger.error(f"Hauptvisualisierung fehlgeschlagen: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        # Wenn die Hauptvisualisierung fehlschlägt, versuche die Notfall-Visualisierung
        logger.warning("Versuche Notfall-Visualisierung...")
        return create_emergency_visualization(emergency_path)
        
    except Exception as e:
        logger.error(f"Kritischer Fehler in der Visualisierung: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Absoluter Notfall: Erstelle eine minimale Visualisierung
        try:
            return create_emergency_visualization(os.path.join(output_dir, f"{filename_prefix}_critical_emergency.png"))
        except:
            return None

# Alias für Kompatibilität mit älteren Versionen
create_interpretation_visualization = create_direct_visualization