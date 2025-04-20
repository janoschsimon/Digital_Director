"""
Worker-Modul für die Hintergrundverarbeitung
-------------------------------------------
Enthält die Klasse für die Hintergrundverarbeitung der Musikdateien.
Verbesserte Version mit robusterer Fehlerbehandlung und Dateipfadüberprüfung.

Verarbeitungsreihenfolge:
1. XML → MIDI mit expandierten Wiederholungen
2. Digital Dirigent für Timing-Anpassungen (wenn aktiviert)
3. CC1-Kurven für Dynamik (nach dem Dirigenten, wenn dieser aktiviert ist)
4. Keyswitches für Artikulation (wenn aktiviert)
"""

import os
import sys
import logging
import traceback
import gc
import subprocess
import webbrowser
import mido
import music21 as m21
import numpy as np
import math
from PyQt6.QtCore import QThread, pyqtSignal
from conductor.note_manipulator import NoteLevelInterpreter

class AnalysisWorker(QThread):
    """Worker-Thread für die Hintergrundverarbeitung der Musikdateien."""
    
    progress_signal = pyqtSignal(str)
    
    def __init__(self, files, do_conversion=True, do_conductor=False, 
                 do_cc1=True, do_keyswitches=True,
                 expressivity=0.5, style="Ausgewogen", tempo_change=0.10):
        super().__init__()
        self.files = files
        self.do_conversion = do_conversion
        self.do_conductor = do_conductor
        self.do_cc1 = do_cc1
        # Humanisierung komplett entfernt – der Digital Dirigent übernimmt diese Aufgabe.
        self.do_keyswitches = do_keyswitches
        self.expressivity = expressivity
        self.style = style
        self.tempo_change = tempo_change

    def find_musescore_path(self):
        """
        Sucht nach MuseScore auf dem System.
        Diese Methode ist identisch mit der in gui_main_window.py,
        um Konsistenz zu gewährleisten.
        
        Returns:
            String mit dem Pfad zu MuseScore oder None, wenn nicht gefunden
        """
        musescore_path = None
        
        # Betriebssystemspezifische Pfade
        if sys.platform.startswith('win'):
            # Windows-Pfade für MuseScore
            musescore_paths = [
                r"C:\Program Files\MuseScore 4\bin\MuseScore4.exe",
                r"C:\Program Files\MuseScore 3\bin\MuseScore3.exe",
                r"C:\Program Files (x86)\MuseScore 4\bin\MuseScore4.exe",
                r"C:\Program Files (x86)\MuseScore 3\bin\MuseScore3.exe"
            ]
        elif sys.platform.startswith('darwin'):
            # MacOS-Pfade für MuseScore
            musescore_paths = [
                "/Applications/MuseScore 4.app/Contents/MacOS/mscore",
                "/Applications/MuseScore 3.app/Contents/MacOS/mscore",
                "/Applications/MuseScore.app/Contents/MacOS/mscore"
            ]
        else:
            # Linux-Pfade
            musescore_paths = [
                "/usr/bin/mscore",
                "/usr/bin/musescore",
                "/usr/local/bin/mscore",
                "/usr/local/bin/musescore"
            ]
        
        for path in musescore_paths:
            if os.path.exists(path):
                musescore_path = path
                break
                
        return musescore_path

    def convert_xml_to_midi(self, xml_file):
        """
        Konvertiert eine XML-Datei zu MIDI mit korrekten Wiederholungen, Tempomarkierungen 
        und optional CC1-Kurven (nur wenn der Digital Dirigent nicht aktiv ist).
        
        Verarbeitungsschritt 1: XML → MIDI mit expandierten Wiederholungen
        
        Optimierter Workflow: 
          1. Wiederholungsexpansion mit music21 
          2. XML-zu-MIDI Konvertierung mit MuseScore (Fallback: music21)
          3. Instrumenterkennung
          4. (Falls kein Digital Dirigent aktiv ist:) CC1-Dynamikkurven erzeugen
          5. Track-Längen korrigieren und finale MIDI-Analyse
          
        Args:
            xml_file: Pfad zur XML-Datei
            
        Returns:
            Pfad zur erzeugten MIDI-Datei oder None bei Fehler
        """
        try:
            # Prüfe, ob die Datei existiert
            if not os.path.exists(xml_file):
                self.progress_signal.emit(f"❌ XML-Datei nicht gefunden: {xml_file}")
                return None
                
            self.progress_signal.emit(f"🔄 Lade {os.path.basename(xml_file)}...")
            
            # Ausgabepfade bestimmen
            base_name = os.path.splitext(os.path.basename(xml_file))[0]
            output_folder = os.path.join(os.path.dirname(xml_file), "results")
            os.makedirs(output_folder, exist_ok=True)
            
            # Pfade für expandierte Dateien
            expanded_xml = os.path.join(output_folder, f"{base_name}_expanded.xml")
            midi_file_path = os.path.join(output_folder, f"{base_name}.mid")
            
            self.progress_signal.emit(f"🔄 Ausgabe-MIDI wird erstellt unter: {midi_file_path}")
            
            # SCHRITT 1: Expandiere Wiederholungen mit music21
            self.progress_signal.emit("🔄 Expandiere Wiederholungen mit music21...")
            try:
                # Memory-Limit erhöhen für music21
                from music21.environment import Environment
                us = Environment()
                us['autoDownload'] = 'allow'
                us['lilypondPath'] = None

                # Verbesserter Parsing-Mechanismus mit Fehlerbehandlung
                try:
                    score = m21.converter.parse(xml_file, format='musicxml', forceSource=True)
                    self.progress_signal.emit("✅ XML erfolgreich geparst!")
                except Exception as parsing_error:
                    self.progress_signal.emit(f"⚠️ Fehler beim Parsen der XML-Datei: {str(parsing_error)}")
                    # Fallback: Sichere Konvertierung ohne Expansion verwenden
                    midi_file_path = self.direct_musescore_conversion(xml_file, midi_file_path)
                    if midi_file_path and os.path.exists(midi_file_path):
                        return midi_file_path
                    else:
                        return None
                
                # Analyse vor Expansion
                parts = score.getElementsByClass(m21.stream.Part)
                original_measures = 0
                original_notes = 0
                for part in parts:
                    measures = part.getElementsByClass(m21.stream.Measure)
                    if len(measures) > original_measures:
                        original_measures = len(measures)
                    original_notes += len(part.flat.getElementsByClass('Note'))
                self.progress_signal.emit(f"📊 Original Score: {len(parts)} Stimmen, ca. {original_measures} Takte, {original_notes} Noten")
                
                # Wiederholungszeichen und RepeatBrackets entfernen
                repeats = score.flat.getElementsByClass('Repeat')
                self.progress_signal.emit(f"🔍 Gefundene Wiederholungszeichen: {len(repeats)}")
                
                # Vorsichtiger Umgang mit RepeatBracket-Entfernung
                try:
                    if hasattr(m21.spanner, "RepeatBracket"):
                        brackets = list(score.flat.getElementsByClass(m21.spanner.RepeatBracket))
                        for rb in brackets:
                            try:
                                rb.removeLocationBySite(score.flat)
                            except:
                                # Einzelne Bracket-Fehler ignorieren
                                pass
                        self.progress_signal.emit("✅ RepeatBrackets entfernt")
                except Exception as bracket_error:
                    self.progress_signal.emit(f"⚠️ Fehler beim Entfernen der RepeatBrackets: {str(bracket_error)}")
                
                # Expandieren mit zusätzlicher Fehlerbehandlung
                self.progress_signal.emit("🔄 Expandiere Wiederholungen...")
                expanded_score = None
                try:
                    expanded_score = score.expandRepeats()
                except MemoryError:
                    self.progress_signal.emit("⚠️ Nicht genügend Speicher für Wiederholungsexpansion. Verwende Original-Score.")
                    expanded_score = score
                except Exception as expand_error:
                    self.progress_signal.emit(f"⚠️ Fehler bei expandRepeats(): {str(expand_error)}")
                    expanded_score = score  # Verwende den nicht-expandierten Score als Fallback
                
                if expanded_score is None:
                    self.progress_signal.emit("⚠️ expandRepeats() gab None zurück, verwende originalen Score")
                    expanded_score = score
                else:
                    try:
                        # Überprüfe, ob die Expansion erfolgreich war
                        expanded_parts = expanded_score.getElementsByClass(m21.stream.Part)
                        expanded_measures = 0
                        expanded_notes = 0
                        for part in expanded_parts:
                            measures = part.getElementsByClass(m21.stream.Measure)
                            if len(measures) > expanded_measures:
                                expanded_measures = len(measures)
                            expanded_notes += len(part.flat.getElementsByClass('Note'))
                        
                        if expanded_notes > 0:
                            expansion_ratio = expanded_measures / max(1, original_measures)
                            notes_ratio = expanded_notes / max(1, original_notes)
                            self.progress_signal.emit(f"✅ Expandierter Score: {len(expanded_parts)} Stimmen, ca. {expanded_measures} Takte, {expanded_notes} Noten")
                            self.progress_signal.emit(f"📊 Expansion Ratio: {expansion_ratio:.2f}x, Noten-Expansion: {notes_ratio:.2f}x")
                            if expansion_ratio <= 1.01:
                                self.progress_signal.emit("⚠️ Keine signifikante Expansion erkannt!")
                        else:
                            self.progress_signal.emit("⚠️ Keine Noten im expandierten Score gefunden, verwende Original")
                            expanded_score = score
                    except Exception as counting_error:
                        self.progress_signal.emit(f"⚠️ Fehler beim Analysieren des expandierten Scores: {str(counting_error)}")
                
                # Sicherheitsprüfung auf leere Partitur
                if not expanded_score or len(expanded_score.flat.notes) == 0:
                    self.progress_signal.emit("⚠️ Expandierter Score ist leer oder ungültig. Versuche direkte Konvertierung...")
                    return self.direct_musescore_conversion(xml_file, midi_file_path)
                
                # Expandierte XML speichern
                try:
                    self.progress_signal.emit(f"🔄 Speichere expandierte MusicXML: {expanded_xml}")
                    expanded_score.write('musicxml', fp=expanded_xml)
                    self.progress_signal.emit("✅ Expandierte MusicXML gespeichert")
                except Exception as write_error:
                    self.progress_signal.emit(f"⚠️ Fehler beim Speichern der expandierten XML: {str(write_error)}")
                    # Versuche es mit dem Original, wenn das Speichern fehlschlägt
                    return self.direct_musescore_conversion(xml_file, midi_file_path)
                
                # SCHRITT 2: Tempomarkierungen analysieren (nur für Log-Ausgabe)
                self.progress_signal.emit("🔄 Analysiere Tempomarkierungen...")
                tempo_marks = expanded_score.flat.getElementsByClass('MetronomeMark')
                if tempo_marks:
                    self.progress_signal.emit(f"✅ {len(tempo_marks)} Tempomarkierungen gefunden")
                    for i, mm in enumerate(tempo_marks[:3]):  # Zeige nur die ersten 3 Tempomarkierungen
                        if hasattr(mm, 'number'):
                            try:
                                offset = mm.offset
                                if hasattr(mm, 'getOffsetBySite'):
                                    try:
                                        offset = mm.getOffsetBySite(expanded_score.flat)
                                    except:
                                        pass
                                self.progress_signal.emit(f"  • Tempo: {mm.number} BPM bei Offset {offset}")
                            except:
                                self.progress_signal.emit(f"  • Tempo: {mm.number} BPM (Offset unbekannt)")
                    if len(tempo_marks) > 3:
                        self.progress_signal.emit(f"  • ... weitere {len(tempo_marks) - 3} Tempomarkierungen")
                else:
                    self.progress_signal.emit("⚠️ Keine expliziten Tempomarkierungen im Score")
                
                # SCHRITT 3: MIDI-Erzeugung mittels MuseScore (Fallback: music21)
                self.progress_signal.emit("🔄 Erzeuge MIDI mit MuseScore aus expandierter XML...")
                
                # Suche nach MuseScore
                musescore_path = self.find_musescore_path()
                
                if not musescore_path:
                    self.progress_signal.emit("⚠️ MuseScore nicht gefunden, verwende music21 für MIDI-Konvertierung")
                    try:
                        expanded_score.write('midi', fp=midi_file_path)
                        if os.path.exists(midi_file_path):
                            file_size = os.path.getsize(midi_file_path)
                            self.progress_signal.emit(f"✅ MIDI-Datei mit music21 erstellt: {midi_file_path} ({file_size} Bytes)")
                            return midi_file_path
                        else:
                            self.progress_signal.emit("❌ Konnte keine MIDI-Datei mit music21 erzeugen")
                            return None
                    except Exception as m21_error:
                        self.progress_signal.emit(f"❌ Fehler bei music21 MIDI-Konvertierung: {str(m21_error)}")
                        return None
                        
                self.progress_signal.emit(f"✅ MuseScore gefunden: {musescore_path}")
                
                try:
                    if not os.path.exists(expanded_xml):
                        self.progress_signal.emit(f"⚠️ Expandierte XML-Datei nicht gefunden: {expanded_xml}")
                        # Versuche direkte Konvertierung von Original-XML
                        return self.direct_musescore_conversion(xml_file, midi_file_path)
                    
                    cmd = [musescore_path, "-o", os.path.abspath(midi_file_path), os.path.abspath(expanded_xml)]
                    self.progress_signal.emit(f"🔄 Führe MuseScore-Konvertierung aus...")
                    
                    try:
                        process = subprocess.run(
                            cmd, 
                            stdout=subprocess.PIPE, 
                            stderr=subprocess.PIPE, 
                            timeout=60,
                            text=True,
                            encoding='utf-8',
                            errors='replace'
                        )
                        
                        # --- HIER IST DIE HAUPTÄNDERUNG ---
                        # Prüfe ZUERST, ob die Datei erstellt wurde, UNABHÄNGIG vom Rückgabecode
                        if os.path.exists(midi_file_path) and os.path.getsize(midi_file_path) > 100:
                            # Datei wurde erstellt, auch wenn MuseScore einen Fehler zurückgab
                            file_size = os.path.getsize(midi_file_path)
                            if process.returncode != 0:
                                self.progress_signal.emit(f"⚠️ MuseScore-Prozess endete mit Code {process.returncode}, aber die Datei wurde trotzdem erstellt")
                            self.progress_signal.emit(f"✅ MIDI-Datei mit MuseScore erstellt: {midi_file_path} ({file_size} Bytes)")
                        else:
                            # Keine Datei erstellt
                            if process.returncode != 0:
                                self.progress_signal.emit(f"⚠️ MuseScore-Prozess endete mit Code {process.returncode}")
                                if process.stdout:
                                    self.progress_signal.emit(f"MuseScore Ausgabe: {process.stdout[:200]}...")
                                if process.stderr:
                                    self.progress_signal.emit(f"MuseScore Fehler: {process.stderr[:200]}...")
                            
                            self.progress_signal.emit("⚠️ MuseScore-Prozess abgeschlossen, aber keine MIDI-Datei erzeugt")
                            # Fallback: Direkte Konvertierung
                            return self.direct_musescore_conversion(xml_file, midi_file_path)
                        # --- ENDE DER HAUPTÄNDERUNG ---
                        
                    except subprocess.TimeoutExpired:
                        self.progress_signal.emit("⚠️ MuseScore-Prozess Timeout nach 60 Sekunden")
                        # Versuche music21 als Fallback
                        try:
                            expanded_score.write('midi', fp=midi_file_path)
                        except Exception as timeout_fallback_error:
                            self.progress_signal.emit(f"❌ Auch Fallback-Konvertierung fehlgeschlagen: {str(timeout_fallback_error)}")
                            # Als letzte Möglichkeit: Direkte Konvertierung
                            return self.direct_musescore_conversion(xml_file, midi_file_path)
                        
                        if os.path.exists(midi_file_path):
                            file_size = os.path.getsize(midi_file_path)
                            self.progress_signal.emit(f"✅ MIDI-Datei mit music21 erstellt: {midi_file_path} ({file_size} Bytes)")
                        else:
                            self.progress_signal.emit("❌ Konnte keine MIDI-Datei erzeugen")
                            return None
                
                except Exception as e:
                    self.progress_signal.emit(f"⚠️ Fehler bei MuseScore-Aufruf: {str(e)}")
                    self.progress_signal.emit("🔄 Fallback: Erzeuge MIDI mit music21...")
                    try:
                        expanded_score.write('midi', fp=midi_file_path)
                    except Exception as fallback_error:
                        self.progress_signal.emit(f"❌ Auch Fallback-Konvertierung fehlgeschlagen: {str(fallback_error)}")
                        # Als letzte Möglichkeit: Direkte Konvertierung
                        return self.direct_musescore_conversion(xml_file, midi_file_path)
                    
                    if os.path.exists(midi_file_path):
                        file_size = os.path.getsize(midi_file_path)
                        self.progress_signal.emit(f"✅ MIDI-Datei mit music21 erstellt: {midi_file_path} ({file_size} Bytes)")
                    else:
                        self.progress_signal.emit("❌ Konnte keine MIDI-Datei erzeugen")
                        return None
                
                # SCHRITT 4: Automatische Instrumenterkennung (auf expandiertem Score)
                self.progress_signal.emit("🔄 Erkenne Instrumente automatisch...")
                try:
                    from instrument_mapper import InstrumentMapper
                    instrument_mapper = InstrumentMapper()
                    instrument_mapping = instrument_mapper.create_mapping_for_score(expanded_score)
                    
                    # Begrenze die Ausgabe auf 5 Instrumente
                    instr_count = 0
                    instr_output = ""
                    for part_idx, instr_name in instrument_mapping.items():
                        if instr_count < 5:
                            instr_output += f"\n  • Part {part_idx}: {instr_name}"
                            instr_count += 1
                    
                    if len(instrument_mapping) > 5:
                        instr_output += f"\n  • ... weitere {len(instrument_mapping) - 5} Instrumente"
                        
                    self.progress_signal.emit(f"✅ {len(instrument_mapping)} Instrumente erkannt:{instr_output}")
                except Exception as e:
                    self.progress_signal.emit(f"⚠️ Fehler bei der Instrumenterkennung: {str(e)}")
                    instrument_mapping = {}
                
                # SCHRITT 5: CC1-Dynamikkurven (auf expandiertem Score)
                # Nur ausführen, wenn CC1 aktiviert ist und der Digital Dirigent NICHT genutzt wird.
                # Wenn der Digital Dirigent aktiv ist, werden CC1-Kurven später eingefügt
                if self.do_cc1 and not self.do_conductor:
                    self.progress_signal.emit("🔄 Extrahiere Dynamikpunkte aus expandiertem Score...")
                    try:
                        from dynamics import extract_dynamic_points, non_linear_interpolate_dynamics
                        voice_dynamics = extract_dynamic_points(expanded_score)
                        
                        # Anzahl der Dynamikpunkte begrenzt ausgeben
                        voice_count = 0
                        dynamics_output = ""
                        for voice_idx, points in voice_dynamics.items():
                            if voice_count < 3:  # Nur die ersten 3 Stimmen ausgeben
                                instrument_name = instrument_mapping.get(str(voice_idx), f"Stimme {voice_idx}")
                                dynamics_output += f"\n  • {len(points)} Punkte für {instrument_name}"
                                voice_count += 1
                        
                        if len(voice_dynamics) > 3:
                            dynamics_output += f"\n  • ... weitere {len(voice_dynamics) - 3} Stimmen"
                            
                        self.progress_signal.emit(f"✅ Dynamikpunkte extrahiert:{dynamics_output}")
                        
                        total_duration = expanded_score.highestTime
                        resolution = 0.1
                        self.progress_signal.emit("🔄 Erzeuge dynamische CC1-Kurven...")
                        dynamic_curves = non_linear_interpolate_dynamics(voice_dynamics, total_duration, resolution=resolution, k=0.1, x0=70)
                        total_points = sum(len(curve) for curve in dynamic_curves.values())
                        self.progress_signal.emit(f"✅ Dynamik-Kurven mit insgesamt {total_points} Punkten erstellt")
                        
                        self.progress_signal.emit("🔄 Füge CC1-Kurven in MIDI ein...")
                        try:
                            from musescore_helper import add_cc1_to_musescore_midi
                            result = add_cc1_to_musescore_midi(midi_file_path, dynamic_curves)
                            
                            # Prüfe, ob die MIDI-Datei nach dem Hinzufügen noch existiert
                            if os.path.exists(result):
                                self.progress_signal.emit("✅ CC1-Kurven erfolgreich hinzugefügt")
                            else:
                                self.progress_signal.emit("⚠️ Nach CC1-Verarbeitung existiert die MIDI-Datei nicht mehr")
                                return None
                        except Exception as cc1_error:
                            self.progress_signal.emit(f"⚠️ Fehler beim Hinzufügen der CC1-Kurven: {str(cc1_error)}")
                    except Exception as dynamics_error:
                        self.progress_signal.emit(f"⚠️ Fehler bei der Dynamikverarbeitung: {str(dynamics_error)}")
                else:
                    msg = "ℹ️ CC1-Kurven werden später (nach Digital Dirigent) hinzugefügt" if self.do_cc1 else "ℹ️ CC1-Kurven deaktiviert"
                    self.progress_signal.emit(msg)
                
                # SCHRITT 6: Track-Längen korrigieren
                self.progress_signal.emit("🔄 Korrigiere Track-Längen für synchrones Timing...")
                try:
                    from midi_utils import fix_track_lengths
                    fix_track_lengths(midi_file_path)
                    self.progress_signal.emit("✅ Track-Längen erfolgreich synchronisiert")
                except Exception as e:
                    self.progress_signal.emit(f"⚠️ Fehler bei der Track-Längenkorrektur: {str(e)}")
                
                # SCHRITT 7: Finale MIDI-Analyse
                try:
                    # Prüfe, ob die Datei existiert
                    if not os.path.exists(midi_file_path):
                        self.progress_signal.emit("❌ Finale MIDI-Datei existiert nicht!")
                        return None
                        
                    mid = mido.MidiFile(midi_file_path)
                    total_notes = sum(sum(1 for msg in track if msg.type == 'note_on' and msg.velocity > 0) for track in mid.tracks)
                    minutes, seconds = divmod(mid.length, 60)
                    self.progress_signal.emit(f"📊 Finale MIDI-Statistik: {total_notes} Noten, Länge: {int(minutes)}:{seconds:.1f}")
                except Exception as e:
                    self.progress_signal.emit(f"⚠️ Fehler bei der MIDI-Analyse: {str(e)}")
                
                # Prüfe nochmals explizit, ob die Datei existiert
                if os.path.exists(midi_file_path):
                    self.progress_signal.emit(f"✅ XML zu MIDI Konvertierung abgeschlossen: {midi_file_path}")
                    return midi_file_path
                else:
                    self.progress_signal.emit("❌ Fehler: Erzeugte MIDI-Datei existiert nicht")
                    return None
            
            except Exception as e:
                self.progress_signal.emit(f"❌ Fehler bei der XML-Verarbeitung: {str(e)}")
                # Speichere den vollen Traceback für bessere Fehlerdiagnose
                import traceback
                error_details = traceback.format_exc()
                self.progress_signal.emit(f"Fehlerdetails: {error_details[:200]}...")  # Gekürzt für Übersichtlichkeit
                
                # Als letzte Möglichkeit: Direkte Konvertierung
                return self.direct_musescore_conversion(xml_file, midi_file_path)
            
        except Exception as e:
            self.progress_signal.emit(f"❌ Fehler beim Konvertieren von {xml_file}: {str(e)}")
            return None

    def direct_musescore_conversion(self, xml_file, output_midi):
        """
        Versucht eine direkte Konvertierung mit MuseScore ohne Expansion als Fallback.
        
        Args:
            xml_file: Original XML-Datei
            output_midi: Ausgabe-MIDI-Pfad
            
        Returns:
            Pfad zur erzeugten MIDI-Datei oder None bei Fehler
        """
        self.progress_signal.emit("🔄 Versuche direkte Konvertierung mit MuseScore (Notfall-Fallback)...")
        
        musescore_path = self.find_musescore_path()
        if not musescore_path:
            self.progress_signal.emit("⚠️ MuseScore nicht gefunden für Fallback-Konvertierung")
            try:
                # Letzte Möglichkeit: music21
                score = m21.converter.parse(xml_file)
                score.write('midi', fp=output_midi)
                if os.path.exists(output_midi):
                    self.progress_signal.emit(f"✅ MIDI mit music21 Fallback erstellt: {output_midi}")
                    return output_midi
                else:
                    self.progress_signal.emit("❌ Alle Konvertierungsmethoden fehlgeschlagen")
                    return None
            except Exception as last_error:
                self.progress_signal.emit(f"❌ Letzter Konvertierungsversuch fehlgeschlagen: {str(last_error)}")
                return None
        
        try:
            cmd = [musescore_path, "-o", os.path.abspath(output_midi), os.path.abspath(xml_file)]
            self.progress_signal.emit("🔄 Direkte MuseScore-Konvertierung läuft...")
            
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            
            if os.path.exists(output_midi) and os.path.getsize(output_midi) > 100:
                self.progress_signal.emit(f"✅ Direkte Konvertierung erfolgreich: {output_midi}")
                return output_midi
            else:
                self.progress_signal.emit("❌ Direkte Konvertierung fehlgeschlagen")
                return None
        except Exception as direct_error:
            self.progress_signal.emit(f"❌ Fehler bei direkter Konvertierung: {str(direct_error)}")
            return None

    def apply_digital_conductor(self, midi_file):
        """
        Wendet den Digital Dirigenten auf eine MIDI-Datei an.
        
        Verarbeitungsschritt 2: Digital Dirigent für Timing-Anpassungen
        
        Args:
            midi_file: Pfad zur MIDI-Datei
            
        Returns:
            Tuple aus (Pfad zur verarbeiteten MIDI-Datei, Interpretationsergebnisse)
            oder (Eingabedatei, None) bei Fehler
        """
        # Prüfe, ob die Eingabedatei existiert
        if not os.path.exists(midi_file):
            self.progress_signal.emit(f"❌ MIDI-Datei für Dirigent nicht gefunden: {midi_file}")
            return midi_file, None
            
        self.progress_signal.emit(f"🔄 Wende Digital Dirigent auf {os.path.basename(midi_file)} an...")
        params = self._get_style_parameters()
        
        try:
            base_name = os.path.splitext(os.path.basename(midi_file))[0]
            output_dir = os.path.join(os.path.dirname(midi_file), "results")
            os.makedirs(output_dir, exist_ok=True)
            output_midi = os.path.join(output_dir, f"{base_name}_conducted.mid")
            
            interpreter = NoteLevelInterpreter(
                expressiveness=self.expressivity,
                rubato_strength=params['rubato_strength'],
                articulation_strength=params['articulation_strength'],
                dynamics_strength=params['dynamics_strength']
            )
            
            # Lade die MIDI-Datei im Interpreter
            if not interpreter.load_midi(midi_file):
                self.progress_signal.emit(f"❌ Dirigent konnte MIDI-Datei nicht laden: {midi_file}")
                return midi_file, None
                
            # Führe die Interpretation durch
            interp_results = interpreter.interpret()
            
            # Erstelle Visualisierungen
            try:
                self.progress_signal.emit("🔄 Erstelle Dirigenten-Visualisierungen...")
                import direct_visualization
                viz_path = direct_visualization.create_combined_visualization(interp_results, output_dir, base_name)
                if viz_path:
                    self.progress_signal.emit(f"✅ Visualisierung erstellt: {os.path.basename(viz_path)}")
            except Exception as e:
                self.progress_signal.emit(f"⚠️ Fehler bei der Visualisierung: {str(e)}")
            
            # Speichere die interpretierte MIDI-Datei
            conducted_midi = interpreter.save_midi(midi_file, output_midi)
            
            # Prüfe, ob die Ausgabedatei existiert
            if os.path.exists(conducted_midi):
                self.progress_signal.emit(f"✅ Digital Dirigent erfolgreich angewendet: {os.path.basename(conducted_midi)}")
                
                # Protokolliere Statistiken
                stats = interp_results.get('stats', {})
                adjusted_notes = stats.get('adjusted_notes', 0)
                total_notes = stats.get('total_notes', 0)
                self.progress_signal.emit(f"📊 {adjusted_notes} von {total_notes} Noten angepasst ({(adjusted_notes/max(1, total_notes)*100):.1f}%)")
                
                melody_voices = stats.get('melody_voices', 0)
                bass_voices = stats.get('bass_voices', 0)
                inner_voices = stats.get('inner_voices', 0)
                self.progress_signal.emit(f"📊 Erkannte Stimmen: {melody_voices} Melodie, {bass_voices} Bass, {inner_voices} Innere")
                
                # Gib den neuen Dateipfad und die Interpretationsergebnisse zurück
                return conducted_midi, interp_results
            else:
                self.progress_signal.emit(f"❌ Dirigent konnte keine interpretierte MIDI-Datei erzeugen")
                return midi_file, None
                
        except Exception as e:
            self.progress_signal.emit(f"❌ Fehler bei der Anwendung des Digital Dirigenten: {str(e)}")
            return midi_file, None

    def add_cc1_curves(self, midi_file, interp_results=None):
        """
        Fügt CC1-Dynamikkurven zur MIDI-Datei hinzu.
        
        Verarbeitungsschritt 3: CC1-Kurven für Dynamik
        
        Args:
            midi_file: Pfad zur MIDI-Datei
            interp_results: Optional, Interpretationsergebnisse vom Digital Dirigenten
            
        Returns:
            Pfad zur MIDI-Datei mit CC1-Kurven oder die Eingabedatei bei Fehler
        """
        # Prüfe, ob die Eingabedatei existiert
        if not os.path.exists(midi_file):
            self.progress_signal.emit(f"❌ MIDI-Datei für CC1-Kurven nicht gefunden: {midi_file}")
            return midi_file
                
        self.progress_signal.emit(f"🔄 Füge CC1-Dynamikkurven zu {os.path.basename(midi_file)} hinzu...")
        
        # Unterschiedliche Verarbeitung je nachdem, ob Interpretationsergebnisse vorliegen
        if interp_results:
            self.progress_signal.emit("🔄 Verwende Interpretationsergebnisse vom Digital Dirigenten für CC1-Kurven...")
            
            try:
                # Lade den Score
                self.progress_signal.emit("🔄 Lade MIDI-Datei für Dynamikanalyse...")
                score = m21.converter.parse(midi_file)
                
                # Extrahiere Dynamikpunkte
                self.progress_signal.emit("🔄 Extrahiere Dynamikpunkte...")
                from dynamics import extract_dynamic_points, non_linear_interpolate_dynamics
                voice_dynamics = extract_dynamic_points(score)
                
                # Hole ticks_per_beat aus der MIDI-Datei
                mid = mido.MidiFile(midi_file)
                ticks_per_beat = mid.ticks_per_beat
                
                # Verwende die spezialisierte Funktion für interpretierte MIDI-Dateien
                from cc1 import insert_cc1_curve_with_interpretation
                result = insert_cc1_curve_with_interpretation(
                    midi_file, 
                    voice_dynamics, 
                    interp_results, 
                    ticks_per_beat, 
                    score
                )
                
                # Prüfe, ob die Datei nach der Verarbeitung existiert
                if os.path.exists(result):
                    self.progress_signal.emit(f"✅ CC1-Kurven mit Interpretationsdaten erfolgreich hinzugefügt zu {os.path.basename(result)}")
                    return result
                else:
                    self.progress_signal.emit("❌ Nach CC1-Verarbeitung existiert die MIDI-Datei nicht mehr")
                    return midi_file
            except Exception as e:
                self.progress_signal.emit(f"⚠️ Fehler bei der interpretierten CC1-Kurven-Erzeugung: {str(e)}")
                # Fallback auf Standard-Methode
                self.progress_signal.emit("🔄 Fallback auf Standard-CC1-Verarbeitung...")
                return self._add_standard_cc1_curves(midi_file)
        else:
            # Standard-CC1-Verarbeitung ohne Interpretationsergebnisse
            return self._add_standard_cc1_curves(midi_file)

    def _add_standard_cc1_curves(self, midi_file):
        """
        Fügt Standard-CC1-Kurven ohne Interpretationsdaten hinzu.
        
        Args:
            midi_file: Pfad zur MIDI-Datei
            
        Returns:
            Pfad zur MIDI-Datei mit CC1-Kurven oder die Eingabedatei bei Fehler
        """
        try:
            from dynamics import extract_dynamic_points, non_linear_interpolate_dynamics
            
            # Lade den Score
            self.progress_signal.emit("🔄 Lade MIDI-Datei für Dynamikanalyse...")
            score = m21.converter.parse(midi_file)
            
            # Extrahiere Dynamikpunkte
            self.progress_signal.emit("🔄 Extrahiere Dynamikpunkte...")
            voice_dynamics = extract_dynamic_points(score)
            
            # Berechne Kurven
            total_duration = score.highestTime
            resolution = 0.1
            dynamic_curves = non_linear_interpolate_dynamics(voice_dynamics, total_duration, resolution=resolution, k=0.1, x0=70)
            
            # Ausgabe begrenzen
            voice_count = 0
            curves_output = ""
            total_points = sum(len(curve) for curve in dynamic_curves.values())
            
            for voice_idx, curve in dynamic_curves.items():
                if voice_count < 3:  # Nur die ersten 3 Stimmen ausgeben
                    curves_output += f"\n  • Stimme {voice_idx}: {len(curve)} Punkte"
                    voice_count += 1
            
            if len(dynamic_curves) > 3:
                curves_output += f"\n  • ... weitere {len(dynamic_curves) - 3} Stimmen"
                
            self.progress_signal.emit(f"✅ Dynamik-Kurven erstellt: {total_points} Punkte gesamt{curves_output}")
            
            # Füge Kurven in MIDI ein
            from musescore_helper import add_cc1_to_musescore_midi
            result = add_cc1_to_musescore_midi(midi_file, dynamic_curves)
            
            # Prüfe, ob die Datei nach der Verarbeitung existiert
            if os.path.exists(result):
                self.progress_signal.emit(f"✅ CC1-Kurven erfolgreich hinzugefügt zu {os.path.basename(result)}")
                return result
            else:
                self.progress_signal.emit("❌ Nach CC1-Verarbeitung existiert die MIDI-Datei nicht mehr")
                return midi_file
                
        except Exception as e:
            self.progress_signal.emit(f"❌ Fehler beim Hinzufügen der CC1-Kurven: {str(e)}")
            return midi_file

    def add_keyswitches(self, midi_file):
        """
        Fügt Keyswitches für Artikulation zur MIDI-Datei hinzu.
        
        Verarbeitungsschritt 4: Keyswitches für Artikulation
        
        Args:
            midi_file: Pfad zur MIDI-Datei
            
        Returns:
            Pfad zur MIDI-Datei mit Keyswitches oder die Eingabedatei bei Fehler
        """
        # Prüfe, ob die Eingabedatei existiert
        if not os.path.exists(midi_file):
            self.progress_signal.emit(f"❌ MIDI-Datei für Keyswitches nicht gefunden: {midi_file}")
            return midi_file
            
        self.progress_signal.emit(f"🔄 Füge Keyswitches zu {os.path.basename(midi_file)} hinzu...")
        
        try:
            from keyswitches import add_keyswitches
            result = add_keyswitches(midi_file, library="miroire")
            
            # Prüfe, ob die Datei nach der Verarbeitung existiert
            if os.path.exists(result):
                self.progress_signal.emit(f"✅ Keyswitches erfolgreich hinzugefügt zu {os.path.basename(result)}")
                return result
            else:
                self.progress_signal.emit("❌ Nach Keyswitch-Verarbeitung existiert die MIDI-Datei nicht mehr")
                return midi_file
                
        except Exception as e:
            self.progress_signal.emit(f"❌ Fehler beim Hinzufügen von Keyswitches: {str(e)}")
            return midi_file

    def _get_style_parameters(self):
        """Gibt Parameter basierend auf dem gewählten Stil zurück."""
        params = {
            'articulation_strength': 0.7,
            'dynamics_strength': 0.7
        }
        base_rubato = 0.65
        if self.style == "HIP (Historisch)":
            base_rubato = 0.4
            params['articulation_strength'] = 0.8
        elif self.style == "Modern":
            base_rubato = 0.6
            params['articulation_strength'] = 0.6
        elif self.style == "Romantisch":
            base_rubato = 0.8
            params['dynamics_strength'] = 0.9
        elif self.style == "Minimalistisch":
            base_rubato = 0.3
            params['articulation_strength'] = 0.5
            params['dynamics_strength'] = 0.5
        tempo_factor = self.tempo_change / 0.10
        params['rubato_strength'] = min(1.0, max(0.1, base_rubato * tempo_factor))
        self.progress_signal.emit(f"ℹ️ Stil: {self.style}, Tempo-Änderung: ±{self.tempo_change*100:.0f}%, Rubato: {params['rubato_strength']:.2f}, Artikulation: {params['articulation_strength']:.2f}, Dynamik: {params['dynamics_strength']:.2f}")
        return params
    
    def run(self):
        """
        Hauptmethode für die Verarbeitung aller Dateien.
        
        Verarbeitungsreihenfolge:
        1. XML → MIDI mit expandierten Wiederholungen (wenn nötig)
        2. Digital Dirigent für Timing-Anpassungen (wenn aktiviert)
        3. CC1-Kurven für Dynamik (nach dem Dirigenten, wenn dieser aktiviert ist)
        4. Keyswitches für Artikulation (wenn aktiviert)
        """
        self.progress_signal.emit(f"🚀 Starte Verarbeitung für {len(self.files)} Datei(en)...")
        
        for file in self.files:
            self.progress_signal.emit(f"🟢 Bearbeite Datei: {file}")
            
            # Schritt 1: XML zu MIDI Konvertierung (falls benötigt)
            if self.do_conversion and file.lower().endswith((".xml", ".musicxml")):
                self.progress_signal.emit(f"🔄 Konvertiere {os.path.basename(file)} zu MIDI...")
                converted_file = self.convert_xml_to_midi(file)
                
                # Prüfe, ob die Konvertierung erfolgreich war
                if not converted_file or not os.path.exists(converted_file):
                    self.progress_signal.emit(f"❌ Konvertierung fehlgeschlagen für {file}, überspringe Datei")
                    continue
                    
                file = converted_file
                self.progress_signal.emit(f"✅ Konvertierung abgeschlossen: {file}")
            elif not file.lower().endswith((".mid", ".midi")):
                self.progress_signal.emit(f"⚠️ Überspringe Datei: {file} ist weder XML noch MIDI")
                continue
            
            # Schritt 2: Digital Dirigent anwenden (falls aktiviert)
            interp_results = None  # Initialisiere mit None für den Fall, dass kein Dirigent verwendet wird
            if self.do_conductor and file.lower().endswith((".mid", ".midi")):
                # Detaillierte Logging-Meldungen vor und nach der Verarbeitung
                self.progress_signal.emit(f"🔄 Dirigent verarbeitet: {os.path.basename(file)}")
                conducted_file, interp_results = self.apply_digital_conductor(file)
                
                # Prüfe, ob die Verarbeitung erfolgreich war
                if conducted_file and os.path.exists(conducted_file) and conducted_file != file:
                    self.progress_signal.emit(f"✅ Dirigent erfolgreich: {os.path.basename(file)} → {os.path.basename(conducted_file)}")
                    file = conducted_file  # Verwende die vom Dirigenten bearbeitete Datei für weitere Schritte
                else:
                    self.progress_signal.emit(f"⚠️ Dirigent-Verarbeitung fehlgeschlagen oder unverändert, verwende Original: {os.path.basename(file)}")
                    interp_results = None  # Setze zurück, falls vorhanden aber fehlerhaft
            
            # Schritt 3: CC1-Kurven hinzufügen (falls aktiviert)
            if file.lower().endswith((".mid", ".midi")) and self.do_cc1:
                # Detaillierte Logging-Meldungen vor und nach der Verarbeitung
                self.progress_signal.emit(f"🔄 CC1-Kurven werden hinzugefügt zu: {os.path.basename(file)}")
                cc1_file = self.add_cc1_curves(file, interp_results)
                
                # Prüfe, ob die Verarbeitung erfolgreich war
                if cc1_file and os.path.exists(cc1_file):
                    self.progress_signal.emit(f"✅ CC1-Kurven erfolgreich: {os.path.basename(file)} → {os.path.basename(cc1_file)}")
                    file = cc1_file  # Verwende die CC1-verarbeitete Datei für weitere Schritte
                else:
                    self.progress_signal.emit(f"⚠️ CC1-Verarbeitung fehlgeschlagen, verwende Original: {os.path.basename(file)}")
            
            # Schritt 4: Keyswitches hinzufügen (falls aktiviert)
            if file.lower().endswith((".mid", ".midi")) and self.do_keyswitches:
                # Detaillierte Logging-Meldungen vor und nach der Verarbeitung
                self.progress_signal.emit(f"🔄 Keyswitches werden hinzugefügt zu: {os.path.basename(file)}")
                keyswitch_file = self.add_keyswitches(file)
                
                # Prüfe, ob die Verarbeitung erfolgreich war
                if keyswitch_file and os.path.exists(keyswitch_file):
                    self.progress_signal.emit(f"✅ Keyswitches erfolgreich: {os.path.basename(file)} → {os.path.basename(keyswitch_file)}")
                    file = keyswitch_file  # Aktualisiere den Dateipfad für weitere Verarbeitung
                else:
                    self.progress_signal.emit(f"⚠️ Keyswitch-Verarbeitung fehlgeschlagen, verwende Original: {os.path.basename(file)}")
            
            # Ende der Verarbeitung für diese Datei
            self.progress_signal.emit(f"✅ Verarbeitung abgeschlossen für: {os.path.basename(file)}")
            
            # Speicherbereinigung nach jeder Datei
            gc.collect()
        
        self.progress_signal.emit("✅ Alle Dateien wurden bearbeitet.")