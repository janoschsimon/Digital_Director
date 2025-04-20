"""
Note Manipulator Modul für den Digital Dirigenten
-------------------------------------------------
Dieses Modul enthält die Hauptklasse für die Note-für-Note Manipulation
und musikalische Interpretation.

Version 3.0 - Mit bidirektionaler Timing-Darstellung und "Schilf im Wind"-Konzept.
"""

import os
import logging
import random
import json
from collections import defaultdict
from typing import Dict, List, Tuple, Any, Optional, Union

import mido
import numpy as np

from conductor.voice_analyzer import MusicalVoice, NoteProperties
from .rule_base import RuleManager, InterpretationContext
from .orchestral_conductor import OrchestralConductor

# Konfiguriere Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Globale Konstante für Debug-Modus
DEBUG_MODE = False  # Auf True setzen für detaillierte Logs

def enable_debug_logging():
    """Aktiviert detaillierte Debug-Protokollierung."""
    global DEBUG_MODE
    DEBUG_MODE = True
    logger.setLevel(logging.DEBUG)
    logger.debug("Debug-Protokollierung aktiviert")

def disable_debug_logging():
    """Deaktiviert detaillierte Debug-Protokollierung."""
    global DEBUG_MODE
    DEBUG_MODE = False
    logger.setLevel(logging.INFO)
    logger.info("Debug-Protokollierung deaktiviert")

class NoteLevelInterpreter:
    """
    Digital Dirigent, der jede Note individuell für eine musikalische Interpretation anpasst.
    
    Diese Version implementiert das "Schilf im Wind"-Konzept: Alle Stimmen folgen einer
    gemeinsamen orchestralen Führung, ähnlich wie Schilf, das im Wind schwankt.
    """
    
    def __init__(self, expressiveness=0.5, rubato_strength=0.6, 
                 articulation_strength=0.7, dynamics_strength=0.7, 
                 debug_mode=False, rule_config=None):
        """
        Initialisiert den notenlevelbasierten Interpreten.
        
        Args:
            expressiveness: Allgemeine Ausdrucksstärke (0.0 = mechanisch, 1.0 = sehr expressiv)
            rubato_strength: Stärke der Timing-Variationen (0.0 - 1.0)
            articulation_strength: Stärke der Artikulationsvariationen (0.0 - 1.0) 
            dynamics_strength: Stärke der Dynamikvariationen (0.0 - 1.0)
            debug_mode: Wenn True, werden detaillierte Debug-Informationen protokolliert
            rule_config: Optional, Pfad zur JSON-Konfigurationsdatei für Regeln
        """
        self.expressiveness = expressiveness
        self.rubato_strength = rubato_strength
        self.articulation_strength = articulation_strength
        self.dynamics_strength = dynamics_strength
        
        # Parameter für Debugging und Protokollierung
        if debug_mode:
            enable_debug_logging()
            logger.debug("Detaillierte Protokollierung für NoteLevelInterpreter aktiviert")
        
        self.voices = []
        self.ticks_per_beat = 480  # Standard-Wert, wird beim Laden der MIDI-Datei aktualisiert
        self.xml_division = 480    # Standard-Wert, kann später gesetzt werden falls abweichend
        
        # Initialisiere den Rule-Manager und lade Regeln
        self.rule_manager = RuleManager()
        self._load_rules(rule_config)
        
        # Initialisiere den Orchestral Conductor für die gemeinsame Führung
        self.orchestral_conductor = OrchestralConductor(
            expressiveness=expressiveness,
            wave_strength=rubato_strength * 0.9,  # Leicht reduziert, um extreme Werte zu vermeiden
            wave_complexity=0.8  # Moderate Komplexität für natürliche Wellen
        )

        # Statistiken
        self.stats = {
            'total_notes': 0,
            'adjusted_notes': 0,
            'total_voices': 0,
            'melody_voices': 0,
            'bass_voices': 0,
            'inner_voices': 0,
            'corrected_durations': 0,
            'critical_corrections': 0,
            'avg_velocity_change': 0.0,
            'avg_timing_change': 0.0,
            'avg_duration_change': 0.0,
            'max_velocity_increase': 0,
            'max_timing_delay': 0,
            'max_duration_reduction': 0,
        }
        
        logger.info(f"Noten-Interpreter initialisiert: Expressivität={expressiveness:.2f}, "
                   f"Rubato={rubato_strength:.2f}, Artikulation={articulation_strength:.2f}, "
                   f"Dynamik={dynamics_strength:.2f}")
    
    def _load_rules(self, config_file=None):
        """
        Lädt Regeln aus Konfiguration oder Standard-Regeln.
        
        Args:
            config_file: Optional, Pfad zur JSON-Konfigurationsdatei
        """
        if config_file and os.path.exists(config_file):
            # Versuche, Regeln aus der Konfigurationsdatei zu laden
            logger.info(f"Lade Regeln aus Konfigurationsdatei: {config_file}")
            success = self.rule_manager.load_from_config(config_file)
            
            if not success:
                logger.warning("Fehler beim Laden der Regeln aus Konfiguration, lade Standard-Regeln")
                self._load_default_rules()
        else:
            # Lade Standard-Regeln
            logger.info("Lade Standard-Regeln")
            self._load_default_rules()

    def _load_default_rules(self):
        """Lädt die Standard-Regeln für alle Stimmentypen."""
        try:
            # Melodie-Regeln importieren und registrieren
            from .melody_rules import (
                PhraseStartRule, PhraseEndRule, PreLeapRule, 
                LocalPeakRule, DownbeatRule, ShortNoteRule, LongNoteRule,
                # Neue Regeln für bidirektionale Timing-Änderungen
                AccelerandoRule, SequenceAccelerationRule, DirectionalRule
            )
            
            self.rule_manager.register_rule("melody", PhraseStartRule())
            self.rule_manager.register_rule("melody", PhraseEndRule())
            self.rule_manager.register_rule("melody", PreLeapRule())
            self.rule_manager.register_rule("melody", LocalPeakRule())
            self.rule_manager.register_rule("melody", DownbeatRule())
            self.rule_manager.register_rule("melody", ShortNoteRule())
            self.rule_manager.register_rule("melody", LongNoteRule())
            
            # Neue Regeln registrieren, die Beschleunigungen (negative Timing-Werte) erzeugen
            self.rule_manager.register_rule("melody", AccelerandoRule())
            self.rule_manager.register_rule("melody", SequenceAccelerationRule())
            self.rule_manager.register_rule("melody", DirectionalRule())
            
            # Bass-Regeln importieren und registrieren
            from .bass_rules import (
                BassDownbeatRule, BassShortNoteRule, 
                BassRepeatedNotesRule, BassPhraseEndRule
            )
            
            self.rule_manager.register_rule("bass", BassDownbeatRule())
            self.rule_manager.register_rule("bass", BassShortNoteRule())
            self.rule_manager.register_rule("bass", BassRepeatedNotesRule())
            self.rule_manager.register_rule("bass", BassPhraseEndRule())
            
            # Regeln für innere Stimmen importieren und registrieren
            from .inner_voice_rules import (
                InnerVoiceBaseVelocityRule, InnerContourRule, InnerConsonantRule,
                InnerFlowTimingRule, InnerShortNoteRule
            )
            
            self.rule_manager.register_rule("inner", InnerVoiceBaseVelocityRule())
            self.rule_manager.register_rule("inner", InnerContourRule())
            self.rule_manager.register_rule("inner", InnerConsonantRule())
            self.rule_manager.register_rule("inner", InnerFlowTimingRule())
            self.rule_manager.register_rule("inner", InnerShortNoteRule())
            
            logger.info("Standard-Regeln erfolgreich geladen")
        except ImportError as e:
            logger.error(f"Fehler beim Importieren der Regelmodule: {e}")
            logger.error("Stelle sicher, dass alle Regelmodule im Python-Pfad sind")
    
    def load_midi(self, midi_file: str) -> bool:
        """
        Lädt eine MIDI-Datei und extrahiert alle Noten und Stimmen.
        
        Args:
            midi_file: Pfad zur MIDI-Datei
            
        Returns:
            True bei erfolgreicher Verarbeitung, False bei Fehler
        """
        logger.info(f"Lade MIDI-Datei: {midi_file}")
        # Speichere das Verzeichnis der Eingabedatei für spätere Verwendung
        self.input_directory = os.path.dirname(os.path.abspath(midi_file))
        # NEU: Extrahiere und speichere den Basisdateinamen ohne Erweiterung  2025.04.11
        self.input_basename = os.path.splitext(os.path.basename(midi_file))[0]

        try:
            mid = mido.MidiFile(midi_file)
            self.ticks_per_beat = mid.ticks_per_beat
            logger.info(f"MIDI Ticks pro Beat: {self.ticks_per_beat}")
            
            # Noten pro Track und Kanal sammeln
            notes_by_track_channel = defaultdict(list)
            
            for track_idx, track in enumerate(mid.tracks):
                # Zusätzliche Informationen über den Track protokollieren
                track_name = "Unbenannt"
                for msg in track:
                    if msg.is_meta and msg.type == 'track_name':
                        track_name = msg.name
                        break
                
                logger.info(f"Verarbeite Track {track_idx}: '{track_name}'")
                
                # Noten-Events sammeln
                notes_on = {}  # (note, channel) -> (start_time, velocity)
                absolute_time = 0
                note_count = 0
                ignored_count = 0
                
                for msg in track:
                    absolute_time += msg.time
                    
                    if msg.type == 'note_on' and hasattr(msg, 'velocity') and msg.velocity > 0:
                        notes_on[(msg.note, msg.channel)] = (absolute_time, msg.velocity)
                    elif (msg.type == 'note_off' or 
                          (msg.type == 'note_on' and hasattr(msg, 'velocity') and msg.velocity == 0)):
                        # Suche das passende note_on Event
                        if (msg.note, msg.channel) in notes_on:
                            start_time, velocity = notes_on.pop((msg.note, msg.channel))
                            duration = absolute_time - start_time
                            
                            # Stellen Sie sicher, dass keine Note mit Dauer 0 existiert
                            if duration <= 0:
                                duration = 1  # Mindestdauer von 1 Tick erzwingen
                                logger.warning(f"Note mit Dauer 0 korrigiert: Track {track_idx}, "
                                              f"Kanal {msg.channel}, Note {msg.note}, Zeit {absolute_time}")
                            
                            try:
                                note = NoteProperties(
                                    pitch=msg.note,
                                    velocity=velocity,
                                    start_time=start_time,
                                    duration=duration,
                                    track=track_idx,
                                    channel=msg.channel
                                )
                                
                                notes_by_track_channel[(track_idx, msg.channel)].append(note)
                                note_count += 1
                                
                                # Protokolliere jede 50. Note für Fortschrittsanzeige
                                if DEBUG_MODE and note_count % 50 == 0:
                                    logger.debug(f"  Gesammelte Noten: {note_count}")
                            except Exception as e:
                                logger.error(f"Fehler beim Erstellen von NoteProperties: {e}")
                                continue
                        else:
                            # Off-Event ohne passendes On-Event
                            ignored_count += 1
                            if DEBUG_MODE and ignored_count < 10:  # Begrenze die Anzahl der Warnungen
                                logger.debug(f"Note-Off ohne passendes Note-On: Track {track_idx}, "
                                           f"Kanal {msg.channel}, Note {msg.note}, Zeit {absolute_time}")
                
                # Zusammenfassung für diesen Track
                if note_count > 0:
                    logger.info(f"Track {track_idx}: {note_count} Noten gesammelt")
                    if ignored_count > 0:
                        logger.info(f"  {ignored_count} Note-Off-Events ohne passendes Note-On ignoriert")
                else:
                    logger.info(f"Track {track_idx}: Keine Noten gefunden")
            
            # Erstelle Stimmen aus den gesammelten Noten
            for (track_idx, channel), notes in notes_by_track_channel.items():
                if notes:  # Ignoriere leere Stimmen
                    voice = MusicalVoice(track_idx, channel)
                    voice.notes = notes
                    self.voices.append(voice)
                    self.stats['total_notes'] += len(notes)
                    logger.info(f"Stimme erstellt: Track {track_idx}, Kanal {channel}, {len(notes)} Noten")
            
            self.stats['total_voices'] = len(self.voices)
            
            # Analysiere jede Stimme
            logger.info(f"Starte Stimmenanalyse für {len(self.voices)} Stimmen...")
            for voice_idx, voice in enumerate(self.voices):
                logger.info(f"Analysiere Stimme {voice_idx+1}/{len(self.voices)}: "
                           f"Track {voice.track_index}, Kanal {voice.channel}")
                
                try:
                    voice.analyze(self.ticks_per_beat)
                    
                    # Bericht über die Analyse
                    pitch_range = getattr(voice, 'pitch_range', (0, 0))
                    avg_pitch = getattr(voice, 'avg_pitch', 0)
                    role = getattr(voice, 'role', 'unbekannt')
                    
                    logger.info(f"  Rolle: {role}")
                    logger.info(f"  Durchschnittliche Tonhöhe: {avg_pitch:.1f}")
                    logger.info(f"  Tonhöhenbereich: {pitch_range}")
                    
                    if hasattr(voice, 'phrases') and voice.phrases:
                        logger.info(f"  Phrasen erkannt: {len(voice.phrases)}")
                    
                    # Aktualisiere Statistiken
                    if voice.role == "melody":
                        self.stats['melody_voices'] += 1
                    elif voice.role == "bass":
                        self.stats['bass_voices'] += 1
                    elif voice.role == "inner_voice":
                        self.stats['inner_voices'] += 1
                except Exception as e:
                    logger.error(f"Fehler bei der Analyse von Stimme {voice_idx}: {e}")
                    logger.error("Stimme wird möglicherweise nicht korrekt interpretiert")
            
            logger.info(f"MIDI-Analyse abgeschlossen: {len(self.voices)} Stimmen gefunden, "
                       f"{self.stats['total_notes']} Noten total")
            
            # Drucke Stimmenzusammenfassung
            logger.info(f"Stimmenverteilung: {self.stats['melody_voices']} Melodien, "
                       f"{self.stats['bass_voices']} Bässe, {self.stats['inner_voices']} Innenlinien")
            
            return True
            
        except Exception as e:
            logger.error(f"Fehler beim Laden der MIDI-Datei: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def interpret(self) -> Dict[str, Any]:
        """
        Wendet musikalische Interpretation auf jede Note an.
        
        Returns:
            Dictionary mit Interpretationsstatistiken und -ergebnissen
        """
        logger.info("Starte musikalische Interpretation...")
        
        # Orchestrale Führung initialisieren
        logger.info("Starte orchestrale Strukturanalyse...")
        
        try:
            # Führe die Strukturanalyse mit Fehlerbehandlung durch
            self.orchestral_conductor.analyze_structure(self.voices)
            self.orchestral_conductor.create_agogic_map()
            
            # Ensure agogic_map is a proper dictionary, not None or a string
            if not hasattr(self.orchestral_conductor, 'agogic_map') or self.orchestral_conductor.agogic_map is None:
                logger.warning("Keine agogic_map in orchestral_conductor gefunden, erstelle leeres Dictionary")
                self.orchestral_conductor.agogic_map = {}
            elif isinstance(self.orchestral_conductor.agogic_map, str):
                logger.warning("agogic_map ist ein String, konvertiere zu Dictionary")
                self.orchestral_conductor.agogic_map = {}
                
            # Ensure phrase_boundaries is a proper list, not None or a string
            if not hasattr(self.orchestral_conductor, 'phrase_boundaries') or self.orchestral_conductor.phrase_boundaries is None:
                logger.warning("Keine phrase_boundaries in orchestral_conductor gefunden, erstelle leere Liste")
                self.orchestral_conductor.phrase_boundaries = []
            elif isinstance(self.orchestral_conductor.phrase_boundaries, str):
                logger.warning("phrase_boundaries ist ein String, konvertiere zu Liste")
                self.orchestral_conductor.phrase_boundaries = []
        except Exception as e:
            logger.error(f"Fehler in der orchestralen Analyse: {e}")
            logger.error("Erstelle Fallback-Datenstrukturen")
            # Fallback: Leere Datenstrukturen erstellen
            self.orchestral_conductor.agogic_map = {}
            self.orchestral_conductor.phrase_boundaries = []

        # Temporäre Sammlungen für Statistiken
        all_velocity_changes = []
        all_timing_changes = []
        all_duration_changes_pct = []
        
        # Verarbeite jede Stimme mit ihren spezifischen Regeln
        for voice_idx, voice in enumerate(self.voices):
            logger.info(f"Interpretiere Stimme {voice_idx+1}/{len(self.voices)}: "
                       f"Rolle={voice.role}, {len(voice.notes)} Noten")
            
            # Zeitmessung für Leistungsüberwachung
            import time
            start_time = time.time()
            
            try:
                self._interpret_voice(voice)
            except Exception as e:
                logger.error(f"Fehler bei der Interpretation von Stimme {voice_idx}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                logger.warning(f"Fahre mit der nächsten Stimme fort")
                continue
            
            # Sammle Änderungen für Statistiken
            for note in voice.notes:
                if hasattr(note, 'adjusted_velocity') and hasattr(note, 'velocity'):
                    velocity_change = note.adjusted_velocity - note.velocity
                    all_velocity_changes.append(velocity_change)
                    
                    # Aktualisiere maximale Erhöhung
                    if velocity_change > self.stats['max_velocity_increase']:
                        self.stats['max_velocity_increase'] = velocity_change
                
                if hasattr(note, 'adjusted_start_time') and hasattr(note, 'original_start_time'):
                    timing_change = note.adjusted_start_time - note.original_start_time
                    all_timing_changes.append(timing_change)
                    
                    # Aktualisiere maximale Verzögerung
                    if timing_change > self.stats['max_timing_delay']:
                        self.stats['max_timing_delay'] = timing_change
                
                if hasattr(note, 'adjusted_duration') and hasattr(note, 'original_duration') and note.original_duration > 0:
                    # Prozentuale Änderung der Dauer
                    duration_change_pct = ((note.adjusted_duration / note.original_duration) - 1.0) * 100
                    all_duration_changes_pct.append(duration_change_pct)
                    
                    # Aktualisiere maximale Reduktion (negative Werte)
                    if duration_change_pct < -self.stats['max_duration_reduction']:
                        self.stats['max_duration_reduction'] = -duration_change_pct
            
            # Zeitmessung abschließen
            elapsed_time = time.time() - start_time
            logger.info(f"Stimme {voice_idx+1} in {elapsed_time:.2f} Sekunden interpretiert")
        
        # Validiere und korrigiere kritische Notendauern
        logger.info("Führe abschließende Sicherheitsprüfung für Notendauern durch...")
        try:
            self._validate_and_fix_note_durations()
        except Exception as e:
            logger.error(f"Fehler bei der Notenvalidierung: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        # Berechne Durchschnittswerte für Statistiken
        if all_velocity_changes:
            self.stats['avg_velocity_change'] = sum(all_velocity_changes) / len(all_velocity_changes)
        
        if all_timing_changes:
            self.stats['avg_timing_change'] = sum(all_timing_changes) / len(all_timing_changes)
            
            # Berechne den Anteil positiver und negativer Timing-Änderungen
            pos_timing = sum(1 for t in all_timing_changes if t > 0)
            neg_timing = sum(1 for t in all_timing_changes if t < 0)
            zero_timing = sum(1 for t in all_timing_changes if t == 0)
            total_timing = len(all_timing_changes)
            
            if total_timing > 0:
                self.stats['positive_timing_percent'] = (pos_timing / total_timing) * 100
                self.stats['negative_timing_percent'] = (neg_timing / total_timing) * 100
                self.stats['zero_timing_percent'] = (zero_timing / total_timing) * 100
                
                # Maximale/minimale Timing-Änderungen
                if neg_timing > 0:
                    self.stats['max_timing_accel'] = abs(min(t for t in all_timing_changes if t < 0))
        
        if all_duration_changes_pct:
            self.stats['avg_duration_change'] = sum(all_duration_changes_pct) / len(all_duration_changes_pct)
        
        logger.info(f"Interpretation abgeschlossen: {self.stats['adjusted_notes']} von "
                   f"{self.stats['total_notes']} Noten angepasst, "
                   f"{self.stats['corrected_durations']} kritische Notendauern korrigiert")
        
        # Detaillierte Statistiken protokollieren
        logger.info(f"Änderungsstatistiken:")
        logger.info(f"  Durchschnittliche Velocity-Änderung: {self.stats['avg_velocity_change']:.2f}")
        logger.info(f"  Durchschnittliche Timing-Änderung: {self.stats['avg_timing_change']:.2f} Ticks")
        
        # Timing-Verteilung in Hauptstatistik
        if 'positive_timing_percent' in self.stats:
            logger.info(f"  Timing-Verteilung: {self.stats['positive_timing_percent']:.1f}% Verzögerungen, "
                      f"{self.stats['negative_timing_percent']:.1f}% Beschleunigungen")
        
        logger.info(f"  Durchschnittliche Daueränderung: {self.stats['avg_duration_change']:.2f}%")
        logger.info(f"  Maximale Velocity-Erhöhung: {self.stats['max_velocity_increase']}")
        logger.info(f"  Maximale Timing-Verzögerung: {self.stats['max_timing_delay']} Ticks")
        
        # Maximale Beschleunigung
        if 'max_timing_accel' in self.stats:
            logger.info(f"  Maximale Timing-Beschleunigung: {self.stats['max_timing_accel']} Ticks")
        
        logger.info(f"  Maximale Dauerreduzierung: {self.stats['max_duration_reduction']:.2f}%")
        
        # Regel-Anwendungsstatistiken ausgeben
        self.rule_manager.print_statistics()
        
        # Erstelle Visualisierung der Interpretation
        interpretation_results = {
            'stats': self.stats,
            'voices': self.voices,
            'xml_division': self.xml_division,
            'rule_manager': self.rule_manager,
            'orchestral_conductor': self.orchestral_conductor,
            'ticks_per_beat': self.ticks_per_beat
        }
        
        # KRITISCHE SICHERHEITSPRÜFUNG vor der Visualisierung
        if hasattr(self, 'orchestral_conductor'):
            if not hasattr(self.orchestral_conductor, 'agogic_map') or self.orchestral_conductor.agogic_map is None:
                logger.critical("KRITISCH: agogic_map ist None vor der Visualisierung - erstelle leeres Dictionary")
                self.orchestral_conductor.agogic_map = {}
            elif not isinstance(self.orchestral_conductor.agogic_map, dict):
                logger.critical(f"KRITISCH: agogic_map hat falschen Typ: {type(self.orchestral_conductor.agogic_map)}")
                self.orchestral_conductor.agogic_map = {}

        # Sichere nochmals die orchestral_conductor Daten, um Fehler in der Visualisierung zu vermeiden
        try:
            # Stelle sicher, dass die Daten für die Visualisierung korrekt sind
            if isinstance(interpretation_results, dict) and 'orchestral_conductor' in interpretation_results:
                oc = interpretation_results['orchestral_conductor']
                
                # Statt None oder String ein leeres Dictionary verwenden
                if hasattr(oc, 'agogic_map'):
                    if oc.agogic_map is None or isinstance(oc.agogic_map, str):
                        logger.warning("Fehlerhafte agogic_map gefunden und korrigiert")
                        oc.agogic_map = {}
                else:
                    # Falls das Attribut fehlt, setze es
                    setattr(oc, 'agogic_map', {})
                
                # Statt None oder String eine leere Liste verwenden
                if hasattr(oc, 'phrase_boundaries'):
                    if oc.phrase_boundaries is None or isinstance(oc.phrase_boundaries, str):
                        logger.warning("Fehlerhafte phrase_boundaries gefunden und korrigiert")
                        oc.phrase_boundaries = []
                else:
                    # Falls das Attribut fehlt, setze es
                    setattr(oc, 'phrase_boundaries', [])
            
       
            # Erzeuge Visualisierung
            try:
                from direct_visualization import create_combined_visualization
                
                # Verwende das Verzeichnis der Eingabedatei für die Ergebnisse
                if hasattr(self, 'input_directory') and self.input_directory:
                    output_dir = os.path.join(self.input_directory, "results")
                else:
                    # Fallback, falls input_directory nicht gesetzt wurde
                    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
                
                # Stelle sicher, dass das Verzeichnis existiert
                os.makedirs(output_dir, exist_ok=True)
                
                filename_prefix = getattr(self, 'input_basename', 'interpretation')
                visualization_path = create_combined_visualization(interpretation_results, output_dir, filename_prefix) 
                
                if visualization_path:
                    logger.info(f"Visualisierung erstellt: {visualization_path}")
                else:
                    logger.warning("Visualisierung konnte nicht erstellt werden")
            except ImportError as e:
                logger.warning(f"Visualisierungs-Modul konnte nicht importiert werden: {e}")
            except Exception as e:
                # Fange den Fehler 'str' object has no attribute 'items', aber lass die Verarbeitung weiterlaufen
                if "'str' object has no attribute 'items'" in str(e):
                    logger.warning("Bekannter Fehler beim Zugriff auf String-Attribute, die Visualisierung wurde dennoch erstellt")
                else:
                    logger.warning(f"Fehler bei der Visualisierung: {e}")
                    import traceback
                    logger.warning(traceback.format_exc())
        except Exception as e:
            logger.error(f"Fehler in der finalen Visualisierung: {e}")
        return interpretation_results 
    
    def _interpret_voice(self, voice):
        """
        Interpretiert eine Stimme basierend auf ihrer Rolle.
        Unterstützt jetzt bidirektionale Timing-Änderungen mit orchestraler Führung.
        """
        import time
        start_time = time.time()
        
        # Cache für Timing-Richtungen pro Takt
        timing_direction_cache = {}
        
        logger.info(f"Interpretiere {voice.role}-Stimme mit orchestraler Führung: {len(voice.notes)} Noten")
        
        # Zähle angepasste Noten und protokolliere Extremwerte
        notes_adjusted = 0
        
        # Tracking für detaillierte Statistiken
        timing_changes = []
        velocity_changes = []
        duration_changes = []
        
        # Verarbeite jede Note
        for note_idx, note in enumerate(voice.notes):
            try:
                # Überprüfe, ob alle benötigten Attribute vorhanden sind
                if not hasattr(note, 'start_time') or not hasattr(note, 'duration'):
                    logger.warning(f"Note {note_idx} hat nicht alle erforderlichen Attribute")
                    continue
                
                # Stelle sicher, dass die Originalwerte vorhanden sind
                if not hasattr(note, 'original_start_time'):
                    note.original_start_time = note.start_time
                    
                if not hasattr(note, 'original_duration'):
                    note.original_duration = note.duration
                
                # Stelle sicher, dass die angepassten Werte initialisiert sind
                if not hasattr(note, 'adjusted_start_time'):
                    note.adjusted_start_time = note.original_start_time
                    
                if not hasattr(note, 'adjusted_duration'):
                    note.adjusted_duration = note.original_duration
                    
                if not hasattr(note, 'adjusted_velocity'):
                    note.adjusted_velocity = note.velocity
                
                # Bestimme den Takt für diese Note
                measure = self._get_measure_number(note)
                
                # Verwende Cache oder hole die Timing-Richtung vom orchestralen Dirigenten
                if measure not in timing_direction_cache:
                    # Bestimme Beat-Position im Takt, falls verfügbar
                    beat_position = self._get_beat_position(note)
                    
                    try:
                        # Hole die Timing-Richtung für diesen Takt
                        timing_direction_bias = self.orchestral_conductor.get_timing_direction(measure, beat_position)
                        timing_direction_cache[measure] = timing_direction_bias
                    except Exception as e:
                        logger.error(f"Fehler beim Abrufen der Timing-Richtung für Takt {measure}: {e}")
                        timing_direction_cache[measure] = 0.0  # Neutraler Wert als Fallback
                else:
                    timing_direction_bias = timing_direction_cache[measure]
                
                # Erstelle den Interpretationskontext mit dem dynamischen Timing-Bias
                context = InterpretationContext(
                    ticks_per_beat=self.ticks_per_beat,
                    expressiveness=self.expressiveness,
                    rubato_strength=self.rubato_strength,
                    articulation_strength=self.articulation_strength,
                    dynamics_strength=self.dynamics_strength,
                    timing_direction_bias=timing_direction_bias
                )
                
                # Wende die passenden Regeln für diese Stimmenart an
                voice_type = "melody"  # Standardtyp
                if voice.role == "bass":
                    voice_type = "bass"
                elif voice.role == "inner_voice":
                    voice_type = "inner"
                        
                # Wende Regeln an, falls vorhanden
                if voice_type in self.rule_manager.rule_sets:
                    for rule in self.rule_manager.rule_sets[voice_type]:
                        if rule.enabled:
                            try:
                                if rule.apply(note, voice, context):
                                    # Statistik aktualisieren
                                    if rule.name in self.rule_manager.stats[voice_type]:
                                        self.rule_manager.stats[voice_type][rule.name] += 1
                                    else:
                                        self.rule_manager.stats[voice_type][rule.name] = 1
                            except Exception as e:
                                logger.error(f"Fehler bei Anwendung der Regel '{rule.name}': {e}")
                
                # Prüfe, ob Anpassungen vorgenommen wurden
                is_adjusted = (note.adjusted_start_time != note.original_start_time or
                              note.adjusted_duration != note.original_duration or
                              note.adjusted_velocity != note.velocity)
                
                # Sammle Statistiken für angepasste Noten
                if is_adjusted:
                    notes_adjusted += 1
                    self.stats['adjusted_notes'] += 1
                    
                    # Sammle detaillierte Änderungen für Statistiken
                    if note.adjusted_start_time != note.original_start_time:
                        timing_change = note.adjusted_start_time - note.original_start_time
                        timing_changes.append(timing_change)
                        
                    if note.adjusted_velocity != note.velocity:
                        velocity_change = note.adjusted_velocity - note.velocity
                        velocity_changes.append(velocity_change)
                        
                    if note.adjusted_duration != note.original_duration and note.original_duration > 0:
                        duration_change_pct = ((note.adjusted_duration / note.original_duration) - 1.0) * 100
                        duration_changes.append(duration_change_pct)
            except Exception as e:
                logger.error(f"Fehler bei der Interpretation von Note {note_idx}: {e}")
                continue
        
        # Berechne und protokolliere Durchschnittswerte für diese Stimme
        elapsed_time = time.time() - start_time
        logger.info(f"{notes_adjusted} von {len(voice.notes)} Noten angepasst "
                   f"({notes_adjusted/max(1, len(voice.notes))*100:.1f}%) in {elapsed_time:.3f} Sekunden")
        
        # Protokolliere Durchschnittswerte, wenn genügend Daten vorhanden sind
        if timing_changes:
            avg_timing = sum(timing_changes) / len(timing_changes)
            logger.info(f"  Durchschnittliche Timing-Änderung: {avg_timing:.2f} Ticks")
            # Berechne den Anteil positiver und negativer Timing-Änderungen
            pos_timing = sum(1 for t in timing_changes if t > 0)
            neg_timing = sum(1 for t in timing_changes if t < 0)
            total_timing = len(timing_changes)
            if total_timing > 0:
                logger.info(f"  Timing-Verteilung: {pos_timing/total_timing*100:.1f}% Verzögerungen, "
                           f"{neg_timing/total_timing*100:.1f}% Beschleunigungen")
    
    def _validate_and_fix_note_durations(self) -> None:
        """
        Überprüft und korrigiert zu kurze Notendauern nach allen Regelanwendungen.
        Diese Funktion dient als letzte Sicherheitsebene, um zu extreme Verkürzungen zu verhindern.
        """
        logger.info("Überprüfe und korrigiere kritische Notendauern...")
        corrected_notes = 0
        critical_notes = 0
        
        # Sammle Statistiken über die Notendauern vor der Korrektur
        if DEBUG_MODE:
            all_durations_before = []
            for voice in self.voices:
                for note in voice.notes:
                    if hasattr(note, 'adjusted_duration'):
                        all_durations_before.append(note.adjusted_duration)
            
            if all_durations_before:
                min_duration = min(all_durations_before)
                max_duration = max(all_durations_before)
                avg_duration = sum(all_durations_before) / len(all_durations_before)
                logger.debug(f"Vor Korrektur - Min: {min_duration}, Max: {max_duration}, "
                           f"Durchschnitt: {avg_duration:.2f} Ticks")
        
        # Prüfe jede Stimme und jede Note
        for voice_idx, voice in enumerate(self.voices):
            voice_corrections = 0
            
            for note_idx, note in enumerate(voice.notes):
                try:
                    # Überprüfe, ob die benötigten Attribute existieren
                    if not hasattr(note, 'original_duration') or not hasattr(note, 'adjusted_duration'):
                        logger.warning(f"Note {note_idx} in Stimme {voice_idx} hat nicht alle erforderlichen Attribute")
                        continue
                    
                    # Ursprüngliche relative Dauer berechnen (z.B. 1/16, 1/8 Note etc.)
                    relative_duration = note.original_duration / self.ticks_per_beat
                    
                    # Minimale akzeptable Dauer basierend auf der ursprünglichen relativen Dauer
                    if relative_duration <= 0.25:  # Kürzere Noten (≤ Viertel) benötigen besondere Behandlung
                        # Für sehr kurze Noten (32stel und kürzer)
                        if relative_duration <= 0.0625:
                            min_percent = 0.9  # Mindestens 90% der Originallänge beibehalten
                            note_type = "32stel oder kürzer"
                        # Für 16tel Noten
                        elif relative_duration <= 0.125:
                            min_percent = 0.8  # Mindestens 80% der Originallänge beibehalten
                            note_type = "16tel"
                        # Für 8tel Noten
                        elif relative_duration <= 0.25:
                            min_percent = 0.7  # Mindestens 70% der Originallänge beibehalten
                            note_type = "8tel"
                        else:
                            min_percent = 0.6  # Standardwert für längere Noten
                            note_type = "längere Note"
                        
                        # Absolute Mindestdauer (variiert nach Notenlänge, nie unter 2 Ticks)
                        absolute_min = max(2, int(self.ticks_per_beat * relative_duration * 0.5))
                        
                        # Berechne Mindestdauer basierend auf Originallänge
                        min_duration = max(absolute_min, int(note.original_duration * min_percent))
                        
                        # Wenn die aktuelle Dauer kleiner ist als die Mindestdauer, korrigiere sie
                        if note.adjusted_duration < min_duration:
                            old_duration = note.adjusted_duration
                            note.adjusted_duration = min_duration
                            corrected_notes += 1
                            voice_corrections += 1
                            
                            # Identifiziere besonders kritische Korrekturen (z.B. Noten, die fast auf 0 reduziert wurden)
                            if old_duration < min_duration * 0.5:
                                critical_notes += 1
                                logger.warning(f"Kritische Korrektur bei Note {note_idx} in Stimme {voice_idx} ({voice.role}): "
                                              f"{old_duration} -> {min_duration} Ticks "
                                              f"(Original: {note.original_duration}, {note_type}, "
                                              f"Pitch: {note.pitch})")
                            elif DEBUG_MODE:
                                # Weniger dramatische Korrekturen nur im Debug-Modus protokollieren
                                logger.debug(f"Korrektur bei Note {note_idx} in Stimme {voice_idx} ({voice.role}): "
                                            f"{old_duration} -> {min_duration} Ticks "
                                            f"(Original: {note.original_duration}, {note_type})")
                except Exception as e:
                    logger.error(f"Fehler bei der Überprüfung von Note {note_idx} in Stimme {voice_idx}: {e}")
                    continue
            
            if voice_corrections > 0:
                logger.info(f"Stimme {voice_idx} ({voice.role}): {voice_corrections} Notendauern korrigiert "
                           f"({voice_corrections/max(1, len(voice.notes))*100:.1f}%)")
        
        # Sammle Statistiken über die Notendauern nach der Korrektur
        if DEBUG_MODE:
            all_durations_after = []
            for voice in self.voices:
                for note in voice.notes:
                    if hasattr(note, 'adjusted_duration'):
                        all_durations_after.append(note.adjusted_duration)
            
            if all_durations_after:
                min_duration = min(all_durations_after)
                max_duration = max(all_durations_after)
                avg_duration = sum(all_durations_after) / len(all_durations_after)
                logger.debug(f"Nach Korrektur - Min: {min_duration}, Max: {max_duration}, "
                           f"Durchschnitt: {avg_duration:.2f} Ticks")
        
        if corrected_notes > 0:
            logger.info(f"Nachkorrektur: {corrected_notes} zu kurze Noten korrigiert, "
                       f"davon {critical_notes} kritische Fälle")
            self.stats['corrected_durations'] = corrected_notes
            self.stats['critical_corrections'] = critical_notes
        else:
            logger.info("Keine Korrekturen erforderlich, alle Notendauern sind angemessen")
    
    def _get_measure_number(self, note):
        """Bestimmt die Taktnummer einer Note."""
        try:
            if hasattr(note, 'measure_number'):
                return note.measure_number
                
            # Fallback: Basierend auf Startzeit
            start_time = note.original_start_time if hasattr(note, 'original_start_time') else note.start_time
            ticks_per_measure = self.ticks_per_beat * 4  # Annahme: 4/4-Takt
            return start_time // ticks_per_measure
        except Exception as e:
            logger.error(f"Fehler bei der Bestimmung der Taktnummer: {e}")
            return 0  # Standardwert im Fehlerfall

    def _get_beat_position(self, note):
        """Bestimmt die Position im Takt (0.0 - 1.0)."""
        try:
            if hasattr(note, 'metric_position'):
                return note.metric_position
                
            # Fallback: Berechne Position basierend auf Startzeit
            start_time = note.original_start_time if hasattr(note, 'original_start_time') else note.start_time
            ticks_per_measure = self.ticks_per_beat * 4  # Annahme: 4/4-Takt
            tick_in_measure = start_time % ticks_per_measure
            return tick_in_measure / ticks_per_measure
        except Exception as e:
            logger.error(f"Fehler bei der Bestimmung der Beat-Position: {e}")
            return 0.0  # Standardwert im Fehlerfall
    
    def save_midi(self, input_midi: str, output_midi: str) -> str:
        """
        Speichert die interpretierte MIDI-Datei.
        
        Args:
            input_midi: Pfad zur Original-MIDI-Datei
            output_midi: Pfad für die interpretierte MIDI-Datei
            
        Returns:
            Pfad zur gespeicherten MIDI-Datei
        """
         # Speichere das Verzeichnis, falls es noch nicht gesetzt wurde
        if not hasattr(self, 'input_directory') or not self.input_directory:
            self.input_directory = os.path.dirname(os.path.abspath(input_midi))

        logger.info(f"Speichere interpretierte MIDI-Datei: {output_midi}")
        
        # Lade die Original-MIDI
        try:
            logger.info(f"Öffne Original-MIDI für Verarbeitung: {input_midi}")
            mid = mido.MidiFile(input_midi)
        except Exception as e:
            logger.error(f"Fehler beim Öffnen der Original-MIDI-Datei: {e}")
            return input_midi  # Rückgabe der Original-Datei im Fehlerfall
        
        # Erstelle Dictionary aller angepassten Noten für schnellen Zugriff
        adjusted_notes = {}
        adjusted_count = 0
        
        try:
            for voice in self.voices:
                for note in voice.notes:
                    # Stelle sicher, dass alle benötigten Attribute vorhanden sind
                    if not all(hasattr(note, attr) for attr in ['track', 'channel', 'pitch', 'original_start_time']):
                        logger.warning(f"Note hat nicht alle erforderlichen Attribute für MIDI-Speicherung")
                        continue
                    
                    key = (note.track, note.channel, note.pitch, note.original_start_time)
                    adjusted_notes[key] = note
                    adjusted_count += 1
            
            logger.info(f"Angepasste Noten für Übertragung vorbereitet: {adjusted_count}")
        except Exception as e:
            logger.error(f"Fehler bei der Vorbereitung angepasster Noten: {e}")
            return input_midi  # Rückgabe der Original-Datei im Fehlerfall
        
        # Zeiterfassung für Performance-Analyse
        import time
        start_time = time.time()
        
        try:
            # Verarbeite jeden Track
            for track_idx, track in enumerate(mid.tracks):
                track_name = "Unbenannt"
                for msg in track:
                    if msg.is_meta and msg.type == 'track_name':
                        track_name = msg.name
                        break
                
                logger.info(f"Verarbeite Track {track_idx}: '{track_name}'")
                
                # Wir müssen Delta-Zeiten neu berechnen, daher absolute Zeit verwenden
                new_track = mido.MidiTrack()
                absolute_time = 0
                active_notes = {}  # (note, channel) -> (adjusted_end_time, original_msg)
                
                # Sammle alle Events mit absoluten Zeiten
                abs_events = []
                track_note_count = 0
                
                for msg in track:
                    absolute_time += msg.time
                    
                    if msg.type == 'note_on' and hasattr(msg, 'velocity') and msg.velocity > 0:
                        # Suche die angepasste Note
                        key = (track_idx, msg.channel, msg.note, absolute_time)
                        if key in adjusted_notes:
                            track_note_count += 1
                            
                            # Verwende die angepassten Parameter
                            adj_note = adjusted_notes[key]
                            
                            # Überprüfe, ob die Note alle benötigten angepassten Attribute hat
                            if not all(hasattr(adj_note, attr) for attr in ['adjusted_start_time', 'adjusted_duration', 'adjusted_velocity']):
                                logger.warning(f"Angepasste Note hat nicht alle benötigten Attribute")
                                # Verwende die Originalnachricht
                                abs_events.append((absolute_time, msg.copy(time=0)))
                                # Speichere die Zuordnung für das Note-Off
                                active_notes[(msg.note, msg.channel)] = (absolute_time + getattr(adj_note, 'original_duration', 0), 
                                                                        msg.note, msg.channel)
                                continue
                            
                            # Erstelle das angepasste Note-On Event
                            adj_note_on = msg.copy(
                                time=0,
                                velocity=adj_note.adjusted_velocity
                            )
                            abs_events.append((adj_note.adjusted_start_time, adj_note_on))
                            
                            # Berechne die Ende-Zeit basierend auf angepasster Dauer
                            adjusted_end_time = adj_note.adjusted_start_time + adj_note.adjusted_duration
                            
                            # Speichere die Zuordnung für das Note-Off
                            active_notes[(msg.note, msg.channel)] = (adjusted_end_time, msg.note, msg.channel)
                            
                            # Debug Details für diese Note
                            if DEBUG_MODE and track_note_count <= 5:  # Nur die ersten 5 Noten
                                logger.debug(f"Note {track_note_count}: Pitch {msg.note}, "
                                            f"Start {absolute_time} -> {adj_note.adjusted_start_time}, "
                                            f"Dauer {adj_note.original_duration} -> {adj_note.adjusted_duration}, "
                                            f"Velocity {msg.velocity} -> {adj_note.adjusted_velocity}")
                        else:
                            # Keine Anpassung gefunden, behalte original
                            abs_events.append((absolute_time, msg.copy(time=0)))
                    
                    elif msg.type == 'note_off' or (msg.type == 'note_on' and hasattr(msg, 'velocity') and msg.velocity == 0):
                        # Suche nach dem passenden Note-On
                        if (msg.note, msg.channel) in active_notes:
                            # Hole die angepasste Ende-Zeit
                            adjusted_end_time, note, channel = active_notes.pop((msg.note, msg.channel))
                            
                            # Erstelle das Note-Off Event mit angepasster Zeit
                            adj_note_off = msg.copy(time=0)
                            abs_events.append((adjusted_end_time, adj_note_off))
                        else:
                            # Kein passendes Note-On gefunden
                            abs_events.append((absolute_time, msg.copy(time=0)))
                    else:
                        # Kein Noten-Event, behalte unverändert
                        abs_events.append((absolute_time, msg.copy(time=0)))
                
                # Protokolliere Anzahl der angepassten Noten
                if track_note_count > 0:
                    logger.info(f"Track {track_idx}: {track_note_count} angepasste Noten übertragen")
                
                # Sortiere nach absoluter Zeit
                abs_events.sort(key=lambda x: x[0])
                
                # Konvertiere zurück zu Delta-Zeiten
                last_time = 0
                for abs_time, msg in abs_events:
                    delta_time = max(0, abs_time - last_time)  # Sicherstellen, dass keine negativen Deltas entstehen
                    new_msg = msg.copy(time=delta_time)
                    new_track.append(new_msg)
                    last_time = abs_time
                
                # Ersetze den Track
                mid.tracks[track_idx] = new_track
            
            # Gesamtzeiterfassung abschließen
            elapsed_time = time.time() - start_time
            logger.info(f"MIDI-Neuberechnung abgeschlossen: {elapsed_time:.2f} Sekunden")
            
            # Speichere die neue MIDI-Datei
            logger.info(f"Speichere verarbeitete MIDI-Datei: {output_midi}")
            mid.save(output_midi)
            
            # Validiere die erzeugte Datei
            if os.path.exists(output_midi):
                file_size = os.path.getsize(output_midi)
                logger.info(f"Interpretierte MIDI-Datei erfolgreich gespeichert: {output_midi} ({file_size} Bytes)")
                return output_midi
            else:
                logger.error(f"Fehler: Die MIDI-Datei konnte nicht gespeichert werden!")
                return input_midi  # Rückgabe der Original-Datei im Fehlerfall
                
        except Exception as e:
            logger.error(f"Fehler beim Speichern der MIDI-Datei: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return input_midi  # Rückgabe der Original-Datei im Fehlerfall