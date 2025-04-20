"""
Tempo-Verarbeitungs-Modul für den Barockmusik MIDI-Prozessor
---------------------------------------------------------
Dieses Modul enthält Funktionen zum Extrahieren und Anwenden von Tempomarkierungen
aus music21-Scores auf MIDI-Dateien.
"""

import mido
import math
import logging
import traceback

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def extract_and_apply_tempos(expanded_score, midi_file_path):
    """
    Extrahiert Tempomarkierungen aus dem expandierten Score und fügt sie explizit
    zur MIDI-Datei hinzu.
    
    Args:
        expanded_score: music21 Score-Objekt
        midi_file_path: Pfad zur MIDI-Datei
    
    Returns:
        Pfad zur aktualisierten MIDI-Datei
    """
    logger.info("Extrahiere und übertrage Tempomarkierungen...")
    
    # 1. Tempomarkierungen aus dem Score extrahieren
    tempo_changes = []
    
    # Methode A: metronomeMarkBoundaries
    try:
        boundaries = expanded_score.metronomeMarkBoundaries()
        for start_time, element, end_time in boundaries:
            if element is not None and hasattr(element, 'number'):
                bpm = element.number
                logger.info(f"Tempo aus Boundaries: {bpm} BPM bei Offset {start_time}")
                tempo_changes.append((start_time, bpm))
    except Exception as e:
        logger.warning(f"Fehler bei metronomeMarkBoundaries: {e}")
    
    # Methode B: Direkte Suche nach MetronomeMarks
    try:
        for mm in expanded_score.flat.getElementsByClass('MetronomeMark'):
            if hasattr(mm, 'number'):
                bpm = mm.number
                offset = mm.offset
                try:
                    offset = mm.getOffsetBySite(expanded_score.flat)
                except:
                    pass
                logger.info(f"Tempo aus MetronomeMark: {bpm} BPM bei Offset {offset}")
                tempo_changes.append((offset, bpm))
    except Exception as e:
        logger.warning(f"Fehler bei der MetronomeMark-Suche: {e}")
    
    # Entferne Duplikate und sortiere nach Zeit
    if tempo_changes:
        from midi_utils import deduplicate_tempos
        tempo_changes = deduplicate_tempos(tempo_changes)
        tempo_changes.sort(key=lambda x: x[0])
        
        # Stelle sicher, dass ein Tempo am Anfang existiert
        if not tempo_changes or tempo_changes[0][0] > 0:
            tempo_changes.insert(0, (0, 120))  # Standardtempo, falls keines definiert ist
    else:
        logger.warning("Keine Tempomarkierungen gefunden, verwende Standardtempo")
        tempo_changes = [(0, 120)]  # Standardtempo
    
    logger.info("Gefundene Tempomarkierungen:")
    for offset, bpm in tempo_changes:
        logger.info(f"  - {bpm} BPM bei Offset {offset}")
    
    # 2. Tempomarkierungen zur MIDI-Datei hinzufügen
    try:
        # Lade MIDI-Datei
        mid = mido.MidiFile(midi_file_path)
        ticks_per_beat = mid.ticks_per_beat
        logger.info(f"MIDI-Datei geladen: Typ {mid.type}, ticks_per_beat={ticks_per_beat}")
        
        # BPM zu MIDI-Tempo konvertieren (Mikrosekunden pro Viertelnote)
        def bpm_to_tempo(bpm):
            return math.floor(60000000 / bpm)
        
        # Entferne bestehende Tempo-Events aus dem ersten Track
        if mid.type == 1 and len(mid.tracks) > 0:
            track0 = mid.tracks[0]
            new_track0 = []
            for msg in track0:
                if not (msg.is_meta and msg.type == 'set_tempo'):
                    new_track0.append(msg)
            mid.tracks[0] = mido.MidiTrack(new_track0)
            logger.info("Bestehende Tempo-Events entfernt")
        
        # Füge neue Tempo-Events hinzu
        # Bei Typ 0 MIDI müssen wir es zuerst zu Typ 1 konvertieren
        if mid.type == 0:
            logger.info("Konvertiere MIDI von Typ 0 zu Typ 1...")
            old_track = mid.tracks[0]
            
            # Erstelle zwei neue Tracks: einen für Meta-Events und einen für Noten
            meta_track = mido.MidiTrack()
            note_track = mido.MidiTrack()
            
            # Sortiere Events in die entsprechenden Tracks
            for msg in old_track:
                if msg.is_meta and msg.type != 'end_of_track':
                    if msg.type != 'set_tempo':  # Ignoriere alte Tempo-Events
                        meta_track.append(msg.copy())
                else:
                    if not (msg.is_meta and msg.type == 'end_of_track'):
                        note_track.append(msg.copy())
            
            # Erstelle eine neue MIDI-Datei
            new_mid = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat)
            new_mid.tracks = [meta_track, note_track]
            mid = new_mid
            logger.info("MIDI zu Typ 1 konvertiert")
        
        # Füge Tempo-Events zum ersten Track hinzu
        tempo_track = mid.tracks[0]
        
        # Konvertiere Tempo-Änderungen zu absoluten und dann relativen Tick-Zeiten
        # Sammle bestehende Events (ohne End-of-Track)
        track_events = []
        for msg in tempo_track:
            if not (msg.is_meta and msg.type == 'end_of_track'):
                track_events.append(msg)
        
        # Füge Tempo-Events hinzu
        for offset, bpm in tempo_changes:
            tick_offset = int(round(offset * ticks_per_beat))
            tempo_value = bpm_to_tempo(bpm)
            logger.info(f"Füge Tempo hinzu: {bpm} BPM ({tempo_value} µs/beat) bei Tick {tick_offset}")
            tempo_msg = mido.MetaMessage('set_tempo', tempo=tempo_value, time=0)
            track_events.append((tick_offset, tempo_msg))
        
        # Sortiere Events nach Zeit und konvertiere zu Delta-Zeiten
        track_events.sort(key=lambda x: x[0] if isinstance(x, tuple) else 0)
        
        new_track = mido.MidiTrack()
        prev_time = 0
        
        for event in track_events:
            if isinstance(event, tuple):
                abs_time, msg = event
                delta = abs_time - prev_time
                new_track.append(msg.copy(time=delta))
                prev_time = abs_time
            else:
                # Bestehende Nachrichten ohne absoluten Zeitstempel
                new_track.append(event)
                prev_time += event.time
        
        # Füge End-of-Track hinzu
        new_track.append(mido.MetaMessage('end_of_track', time=0))
        
        # Ersetze den ersten Track
        mid.tracks[0] = new_track
        
        # Speichere die aktualisierte MIDI-Datei
        mid.save(midi_file_path)
        logger.info(f"✅ MIDI-Datei mit Tempomarkierungen aktualisiert: {midi_file_path}")
        
        return midi_file_path
    
    except Exception as e:
        logger.error(f"Fehler beim Hinzufügen der Tempomarkierungen: {e}")
        logger.error(f"Stack Trace: {traceback.format_exc()}")
        return midi_file_path