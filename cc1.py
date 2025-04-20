"""
CC1 Hauptmodul für den Barockmusik MIDI-Prozessor
-------------------------------------------------
Hauptmodul für die Verarbeitung von MusicXML-Dateien und MIDI-Dateien.
Orchestriert die Verwendung der anderen Module für Dynamik, XML-Parsing und MIDI-Verarbeitung.
"""

import mido
import music21 as m21
import logging
import os
import sys
import json
import traceback
from typing import Dict, List, Tuple, Any, Optional

# Import internal modules
from xml_parser import parse_tempos_from_musicxml
from dynamics import extract_dynamic_points, non_linear_interpolate_dynamics
from midi_utils import (
    fix_track_lengths_mid, 
    fix_musescore_midi_tracks, 
    
)

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Globale Variable zur Kontrolle, ob MuseScore-Integration verfügbar ist
MUSESCORE_AVAILABLE = False

# Standard-Konfiguration für CC1-Kurven
DEFAULT_CC1_CONFIG = {
    "dynamic_range": {
        "min": 30,
        "max": 115
    },
    "role_factors": {
        "melody": 1.15,
        "bass": 1.05,
        "inner_voice": 1.0,
        "unknown": 1.0
    },
    "curve_points": {
        "local_peak": {
            "rise_point": 0.15,
            "peak_point": 0.3,
            "fall_point": 0.45,
            "rise_factor": 1.03,
            "peak_factor": 1.08,
            "fall_factor": 1.04
        },
        "phrase_start": {
            "time_points": [0.2, 0.3, 0.4],
            "value_factors": [1.02, 1.04, 1.05]
        },
        "phrase_end": {
            "time_points": [0.3, 0.5, 0.7],
            "value_factors": [0.98, 0.93, 0.88]
        },
        "note_decay": {
            "short_note": {
                "end_factor": 0.90
            },
            "long_note": {
                "time_points": [0.85, 0.93, 1.0],
                "value_factors": [0.96, 0.93, 0.90]
            },
            "min_duration": 15
        },
        "bass_patterns": [
            {
                "time_points": [0.25, 0.5, 0.75],
                "value_factors": [0.97, 0.95, 0.93]
            }
        ],
        "long_note_patterns": [
            {
                "name": "crescendo-diminuendo",
                "time_points": [0.2, 0.4, 0.6, 0.8],
                "value_factors": [0.98, 1.03, 1.03, 0.96]
            },
            {
                "name": "vibrato",
                "time_points": [0.2, 0.35, 0.5, 0.65, 0.8],
                "value_factors": [1.02, 0.99, 1.03, 0.98, 1.01]
            },
            {
                "name": "diminuendo",
                "time_points": [0.25, 0.5, 0.75],
                "value_factors": [0.99, 0.97, 0.95]
            }
        ],
        "long_note_min_duration": 20
    },
    "filtering": {
        "thresholds": {
            "fast_change": {
                "rate": 0.4,
                "time_gap": 4,
                "value_diff": 2
            },
            "moderate_change": {
                "rate": 0.2,
                "time_gap": 6,
                "value_diff": 3
            },
            "slow_change": {
                "time_gap": 10,
                "value_diff": 4
            }
        },
        "important_points": {
            "window_size": 5
        }
    },
    "velocity_mapping": {
        "very_low": {
            "threshold": 20,
            "min_value": 30
        },
        "low": {
            "threshold": 40,
            "slope": 1.5
        },
        "mid": {
            "threshold": 80,
            "range": 40
        },
        "high": {
            "range": 35
        }
    }
}

def load_cc1_config(config_file="cc1_config.json"):
    """
    Lädt die CC1-Konfiguration aus einer JSON-Datei.
    
    Args:
        config_file: Pfad zur Konfigurationsdatei
        
    Returns:
        Dictionary mit der Konfiguration
    """
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            logger.info(f"CC1-Konfiguration geladen aus: {config_file}")
            return config
        except Exception as e:
            logger.error(f"Fehler beim Laden der CC1-Konfiguration: {e}")
            logger.info(f"Verwende Standard-Konfiguration")
    else:
        logger.info(f"Konfigurationsdatei {config_file} nicht gefunden, verwende Standard-Konfiguration")
            
    # Standardkonfiguration zurückgeben
    return DEFAULT_CC1_CONFIG

# Versuche, das musescore_helper Modul zu importieren
try:
    logger.info("Versuche musescore_helper zu importieren...")
    from musescore_helper import convert_xml_to_midi_with_musescore, add_cc1_to_musescore_midi
    MUSESCORE_AVAILABLE = True
    logger.info("musescore_helper erfolgreich importiert!")
except ImportError as e:
    logger.error(f"!!! Konnte musescore_helper nicht importieren: {e}")
    logger.error("Fallback auf alte Methode ohne MuseScore")
    MUSESCORE_AVAILABLE = False
except Exception as e:
    logger.error(f"!!! Unerwarteter Fehler beim Import von musescore_helper: {e}")
    logger.error(f"Stack Trace: {traceback.format_exc()}")
    MUSESCORE_AVAILABLE = False

def insert_cc1_curve_with_interpretation(midi_file, interpretation_results):
    """
    Schreibt CC1-Kurven für jede Stimme in die MIDI-Datei unter Berücksichtigung der
    Timing-Anpassungen aus dem Digital Dirigenten.
    """
    logger.info(f"====== Synchronisierte CC1-Verarbeitung gestartet für {midi_file} ======")
    
    if not os.path.exists(midi_file):
        logger.error(f"MIDI-Datei existiert nicht: {midi_file}")
        return None
    
    try:
        # Lade die MIDI-Datei
        mid = mido.MidiFile(midi_file)
        logger.info(f"MIDI-Datei geladen: Typ {mid.type}, {len(mid.tracks)} Tracks, {mid.ticks_per_beat} Ticks/Beat")
        
        # Extrahiere die Voices aus den Interpretationsergebnissen
        voices = interpretation_results.get('voices', [])
        if not voices:
            logger.warning("Keine Stimmeninformationen in den Interpretationsergebnissen gefunden")
            return insert_cc1_curve(midi_file, None, mid.ticks_per_beat, None)
        
        # SCHRITT 1: Analysiere die MIDI-Tracks im Detail
        track_data = []
        for i, track in enumerate(mid.tracks):
            # Sammle alle wichtigen Informationen über den Track
            track_name = "Unbenannt"
            channels = set()
            note_events = []  # Sammle (note, time) Paare
            note_count = 0
            current_time = 0
            
            for msg in track:
                current_time += msg.time
                
                if msg.type == 'track_name':
                    track_name = msg.name
                
                if hasattr(msg, 'channel'):
                    channels.add(msg.channel)
                
                if msg.type == 'note_on' and hasattr(msg, 'velocity') and msg.velocity > 0:
                    note_events.append((msg.note, current_time))
                    note_count += 1
            
            # Ignoriere leere Tracks oder den ersten Track bei MIDI Typ 1 (meist Tempo-Track)
            if note_count == 0 and i == 0 and mid.type == 1:
                logger.info(f"Track {i}: '{track_name}' hat keine Noten, vermutlich Tempo-Track")
                track_data.append({
                    'index': i,
                    'name': track_name,
                    'channels': list(channels),
                    'notes': note_count,
                    'has_notes': False,
                    'note_events': []
                })
                continue
            
            track_data.append({
                'index': i,
                'name': track_name,
                'channels': list(channels),
                'notes': note_count,
                'has_notes': note_count > 0,
                'note_events': note_events[:100]  # Nur die ersten 100 Noten für Vergleiche
            })
            
            logger.info(f"Track {i}: '{track_name}', {note_count} Noten, Kanäle: {list(channels)}")
        
        # SCHRITT 2: Sammle Voice-Daten
        voice_data = []
        for i, voice in enumerate(voices):
            voice_name = getattr(voice, 'name', f"Voice {i}")
            voice_track = getattr(voice, 'track_index', -1)
            voice_channel = getattr(voice, 'channel', -1)
            
            # Sammle Noten-Events aus der Stimme
            note_events = []
            if hasattr(voice, 'notes'):
                for note in voice.notes[:100]:  # Nur die ersten 100 Noten für Vergleiche
                    if hasattr(note, 'pitch') and hasattr(note, 'original_start_time'):
                        note_events.append((note.pitch, note.original_start_time))
            
            voice_data.append({
                'index': i,
                'name': voice_name,
                'track': voice_track,
                'channel': voice_channel,
                'has_notes': len(note_events) > 0,
                'note_events': note_events
            })
            
            logger.info(f"Voice {i}: '{voice_name}', Track-Attr: {voice_track}, Kanal: {voice_channel}, {len(note_events)} Noten")
        
        # SCHRITT 3: Lade den Score und extrahiere Dynamikpunkte
        score = m21.converter.parse(midi_file)
        voice_dynamics = extract_dynamic_points(score)
        
        if not voice_dynamics:
            logger.warning("Keine Dynamikpunkte gefunden")
            return midi_file
        
        logger.info(f"Dynamikpunkte für {len(voice_dynamics)} Stimmen extrahiert")
        
        # Berechne Kurven
        total_duration = score.highestTime
        dynamic_curves = non_linear_interpolate_dynamics(voice_dynamics, total_duration, resolution=0.1)
        
        # SCHRITT 4: Erstelle Timing-Mapping für jede Taktposition
        timing_adjustments = []
        for voice in voices:
            if hasattr(voice, 'notes'):
                for note in voice.notes:
                    if hasattr(note, 'original_start_time') and hasattr(note, 'adjusted_start_time'):
                        # Speichere die Timing-Anpassung
                        timing_adjustments.append({
                            'original': note.original_start_time,
                            'adjustment': int(note.adjusted_start_time - note.original_start_time)
                        })
        
        # Gruppiere nach Taktposition
        ticks_per_measure = mid.ticks_per_beat * 4  # Annahme: 4/4-Takt
        position_adjustments = {}
        
        for item in timing_adjustments:
            # Position innerhalb eines Taktes (0 bis ticks_per_measure-1)
            position = int(item['original'] % ticks_per_measure)
            
            if position not in position_adjustments:
                position_adjustments[position] = []
                
            position_adjustments[position].append(item['adjustment'])
        
        # Berechne Durchschnitt für jede Position
        timing_map = {}
        for position, adjustments in position_adjustments.items():
            if adjustments:
                timing_map[position] = int(sum(adjustments) / len(adjustments))
        
        logger.info(f"Timing-Map mit {len(timing_map)} Positions-Einträgen erstellt")
        
        # SCHRITT 5: Entferne bestehende CC1-Events
        for i, track in enumerate(mid.tracks):
            non_cc1_events = []
            for msg in track:
                if not (msg.type == 'control_change' and msg.control == 1):
                    non_cc1_events.append(msg)
            
            mid.tracks[i] = mido.MidiTrack(non_cc1_events)
            
        # Funktion zur Anpassung des Timings
        def adjust_timing(original_time):
            position = int(original_time % ticks_per_measure)
            
            # Finde die nächstgelegene Position mit bekannter Anpassung
            nearest_position = min(timing_map.keys(), key=lambda x: abs(x - position)) if timing_map else position
            adjustment = timing_map.get(nearest_position, 0)
            
            return int(max(0, original_time + adjustment))
        
        # SCHRITT 6: KRITISCH - Ordne die CC1-Kurven den richtigen Tracks zu
        # Erstelle ein Mapping von Part/Voice-Index zu Track-Index
        part_to_track = {}
        
        # Methode 1: Direkte Zuordnung über track_index Attribut
        for i, voice in enumerate(voice_data):
            if voice['track'] >= 0 and voice['track'] < len(mid.tracks):
                part_to_track[i] = voice['track']
                logger.info(f"Part {i} direkt zugeordnet zu Track {voice['track']} (über Attribut)")
        
        # Methode 2: Name-basierte Zuordnung
        for voice_idx, voice in enumerate(voice_data):
            if voice_idx in part_to_track:
                continue  # Bereits zugeordnet
                
            for track in track_data:
                if track['name'] and voice['name'] and track['name'].lower() == voice['name'].lower():
                    part_to_track[voice_idx] = track['index']
                    logger.info(f"Part {voice_idx} zugeordnet zu Track {track['index']} (über Namen)")
                    break
        
        # Methode 3: Kanal-basierte Zuordnung
        for voice_idx, voice in enumerate(voice_data):
            if voice_idx in part_to_track:
                continue  # Bereits zugeordnet
                
            if voice['channel'] >= 0:
                for track in track_data:
                    if voice['channel'] in track['channels']:
                        part_to_track[voice_idx] = track['index']
                        logger.info(f"Part {voice_idx} zugeordnet zu Track {track['index']} (über Kanal {voice['channel']})")
                        break
        
        # Methode 4: Heuristisches Matching basierend auf Part-Index
        for voice_idx in range(len(voice_data)):
            if voice_idx in part_to_track:
                continue  # Bereits zugeordnet
            
            # Kandidaten sind Tracks mit Index > 0, die Noten enthalten
            candidates = [t for t in track_data if t['index'] > 0 and t['has_notes']]
            
            # Sortiere Kandidaten nach Anzahl der Noten
            candidates.sort(key=lambda x: x['notes'], reverse=True)
            
            # Wähle nur Tracks, die noch keinem Part zugeordnet wurden
            used_tracks = set(part_to_track.values())
            available_candidates = [t for t in candidates if t['index'] not in used_tracks]
            
            if available_candidates:
                # Wähle den besten verfügbaren Kandidaten
                best_track_idx = available_candidates[0]['index']
                part_to_track[voice_idx] = best_track_idx
                logger.info(f"Part {voice_idx} zugeordnet zu Track {best_track_idx} (heuristisch)")
        
        # Methode 5: Fallback auf Basis der Position im Array für verbleibende Parts
        remaining_voices = [i for i in range(len(voice_data)) if i not in part_to_track]
        remaining_tracks = [t['index'] for t in track_data if t['has_notes'] and t['index'] not in part_to_track.values()]
        
        # Sortiere übrig gebliebene Tracks nach Index
        remaining_tracks.sort()
        
        for i, voice_idx in enumerate(remaining_voices):
            if i < len(remaining_tracks):
                part_to_track[voice_idx] = remaining_tracks[i]
                logger.info(f"Part {voice_idx} zugeordnet zu Track {remaining_tracks[i]} (Fallback)")
        
        # SCHRITT 7: Jetzt füge CC1-Kurven ein, basierend auf dem Mapping
        logger.info(f"Finales Part-to-Track Mapping: {part_to_track}")
        
        for part_idx, dynamic_curve in dynamic_curves.items():
            # Konvertiere part_idx zu int, falls es ein String ist
            try:
                part_idx_int = int(part_idx)
            except (ValueError, TypeError):
                logger.warning(f"Ungültiger Part-Index: {part_idx}")
                continue
            
            # Prüfe, ob für diesen Part ein Track zugeordnet wurde
            if part_idx_int not in part_to_track:
                logger.warning(f"Keine Track-Zuordnung für Part {part_idx_int}")
                continue
            
            track_idx = part_to_track[part_idx_int]
            
            # Sicherheitsprüfung, falls der Track nicht existiert
            if track_idx < 0 or track_idx >= len(mid.tracks):
                logger.warning(f"Track-Index {track_idx} außerhalb des gültigen Bereichs für Part {part_idx_int}")
                continue
            
            logger.info(f"Erstelle CC1-Kurve für Part {part_idx_int} (Track {track_idx}) mit {len(dynamic_curve)} Punkten")
            
            # Absoluter Zeitpunkt für jedes vorhandene Event im Track
            abs_events = []
            current_time = 0
            
            for msg in mid.tracks[track_idx]:
                current_time += msg.time
                abs_events.append((current_time, msg.copy(time=0)))
            
            # Bestimme den häufigsten Kanal im Track
            channel_counts = {}
            for _, msg in abs_events:
                if hasattr(msg, 'channel'):
                    channel_counts[msg.channel] = channel_counts.get(msg.channel, 0) + 1
            
            channel = 0  # Standardwert
            if channel_counts:
                channel = max(channel_counts.items(), key=lambda x: x[1])[0]
            
            # Erstelle CC1-Events mit angepasster Timing
            cc1_events = []
            prev_value = None
            
            for beat, cc_value in dynamic_curve:
                # Überspringe wiederholte Werte
                if prev_value == cc_value:
                    continue
                
                # Konvertiere und passe Timing an
                original_tick = int(beat * mid.ticks_per_beat)
                adjusted_tick = adjust_timing(original_tick)
                
                cc1_msg = mido.Message('control_change', channel=channel, control=1, value=cc_value, time=0)
                cc1_events.append((adjusted_tick, cc1_msg))
                prev_value = cc_value
            
            # Kombiniere und sortiere Events
            combined_events = abs_events + cc1_events
            combined_events.sort(key=lambda x: x[0])
            
            # Konvertiere zurück zu Delta-Zeiten
            new_track = mido.MidiTrack()
            prev_tick = 0
            
            for abs_tick, msg in combined_events:
                # WICHTIG: Integer-Konvertierung für delta_time!
                delta_tick = int(abs_tick - prev_tick)
                delta_tick = max(0, delta_tick)  # Sicherstellen, dass Delta nicht negativ ist
                
                new_track.append(msg.copy(time=delta_tick))
                prev_tick = abs_tick
            
            # End of Track hinzufügen
            if not any(msg.type == 'end_of_track' for msg in new_track if msg.is_meta):
                new_track.append(mido.MetaMessage('end_of_track', time=0))
            
            # Ersetze den Track
            mid.tracks[track_idx] = new_track
            logger.info(f"Track {track_idx} mit CC1-Kurven aktualisiert")
        
        # Korrigiere die Tracklängen
        from midi_utils import fix_track_lengths_mid
        mid = fix_track_lengths_mid(mid)
        
        # Speichere die aktualisierte MIDI-Datei
        mid.save(midi_file)
        logger.info(f"MIDI-Datei mit synchronisierten CC1-Kurven gespeichert: {midi_file}")
        
        return midi_file
    
    except Exception as e:
        logger.error(f"Fehler bei der synchronisierten CC1-Verarbeitung: {e}")
        logger.error(f"Stack Trace: {traceback.format_exc()}")
        return midi_file

def insert_cc1_curve(midi_file, voice_dynamic_curves, ticks_per_beat, score, xml_path=None):
    """
    Schreibt separate CC1-Kurven für jede Stimme in die entsprechenden MIDI-Tracks.
    Verbesserte Version mit korrekter Positionierung der CC1-Kurven.
    
    Args:
        midi_file: Pfad zur MIDI-Datei
        voice_dynamic_curves: Dictionary mit Dynamikkurven für jede Stimme
        ticks_per_beat: MIDI-Ticks pro Viertelnote
        score: music21 Score-Objekt
        xml_path: Optional, Pfad zur MusicXML-Datei für zusätzliche Tempo-Informationen
        
    Returns:
        Pfad zur aktualisierten MIDI-Datei
    """
    import mido
    import logging
    import os
    import traceback
    from midi_utils import fix_track_lengths_mid
    
    logger = logging.getLogger(__name__)
    logger.info(f"====== CC1-Verarbeitung gestartet für {midi_file} ======")
    
    if not os.path.exists(midi_file):
        logger.error(f"MIDI-Datei existiert nicht: {midi_file}")
        return None
    
    try:
        mid = mido.MidiFile(midi_file)
        logger.info(f"MIDI-Datei geladen: Typ {mid.type}, {len(mid.tracks)} Tracks, {mid.ticks_per_beat} Ticks/Beat")
        
        # Stellen Sie sicher, dass die MIDI-Datei Typ 1 ist (mehrere Tracks)
        if mid.type == 0:
            logger.info("Konvertiere MIDI-Typ 0 zu Typ 1")
            content = mid.tracks[0]
            
            # Trenne Meta-Events von Noten-Events
            meta_track = mido.MidiTrack()
            note_tracks = {}
            
            # Analysiere alle Events und gruppiere sie
            current_time = 0
            for msg in content:
                current_time += msg.time
                
                if msg.is_meta:
                    # Füge Meta-Events zum Tempo-Track hinzu
                    meta_track.append(msg.copy(time=0))
                else:
                    # Identifiziere den Kanal für Noten-Events
                    channel = getattr(msg, 'channel', 0)
                    if channel not in note_tracks:
                        note_tracks[channel] = []
                    
                    # Speichere das Event mit absoluter Zeit
                    note_tracks[channel].append((current_time, msg.copy(time=0)))
            
            # Erstelle neue Tracks mit relativen Zeiten
            tracks = [meta_track]
            for channel, events in note_tracks.items():
                # Sortiere Events nach Zeit
                events.sort(key=lambda x: x[0])
                
                # Konvertiere zu relativer Zeit
                track = mido.MidiTrack()
                prev_time = 0
                
                for abs_time, msg in events:
                    delta = abs_time - prev_time
                    track.append(msg.copy(time=delta))
                    prev_time = abs_time
                
                # Füge End-of-Track hinzu
                if not any(msg.type == 'end_of_track' for msg in track if msg.is_meta):
                    track.append(mido.MetaMessage('end_of_track', time=0))
                
                tracks.append(track)
            
            # Erstelle neue MIDI-Datei
            new_mid = mido.MidiFile(type=1, ticks_per_beat=mid.ticks_per_beat)
            new_mid.tracks = tracks
            mid = new_mid
            logger.info(f"MIDI-Typ 0 zu Typ 1 konvertiert: {len(mid.tracks)} Tracks erstellt")
        
        # Identifiziere die Tracks mit Noten
        logger.info("Analysiere Tracks für die CC1-Einfügung")
        note_tracks = {}
        for i, track in enumerate(mid.tracks):
            note_count = sum(1 for msg in track if msg.type in ('note_on', 'note_off') and not msg.is_meta)
            if note_count > 0:
                if i == 0:
                    logger.info(f"Track {i} hat {note_count} Noten, aber wird als Tempo-Track übersprungen")
                    continue
                
                # Versuche, die Stimme zu identifizieren (MIDI-Track => music21 Part)
                part_idx = i - 1  # Übliche Zuordnung: track_idx - 1 = part_idx
                logger.info(f"Track {i} hat {note_count} Noten => Part {part_idx}")
                note_tracks[i] = part_idx
        
        logger.info(f"Identifizierte Noten-Tracks: {note_tracks}")
        
        # Extrahiere den Score-Namen für bessere Logs
        score_name = os.path.basename(midi_file) if midi_file else "unbekannt"
        if hasattr(score, 'metadata') and score.metadata and hasattr(score.metadata, 'title'):
            score_name = score.metadata.title
        
        logger.info(f"Score: {score_name}, Dauer: {score.highestTime} Beats")
        
        # Entferne bestehende CC1-Events aus allen Tracks
        logger.info("Entferne bestehende CC1-Events")
        for i, track in enumerate(mid.tracks):
            if i in note_tracks:
                # Extrahiere alle non-CC1-Events
                non_cc1_events = []
                for msg in track:
                    if not (msg.type == 'control_change' and msg.control == 1):
                        non_cc1_events.append(msg)
                
                # Ersetze den Track ohne CC1-Events
                mid.tracks[i] = mido.MidiTrack(non_cc1_events)
                logger.info(f"CC1-Events aus Track {i} entfernt")
        
        # Füge CC1-Kurven zu den Noten-Tracks hinzu
        for track_idx, part_idx in note_tracks.items():
            if part_idx in voice_dynamic_curves:
                dynamic_curve = voice_dynamic_curves[part_idx]
                logger.info(f"Füge {len(dynamic_curve)} CC1-Events zu Track {track_idx} (Part {part_idx}) hinzu")
                
                # Sammle alle bestehenden Events mit absoluten Zeiten
                abs_events = []
                current_tick = 0
                
                for msg in mid.tracks[track_idx]:
                    current_tick += msg.time
                    # Speichere Kopie mit Zeit 0 und absoluter Position
                    abs_events.append((current_tick, msg.copy(time=0)))
                
                # Erstelle CC1-Events mit absoluten Zeiten
                cc1_events = []
                prev_value = None
                
                for offset_beats, cc_value in dynamic_curve:
                    # Überspringe wiederholte Werte für bessere Performance
                    if prev_value == cc_value:
                        continue
                    
                    # Konvertiere Beat-Position zu Ticks
                    tick_pos = int(round(offset_beats * ticks_per_beat))
                    
                    # Erstelle CC1-Event mit derselben Kanal-Nummer wie die Notes
                    # Finde den Kanal für diesen Track
                    channel = 0
                    for _, msg in abs_events:
                        if hasattr(msg, 'channel'):
                            channel = msg.channel
                            break
                    
                    cc1_msg = mido.Message('control_change', channel=channel, control=1, value=cc_value, time=0)
                    cc1_events.append((tick_pos, cc1_msg))
                    prev_value = cc_value
                
                logger.info(f"Erstellt: {len(cc1_events)} CC1-Events für Track {track_idx}")
                
                # Kombiniere Events und sortiere nach Zeit
                combined_events = abs_events + cc1_events
                combined_events.sort(key=lambda x: x[0])
                
                # Konvertiere zurück zu Delta-Zeiten
                new_track = mido.MidiTrack()
                prev_tick = 0
                
                for abs_tick, msg in combined_events:
                    delta_tick = abs_tick - prev_tick
                    # Kopiere das Event mit der berechneten Delta-Zeit
                    new_track.append(msg.copy(time=delta_tick))
                    prev_tick = abs_tick
                
                # Stelle sicher, dass ein End-of-Track-Event vorhanden ist
                if not any(msg.type == 'end_of_track' for msg in new_track if msg.is_meta):
                    new_track.append(mido.MetaMessage('end_of_track', time=0))
                
                # Ersetze den Track
                mid.tracks[track_idx] = new_track
                logger.info(f"Track {track_idx} mit CC1-Kurven aktualisiert")
            else:
                logger.warning(f"Keine Dynamikkurve für Part {part_idx} (Track {track_idx}) gefunden")
        
        # Korrigiere die Tracklängen, damit alle Tracks synchron enden
        logger.info("Synchronisiere Tracklängen...")
        mid = fix_track_lengths_mid(mid)
        
        # Speichere die aktualisierte MIDI-Datei
        mid.save(midi_file)
        logger.info(f"MIDI-Datei mit CC1-Kurven gespeichert: {midi_file}")
        
        return midi_file
    
    except Exception as e:
        logger.error(f"Fehler bei der CC1-Verarbeitung: {e}")
        logger.error(f"Stack Trace: {traceback.format_exc()}")
        return midi_file

def insert_cc1_curve_with_interpretation(midi_file, voice_dynamic_curves, interpretation_results, ticks_per_beat, score, xml_path=None):
    """
    Schreibt organische CC1-Kurven in die MIDI-Datei, die direkt aus den 
    Interpretationsergebnissen des Digital Dirigenten abgeleitet werden.
    
    Args:
        midi_file: Pfad zur MIDI-Datei
        voice_dynamic_curves: Dictionary mit Dynamikkurven (wird nur als Fallback verwendet)
        interpretation_results: Ergebnisse der Interpretation vom Digital Dirigenten
        ticks_per_beat: MIDI-Ticks pro Viertelnote
        score: music21 Score-Objekt (wird nur als Fallback verwendet)
        xml_path: Optional, Pfad zur MusicXML-Datei
        
    Returns:
        Pfad zur verarbeiteten MIDI-Datei
    """
    logger.info(f"====== Organische CC1-Verarbeitung aus Interpretationsdaten für {midi_file} ======")
    
    if not os.path.exists(midi_file):
        logger.error(f"MIDI-Datei existiert nicht: {midi_file}")
        return None
    
    try:
        # Lade die CC1-Konfiguration
        cc1_config = load_cc1_config()
        logger.info("CC1-Konfiguration geladen")
        
        # Lade die MIDI-Datei
        mid = mido.MidiFile(midi_file)
        logger.info(f"MIDI-Datei geladen: Typ {mid.type}, {len(mid.tracks)} Tracks, {mid.ticks_per_beat} Ticks/Beat")
        
        # Extrahiere die Voices aus den Interpretationsergebnissen
        voices = interpretation_results.get('voices', [])
        if not voices:
            logger.warning("Keine Stimmeninformationen in den Interpretationsergebnissen gefunden")
            return insert_cc1_curve(midi_file, voice_dynamic_curves, ticks_per_beat, score, xml_path)
        
        # SCHRITT 1: Analysiere die MIDI-Tracks für Track-zu-Voice Mapping
        track_data = []
        max_note_end_time = 0  # Speichert das Ende der letzten Note
        
        for i, track in enumerate(mid.tracks):
            # Sammle alle wichtigen Informationen über den Track
            track_name = "Unbenannt"
            channels = set()
            note_events = []  # Sammle (note, time) Paare
            note_count = 0
            current_time = 0
            track_end_time = 0
            
            for msg in track:
                current_time += msg.time
                
                if msg.type == 'track_name':
                    track_name = msg.name
                
                if hasattr(msg, 'channel'):
                    channels.add(msg.channel)
                
                if msg.type == 'note_on' and hasattr(msg, 'velocity') and msg.velocity > 0:
                    note_events.append((msg.note, current_time))
                    note_count += 1
                
                # Berechne die End-Zeit der Note
                if msg.type == 'note_off' or (msg.type == 'note_on' and hasattr(msg, 'velocity') and msg.velocity == 0):
                    track_end_time = current_time
                    max_note_end_time = max(max_note_end_time, track_end_time)
            
            track_data.append({
                'index': i,
                'name': track_name,
                'channels': list(channels),
                'notes': note_count,
                'has_notes': note_count > 0,
                'note_events': note_events[:100],
                'end_time': track_end_time
            })
            
            logger.info(f"Track {i}: '{track_name}', {note_count} Noten, Kanäle: {list(channels)}, Endet bei: {track_end_time} Ticks")
        
        # SCHRITT 2: Ordne Voices zu Tracks zu
        voice_to_track = {}
        
        for voice_idx, voice in enumerate(voices):
            voice_name = getattr(voice, 'name', f"Stimme {voice_idx}")
            voice_track = getattr(voice, 'track_index', -1)
            voice_channel = getattr(voice, 'channel', -1)
            
            # Methode 1: Direkte Zuordnung über track_index Attribut
            if voice_track >= 0 and voice_track < len(mid.tracks):
                voice_to_track[voice_idx] = voice_track
                logger.info(f"Voice {voice_idx} direkt zugeordnet zu Track {voice_track} (über Attribut)")
                continue
                
            # Methode 2: Name-basierte Zuordnung
            for track in track_data:
                if track['name'] and voice_name and track['name'].lower() == voice_name.lower():
                    voice_to_track[voice_idx] = track['index']
                    logger.info(f"Voice {voice_idx} zugeordnet zu Track {track['index']} (über Namen)")
                    break
            
            # Methode 3: Kanal-basierte Zuordnung
            if voice_idx not in voice_to_track and voice_channel >= 0:
                for track in track_data:
                    if voice_channel in track['channels']:
                        voice_to_track[voice_idx] = track['index']
                        logger.info(f"Voice {voice_idx} zugeordnet zu Track {track['index']} (über Kanal {voice_channel})")
                        break
            
            # Methode 4: Heuristisches Matching (verbleibende Voices zu verbleibenden Tracks)
            if voice_idx not in voice_to_track:
                # Kandidaten sind Tracks mit Index > 0, die Noten enthalten
                candidates = [t for t in track_data if t['index'] > 0 and t['has_notes']]
                
                # Sortiere Kandidaten nach Anzahl der Noten
                candidates.sort(key=lambda x: x['notes'], reverse=True)
                
                # Wähle nur Tracks, die noch keiner Voice zugeordnet wurden
                used_tracks = set(voice_to_track.values())
                available_candidates = [t for t in candidates if t['index'] not in used_tracks]
                
                if available_candidates:
                    # Wähle den besten verfügbaren Kandidaten
                    best_track_idx = available_candidates[0]['index']
                    voice_to_track[voice_idx] = best_track_idx
                    logger.info(f"Voice {voice_idx} zugeordnet zu Track {best_track_idx} (heuristisch)")
        
        logger.info(f"Voice-to-Track Mapping: {voice_to_track}")
        
        # SCHRITT 3: Entferne bestehende CC1-Events
        for i, track in enumerate(mid.tracks):
            non_cc1_events = []
            for msg in track:
                if not (msg.type == 'control_change' and msg.control == 1):
                    non_cc1_events.append(msg)
            
            mid.tracks[i] = mido.MidiTrack(non_cc1_events)
        
        # SCHRITT 4: Erzeuge organische CC1-Kurven aus den interpretierten Noten
        for voice_idx, voice in enumerate(voices):
            if voice_idx not in voice_to_track:
                logger.warning(f"Keine Track-Zuordnung für Voice {voice_idx}")
                continue
                
            track_idx = voice_to_track[voice_idx]
            
            if not hasattr(voice, 'notes') or not voice.notes:
                logger.warning(f"Voice {voice_idx} hat keine Noten")
                continue
                
            logger.info(f"Erzeuge organische CC1-Kurve für Voice {voice_idx} (Track {track_idx}) mit {len(voice.notes)} Noten")
            
            # Sammle alle bestehenden Events mit absoluten Zeiten
            abs_events = []
            current_time = 0
            
            for msg in mid.tracks[track_idx]:
                current_time += msg.time
                abs_events.append((current_time, msg.copy(time=0)))
            
            # Bestimme den häufigsten Kanal im Track
            channel_counts = {}
            for _, msg in abs_events:
                if hasattr(msg, 'channel'):
                    channel_counts[msg.channel] = channel_counts.get(msg.channel, 0) + 1
            
            channel = 0  # Standardwert
            if channel_counts:
                channel = max(channel_counts.items(), key=lambda x: x[1])[0]
            
            # Finde die Rolle der Stimme (für angepasste Dynamik)
            voice_role = getattr(voice, 'role', 'unknown')
            logger.info(f"Voice {voice_idx} hat Rolle: {voice_role}")
            
            # --- KERNSTÜCK: VERBESSERTE Organische CC1-Kurvenberechnung ---
            cc1_points = []
            
            # Hilfsfunktion zur Transformation von MIDI-Velocity in erweiterten CC1-Bereich
            def enhance_dynamic_range(velocity, role_factor=1.0):
                # Parameter aus der Konfiguration holen
                min_cc = cc1_config["dynamic_range"]["min"]
                max_cc = cc1_config["dynamic_range"]["max"]
                velocity_mapping = cc1_config["velocity_mapping"]
                
                # Transformiere MIDI-Velocity in erweiterten CC-Bereich
                if velocity <= velocity_mapping["very_low"]["threshold"]:
                    return max(min_cc, int(min_cc * role_factor))  # Sehr leise Noten
                elif velocity <= velocity_mapping["low"]["threshold"]:
                    return max(min_cc, int((min_cc + (velocity - velocity_mapping["very_low"]["threshold"]) * 
                                          velocity_mapping["low"]["slope"]) * role_factor))  # Leise Noten
                elif velocity <= velocity_mapping["mid"]["threshold"]:
                    # Mittlerer Bereich - hier mehr Differenzierung
                    normalized = (velocity - velocity_mapping["low"]["threshold"]) / (
                        velocity_mapping["mid"]["threshold"] - velocity_mapping["low"]["threshold"])
                    expanded = velocity_mapping["low"]["threshold"] + normalized * velocity_mapping["mid"]["range"]
                    return int(min(max_cc, expanded * role_factor))
                else:
                    # Laute Noten - progressiv erhöhen
                    normalized = (velocity - velocity_mapping["mid"]["threshold"]) / (127 - velocity_mapping["mid"]["threshold"])
                    expanded = velocity_mapping["mid"]["threshold"] + normalized * velocity_mapping["high"]["range"]
                    return min(max_cc, int(expanded * role_factor))
            
            # Dynamikfaktoren nach Stimmtyp aus Konfiguration
            role_factor = cc1_config["role_factors"].get(voice_role, 1.0)
            
            # Für die Verbindung zwischen Noten
            prev_note_end = None
            prev_note_cc = None
            
            # 1. Sammle alle wichtigen Notenpunkte
            for note_idx, note in enumerate(voice.notes):
                if not hasattr(note, 'adjusted_start_time') or not hasattr(note, 'adjusted_velocity'):
                    continue
                
                # Berechne Note-On und Note-Off Zeiten
                note_on_time = note.adjusted_start_time
                note_off_time = note_on_time + note.adjusted_duration
                
                # Basis-Velocity für diese Note mit erweitertem Dynamikbereich
                base_velocity = note.adjusted_velocity
                note_on_cc = enhance_dynamic_range(base_velocity, role_factor)
                
                # A) Punkt am Notenbeginn (basierend auf interpretierter Velocity)
                cc1_points.append((note_on_time, note_on_cc))
                
                # Füge Übergangspunkte zwischen Noten hinzu, für weichere Kurven
                if prev_note_end is not None:
                    gap = note_on_time - prev_note_end
                    
                    # Nur wenn eine signifikante Lücke zwischen Noten existiert
                    if gap > 15 and abs(note_on_cc - prev_note_cc) > 5:
                        # Füge zwei Zwischenpunkte für kubische Annäherung ein
                        t1 = prev_note_end + gap * 0.3
                        t2 = prev_note_end + gap * 0.7
                        
                        # Kubische Interpolation für natürlicheren Übergang
                        # Langsamerer Start, schnelleres Ende
                        if note_on_cc > prev_note_cc:  # Ansteigend
                            v1 = prev_note_cc + (note_on_cc - prev_note_cc) * 0.15  # Langsam starten
                            v2 = prev_note_cc + (note_on_cc - prev_note_cc) * 0.75  # Schneller enden
                        else:  # Abfallend
                            v1 = prev_note_cc - (prev_note_cc - note_on_cc) * 0.25  # Schneller starten
                            v2 = prev_note_cc - (prev_note_cc - note_on_cc) * 0.85  # Langsam enden
                        
                        cc1_points.append((t1, int(v1)))
                        cc1_points.append((t2, int(v2)))
                
                # B) Für eine organischere Kurve, füge folgende Punkte hinzu:
                
                # B1) Melodische Konturen hervorheben
                if hasattr(note, 'is_melody') and note.is_melody:
                    # Für lokale Höhepunkte in Melodien
                    is_local_peak = (hasattr(note, 'prev_note') and hasattr(note, 'next_note') and 
                                     note.prev_note and note.next_note and
                                     hasattr(note, 'pitch') and 
                                     hasattr(note.prev_note, 'pitch') and hasattr(note.next_note, 'pitch') and
                                     note.pitch > note.prev_note.pitch and note.pitch > note.next_note.pitch)
                    
                    if is_local_peak:
                        # Parameter aus der Konfiguration holen
                        peak_params = cc1_config["curve_points"]["local_peak"]
                        
                        # Mehrere Punkte für sanfteren, ausdrucksvolleren Höhepunkt
                        rise_time = note_on_time + int(note.adjusted_duration * peak_params["rise_point"])
                        peak_time = note_on_time + int(note.adjusted_duration * peak_params["peak_point"])
                        fall_time = note_on_time + int(note.adjusted_duration * peak_params["fall_point"])
                        
                        rise_cc = min(cc1_config["dynamic_range"]["max"], int(note_on_cc * peak_params["rise_factor"]))
                        peak_cc = min(cc1_config["dynamic_range"]["max"], int(note_on_cc * peak_params["peak_factor"]))
                        fall_cc = min(cc1_config["dynamic_range"]["max"], int(note_on_cc * peak_params["fall_factor"]))
                        
                        cc1_points.append((rise_time, rise_cc))
                        cc1_points.append((peak_time, peak_cc))
                        cc1_points.append((fall_time, fall_cc))
                    
                    # Phrasenposition berücksichtigen
                    if hasattr(note, 'phrase_position') and note.phrase_position is not None:
                        if note.phrase_position < 0.1:  # Phrasenanfang
                            # Parameter aus der Konfiguration holen
                            phrase_start_params = cc1_config["curve_points"]["phrase_start"]
                            
                            # Progressive Steigerung am Phrasenanfang
                            time_points = phrase_start_params["time_points"]
                            value_factors = phrase_start_params["value_factors"]
                            
                            for t_factor, v_factor in zip(time_points, value_factors):
                                t = note_on_time + int(note.adjusted_duration * t_factor)
                                v = min(cc1_config["dynamic_range"]["max"], int(note_on_cc * v_factor))
                                cc1_points.append((t, v))
                                
                        elif note.phrase_position > 0.9:  # Phrasenende
                            # Parameter aus der Konfiguration holen
                            phrase_end_params = cc1_config["curve_points"]["phrase_end"]
                            
                            # Progressives Abschwächen am Phrasenende
                            time_points = phrase_end_params["time_points"]
                            value_factors = phrase_end_params["value_factors"]
                            
                            for t_factor, v_factor in zip(time_points, value_factors):
                                t = note_on_time + int(note.adjusted_duration * t_factor)
                                v = max(cc1_config["dynamic_range"]["min"], int(note_on_cc * v_factor))
                                cc1_points.append((t, v))
                
                # B2) Basslinien und längere Noten mit subtilen Veränderungen
                if (hasattr(note, 'is_bass') and note.is_bass) or note.adjusted_duration > (ticks_per_beat/2):
                    # Mehr Punkte für organischere Dynamik
                    duration = note.adjusted_duration
                    
                    if hasattr(note, 'is_bass') and note.is_bass:
                        # Für Bass: Parameter aus der Konfiguration holen
                        bass_patterns = cc1_config["curve_points"]["bass_patterns"]
                        for pattern in bass_patterns:
                            points = []
                            for i, time_factor in enumerate(pattern["time_points"]):
                                value_factor = pattern["value_factors"][i]
                                t = note_on_time + int(duration * time_factor)
                                v = max(cc1_config["dynamic_range"]["min"], int(note_on_cc * value_factor))
                                points.append((t, v))
                            cc1_points.extend(points)
                    else:
                        # Für andere lange Noten: Parameter aus der Konfiguration holen
                        long_note_min_duration = cc1_config["curve_points"]["long_note_min_duration"]
                        
                        if duration > long_note_min_duration:  # Nur für ausreichend lange Noten
                            import random
                            # Verschiedene organische Muster für Variation
                            patterns = cc1_config["curve_points"]["long_note_patterns"]
                            
                            # Zufällig ein Pattern auswählen für musikalische Variation
                            selected_pattern = random.choice(patterns)
                            
                            for i, pos in enumerate(selected_pattern["time_points"]):
                                factor = selected_pattern["value_factors"][i]
                                time_point = note_on_time + int(duration * pos)
                                value = min(cc1_config["dynamic_range"]["max"], 
                                           max(cc1_config["dynamic_range"]["min"], 
                                               int(note_on_cc * factor)))
                                cc1_points.append((time_point, value))
                
                # B3) Allen Noten ein organisches Ausklingen geben
                note_decay_params = cc1_config["curve_points"]["note_decay"]
                min_duration = note_decay_params["min_duration"]
                
                if note.adjusted_duration > min_duration:  # Nur für ausreichend lange Noten
                    # Parameter aus der Konfiguration holen
                    long_note_params = note_decay_params["long_note"]
                    time_points = long_note_params["time_points"]
                    value_factors = long_note_params["value_factors"]
                    
                    # Mehrere Punkte für sanfteres Ausklingen
                    decay_points = []
                    for i, time_factor in enumerate(time_points):
                        value_factor = value_factors[i]
                        t = note_off_time - min(int(note.adjusted_duration * (1 - time_factor)), 
                                              int(note.adjusted_duration * 0.15))
                        v = max(cc1_config["dynamic_range"]["min"], int(note_on_cc * value_factor))
                        decay_points.append((t, v))
                    cc1_points.extend(decay_points)
                else:
                    # Für kurze Noten: einfacheres Ausklingen
                    end_factor = note_decay_params["short_note"]["end_factor"]
                    cc1_points.append((note_off_time, 
                                     max(cc1_config["dynamic_range"]["min"], 
                                         int(note_on_cc * end_factor))))
                
                # Speichere für den nächsten Durchlauf
                prev_note_end = note_off_time
                prev_note_cc = max(cc1_config["dynamic_range"]["min"], 
                                 int(note_on_cc * note_decay_params["short_note"]["end_factor"]))
            
            # 2. Sortiere und filtere die CC1-Punkte
            cc1_points.sort(key=lambda x: x[0])
            
            # Verbesserte Filterung mit adaptiven Kriterien aus Konfiguration
            filtered_points = []
            prev_time = -1
            prev_value = -1
            
            # Identifiziere wichtige Punkte (lokale Extrema)
            important_points = set()
            if len(cc1_points) > 5:  # Nur bei genügend Punkten prüfen
                window_size = cc1_config["filtering"]["important_points"]["window_size"]
                
                for i in range(window_size, len(cc1_points) - window_size):
                    curr_time, curr_value = cc1_points[i]
                    
                    # Prüfe auf lokales Maximum/Minimum innerhalb des Fensters
                    is_max = True
                    is_min = True
                    
                    for j in range(i - window_size, i + window_size + 1):
                        if j == i:
                            continue
                        
                        if j < 0 or j >= len(cc1_points):
                            continue
                        
                        if cc1_points[j][1] >= curr_value:
                            is_max = False
                        if cc1_points[j][1] <= curr_value:
                            is_min = False
                    
                    if is_max or is_min:
                        important_points.add(curr_time)
            
            # Filterungsparameter aus Konfiguration
            filtering = cc1_config["filtering"]["thresholds"]
            
            for i, (time, value) in enumerate(cc1_points):
                # Standardkriterien
                min_time_gap = filtering["slow_change"]["time_gap"]
                min_value_diff = filtering["slow_change"]["value_diff"]
                
                if prev_time > 0:
                    # Berechne Änderungsrate für adaptive Filterung
                    time_diff = time - prev_time
                    value_diff = abs(value - prev_value)
                    change_rate = value_diff / max(1, time_diff)
                    
                    # Adaptive Filterung basierend auf Änderungsrate
                    if change_rate > filtering["fast_change"]["rate"]:  # Schnelle Änderung
                        min_time_gap = filtering["fast_change"]["time_gap"]
                        min_value_diff = filtering["fast_change"]["value_diff"]
                    elif change_rate > filtering["moderate_change"]["rate"]:  # Moderate Änderung
                        min_time_gap = filtering["moderate_change"]["time_gap"]
                        min_value_diff = filtering["moderate_change"]["value_diff"]
                
                # Kriterien für die Beibehaltung des Punktes
                is_important = time in important_points
                keep_by_time = (prev_time < 0) or (time - prev_time >= min_time_gap)
                keep_by_value = (prev_value < 0) or (abs(value - prev_value) >= min_value_diff)
                
                # Ersten und letzten Punkt immer behalten
                is_endpoint = (i == 0) or (i == len(cc1_points) - 1)
                
                if is_important or keep_by_time or keep_by_value or is_endpoint:
                    filtered_points.append((time, value))
                    prev_time = time
                    prev_value = value
            
            # 3. Füge die CC1-Events zum Track hinzu
            cc1_events = []
            
            for time, value in filtered_points:
                cc1_msg = mido.Message('control_change', channel=channel, control=1, value=value, time=0)
                cc1_events.append((time, cc1_msg))
            
            # Kombiniere bestehende Events mit neuen CC1-Events
            combined_events = abs_events + cc1_events
            combined_events.sort(key=lambda x: x[0])
            
            # Konvertiere zurück zu Delta-Zeiten
            new_track = mido.MidiTrack()
            prev_time = 0
            
            for abs_time, msg in combined_events:
                delta_time = int(abs_time - prev_time)
                delta_time = max(0, delta_time)  # Sicherstellen, dass Delta nicht negativ ist
                
                new_track.append(msg.copy(time=delta_time))
                prev_time = abs_time
            
            # End of Track hinzufügen, falls noch nicht vorhanden
            if not any(msg.type == 'end_of_track' for msg in new_track if msg.is_meta):
                new_track.append(mido.MetaMessage('end_of_track', time=0))
            
            # Ersetze den Track
            mid.tracks[track_idx] = new_track
            logger.info(f"Track {track_idx} mit organischen CC1-Kurven aktualisiert ({len(filtered_points)} Punkte)")
        
        # SCHRITT 5: Korrigiere die Tracklängen für korrekte Synchronisation
        from midi_utils import fix_track_lengths_mid
        mid = fix_track_lengths_mid(mid)
        
        # Speichere die aktualisierte MIDI-Datei
        mid.save(midi_file)
        logger.info(f"MIDI-Datei mit organischen CC1-Kurven gespeichert: {midi_file}")
        
        return midi_file
    
    except Exception as e:
        logger.error(f"Fehler bei der organischen CC1-Verarbeitung: {e}")
        logger.error(f"Stack Trace: {traceback.format_exc()}")
        
        # Fallback auf standard CC1-Methode
        logger.info("Versuche Fallback auf Standard-CC1-Methode...")
        return insert_cc1_curve(midi_file, voice_dynamic_curves, ticks_per_beat, score, xml_path)


def process_file(xml_file, output_midi=None, ):
    """
    Konvertiert eine MusicXML-Datei in eine MIDI-Datei mit verbesserten Dynamik-Kurven
    und optionaler Humanisierung.
    Verwendet MuseScore, wenn verfügbar.
    
    Args:
        xml_file: Pfad zur MusicXML-Datei
        output_midi: Optional, Pfad zur Ausgabe-MIDI-Datei
       
        
    Returns:
        Pfad zur erzeugten MIDI-Datei
    """
    logger.info(f"Verarbeite MusicXML-Datei: {xml_file}")
  
    
    # Prüfe, ob die XML-Datei existiert
    if not os.path.exists(xml_file):
        logger.error(f"!!! XML-Datei existiert nicht: {xml_file}")
        return None
    
    # Parse Score für Analyse
    try:
        logger.info("Parse Score mit music21...")
        score = m21.converter.parse(xml_file)
        logger.info("Score erfolgreich geparst")
    except Exception as e:
        logger.error(f"!!! Fehler beim Parsen der MusicXML-Datei: {e}")
        logger.error(f"Stack Trace: {traceback.format_exc()}")
        return None
    
    # Bestimme Ausgabepfad, falls nicht angegeben
    if not output_midi:
        base_name = os.path.splitext(os.path.basename(xml_file))[0]
        output_dir = os.path.join(os.path.dirname(xml_file), "results")
        os.makedirs(output_dir, exist_ok=True)
        output_midi = os.path.join(output_dir, f"{base_name}.mid")
    
    # Konvertiere zu MIDI - mit MuseScore, wenn verfügbar
    if MUSESCORE_AVAILABLE:
        try:
            logger.info("Versuche, MuseScore für MIDI-Konvertierung zu verwenden...")
            midi_file = convert_xml_to_midi_with_musescore(xml_file, output_midi)
            if midi_file:
                logger.info(f"MIDI-Datei mit MuseScore erstellt: {midi_file}")
            else:
                logger.error("!!! MuseScore-Konvertierung fehlgeschlagen")
                # Fallback auf music21, wenn MuseScore fehlschlägt
                logger.info("Fallback auf music21 für MIDI-Konvertierung...")
                score.write('midi', fp=output_midi, ticksPerQuarter=480)
                logger.info(f"MIDI-Datei mit music21 erstellt: {output_midi}")
                midi_file = output_midi
        except Exception as e:
            logger.error(f"!!! Fehler bei der MuseScore-Konvertierung: {e}")
            logger.error(f"Stack Trace: {traceback.format_exc()}")
            logger.info("Fallback auf music21 für MIDI-Konvertierung...")
            score.write('midi', fp=output_midi, ticksPerQuarter=480)
            logger.info(f"MIDI-Datei mit music21 erstellt: {output_midi}")
            midi_file = output_midi
    else:
        try:
            logger.info("Verwende music21 für MIDI-Konvertierung (MuseScore nicht verfügbar)...")
            # Setze explizit ticks_per_beat=480 für bessere Kompatibilität
            score.write('midi', fp=output_midi, ticksPerQuarter=480)
            logger.info(f"MIDI-Datei mit music21 erstellt: {output_midi}")
            midi_file = output_midi
        except Exception as e:
            logger.error(f"!!! Fehler bei der music21-MIDI-Konvertierung: {e}")
            logger.error(f"Stack Trace: {traceback.format_exc()}")
            return None
    
    # Korrigiere die MIDI-Track-Struktur
    try:
        logger.info("Korrigiere MIDI-Track-Struktur...")
        fix_musescore_midi_tracks(midi_file)
        logger.info("MIDI-Track-Struktur erfolgreich korrigiert")
    except Exception as e:
        logger.error(f"!!! Fehler bei der MIDI-Struktur-Korrektur: {e}")
        logger.error(f"Stack Trace: {traceback.format_exc()}")
    
    # Extrahiere dynamische Punkte
    try:
        logger.info("Extrahiere dynamische Punkte aus Score...")
        dynamic_points = extract_dynamic_points(score)
        logger.info(f"Dynamik-Punkte für {len(dynamic_points)} Stimmen extrahiert")
    except Exception as e:
        logger.error(f"!!! Fehler bei der Extraktion von Dynamikpunkten: {e}")
        logger.error(f"Stack Trace: {traceback.format_exc()}")
        return midi_file  # Trotzdem fortfahren mit leeren Dynamikkurven
        
    # Interpoliere Dynamik
    try:
        logger.info("Interpoliere Dynamik...")
        total_duration = score.highestTime
        resolution = 0.1
        dynamic_curves = non_linear_interpolate_dynamics(dynamic_points, total_duration, resolution)
        logger.info(f"Dynamik-Kurven erstellt für {len(dynamic_curves)} Stimmen")
    except Exception as e:
        logger.error(f"!!! Fehler bei der Interpolation der Dynamik: {e}")
        logger.error(f"Stack Trace: {traceback.format_exc()}")
        return midi_file  # Trotzdem fortfahren mit leeren Dynamikkurven
    
    # Bestimme MIDI-Ticks pro Beat
    try:
        logger.info(f"Lade MIDI-Datei zur Bestimmung von ticks_per_beat: {midi_file}")
        midi_file_obj = mido.MidiFile(midi_file)
        ticks_per_beat = midi_file_obj.ticks_per_beat
        logger.info(f"MIDI ticks_per_beat: {ticks_per_beat}")
    except Exception as e:
        logger.error(f"!!! Fehler beim Bestimmen von ticks_per_beat: {e}")
        logger.error(f"Stack Trace: {traceback.format_exc()}")
        ticks_per_beat = 480  # Standard-Wert
        logger.info(f"Verwende Standard-Wert: ticks_per_beat = {ticks_per_beat}")
    
    # Integriere CC1-Kurven
    try:
        logger.info("Füge CC1-Kurven in MIDI ein...")
        output_midi = insert_cc1_curve(midi_file, dynamic_curves, ticks_per_beat, score, xml_path=xml_file)
        
       
        logger.info(f"Verarbeitung abgeschlossen: {output_midi}")
    except Exception as e:
        logger.error(f"!!! Fehler beim Einfügen der CC1-Kurven: {e}")
        logger.error(f"Stack Trace: {traceback.format_exc()}")
        return midi_file
    
    return output_midi

if __name__ == "__main__":
    # Einfacher Test, wenn dieses Skript direkt ausgeführt wird
    if len(sys.argv) > 1:
        xml_file = sys.argv[1]
        logger.info(f"Teste Verarbeitung von: {xml_file}")
        midi_file = process_file(xml_file)
        if midi_file:
            logger.info(f"Verarbeitung erfolgreich abgeschlossen: {midi_file}")
        else:
            logger.error("!!! Verarbeitung fehlgeschlagen")