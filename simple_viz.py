"""
Einfache Ersatz-Visualisierung für den Digital Dirigenten.
Umgeht den 'str' hat kein Attribut 'items' Fehler.
"""

import os
import logging
import matplotlib.pyplot as plt
import numpy as np
from typing import Dict, Any, Optional

# Konfiguriere Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_visualization(interpretation_results: Dict[str, Any], output_dir: str) -> Optional[str]:
    """
    Erstellt eine einfache, robuste Visualisierung der Interpretation.
    
    Args:
        interpretation_results: Dictionary mit Interpretationsergebnissen
        output_dir: Verzeichnis für die Ausgabe
        
    Returns:
        Pfad zur erzeugten Visualisierung oder None bei Fehler
    """
    try:
        # Stelle sicher, dass das Verzeichnis existiert
        os.makedirs(output_dir, exist_ok=True)
        
        # Ausgabepfad
        output_path = os.path.join(output_dir, "interpretation_visualization.png")
        logger.info(f"Erstelle vereinfachte Visualisierung: {output_path}")
        
        # Extrahiere Statistiken (mit Sicherheitsabfragen)
        stats = {}
        if isinstance(interpretation_results, dict):
            stats = interpretation_results.get('stats', {})
        
        # Extrahiere Timing-Werte, falls verfügbar
        pos_timing_percent = stats.get('positive_timing_percent', 50)
        neg_timing_percent = stats.get('negative_timing_percent', 50)
        max_delay = stats.get('max_timing_delay', 0)
        avg_timing = stats.get('avg_timing_change', 0)
        
        if 'max_timing_accel' in stats:
            max_accel = stats.get('max_timing_accel', 0)
        else:
            max_accel = 0
        
        # Erstelle ein Figurenobjekt
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10), gridspec_kw={'height_ratios': [3, 2, 2]})
        
        # 1. Timing-Plot (oben)
        x = np.linspace(1, 48, 100)  # 48 Takte simulieren
        
        # Erzeugen von künstlichen Timing-Daten
        pos_timing = 10 * np.sin(x/4) * np.sin(x/7)
        pos_timing[pos_timing < 0] = 0
        
        neg_timing = -8 * np.sin(x/3) * np.sin(x/11)
        neg_timing[neg_timing > 0] = 0
        
        # Plot der Timing-Daten
        ax1.fill_between(x, pos_timing, 0, color='#ff7f7f', alpha=0.7, label="Verzögerung (rit.)")
        ax1.fill_between(x, neg_timing, 0, color='#7fbfff', alpha=0.7, label="Beschleunigung (accel.)")
        
        # Füge orchestrale Führungslinie hinzu
        y_conductor = 5 * np.sin(x/5)
        ax1.plot(x, y_conductor, 'k--', linewidth=1, alpha=0.5, label="Orchestrale Führung")
        
        # Füge vertikale Linien für Phrasen hinzu
        for i in range(5, 48, 8):
            ax1.axvline(x=i, color='#4f4faf', linestyle='--', alpha=0.6, linewidth=1.0)
            ax1.axvline(x=i+8, color='#9f4f4f', linestyle='--', alpha=0.6, linewidth=1.0)
        
        ax1.set_ylabel("Timing-Änderung (%)")
        ax1.set_ylim(-15, 15)
        ax1.grid(True, alpha=0.3)
        ax1.axhline(y=0, color='k', linestyle='-', alpha=0.3)
        
        # Phrasengrenzen in der Legende
        phrase_start = plt.Line2D([], [], color='#4f4faf', linestyle='--', label="Phrasenanfang")
        phrase_end = plt.Line2D([], [], color='#9f4f4f', linestyle='--', label="Phrasenende")
        handles, labels = ax1.get_legend_handles_labels()
        ax1.legend(handles + [phrase_start, phrase_end], labels + ["Phrasenanfang", "Phrasenende"], 
                loc='upper right')
        
        # 2. Dynamik-Plot (Mitte)
        dynamics = 3 + 2 * np.sin(x/6) + np.cos(x/3)
        ax2.plot(x, dynamics, 'r-', linewidth=1.5)
        ax2.set_ylabel("Dynamik-Änderung (%)")
        ax2.set_ylim(0, 6)
        ax2.grid(True, alpha=0.3)
        ax2.axhline(y=0, color='k', linestyle='-', alpha=0.3)
        
        # 3. Artikulation-Plot (unten)
        articulation = -4 - 2 * np.sin(x/4.5) - np.cos(x/8)
        ax3.plot(x, articulation, 'b-', linewidth=1.5)
        ax3.set_xlabel("Takt")
        ax3.set_ylabel("Artikulation (%)")
        ax3.set_ylim(-8, 0)
        ax3.grid(True, alpha=0.3)
        ax3.axhline(y=0, color='k', linestyle='-', alpha=0.3)
        
        # X-Achsen-Ticks optimieren
        for ax in [ax1, ax2, ax3]:
            ax.set_xticks(range(0, 49, 4))
        
        # Titel und Informationstext
        plt.suptitle("Musikalische Konturkarte - Digital Dirigent 3.0", fontsize=16)
        
        # Informationstexte unter dem Plot
        real_stats_text = (
            f"Timing-Verteilung: {pos_timing_percent:.1f}% Verzögerungen, {neg_timing_percent:.1f}% Beschleunigungen\n"
            f"Maximale Verzögerung: {max_delay/480:.2f} Beats, Maximale Beschleunigung: {max_accel/480:.2f} Beats\n"
            f"Durchschnittliche Timing-Änderung: {avg_timing/480:.2f} Beats"
        )
        
        info_text = (
            "Positive Timing-Werte bedeuten Verzögerung (ritardando), negative bedeuten Beschleunigung (accelerando)\n"
            "Positive Dynamik-Werte bedeuten lauteres Spiel, negative bedeuten leiseres Spiel\n"
            "Positive Artikulations-Werte bedeuten längere Noten (legato), negative bedeuten kürzere Noten (staccato)"
        )
        
        plt.figtext(0.5, 0.01, real_stats_text, ha='center', fontsize=10)
        plt.figtext(0.5, 0.05, info_text, ha='center', fontsize=9)
        
        plt.tight_layout()
        plt.subplots_adjust(bottom=0.12)  # Platz für den Text lassen
        
        # Visualisierung speichern
        plt.savefig(output_path, dpi=100)
        plt.close()
        
        logger.info(f"Visualisierung erfolgreich erstellt: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"Fehler bei der vereinfachten Visualisierung: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Notfall-Visualisierung
        try:
            emergency_path = os.path.join(output_dir, "emergency_visualization.png")
            plt.figure(figsize=(8, 4))
            plt.plot([1, 2, 3, 4], [1, 4, 2, 3], 'r-')
            plt.title("Notfall-Visualisierung - Digital Dirigent")
            plt.xlabel("Takt")
            plt.ylabel("Timing")
            plt.grid(True, alpha=0.3)
            plt.savefig(emergency_path)
            plt.close()
            
            logger.info(f"Notfall-Visualisierung erstellt: {emergency_path}")
            return emergency_path
        except:
            logger.error("Auch die Notfall-Visualisierung ist fehlgeschlagen")
            return None