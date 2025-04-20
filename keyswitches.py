"""
Vereinfachtes Keyswitch-Modul für den Barockmusik MIDI-Prozessor
-------------------------------------------------------
Dieses Modul fügt Keyswitches basierend auf der Notenlänge hinzu:
- Kurze Noten (< 1/8) erhalten Staccato
- Längere Noten (≥ 1/8) erhalten Sustain

Verwendet die articulations_config.json für Instrumenterkennung und Keyswitch-Werte.
Enthält Oktavkorrektur für Basso Continuo und French Harpsichord.

Autor: Claude
"""

import mido
import logging
import os
import json
import traceback
from typing import Dict, List, Tuple, Optional, Any

# Logging konfigurieren
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_articulation_config(library_name="miroire"):
    """
    Lädt die Artikulationskonfiguration aus der JSON-Datei.
    
    Args:
        library_name: Name der Sample Library (default: "miroire")
        
    Returns:
        Dictionary mit der Konfiguration
    """
    try:
        config_path = os.path.join(os.path.dirname(__file__), "articulations_config.json")
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        if library_name not in config:
            logger.warning(f"Bibliothek '{library_name}' nicht in der Konfiguration gefunden")
            return {}
            
        return config.get(library_name, {})
    except Exception as e:
        logger.error(f"Fehler beim Laden der Artikulationskonfiguration: {e}")
        return {}

def identify_instrument(track_name: str, config: Dict) -> Optional[str]:
    """
    Identifiziert den Instrumenttyp anhand des Track-Namens mit verbesserter Basso Continuo Erkennung.
    
    Args:
        track_name: Name des MIDI-Tracks
        config: Artikulationskonfiguration
        
    Returns:
        Identifizierter Instrumenttyp oder None
    """
    if not track_name or not config or "instrument_mapper" not in config:
        return None
    
    track_name_lower = track_name.lower()
    
    # Spezielle Erkennung für Basso Continuo mit häufigen Varianten
    continuo_patterns = [
        'continuo', 'basso', 'cello', 'bc', 'bass', 'violoncello', 'vc', 'vcl'
    ]
    
    # Prüfe direkt auf Basso Continuo Muster
    for pattern in continuo_patterns:
        if pattern in track_name_lower:
            logger.info(f"Basso Continuo erkannt für Track '{track_name}' über Muster '{pattern}'")
            return "Basso Continuo"
    
    # Standarderkennung über Instrument Mapper
    for instrument, aliases in config["instrument_mapper"].items():
        for alias in aliases:
            if alias.lower() in track_name_lower:
                logger.info(f"Instrument '{instrument}' erkannt für Track '{track_name}'")
                return instrument
    
    logger.warning(f"Kein passendes Instrument für Track '{track_name}' gefunden")
    return None

def get_keyswitch_values(instrument_type: str, config: Dict) -> Tuple[int, int]:
    """
    Holt die Keyswitch-Werte für Staccato und Sustain für ein bestimmtes Instrument.
    
    Args:
        instrument_type: Typ des Instruments
        config: Artikulationskonfiguration
        
    Returns:
        Tupel mit (sustain_keyswitch, staccato_keyswitch)
    """
    # Standardwerte falls nichts gefunden wird
    default_sustain = 24  # C0
    default_staccato = 32  # G#0
    
    if not instrument_type or "instruments" not in config or instrument_type not in config["instruments"]:
        return default_sustain, default_staccato
    
    instrument_config = config["instruments"][instrument_type]
    articulations = instrument_config.get("articulations", {})
    
    # Suche nach Sustain und Staccato Artikulationen
    sustain_key = None
    staccato_key = None
    
    for key, data in articulations.items():
        name = data.get("name", "").lower()
        if "sustain" in name and (not "soft" in name) and not sustain_key:
            sustain_key = key
        elif "staccato" in name and not "staccatissimo" in name and not staccato_key:
            staccato_key = key
    
    # Falls nichts gefunden, versuche es mit C0/C6 und G#0/G#6 (falls vorhanden)
    if not sustain_key:
        # Prüfe auf C0 oder C6 (je nach Instrument)
        if "C0" in articulations:
            sustain_key = "C0"
        elif "C6" in articulations:
            sustain_key = "C6"
    
    if not staccato_key:
        # Prüfe auf G#0 oder G#6 (je nach Instrument)
        if "G#0" in articulations:
            staccato_key = "G#0"
        elif "G#6" in articulations:
            staccato_key = "G#6"
    
    # MIDI-Nummern abrufen
    sustain_ks = articulations.get(sustain_key, {}).get("midi_number", default_sustain) if sustain_key else default_sustain
    staccato_ks = articulations.get(staccato_key, {}).get("midi_number", default_staccato) if staccato_key else default_staccato
    
    logger.debug(f"Instrument {instrument_type}: Sustain KS {sustain_ks} ({sustain_key}), Staccato KS {staccato_ks} ({staccato_key})")
    return sustain_ks, staccato_ks

def add_keyswitches(midi_file: str, library: str = "miroire", debug_mode: bool = True) -> str:
    """
    Fügt einfache längenbasierte Keyswitches zu einer MIDI-Datei hinzu.
    Ein Keyswitch wird vor jeder Note eingefügt:
    - Kurze Noten (< 1/8) erhalten Staccato-Keyswitch
    - Längere Noten (≥ 1/8) erhalten Sustain-Keyswitch
    
    Verwendet die articulations_config.json für Instrumenterkennung und Keyswitch-Werte.
    
    Args:
        midi_file: Pfad zur MIDI-Datei
        library: Name der Sample Library (z.B. "miroire")
        debug_mode: Aktiviert ausführliches Logging
        
    Returns:
        Pfad zur aktualisierten MIDI-Datei
    """
    logger.info(f"Füge einfache Keyswitches zur MIDI-Datei hinzu: {midi_file} (Library: {library})")
    
    # DEBUG-Log-Level setzen, wenn debug_mode aktiviert ist
    original_level = logger.level
    if debug_mode:
        logger.setLevel(logging.DEBUG)
        logger.debug("DEBUG-Modus aktiviert - ausführliches Logging eingeschaltet")
    
    try:
        # Validiere Eingabeparameter
        if not midi_file or not os.path.exists(midi_file):
            logger.error(f"MIDI-Datei existiert nicht: {midi_file}")
            return midi_file
        
        # Lade Artikulationskonfiguration
        config = load_articulation_config(library)
        if not config:
            logger.error(f"Keine Konfiguration für Library '{library}' gefunden")
            return midi_file
        
        # MIDI-Datei laden
        try:
            mid = mido.MidiFile(midi_file)
            ticks_per_beat = mid.ticks_per_beat
        except Exception as e:
            logger.error(f"Fehler beim Laden der MIDI-Datei: {e}")
            return midi_file
        
        # Achtelnote in Ticks definieren
        eighth_note_ticks = ticks_per_beat // 2
        
        logger.info(f"MIDI-Datei geladen: Typ {mid.type}, {len(mid.tracks)} Tracks, {ticks_per_beat} Ticks/Beat")
        logger.info(f"Achtelnote = {eighth_note_ticks} Ticks")
        
        # Log-Level für Debugging auf INFO setzen
        log_level_save = logging.getLogger().level
        logging.getLogger().setLevel(logging.INFO)
        
        # Debug-Info: Zeige tatsächliche MIDI-Struktur vor der Verarbeitung
        logger.info(f"=== MIDI-Struktur vor Keyswitch-Verarbeitung ===")
        for i, track in enumerate(mid.tracks):
            name = "Unbenannt"
            for msg in track:
                if msg.is_meta and msg.type == 'track_name':
                    name = msg.name
                    break
            
            notes = sum(1 for msg in track if msg.type == 'note_on' and hasattr(msg, 'velocity') and msg.velocity > 0)
            logger.info(f"Track {i}: '{name}' - {notes} Noten")
        
        # WICHTIG: Verarbeite jeden Track mit Noten - ohne Annahmen über Track-Index
        tracks_modified = 0
        
        for track_idx, track in enumerate(mid.tracks):
            # Track-Name finden
            track_name = "Unbenannt"
            for msg in track:
                if msg.is_meta and msg.type == 'track_name':
                    track_name = msg.name
                    break
                    
            # Prüfe, ob der Track Noten enthält
            note_count = sum(1 for msg in track if msg.type == 'note_on' and hasattr(msg, 'velocity') and msg.velocity > 0)
            
            # Tracks ohne Noten überspringen (unabhängig vom Index)
            if note_count == 0:
                logger.info(f"Überspringe Track {track_idx} ('{track_name}') - keine Noten")
                continue
                
            # Part-Index bestimmen (für Konsistenz mit anderen Prozessen)
            part_idx = track_idx  # Verwende direkt den Track-Index als Part-Index
            
            logger.info(f"Verarbeite Track {track_idx} (Part {part_idx}): '{track_name}'")
            
            # Instrument anhand des Track-Namens identifizieren
            instrument_type = identify_instrument(track_name, config)
            
            # Keyswitch-Werte für dieses Instrument aus der Konfiguration holen
            if instrument_type:
                sustain_keyswitch, staccato_keyswitch = get_keyswitch_values(instrument_type, config)
                logger.info(f"Instrument {instrument_type} erkannt: Sustain KS = {sustain_keyswitch}, Staccato KS = {staccato_keyswitch}")
                
                # Oktavkorrektur für unterschiedliche Instrumente
                if "Harpsichord" in instrument_type:
                    # Eine Oktave HÖHER für Harpsichord (+12 MIDI-Noten)
                    original_sustain = sustain_keyswitch
                    original_staccato = staccato_keyswitch
                    sustain_keyswitch += 12
                    staccato_keyswitch += 12
                    logger.info(f"Oktavkorrektur (+12) für {instrument_type}: Sustain {original_sustain} -> {sustain_keyswitch}, Staccato {original_staccato} -> {staccato_keyswitch}")
                elif "Continuo" in instrument_type or "Basso" in instrument_type or "Cello" in instrument_type:
                    # Eine Oktave HÖHER für Continuo (+12 MIDI-Noten)
                    original_sustain = sustain_keyswitch
                    original_staccato = staccato_keyswitch
                    sustain_keyswitch += 12
                    staccato_keyswitch += 12
                    logger.info(f"Oktavkorrektur (+12) für {instrument_type}: Sustain {original_sustain} -> {sustain_keyswitch}, Staccato {original_staccato} -> {staccato_keyswitch}")
            else:
                # Standardwerte falls kein Instrument erkannt wurde
                sustain_keyswitch = 24  # C0
                staccato_keyswitch = 32  # G#0
                logger.warning(f"Kein Instrument für Track {track_idx} ({track_name}) erkannt, verwende Standardwerte")
            
            # Noten vor der Verarbeitung zählen
            note_count_before = note_count
            logger.info(f"Verarbeite Track {track_idx}: '{track_name}' mit {note_count_before} Noten")
            
            # Erster Durchlauf: Alle Noten mit ihren absoluten Zeiten und Dauern sammeln
            notes_data = []
            current_time = 0
            notes_on = {}  # {(note, channel, counter): (abs_time, msg)}
            notes_on_counter = 0  # Zähler für wiederholte Noten
            
            try:
                for msg in track:
                    current_time += msg.time
                    
                    if msg.type == 'note_on' and hasattr(msg, 'velocity') and msg.velocity > 0:
                        # Note-On Event
                        key = (msg.note, msg.channel, notes_on_counter)
                        notes_on[key] = (current_time, msg)
                        notes_on_counter += 1
                    elif (msg.type == 'note_off') or (msg.type == 'note_on' and hasattr(msg, 'velocity') and msg.velocity == 0):
                        # Note-Off Event
                        # Finde das passende Note-On
                        matching_key = None
                        for key in list(notes_on.keys()):
                            if key[0] == msg.note and key[1] == msg.channel:
                                matching_key = key
                                break
                                
                        if matching_key:
                            on_time, on_msg = notes_on.pop(matching_key)
                            note_length = current_time - on_time
                            
                            # Stellen Sie sicher, dass keine Note mit Dauer 0 existiert
                            if note_length <= 0:
                                note_length = 1  # Mindestdauer von 1 Tick erzwingen
                                logger.warning(f"Note mit Dauer 0 korrigiert: Track {track_idx}, "
                                              f"Kanal {msg.channel}, Note {msg.note}, Zeit {current_time}")
                            
                            # Artikulation basierend auf Notenlänge bestimmen
                            # Für eine bessere Verteilung der Artikulationen, variieren wir die Schwelle etwas
                            # basierend auf der Velocity: Schnellere und lautere Noten eher Staccato
                            velocity_factor = on_msg.velocity / 127.0  # 0.0 bis 1.0
                            adjusted_threshold = eighth_note_ticks * (0.9 + 0.2 * velocity_factor)
                            
                            keyswitch = staccato_keyswitch if note_length < adjusted_threshold else sustain_keyswitch
                            articulation = "staccato" if note_length < adjusted_threshold else "sustain"
                            
                            notes_data.append({
                                'note': msg.note,
                                'channel': msg.channel,
                                'on_time': on_time,
                                'off_time': current_time,
                                'length': note_length,
                                'velocity': on_msg.velocity,
                                'keyswitch': keyswitch,
                                'articulation': articulation
                            })
            except Exception as e:
                logger.error(f"Fehler beim Sammeln der Noten für Track {track_idx}: {e}")
                logger.error(traceback.format_exc())
                continue
            
            # Sortiere Noten nach Startzeit
            notes_data.sort(key=lambda x: x['on_time'])
            logger.debug(f"{len(notes_data)} Noten mit ihren Dauern gesammelt")
            
            # Zähle jeden Artikulationstyp
            staccato_count = sum(1 for n in notes_data if n['articulation'] == 'staccato')
            sustain_count = sum(1 for n in notes_data if n['articulation'] == 'sustain')
            logger.info(f"Artikulationsverteilung: {staccato_count} Staccato-Noten, {sustain_count} Sustain-Noten")
            
            # Zweiter Durchlauf: Alle Events mit absoluten Zeiten sammeln
            try:
                abs_events = []
                current_time = 0
                
                for msg in track:
                    current_time += msg.time
                    abs_events.append((current_time, msg.copy(time=0)))
                
                # Keyswitch-Nachrichten vor jeder Note hinzufügen
                keyswitch_events = []
                
                for note_data in notes_data:
                    # Positioniere den Keyswitch vor der Note
                    # Mit instrumentspezifischen Anpassungen
                    if "Harpsichord" in (instrument_type or ""):
                        ks_time = max(0, note_data['on_time'] - 20)  # 20 Ticks vor der Note für Cembalo
                        ks_velocity = 127  # Maximale Velocity für Cembalo
                    elif "Continuo" in (instrument_type or "") or "Basso" in (instrument_type or "") or "Cello" in (instrument_type or ""):
                        ks_time = max(0, note_data['on_time'] - 15)  # 15 Ticks vor der Note für Continuo
                        ks_velocity = 120  # Hohe Velocity für Continuo
                    else:
                        ks_time = max(0, note_data['on_time'] - 10)  # 10 Ticks vor der Note für Streicher
                        ks_velocity = 100  # Standard Velocity
                    
                    # Erstelle Keyswitch-Nachrichten (Note-On und Note-Off)
                    ks_on = mido.Message('note_on', note=note_data['keyswitch'], velocity=ks_velocity, 
                                        channel=note_data['channel'], time=0)
                    ks_off = mido.Message('note_off', note=note_data['keyswitch'], velocity=0, 
                                        channel=note_data['channel'], time=0)
                    
                    # Füge die Keyswitch-Events mit instrumentspezifischer Dauer hinzu
                    if "Harpsichord" in (instrument_type or ""):
                        ks_duration = 10  # Längere Dauer für Cembalo (10 Ticks)
                    elif "Continuo" in (instrument_type or "") or "Basso" in (instrument_type or ""):
                        ks_duration = 5   # Mittlere Dauer für Continuo (5 Ticks)
                    else:
                        ks_duration = 1   # Kurze Dauer für Streicher (1 Tick)
                    keyswitch_events.append((ks_time, ks_on))
                    keyswitch_events.append((ks_time + ks_duration, ks_off))
                    
                    logger.debug(f"Note {note_data['note']} (Länge {note_data['length']} Ticks): {note_data['articulation']} Keyswitch bei {ks_time}")
                
                # Kombiniere alle Events und sortiere nach Zeit
                all_events = abs_events + keyswitch_events
                all_events.sort(key=lambda x: x[0])
                
                # Konvertiere zurück zu Delta-Zeiten
                new_track = mido.MidiTrack()
                prev_time = 0
                
                for abs_time, msg in all_events:
                    delta = max(0, abs_time - prev_time)  # Stelle sicher, dass Delta nicht negativ ist
                    new_track.append(msg.copy(time=delta))
                    prev_time = abs_time
                
                # Stelle sicher, dass ein End-of-Track Event vorhanden ist
                if not any(msg.type == 'end_of_track' for msg in new_track if msg.is_meta):
                    new_track.append(mido.MetaMessage('end_of_track', time=0))
                
                # Validiere den neuen Track
                note_count_after = sum(1 for msg in new_track if msg.type == 'note_on' and hasattr(msg, 'velocity') and msg.velocity > 0 
                                    and msg.note not in (sustain_keyswitch, staccato_keyswitch))
                ks_count = sum(1 for msg in new_track if msg.type == 'note_on' and hasattr(msg, 'note') 
                                and msg.note in (sustain_keyswitch, staccato_keyswitch))
                
                logger.info(f"Track {track_idx}: {note_count_before} originale Noten, {note_count_after} Noten nach Verarbeitung")
                logger.info(f"{ks_count} Keyswitch-Events hinzugefügt")
                
                # Sicherheitsprüfung: Stelle sicher, dass keine Noten verloren gegangen sind
                if note_count_after < note_count_before:
                    logger.error(f"VALIDIERUNGSFEHLER: {note_count_before - note_count_after} Noten in Track {track_idx} verloren!")
                    logger.error(f"Behalte originalen Track, um Datenverlust zu vermeiden")
                    continue
                
                # Ersetze den Track
                mid.tracks[track_idx] = new_track
                tracks_modified += 1
                logger.info(f"Track {track_idx} erfolgreich verarbeitet")
            except Exception as e:
                logger.error(f"Fehler bei der Verarbeitung von Track {track_idx}: {e}")
                logger.error(traceback.format_exc())
                continue
        
        # Speichere die aktualisierte MIDI-Datei
        try:
            if tracks_modified > 0:
                mid.save(midi_file)
                logger.info(f"✅ MIDI-Datei mit Keyswitches gespeichert: {midi_file} ({tracks_modified} Tracks modifiziert)")
            else:
                logger.warning("Keine Tracks wurden modifiziert, MIDI-Datei bleibt unverändert")
            
            return midi_file
        except Exception as e:
            logger.error(f"Fehler beim Speichern der MIDI-Datei: {e}")
            logger.error(traceback.format_exc())
            return midi_file
        
    except Exception as e:
        logger.error(f"Fehler beim Hinzufügen von Keyswitches: {e}")
        logger.error(f"Stack Trace: {traceback.format_exc()}")
        return midi_file
    finally:
        # Log-Level zurücksetzen
        if debug_mode:
            logger.setLevel(original_level)
            
def get_note_start_time(note):
    """
    Hilfsfunktion, um die Startzeit einer Note zu ermitteln.
    Berücksichtigt verschiedene mögliche Attributnamen.
    
    Args:
        note: Notenobjekt
        
    Returns:
        Startzeit der Note oder None, wenn nicht ermittelbar
    """
    # Versuche verschiedene Attributnamen für die Startzeit
    if hasattr(note, 'original_start_time'):
        return note.original_start_time
    elif hasattr(note, 'start_time'):
        return note.start_time
    elif hasattr(note, 'adjusted_start_time'):
        return note.adjusted_start_time
    else:
        return None

def get_note_duration(note):
    """
    Hilfsfunktion, um die Dauer einer Note zu ermitteln.
    Berücksichtigt verschiedene mögliche Attributnamen.
    
    Args:
        note: Notenobjekt
        
    Returns:
        Dauer der Note oder None, wenn nicht ermittelbar
    """
    # Versuche verschiedene Attributnamen für die Dauer
    if hasattr(note, 'original_duration'):
        return note.original_duration
    elif hasattr(note, 'duration'):
        return note.duration
    elif hasattr(note, 'adjusted_duration'):
        return note.adjusted_duration
    else:
        return None

if __name__ == "__main__":
    """Einfacher Test, wenn dieses Skript direkt ausgeführt wird."""
    import sys
    
    if len(sys.argv) > 1:
        midi_file = sys.argv[1]
        logger.info(f"Teste Keyswitch-Hinzufügung für: {midi_file}")
        add_keyswitches(midi_file)
    else:
        logger.info("Verwendung: python keyswitches.py <midi_file>")