"""
MIDI-Prozessor Modul für den Digital Dirigenten
-----------------------------------------------
Enthält Funktionen zur MIDI-Verarbeitung auf Notenebene.
"""

import os
import logging
import mido
import time
from typing import Dict, List, Tuple, Any, Optional, Union

# Konfiguriere Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Debugging-Hilfsvariable
DEBUG_MODE = False

def enable_debug_logging():
    """Aktiviert detaillierte Debug-Protokollierung."""
    global DEBUG_MODE
    DEBUG_MODE = True
    logger.setLevel(logging.DEBUG)
    logger.debug("Debug-Protokollierung für MIDI-Prozessor aktiviert")

def disable_debug_logging():
    """Deaktiviert detaillierte Debug-Protokollierung."""
    global DEBUG_MODE
    DEBUG_MODE = False
    logger.setLevel(logging.INFO)
    logger.info("Debug-Protokollierung für MIDI-Prozessor deaktiviert")

def process_midi_with_interpretation(input_midi: str, interpretation_results: Dict[str, Any], 
                                   output_midi: Optional[str] = None) -> str:
    """
    Verarbeitet eine MIDI-Datei mit den Interpretationsergebnissen.
    
    Args:
        input_midi: Pfad zur Eingabe-MIDI-Datei
        interpretation_results: Ergebnisse der Interpretation
        output_midi: Optionaler Pfad zur Ausgabe-MIDI-Datei
        
    Returns:
        Pfad zur verarbeiteten MIDI-Datei
    """
    start_time = time.time()
    
    if output_midi is None:
        # Generiere Ausgabepfad, wenn nicht angegeben
        base_dir = os.path.dirname(input_midi)
        base_name = os.path.splitext(os.path.basename(input_midi))[0]
        output_midi = os.path.join(base_dir, f"{base_name}_interpreted.mid")
    
    logger.info(f"Verarbeite MIDI mit Interpretation: {input_midi} -> {output_midi}")
    
    # Lade die MIDI-Datei
    try:
        logger.info(f"Öffne Eingangs-MIDI: {input_midi}")
        mid = mido.MidiFile(input_midi)
        logger.info(f"MIDI-Datei geladen: Typ {mid.type}, {len(mid.tracks)} Tracks, {mid.ticks_per_beat} Ticks/Beat")
    except Exception as e:
        logger.error(f"Fehler beim Laden der MIDI-Datei: {e}")
        return input_midi
    
    # Prüfe auf Unterschiede in der Tick-Auflösung zwischen XML und MIDI
    xml_division = interpretation_results.get('xml_division', 480)  # Default oder aus XML
    midi_ticks = mid.ticks_per_beat
    
    # Skalierungsfaktor berechnen, falls die XML-Division von MIDI-Ticks abweicht
    scale_factor = 1.0
    if xml_division != midi_ticks and xml_division > 0:
        scale_factor = midi_ticks / xml_division
        if abs(scale_factor - 1.0) > 0.1:  # Nur skalieren, wenn der Unterschied signifikant ist
            logger.info(f"Auflösungsunterschiede erkannt: MIDI ticks/beat={midi_ticks}, "
                       f"XML division={xml_division}, Skalierungsfaktor={scale_factor:.4f}")
            
            # Protokolliere Beispiele für die Skalierung
            logger.debug("Beispiele für die Skalierung:")
            logger.debug(f"  100 XML-Ticks => {int(100 * scale_factor)} MIDI-Ticks")
            logger.debug(f"  240 XML-Ticks => {int(240 * scale_factor)} MIDI-Ticks")
            logger.debug(f"  480 XML-Ticks => {int(480 * scale_factor)} MIDI-Ticks")
            
            # Skaliere alle Zeitwerte in den Interpretationsergebnissen
            scaling_start = time.time()
            
            scaled_notes = 0
            for voice in interpretation_results.get('voices', []):
                for note in voice.notes:
                    # Speichere Original-Werte für Debug-Output
                    if DEBUG_MODE and scaled_notes < 5:  # Zeige nur die ersten 5 Noten
                        original_start = note.adjusted_start_time
                        original_duration = note.adjusted_duration
                    
                    # Skaliere Start-Zeiten und Dauern
                    note.adjusted_start_time = int(note.adjusted_start_time * scale_factor)
                    note.adjusted_duration = max(1, int(note.adjusted_duration * scale_factor))
                    note.original_start_time = int(note.original_start_time * scale_factor)
                    note.original_duration = max(1, int(note.original_duration * scale_factor))
                    
                    scaled_notes += 1
                    
                    # Zeige Beispiele für die ersten 5 Noten
                    if DEBUG_MODE and scaled_notes <= 5:
                        logger.debug(f"Skalierungsbeispiel Note {scaled_notes}: "
                                   f"Start: {original_start} -> {note.adjusted_start_time}, "
                                   f"Dauer: {original_duration} -> {note.adjusted_duration}")
            
            scaling_time = time.time() - scaling_start
            logger.info(f"Zeitwerte skaliert mit Faktor {scale_factor} für {scaled_notes} Noten "
                       f"in {scaling_time:.3f} Sekunden")
    
    # Extrahiere die Informationen über angepasste Noten
    try:
        voices = interpretation_results.get('voices', [])
        if not voices:
            logger.warning("Keine Stimmeninformationen in den Interpretationsergebnissen gefunden")
            return input_midi
        
        # Log voice information
        logger.info(f"Gefundene Stimmen: {len(voices)}")
        for i, voice in enumerate(voices):
            note_count = len(voice.notes) if hasattr(voice, 'notes') else 0
            role = voice.role if hasattr(voice, 'role') else "unbekannt"
            logger.info(f"  Stimme {i+1}: Rolle={role}, {note_count} Noten")
        
        # Erstelle ein Dictionary aller angepassten Noten für schnellen Zugriff
        note_mapping_start = time.time()
        
        adjusted_notes = {}
        correction_count = 0
        for voice in voices:
            for note in voice.notes:
                key = (note.track, note.channel, note.pitch, note.original_start_time)
                
                # SICHERHEITSCHECK: Stelle sicher, dass keine Note mit Dauer 0 existiert
                if note.adjusted_duration <= 0:
                    logger.warning(f"Korrigiere Note mit Dauer 0: Track {note.track}, "
                                  f"Kanal {note.channel}, Note {note.pitch}, "
                                  f"Original-Dauer: {note.original_duration}")
                    # Setze auf 50% der Originaldauer oder mindestens 1 Tick
                    note.adjusted_duration = max(1, note.original_duration // 2)
                    correction_count += 1
                
                adjusted_notes[key] = note
        
        note_mapping_time = time.time() - note_mapping_start
        logger.info(f"Interpretationsdaten extrahiert: {len(adjusted_notes)} angepasste Noten "
                   f"({correction_count} Notendauern korrigiert) in {note_mapping_time:.3f} Sekunden")
        
        # Verarbeite jeden Track in der MIDI-Datei
        logger.info(f"Starte Verarbeitung von {len(mid.tracks)} Tracks...")
        track_start_time = time.time()
        
        for track_idx, track in enumerate(mid.tracks):
            # Finde den Track-Namen für bessere Logs
            track_name = "Unbekannt"
            for msg in track:
                if msg.is_meta and msg.type == 'track_name':
                    track_name = msg.name
                    break
            
            logger.info(f"Verarbeite Track {track_idx}: '{track_name}'")
            
            # Zähle Noten im Track für Statistik
            note_count = sum(1 for msg in track if msg.type == 'note_on' and hasattr(msg, 'velocity') and msg.velocity > 0)
            logger.info(f"  Track enthält {note_count} Noten")
            
            # Verarbeite und aktualisiere den Track
            process_track(track_idx, track, adjusted_notes, mid.ticks_per_beat)
        
        track_processing_time = time.time() - track_start_time
        logger.info(f"Track-Verarbeitung abgeschlossen in {track_processing_time:.3f} Sekunden")
        
        # Speichere die verarbeitete MIDI-Datei
        save_start = time.time()
        mid.save(output_midi)
        save_time = time.time() - save_start
        
        # Validiere die erzeugte Datei
        if os.path.exists(output_midi):
            file_size = os.path.getsize(output_midi)
            logger.info(f"Interpretierte MIDI-Datei gespeichert: {output_midi} ({file_size} Bytes) "
                       f"in {save_time:.3f} Sekunden")
        else:
            logger.error(f"Fehler: MIDI-Datei konnte nicht gespeichert werden!")
        
        # Gesamtzeit erfassen
        total_time = time.time() - start_time
        logger.info(f"Gesamtverarbeitungszeit: {total_time:.3f} Sekunden")
        
        return output_midi
    
    except Exception as e:
        logger.error(f"Fehler bei der MIDI-Verarbeitung: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return input_midi

def process_track(track_idx: int, track: mido.MidiTrack, 
                adjusted_notes: Dict[Tuple[int, int, int, int], Any],
                ticks_per_beat: int) -> None:
    """
    Verarbeitet einen einzelnen MIDI-Track mit den angepassten Notendaten.
    
    Args:
        track_idx: Index des Tracks
        track: MIDI-Track
        adjusted_notes: Dictionary mit angepassten Noten
        ticks_per_beat: MIDI-Ticks pro Viertelnote
    """
    track_start_time = time.time()
    
    # Sammle alle Events mit absoluten Zeiten
    abs_events = []
    current_time = 0
    
    # Aktive Noten (für Note-Off-Ereignisse)
    active_notes = {}  # (note, channel) -> (adjusted_end_time, original_msg)
    
    # Statistiken für diesen Track
    original_notes = 0
    adjusted_notes_count = 0
    timing_changes = []
    velocity_changes = []
    duration_changes = []
    
    # Sammle Events und identifiziere Note-Events für Anpassung
    event_collection_start = time.time()
    
    for msg in track:
        current_time += msg.time
        
        if msg.type == 'note_on' and hasattr(msg, 'velocity') and msg.velocity > 0:
            original_notes += 1
            
            # Suche die angepasste Note
            key = (track_idx, msg.channel, msg.note, current_time)
            if key in adjusted_notes:
                adjusted_notes_count += 1
                
                # Verwende die angepassten Parameter
                adj_note = adjusted_notes[key]
                
                # SICHERHEITSCHECK: Prüfe nochmals, ob die Dauer in Ordnung ist
                if adj_note.adjusted_duration <= 0:
                    logger.warning(f"Korrigiere Note mit Dauer 0 im Track-Processing: Track {track_idx}, "
                                  f"Kanal {msg.channel}, Note {msg.note}")
                    # Korrigiere auf mindestens 1 Tick oder die Hälfte der ursprünglichen Dauer
                    adj_note.adjusted_duration = max(1, adj_note.original_duration // 2)
                
                # Sammle Änderungsstatistiken
                time_change = adj_note.adjusted_start_time - current_time
                velocity_change = adj_note.adjusted_velocity - msg.velocity
                duration_change = adj_note.adjusted_duration - adj_note.original_duration
                
                timing_changes.append(time_change)
                velocity_changes.append(velocity_change)
                duration_changes.append(duration_change)
                
                # Ersetze das Note-On Event mit angepassten Werten
                adj_note_on = msg.copy(time=0, velocity=adj_note.adjusted_velocity)
                abs_events.append((adj_note.adjusted_start_time, adj_note_on))
                
                # Berechne die Ende-Zeit basierend auf angepasster Dauer
                adjusted_end_time = adj_note.adjusted_start_time + adj_note.adjusted_duration
                
                # Speichere das originale Note-Off, um es später anzupassen
                active_notes[(msg.note, msg.channel)] = (adjusted_end_time, msg.note, msg.channel)
                
                # Zeige Beispiele für die ersten paar Noten, wenn im Debug-Modus
                if DEBUG_MODE and adjusted_notes_count <= 5:
                    logger.debug(f"Note {adjusted_notes_count}: Pitch {msg.note}, "
                               f"Startzeit: {current_time} -> {adj_note.adjusted_start_time} "
                               f"(Differenz: {time_change}), "
                               f"Dauer: {adj_note.original_duration} -> {adj_note.adjusted_duration} "
                               f"(Differenz: {duration_change}), "
                               f"Velocity: {msg.velocity} -> {adj_note.adjusted_velocity} "
                               f"(Differenz: {velocity_change})")
            else:
                # Keine Anpassung gefunden, behalte original
                abs_events.append((current_time, msg.copy(time=0)))
                
                if DEBUG_MODE and original_notes <= 5:
                    logger.debug(f"Nicht angepasste Note: Pitch {msg.note}, Zeit {current_time}, "
                               f"Velocity {msg.velocity}")
        
        elif (msg.type == 'note_off' or 
              (msg.type == 'note_on' and hasattr(msg, 'velocity') and msg.velocity == 0)):
            # Suche nach dem passenden Note-On
            if (msg.note, msg.channel) in active_notes:
                # Hole die angepasste Ende-Zeit
                adjusted_end_time, note, channel = active_notes.pop((msg.note, msg.channel))
                
                # Erstelle das Note-Off Event mit angepasster Zeit
                adj_note_off = msg.copy(time=0)
                abs_events.append((adjusted_end_time, adj_note_off))
            else:
                # Kein passendes Note-On gefunden
                abs_events.append((current_time, msg.copy(time=0)))
        else:
            # Kein Noten-Event, behalte unverändert
            abs_events.append((current_time, msg.copy(time=0)))
    
    event_collection_time = time.time() - event_collection_start
    logger.debug(f"Events gesammelt: {len(abs_events)} Events in {event_collection_time:.3f} Sekunden")
    
    # Sortiere nach absoluter Zeit
    sorting_start = time.time()
    abs_events.sort(key=lambda x: x[0])
    sorting_time = time.time() - sorting_start
    logger.debug(f"Events sortiert in {sorting_time:.3f} Sekunden")
    
    # Konvertiere zurück zu Delta-Zeiten
    conversion_start = time.time()
    new_track = mido.MidiTrack()
    last_time = 0
    
    for abs_time, msg in abs_events:
        delta_time = max(0, abs_time - last_time)
        new_msg = msg.copy(time=delta_time)
        new_track.append(new_msg)
        last_time = abs_time
    
    conversion_time = time.time() - conversion_start
    logger.debug(f"Delta-Zeiten berechnet in {conversion_time:.3f} Sekunden")
    
    # Ersetze den Track
    track.clear()
    for msg in new_track:
        track.append(msg)
    
    # Gesamtzeit und Statistiken
    track_time = time.time() - track_start_time
    
    # Berechne Durchschnittswerte für Änderungen
    avg_timing = sum(timing_changes) / max(1, len(timing_changes))
    avg_velocity = sum(velocity_changes) / max(1, len(velocity_changes))
    avg_duration = sum(duration_changes) / max(1, len(duration_changes))
    
    logger.info(f"Track {track_idx} verarbeitet: {original_notes} Noten, {adjusted_notes_count} angepasst "
               f"({(adjusted_notes_count/max(1, original_notes))*100:.1f}%) in {track_time:.3f} Sekunden")
    
    if adjusted_notes_count > 0:
        logger.info(f"  Durchschnittliche Änderungen: Timing {avg_timing:.1f} Ticks, "
                   f"Velocity {avg_velocity:.1f}, Dauer {avg_duration:.1f} Ticks")

def get_key_signature(midi_file: str) -> Optional[int]:
    """
    Versucht, die Tonart einer MIDI-Datei zu bestimmen.
    
    Args:
        midi_file: Pfad zur MIDI-Datei
        
    Returns:
        Key signature (0 = C, 1 = G/Em, usw.) oder None falls nicht gefunden
    """
    try:
        mid = mido.MidiFile(midi_file)
        
        # Suche nach key_signature Meta-Events
        for track in mid.tracks:
            for msg in track:
                if msg.is_meta and msg.type == 'key_signature':
                    # Parse the key signature
                    key = msg.key
                    
                    # Konvertiere zu einfacher Zahl für C, G, D, etc.
                    if key[-1] == 'm':  # Moll-Tonart
                        base = key[:-1]
                        # Berechne die relative Dur-Tonart
                        # Relative Dur ist 3 Halbtöne höher als Moll
                        # Vereinfachte Berechnung - nicht vollständig
                        pass  # Komplexere Logik wäre hier nötig
                    else:  # Dur-Tonart
                        # Versuche nach der Anzahl der # oder b zu bestimmen
                        # Vereinfachte Berechnung - nicht vollständig
                        pass  # Komplexere Logik wäre hier nötig
                    
                    return 0  # Einfache Implementierung: Annahme C-Dur
        
        # Keine explizite Tonart gefunden
        return None
    
    except Exception as e:
        logger.error(f"Fehler beim Bestimmen der Tonart: {e}")
        return None