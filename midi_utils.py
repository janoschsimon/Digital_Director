"""
MIDI Utilities Modul für den Barockmusik MIDI-Prozessor
------------------------------------------------------
Dieses Modul enthält Hilfsfunktionen für die Arbeit mit MIDI-Dateien.
"""

import mido
import logging
import traceback
import random
import math
import numpy as np
from typing import List, Tuple, Dict, Optional, Union

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def remove_all_keyswitches(midi_file):
    """
    Entfernt alle Keyswitch-Noten (sehr tiefe oder sehr hohe MIDI-Noten) aus einer MIDI-Datei.
    
    Args:
        midi_file: Pfad zur MIDI-Datei
        
    Returns:
        mido.MidiFile Objekt der bereinigten MIDI-Datei
    """
    mid = mido.MidiFile(midi_file)
    
    # Definiere Bereiche für Keyswitches
    keyswitch_ranges = [(0, 23), (108, 127)]  # C-2 bis B-1, C8 und höher
    
    for track in mid.tracks:
        # Finde alle Keyswitch-Noten
        keyswitch_notes = set()
        for msg in track:
            if msg.type in ('note_on', 'note_off') and any(low <= msg.note <= high for low, high in keyswitch_ranges):
                keyswitch_notes.add(msg.note)
        
        # Entferne alle Events für diese Noten
        filtered_messages = []
        for msg in track:
            if not (msg.type in ('note_on', 'note_off') and msg.note in keyswitch_notes):
                filtered_messages.append(msg)
        
        track.clear()
        track.extend(filtered_messages)
    
    mid.save(midi_file)
    logger.info(f"Alle Keyswitch-Noten wurden aus {midi_file} entfernt.")
    return mid

def fix_musescore_midi_tracks(midi_file: str) -> None:
    """
    Korrigiert die von MuseScore erzeugte MIDI-Datei, indem Instrumenten-Events aus Track 0
    in einen neuen Track verschoben werden, sodass Track 0 ausschließlich Meta-Events enthält.
    
    Überträgt auch den Track-Namen korrekt, sodass Track 0 als "Tempo" bezeichnet wird und
    Track 1 den Namen des Instruments (z.B. "Violino I") erhält.
    
    Args:
        midi_file: Pfad zur MIDI-Datei
    """
    logger.info(f"Korrigiere MIDI-Track-Struktur für: {midi_file}")
    
    try:
        # Lade die MIDI-Datei
        mid = mido.MidiFile(midi_file)
        
        # Prüfe, ob Track 0 Instrumenten-Events enthält
        note_events = sum(1 for msg in mid.tracks[0] 
                         if not msg.is_meta and msg.type in ('note_on', 'note_off'))
        
        if note_events > 0:
            logger.info(f"Track 0 enthält {note_events} Noten-Events - Struktur wird korrigiert")
            
            # Extrahiere den aktuellen Tracknamen von Track 0
            track_name = "Tempo"  # Standardname für Track 0, falls kein Name gefunden wird
            instrument_name = "Instrument"  # Standardname für den neuen Track 1
            
            for msg in mid.tracks[0]:
                if msg.is_meta and msg.type == 'track_name':
                    instrument_name = msg.name  # Speichere den Namen für Track 1
                    break
            
            # Erstelle einen neuen Tempo-Track (nur Meta-Events)
            new_tempo_track = mido.MidiTrack()
            # Erstelle einen neuen Instrumenten-Track für die Noten aus Track 0
            new_instrument_track = mido.MidiTrack()
            
            # Sammle die Events mit absoluten Zeiten
            abs_tempo_events = []
            abs_instrument_events = []
            current_time = 0
            
            # Füge angepassten Tracknamen für Track 0 (Tempo) hinzu
            abs_tempo_events.append((0, mido.MetaMessage('track_name', name=track_name, time=0)))
            
            # Füge ursprünglichen Tracknamen für Track 1 (Instrument) hinzu
            abs_instrument_events.append((0, mido.MetaMessage('track_name', name=instrument_name, time=0)))
            
            # Verarbeite alle anderen Events aus Track 0
            for msg in mid.tracks[0]:
                current_time += msg.time
                # Überspringe track_name Events, da wir sie bereits oben gesetzt haben
                if msg.is_meta and msg.type == 'track_name':
                    continue
                    
                # Meta-Events gehen in den Tempo-Track, Instrumenten-Events in den neuen Track
                if msg.is_meta:
                    abs_tempo_events.append((current_time, msg.copy(time=0)))
                else:
                    abs_instrument_events.append((current_time, msg.copy(time=0)))
            
            # Sortiere nach Zeit
            abs_tempo_events.sort(key=lambda x: x[0])
            abs_instrument_events.sort(key=lambda x: x[0])
            
            # Konvertiere zurück zu Delta-Zeiten für den Tempo-Track
            prev_time = 0
            for abs_time, msg in abs_tempo_events:
                delta = abs_time - prev_time
                msg.time = delta
                new_tempo_track.append(msg)
                prev_time = abs_time
            
            # Konvertiere zurück zu Delta-Zeiten für den Instrument-Track
            prev_time = 0
            for abs_time, msg in abs_instrument_events:
                delta = abs_time - prev_time
                msg.time = delta
                new_instrument_track.append(msg)
                prev_time = abs_time
            
            # Stelle sicher, dass End-of-Track Events vorhanden sind
            if not any(msg.type == 'end_of_track' for msg in new_tempo_track if msg.is_meta):
                new_tempo_track.append(mido.MetaMessage('end_of_track', time=0))
            
            if not any(msg.type == 'end_of_track' for msg in new_instrument_track if msg.is_meta):
                new_instrument_track.append(mido.MetaMessage('end_of_track', time=0))
            
            # Ersetze Track 0 mit dem reinen Tempo-Track
            mid.tracks[0] = new_tempo_track
            
            # Füge den neuen Instrumenten-Track als Track 1 ein
            if len(mid.tracks) == 1:
                mid.tracks.append(new_instrument_track)
            else:
                mid.tracks.insert(1, new_instrument_track)
            
            # Speichere die korrigierte MIDI-Datei
            mid.save(midi_file)
            logger.info("✅ MIDI-Struktur korrigiert: Track 0 enthält jetzt nur Meta-Events")
            logger.info(f"✅ Noten von '{instrument_name}' wurden in Track 1 verschoben")
            logger.info(f"✅ Tracknamen wurden korrigiert: Track 0: '{track_name}', Track 1: '{instrument_name}'")
        else:
            logger.info("Track 0 enthält ausschließlich Meta-Events - keine Korrektur nötig")
        
    except Exception as e:
        logger.error(f"Fehler beim Korrigieren der MIDI-Struktur: {e}")
        logger.error(traceback.format_exc())

def fix_track_lengths(midi_file):
    """
    Korrigiert die Längen aller Tracks in einer MIDI-Datei.
    Verbesserte Version mit präziserer Längenberechnung.
    
    Args:
        midi_file: Pfad zur MIDI-Datei
        
    Returns:
        Pfad zur korrigierten MIDI-Datei
    """
    # Import mido und logging bereits oben gemacht, nicht erneut importieren
    
    logger.info(f"Korrigiere Track-Längen für: {midi_file}")
    
    mid = mido.MidiFile(midi_file)
    
    # Finde die maximale absolute Zeit über alle Tracks
    max_time = 0
    track_lengths = []
    
    for i, track in enumerate(mid.tracks):
        # Berechne die tatsächliche Länge des Tracks in Ticks
        current_time = 0
        for msg in track:
            current_time += msg.time
        
        track_lengths.append(current_time)
        logger.info(f"Track {i} Länge: {current_time} Ticks")
        max_time = max(max_time, current_time)
    
    logger.info(f"Maximale Track-Länge: {max_time} Ticks")
    
    # Stelle sicher, dass alle Tracks die gleiche Länge haben
    for i, (track, length) in enumerate(zip(mid.tracks, track_lengths)):
        if i == 0 and mid.type == 1:  # Überspringe Meta-Track bei Typ 1 MIDI
            continue
            
        if length < max_time:
            logger.info(f"Korrigiere Länge von Track {i}: {length} -> {max_time}")
            
            # Entferne das alte End-of-Track-Event, falls vorhanden
            new_track = []
            for msg in track:
                if not (msg.is_meta and msg.type == 'end_of_track'):
                    new_track.append(msg)
            
            # Berechne die aktuelle Länge ohne End-of-Track
            current_time = 0
            for msg in new_track:
                current_time += msg.time
            
            # Füge ein neues End-of-Track-Event mit korrektem Timing hinzu
            time_diff = max_time - current_time
            logger.info(f"Füge End-of-Track mit Delta-Zeit {time_diff} Ticks hinzu")
            eot = mido.MetaMessage('end_of_track', time=time_diff)
            new_track.append(eot)
            
            # Ersetze den Track
            mid.tracks[i] = mido.MidiTrack(new_track)
    
    # Speichere die aktualisierte MIDI-Datei
    mid.save(midi_file)
    logger.info(f"MIDI-Datei mit synchronisierten Tracklängen gespeichert: {midi_file}")
    
    return midi_file

def fix_track_lengths_mid(mid):
    """
    Korrigiert die Länge aller Tracks in einem mido.MidiFile-Objekt,
    um sicherzustellen, dass sie synchron enden.
    Verbesserte Version mit präziserer Längenberechnung.
    
    Args:
        mid: mido.MidiFile-Objekt
        
    Returns:
        Korrigiertes mido.MidiFile-Objekt
    """
    # Finde die maximale absolute Zeit über alle Tracks
    max_time = 0
    track_lengths = []
    
    for i, track in enumerate(mid.tracks):
        # Berechne die tatsächliche Länge des Tracks in Ticks
        current_time = 0
        for msg in track:
            current_time += msg.time
        
        track_lengths.append(current_time)
        logger.info(f"Track {i} Länge: {current_time} Ticks")
        max_time = max(max_time, current_time)
    
    logger.info(f"Maximale Track-Länge: {max_time} Ticks")
    
    # Stelle sicher, dass alle Tracks die gleiche Länge haben
    for i, (track, length) in enumerate(zip(mid.tracks, track_lengths)):
        if i == 0 and mid.type == 1:  # Überspringe Meta-Track bei Typ 1 MIDI
            continue
            
        if length < max_time:
            logger.info(f"Korrigiere Länge von Track {i}: {length} -> {max_time}")
            
            # Entferne das alte End-of-Track-Event, falls vorhanden
            new_track = []
            for msg in track:
                if not (msg.is_meta and msg.type == 'end_of_track'):
                    new_track.append(msg)
            
            # Berechne die aktuelle Länge ohne End-of-Track
            current_time = 0
            for msg in new_track:
                current_time += msg.time
            
            # Füge ein neues End-of-Track-Event mit korrektem Timing hinzu
            time_diff = max_time - current_time
            logger.info(f"Füge End-of-Track mit Delta-Zeit {time_diff} Ticks hinzu")
            eot = mido.MetaMessage('end_of_track', time=time_diff)
            new_track.append(eot)
            
            # Ersetze den Track
            mid.tracks[i] = mido.MidiTrack(new_track)
    
    return mid

def deduplicate_tempos(tempo_list, time_tolerance=0.5):
    """
    Entfernt doppelte Tempoeinträge und löst Konflikte, wenn mehrere Tempos an der gleichen Position sind.
    
    Args:
        tempo_list: Liste von (offset, bpm) Tupeln
        time_tolerance: Toleranz in Beats für die Zeit
        
    Returns:
        Bereinigte Liste von (offset, bpm) Tupeln
    """
    if not tempo_list:
        return []
    
    # Sortiere nach Offset und gruppiere ähnliche Positionen
    tempo_list.sort(key=lambda x: x[0])
    
    # Gruppiere Tempos an ähnlichen Positionen
    grouped_tempos = []
    current_group = [tempo_list[0]]
    
    for i in range(1, len(tempo_list)):
        if abs(tempo_list[i][0] - current_group[0][0]) <= time_tolerance:
            # Ähnliche Position - zur aktuellen Gruppe hinzufügen
            current_group.append(tempo_list[i])
        else:
            # Neue Position - verarbeite die aktuelle Gruppe und starte eine neue
            grouped_tempos.append(current_group)
            current_group = [tempo_list[i]]
    
    # Letzte Gruppe hinzufügen
    if current_group:
        grouped_tempos.append(current_group)
    
    # Wähle für jede Gruppe das beste Tempo aus
    result = []
    
    for group in grouped_tempos:
        if len(group) == 1:
            # Einfacher Fall: Nur ein Tempo in dieser Gruppe
            result.append(group[0])
        else:
            # Mehrere Tempos an ähnlicher Position - wähle das beste aus
            
            # Priorisiere exakte Tempos gegenüber gerundeten Werten
            # Bevorzuge genauere Tempos (z.B. 78.0 statt 120)
            # Spezifische Tempo-Regeln für Barockmusik:
            # - Allegro: 78 (Nicht 120)
            # - Grave/Adagio: 35-52
            selected_tempo = None
            
            # Suche nach XML-Tempos (haben typischerweise Dezimalstellen)
            xml_tempos = [t for t in group if isinstance(t[1], float)]
            if xml_tempos:
                # Bevorzuge XML-Tempos, wenn verfügbar
                selected_tempo = xml_tempos[0]
            else:
                # Bevorzuge barocke Tempos gegenüber modernen Standard-Tempos
                baroque_tempos = [t for t in group if t[1] != 120]
                if baroque_tempos:
                    selected_tempo = baroque_tempos[0]
                else:
                    # Fallback: Nimm das erste Tempo in der Gruppe
                    selected_tempo = group[0]
            
            # Verwende den mittleren Offset für eine genauere Position
            avg_offset = sum(t[0] for t in group) / len(group)
            result.append((avg_offset, selected_tempo[1]))
    
    # Sortiere das Ergebnis nach Offset
    result.sort(key=lambda x: x[0])
    
    return result


def is_baroque_inegalite_candidate(note: int, time: int, ticks_per_beat: int) -> bool:
    """
    Prüft, ob eine Note ein Kandidat für den Inégalité-Effekt (typisch für Barockmusik) ist.
    
    In der barocken Aufführungspraxis wurden bestimmte Notenpaare (insbesondere Achtelpaare)
    oft leicht punktiert gespielt, obwohl sie gleichmäßig notiert waren.
    
    Args:
        note: MIDI-Notennummer
        time: Absolute Zeit in Ticks
        ticks_per_beat: Ticks pro Viertelnote
        
    Returns:
        True, wenn die Note ein Kandidat für Inégalité ist
    """
    # Prüfe, ob die Note auf einem Achtel-Schlag liegt
    is_on_eighth = (time % (ticks_per_beat // 2)) < (ticks_per_beat // 16)
    
    # Prüfe, ob die Note im mittleren Bereich liegt (meist Melodienoten)
    is_mid_range = 55 <= note <= 88
    
    # In Barockmusik wird Inégalité oft auf bestimmte Tonleiternoten angewendet
    # Eine präzisere Implementierung würde Tonarten erkennen und diatonische Noten prüfen
    
    return is_on_eighth and is_mid_range