"""
Verbesserte Version des Helfer-Moduls zur Nutzung von MuseScore für zuverlässige MIDI-Erzeugung
Mit korrekter Verarbeitung von Wiederholungen und Tempowechseln
"""

import subprocess
import os
import logging
import mido
import sys
import traceback
import tempfile
import math
from typing import Dict, List, Tuple, Any, Optional

# Importiere die neue Funktion für die MIDI-Struktur-Korrektur
from midi_utils import fix_musescore_midi_tracks, deduplicate_tempos

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def convert_xml_to_midi_with_musescore(xml_file: str, output_midi: Optional[str] = None) -> Optional[str]:
    """
    Verwendet MuseScore CLI, um eine MusicXML-Datei zu MIDI zu konvertieren.
    
    Args:
        xml_file: Pfad zur MusicXML-Datei
        output_midi: Optional, Pfad zur Ausgabe-MIDI-Datei
        
    Returns:
        Pfad zur erzeugten MIDI-Datei oder None bei Fehler
    """
    logger.info("===== MUSESCORE HELPER: KONVERTIERUNG STARTET =====")
    logger.info(f"XML-Datei: {xml_file}")
    logger.info(f"Ausgabe-MIDI (wenn angegeben): {output_midi}")
    
    # Prüfe, ob die XML-Datei existiert
    if not os.path.exists(xml_file):
        logger.error(f"XML-Datei existiert nicht: {xml_file}")
        return None
    
    if not output_midi:
        base_name = os.path.splitext(os.path.basename(xml_file))[0]
        output_dir = os.path.join(os.path.dirname(xml_file), "results")
        os.makedirs(output_dir, exist_ok=True)
        output_midi = os.path.join(output_dir, f"{base_name}.mid")
    
    logger.info(f"Finale Ausgabe-MIDI: {output_midi}")
    
    # Pfad zu MuseScore - passe dies an dein System an
    # Windows Standard-Installation:
    musescore_paths = [
        r"C:\Program Files\MuseScore 4\bin\MuseScore4.exe",
        r"C:\Program Files\MuseScore 3\bin\MuseScore3.exe",
        r"C:\Program Files (x86)\MuseScore 4\bin\MuseScore4.exe",
        r"C:\Program Files (x86)\MuseScore 3\bin\MuseScore3.exe"
    ]
    
    # Für macOS/Linux Benutzer kommentiere die Windows-Pfade aus und nutze diese:
    # musescore_paths = [
    #     "/Applications/MuseScore 3.app/Contents/MacOS/mscore",
    #     "/Applications/MuseScore 4.app/Contents/MacOS/mscore",
    #     "/usr/bin/mscore",
    #     "/usr/bin/musescore"
    # ]
    
    # Finde den korrekten MuseScore-Pfad
    musescore_path = None
    logger.info("Suche nach installierten MuseScore-Versionen...")
    
    for path in musescore_paths:
        logger.info(f"Prüfe Pfad: {path}")
        if os.path.exists(path):
            musescore_path = path
            logger.info(f"MuseScore gefunden: {path}")
            break
        else:
            logger.info(f"Nicht gefunden: {path}")
    
    if not musescore_path:
        logger.error("!!! MuseScore konnte nicht gefunden werden !!!")
        logger.error("Bitte installiere MuseScore oder gib den Pfad manuell an.")
        logger.error("Geprüfte Pfade: " + ", ".join(musescore_paths))
        return None
    
    # Führe MuseScore aus, um die Konvertierung durchzuführen
    try:
        logger.info(f"Starte MuseScore-Konvertierung mit: {musescore_path}")
        
        # KRITISCHER FIX: Entferne die Anführungszeichen um die Pfade
        # Vorher problematisch: cmd = [musescore_path, "-o", f'"{output_midi}"', f'"{xml_file}"']
        # Korrekt:
        cmd = [musescore_path, "-o", output_midi, xml_file]
        
        logger.info(f"Befehl: {' '.join(str(arg) for arg in cmd)}")
        
        # Führe den Befehl aus
        # Hinweis: Bei Pfaden mit Leerzeichen muss shell=False sein (default)
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        
        # Protokolliere Ausgabe und Fehler
        logger.debug(f"Ausgabe: {result.stdout.decode('utf-8', errors='replace')}")
        logger.debug(f"Fehler: {result.stderr.decode('utf-8', errors='replace')}")
        
        # Prüfe, ob die Datei erstellt wurde
        if os.path.exists(output_midi):
            file_size = os.path.getsize(output_midi)
            logger.info(f"MIDI-Datei erfolgreich erstellt: {output_midi} (Größe: {file_size} Bytes)")
            
            # Korrigiere die MIDI-Track-Struktur, sodass Track 0 nur Meta-Events enthält
            fix_musescore_midi_tracks(output_midi)
            
            return output_midi
        else:
            logger.error(f"!!! MIDI-Datei wurde nicht erstellt: {output_midi}")
            logger.error("MuseScore wurde ohne Fehler ausgeführt, aber keine Datei wurde erzeugt.")
            return None
    except subprocess.CalledProcessError as e:
        logger.error(f"!!! Fehler bei der MuseScore-Ausführung: {e}")
        logger.error(f"Ausgabe: {e.stdout.decode('utf-8', errors='replace')}")
        logger.error(f"Fehler: {e.stderr.decode('utf-8', errors='replace')}")
        return None
    except Exception as e:
        logger.error(f"!!! Unerwarteter Fehler: {e}")
        logger.error(f"Stack Trace: {traceback.format_exc()}")
        return None

def add_cc1_to_musescore_midi(midi_file: str, 
                              voice_dynamic_curves: Dict[int, List[Tuple[float, int]]]) -> str:
    """
    Fügt CC1-Kurven zu einer von MuseScore erzeugten MIDI-Datei hinzu.
    
    Args:
        midi_file: Pfad zur MIDI-Datei
        voice_dynamic_curves: Dictionary mit Stimmenindex als Schlüssel und Liste von 
                             (Zeit in Beats, CC1-Wert) Tupeln als Werte
        
    Returns:
        Pfad zur aktualisierten MIDI-Datei
    """
    logger.info("===== MUSESCORE HELPER: CC1-HINZUFÜGEN STARTET =====")
    logger.info(f"MIDI-Datei: {midi_file}")
    logger.info(f"Anzahl der Dynamikkurven: {len(voice_dynamic_curves)}")
    
    # Prüfe, ob die MIDI-Datei existiert
    if not os.path.exists(midi_file):
        logger.error(f"!!! MIDI-Datei existiert nicht: {midi_file}")
        return midi_file
    
    # WICHTIG: Korrigiere zuerst die MIDI-Track-Struktur
    # Dadurch wird sichergestellt, dass Track 0 nur Meta-Events enthält,
    # und die Instrument-Events in die richtigen Tracks verschoben werden
    try:
        fix_musescore_midi_tracks(midi_file)
    except Exception as e:
        logger.error(f"!!! Fehler bei der MIDI-Struktur-Korrektur: {e}")
        logger.error(f"Stack Trace: {traceback.format_exc()}")
    
    # Lade die MIDI-Datei (nach der Struktur-Korrektur)
    try:
        logger.info(f"Lade MIDI-Datei: {midi_file}")
        mid = mido.MidiFile(midi_file)
        logger.info(f"MIDI-Datei geladen: Typ {mid.type}, {len(mid.tracks)} Tracks, {mid.ticks_per_beat} Ticks/Beat")
    except Exception as e:
        logger.error(f"!!! Fehler beim Laden der MIDI-Datei: {e}")
        logger.error(f"Stack Trace: {traceback.format_exc()}")
        return midi_file
    
    # Rest der Funktion bleibt unverändert...
    # ... (Der Rest der Funktion bleibt gleich)
    
    # Zeige Tracks und ihre Eigenschaften
    logger.info("Track-Analyse:")
    for i, track in enumerate(mid.tracks):
        note_count = sum(1 for msg in track if not msg.is_meta and msg.type == 'note_on')
        cc_count = sum(1 for msg in track if not msg.is_meta and msg.type == 'control_change')
        meta_count = sum(1 for msg in track if msg.is_meta)
        
        track_name = "Unbenannt"
        for msg in track:
            if msg.is_meta and msg.type == 'track_name':
                track_name = msg.name
                break
                
        logger.info(f"Track {i}: '{track_name}' - {note_count} Noten, {cc_count} CC-Events, {meta_count} Meta-Events")
    
    # Finde alle Tracks mit Noten und erstelle ein Mapping
    note_tracks = {}
    for i, track in enumerate(mid.tracks):
        # Zähle Noten-Events
        note_events = sum(1 for msg in track if not msg.is_meta and msg.type in ('note_on', 'note_off'))
        
        if note_events > 0:
            # Überspringe Track 0 bei Typ 1 MIDI, der enthält typischerweise nur Metadaten
            if i == 0 and mid.type == 1 and not any(msg.type in ('note_on', 'note_off') for msg in track):
                logger.info(f"Überspringe Track 0 (wahrscheinlich Metadaten)")
                continue
                
            # Bei MuseScore-MIDI entspricht typischerweise der Track-Index dem Part-Index
            # Wir müssen 1 abziehen, falls Track 0 nur Metadaten enthält
            part_idx = i if mid.type == 0 else i - 1
            note_tracks[i] = part_idx
            logger.info(f"Track {i} enthält {note_events} Noten-Events -> Part-Index {part_idx}")
    
    logger.info(f"Gefundene Noten-Tracks: {note_tracks}")
    
    # Für jeden Track mit Noten: Füge CC1-Events hinzu, wenn vorhanden
    tracks_modified = 0
    
    for track_idx, part_idx in note_tracks.items():
        if part_idx in voice_dynamic_curves:
            dynamic_curve = voice_dynamic_curves[part_idx]
            logger.info(f"Füge {len(dynamic_curve)} CC1-Events zu Track {track_idx} (Part {part_idx}) hinzu")
            
            # Extrahiere bestehende Events mit absoluten Zeiten
            track = mid.tracks[track_idx]
            abs_events = []
            current_time = 0
            
            for msg in track:
                current_time += msg.time
                abs_events.append((current_time, msg.copy(time=0)))
            
            # Erstelle CC1-Events mit absoluten Zeiten
            cc1_events = []
            prev_val = None
            
            for time_in_beats, val in dynamic_curve:
                # Überspringe redundante aufeinanderfolgende Werte
                if prev_val == val:
                    continue
                
                # Konvertiere Zeit in Beats zu Ticks
                tick_time = int(round(time_in_beats * mid.ticks_per_beat))
                
                # Erstelle CC1-Event (verwende Kanal 0)
                cc1_events.append((tick_time, mido.Message('control_change', channel=0, control=1, value=val, time=0)))
                prev_val = val
            
            logger.info(f"Erstellt: {len(cc1_events)} CC1-Events für Track {track_idx}")
            
            # Kombiniere alle Events und sortiere nach Zeit
            all_events = abs_events + cc1_events
            all_events.sort(key=lambda x: x[0])
            
            # Konvertiere zurück zu Delta-Zeiten
            new_track = mido.MidiTrack()
            prev_time = 0
            
            for abs_time, msg in all_events:
                delta = abs_time - prev_time
                new_track.append(msg.copy(time=delta))
                prev_time = abs_time
            
            # Stelle sicher, dass End-of-Track am Ende steht
            if not any(msg.type == 'end_of_track' for msg in new_track if msg.is_meta):
                new_track.append(mido.MetaMessage('end_of_track', time=0))
            
            # Ersetze den Track
            mid.tracks[track_idx] = new_track
            tracks_modified += 1
        else:
            logger.warning(f"Keine CC1-Kurve für Part {part_idx} (Track {track_idx}) gefunden")
    
    logger.info(f"{tracks_modified} Tracks wurden mit CC1-Kurven aktualisiert")
    
    # Speichere die aktualisierte MIDI-Datei
    try:
        mid.save(midi_file)
        logger.info(f"MIDI-Datei mit CC1-Kurven gespeichert: {midi_file}")
    except Exception as e:
        logger.error(f"!!! Fehler beim Speichern der MIDI-Datei: {e}")
        logger.error(f"Stack Trace: {traceback.format_exc()}")
    
    return midi_file

def add_tempo_changes_to_midi(midi_file, tempo_changes):
    """
    Fügt Tempowechsel zu einer MIDI-Datei hinzu.
    
    Args:
        midi_file: Pfad zur MIDI-Datei
        tempo_changes: Liste von (offset, bpm) Tupeln
    """
    logger.info("===== TEMPO-ÄNDERUNGEN HINZUFÜGEN =====")
    logger.info(f"MIDI-Datei: {midi_file}")
    logger.info(f"Tempowechsel ({len(tempo_changes)}): {tempo_changes}")
    
    try:
        # Lade MIDI-Datei
        mid = mido.MidiFile(midi_file)
        ticks_per_beat = mid.ticks_per_beat
        logger.info(f"MIDI-Datei geladen: Typ {mid.type}, ticks_per_beat: {ticks_per_beat}")
        
        # Konvertiere BPM zu MIDI Tempo (Mikrosekunden pro Viertelnote)
        def bpm_to_tempo(bpm):
            return math.floor(60000000 / bpm)
        
        # Erstelle einen Tempo-Track (falls nicht vorhanden)
        if mid.type == 0:
            # Für Typ 0 MIDI: Konvertiere zu Typ 1
            tracks = []
            tempo_track = mido.MidiTrack()
            
            # Verschiebe alle Meta-Events in den neuen Tempo-Track
            note_track = mido.MidiTrack()
            current_time = 0
            
            for msg in mid.tracks[0]:
                if msg.is_meta:
                    if msg.type != 'end_of_track':  # Ignoriere end_of_track
                        tempo_track.append(msg.copy(time=0))
                else:
                    note_track.append(msg.copy())
            
            # Füge End-of-Track hinzu
            tempo_track.append(mido.MetaMessage('end_of_track', time=0))
            
            tracks.append(tempo_track)
            tracks.append(note_track)
            
            # Erstelle neue MIDI-Datei
            new_mid = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat)
            new_mid.tracks = tracks
            mid = new_mid
            logger.info("MIDI-Typ von 0 auf 1 konvertiert")
        
        # Entferne alle existierenden Tempo-Events aus dem ersten Track
        tempo_track = mid.tracks[0]
        new_tempo_track = mido.MidiTrack()
        
        for msg in tempo_track:
            if not (msg.is_meta and msg.type == 'set_tempo'):
                new_tempo_track.append(msg)
        
        # Behalte alle non-tempo und non-end_of_track Events
        mid.tracks[0] = mido.MidiTrack([msg for msg in new_tempo_track 
                                      if not (msg.is_meta and msg.type == 'end_of_track')])
        
        # Füge Tempo-Events hinzu
        abs_tempo_events = []
        
        for offset, bpm in tempo_changes:
            # Konvertiere Offset in Beats zu Ticks
            tick_offset = int(round(offset * ticks_per_beat))
            tempo_value = bpm_to_tempo(bpm)
            logger.info(f"Tempowechsel: {bpm} BPM bei Tick {tick_offset} (Offset {offset} Beats)")
            abs_tempo_events.append((tick_offset, mido.MetaMessage('set_tempo', tempo=tempo_value, time=0)))
        
        # Kombiniere mit existierenden Events im Tempo-Track
        tempo_track = mid.tracks[0]
        abs_track_events = []
        current_time = 0
        
        for msg in tempo_track:
            current_time += msg.time
            abs_track_events.append((current_time, msg.copy(time=0)))
        
        # Kombiniere und sortiere nach Zeit
        all_events = abs_track_events + abs_tempo_events
        all_events.sort(key=lambda x: x[0])
        
        # Konvertiere zurück zu Delta-Zeiten
        new_track = mido.MidiTrack()
        prev_time = 0
        
        for abs_time, msg in all_events:
            delta = abs_time - prev_time
            new_track.append(msg.copy(time=delta))
            prev_time = abs_time
        
        # Stelle sicher, dass End-of-Track am Ende steht
        new_track.append(mido.MetaMessage('end_of_track', time=0))
        
        # Ersetze den Tempo-Track
        mid.tracks[0] = new_track
        
        # Speichere die aktualisierte MIDI-Datei
        mid.save(midi_file)
        logger.info(f"✅ MIDI-Datei mit Tempowechseln gespeichert: {midi_file}")
        
    except Exception as e:
        logger.error(f"!!! Fehler beim Hinzufügen der Tempos: {e}")
        logger.error(f"Stack Trace: {traceback.format_exc()}")

def convert_xml_to_midi_with_expanded_repeats(xml_file, output_midi=None):
    """
    Verbesserte Konvertierung von XML zu MIDI mit korrekt expandierten Wiederholungen
    und Tempowechseln. Nutzt music21 für die Wiederholungsexpansion und MuseScore
    für die hochwertige MIDI-Generierung.
    
    Args:
        xml_file: Pfad zur XML-Datei
        output_midi: Optionaler Pfad zur Ausgabe-MIDI-Datei
        
    Returns:
        Pfad zur erzeugten MIDI-Datei oder None bei Fehler
    """
    import music21 as m21
    
    logger.info("===== VERBESSERTER WORKFLOW: XML -> MIDI MIT WIEDERHOLUNGEN =====")
    logger.info(f"Verarbeite: {xml_file}")
    
    # Bestimme Ausgabepfad
    if not output_midi:
        base_name = os.path.splitext(os.path.basename(xml_file))[0]
        output_dir = os.path.join(os.path.dirname(xml_file), "results")
        os.makedirs(output_dir, exist_ok=True)
        output_midi = os.path.join(output_dir, f"{base_name}.mid")
    
    try:
        # SCHRITT 1: Lade Score mit music21
        logger.info("Lade XML mit music21...")
        score = m21.converter.parse(xml_file)
        
        # SCHRITT 2: Expandiere Wiederholungen
        logger.info("Expandiere Wiederholungen...")
        try:
            # Entferne RepeatBrackets
            if hasattr(m21.spanner, "RepeatBracket"):
                score.removeByClass(m21.spanner.RepeatBracket)
            
            # Expandiere Wiederholungen
            if hasattr(score, "expandRepeats"):
                # Wichtig: Speichere das Ergebnis der expandRepeats-Methode
                # Die Funktion gibt einen neuen Score zurück!
                expanded_score = score.expandRepeats()
                if expanded_score is not None:
                    score = expanded_score
                    logger.info("✅ Wiederholungen erfolgreich expandiert!")
                else:
                    logger.warning("expandRepeats() gab None zurück, verwende originalen Score")
            else:
                logger.warning("expandRepeats() ist nicht verfügbar.")
        except Exception as e:
            logger.error(f"Fehler beim Expandieren der Wiederholungen: {e}")
            logger.error(f"Stack Trace: {traceback.format_exc()}")
        
        # SCHRITT 3: Speichere den expandierten Score als temporäre XML-Datei
        with tempfile.NamedTemporaryFile(suffix='.xml', delete=False) as temp:
            temp_xml = temp.name
        
        logger.info(f"Speichere expandierten Score als temporäre XML-Datei: {temp_xml}")
        score.write('musicxml', fp=temp_xml)
        
        # SCHRITT 4: Konvertiere die temporäre XML mit MuseScore
        logger.info("Konvertiere expandierte XML zu MIDI mit MuseScore...")
        midi_file = convert_xml_to_midi_with_musescore(temp_xml, output_midi)
        
        # SCHRITT 5: Lösche die temporäre Datei
        try:
            os.remove(temp_xml)
            logger.info(f"Temporäre XML-Datei gelöscht: {temp_xml}")
        except Exception as e:
            logger.warning(f"Konnte temporäre Datei nicht löschen: {e}")
        
        # SCHRITT 6: Extrahiere Tempomarkierungen und füge sie zur MIDI-Datei hinzu
        logger.info("Extrahiere Tempomarkierungen aus expandiertem Score...")
        tempo_changes = []
        
        # Methode 1: metronomeMarkBoundaries
        try:
            boundaries = score.metronomeMarkBoundaries()
            for (start_time, element, end_time) in boundaries:
                if element is not None and hasattr(element, 'number'):
                    bpm = element.number
                    logger.info(f"Tempo aus Boundaries: {bpm} BPM bei Offset {start_time}")
                    tempo_changes.append((start_time, bpm))
        except Exception as e:
            logger.warning(f"Fehler bei metronomeMarkBoundaries: {e}")
        
        # Methode 2: Direkte Suche nach MetronomeMarks
        try:
            # Verwende .flatten() statt .flat für neuere music21-Versionen
            for mm in score.flatten().getElementsByClass('MetronomeMark'):
                if hasattr(mm, 'number'):
                    bpm = mm.number
                    offset = mm.offset
                    try:
                        offset = mm.getOffsetBySite(score)
                    except:
                        pass
                    logger.info(f"Tempo aus MetronomeMark: {bpm} BPM bei Offset {offset}")
                    tempo_changes.append((offset, bpm))
        except Exception as e:
            logger.warning(f"Fehler bei der MetronomeMark-Suche: {e}")
        
        # Methode 3: Aus XML direkt parsen
        try:
            from xml_parser import parse_tempos_from_musicxml
            xml_tempos = parse_tempos_from_musicxml(xml_file)
            
            if xml_tempos:
                for offset, bpm in xml_tempos:
                    logger.info(f"Tempo aus XML: {bpm} BPM bei Offset {offset}")
                    tempo_changes.append((offset, bpm))
        except Exception as e:
            logger.warning(f"Fehler beim XML-Tempo-Parsing: {e}")
        
        # Dedupliziere und sortiere Tempos
        if tempo_changes:
            tempo_changes = deduplicate_tempos(tempo_changes)
            tempo_changes.sort(key=lambda x: x[0])
            
            # Stelle sicher, dass es einen Tempowechsel am Anfang gibt
            if not tempo_changes or tempo_changes[0][0] > 0:
                tempo_changes.insert(0, (0, 120))
            
            logger.info("Finale Tempowechsel:")
            for offset, bpm in tempo_changes:
                logger.info(f"- {bpm} BPM bei Offset {offset}")
            
            # Füge Tempowechsel zur MIDI-Datei hinzu
            if midi_file and os.path.exists(midi_file):
                logger.info("Füge Tempowechsel zur MIDI-Datei hinzu...")
                add_tempo_changes_to_midi(midi_file, tempo_changes)
                logger.info("✅ Tempowechsel erfolgreich hinzugefügt")
        else:
            logger.warning("Keine Tempowechsel gefunden!")
        
        return midi_file
        
    except Exception as e:
        logger.error(f"Fehler im verbesserten Workflow: {e}")
        logger.error(f"Stack Trace: {traceback.format_exc()}")
        return None

if __name__ == "__main__":
    # Einfacher Test, wenn dieses Skript direkt ausgeführt wird
    if len(sys.argv) > 1:
        xml_file = sys.argv[1]
        logger.info(f"Teste Konvertierung von: {xml_file}")
        
        # Teste die verbesserte Konvertierung
        logger.info("=== TESTE VERBESSERTEN WORKFLOW ===")
        midi_file = convert_xml_to_midi_with_expanded_repeats(xml_file)
        
        if midi_file:
            logger.info(f"Verbesserte Konvertierung erfolgreich: {midi_file}")
            # Testweise eine Dummy-CC1-Kurve hinzufügen
            test_curves = {0: [(0, 64), (1, 80), (2, 100), (3, 64)]}
            add_cc1_to_musescore_midi(midi_file, test_curves)