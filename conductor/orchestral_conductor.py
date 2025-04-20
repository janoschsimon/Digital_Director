"""
Orchestral Conductor Modul für den Digital Dirigenten
-----------------------------------------------------
Implementiert eine übergeordnete Führungsschicht für kohärente Tempo-Änderungen
über alle Stimmen hinweg basierend auf dem "Schilf im Wind"-Konzept.
"""

import logging
import numpy as np
from typing import Dict, List, Tuple, Any, Optional

# Konfiguriere Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OrchestralConductor:
    """
    Orchestraler Dirigent, der eine gemeinsame Timing-Strategie für alle
    Stimmen implementiert, um einen kohärenten "Atem" zu erzeugen.
    """
    
    def __init__(self, expressiveness=0.7, wave_strength=0.8, wave_complexity=1.0):
        """
        Initialisiert den orchestralen Dirigenten.
        
        Args:
            expressiveness: Allgemeine Ausdrucksstärke (0.0 = mechanisch, 1.0 = sehr expressiv)
            wave_strength: Stärke der Tempo-Wellenfunktion (0.0 - 1.0)
            wave_complexity: Komplexität der Wellenfunktion (0.0 = einfach, 1.0 = komplex)
        """
        self.expressiveness = expressiveness
        self.wave_strength = wave_strength
        self.wave_complexity = wave_complexity
        
        # Agogische Landkarte: Takt -> Timing-Richtung (-1.0 bis 1.0)
        # Immer mit einem leeren Dictionary initialisieren (nie None)
        self.agogic_map = {}
        
        # Strukturinformationen
        # Immer mit leeren Listen initialisieren (nie None)
        self.phrase_boundaries = []  # Liste von Taktnummern für Phrasengrenzen
        self.cadences = []           # Liste von Taktnummern für Kadenzen
        self.gravity_centers = {}    # Taktnummer -> Gravitationsstärke (0.0 - 1.0)
        
        # Statistiken
        self.stats = {
            'phrase_count': 0,
            'cadence_count': 0,
            'measure_count': 0,
            'avg_wave_amplitude': 0.0,
            'max_acceleration': 0.0,
            'max_delay': 0.0
        }
        
        logger.info(f"Orchestraler Dirigent initialisiert: Expressivität={expressiveness:.2f}, "
                   f"Wellenstärke={wave_strength:.2f}, Komplexität={wave_complexity:.2f}")
    
    def analyze_structure(self, voices: List[Any]) -> None:
        """
        Analysiert die musikalische Struktur über alle Stimmen hinweg.
        Implementiert robuste Fehlerbehandlung und Fallback-Mechanismen.
        
        Args:
            voices: Liste der Stimmen (aus note_manipulator)
        """
        if not voices:
            logger.warning("Keine Stimmen für Analyse vorhanden, erstelle Standard-Phrasenstruktur")
            self._create_default_structure(16)  # Erzeuge Standardstruktur für 16 Takte
            return
        
        try:
            logger.info(f"Analysiere musikalische Struktur: {len(voices)} Stimmen")
            
            # Sammelphase: Sammle Phraseninformationen aus allen Stimmen
            all_phrase_boundaries = []
            max_measure_found = 0
            
            for voice_idx, voice in enumerate(voices):
                # Bestimme die maximale Taktnummer für die Dimensionierung
                if hasattr(voice, 'notes') and voice.notes:
                    try:
                        for note in voice.notes:
                            measure = self._estimate_measure_number(note)
                            max_measure_found = max(max_measure_found, measure)
                    except Exception as e:
                        logger.warning(f"Fehler bei der Bestimmung der maximalen Taktnummer: {e}")
                
                # Extrahiere Phrasengrenzen aus der Stimme
                if hasattr(voice, 'phrases') and voice.phrases:
                    for phrase_start, phrase_end, phrase_type in voice.phrases:
                        try:
                            # Bestimme Taktnummern für Anfang und Ende
                            start_measure = self._get_measure_from_note_index(voice, phrase_start)
                            end_measure = self._get_measure_from_note_index(voice, phrase_end)
                            
                            if start_measure is not None and end_measure is not None:
                                all_phrase_boundaries.append((start_measure, end_measure, voice_idx, phrase_type))
                                logger.debug(f"Phrase in Stimme {voice_idx}: Takt {start_measure}-{end_measure} ({phrase_type})")
                        except Exception as e:
                            logger.warning(f"Fehler bei der Verarbeitung einer Phrase in Stimme {voice_idx}: {e}")
            
            # Analysephase: Finde überlappende Phrasen für global wichtige Grenzen
            if all_phrase_boundaries:
                # Sortiere nach Anfangstakt
                all_phrase_boundaries.sort(key=lambda x: x[0])
                
                # Maximaler Takt für Agogik-Map-Dimensionierung
                max_measure = max(end for _, end, _, _ in all_phrase_boundaries)
                self.stats['measure_count'] = max(max_measure + 1, max_measure_found + 1)
                
                # Einfache Heuristik: Gruppiere ähnliche Grenzen
                current_group = []
                grouped_boundaries = []
                
                for boundary in all_phrase_boundaries:
                    start, end, voice_idx, phrase_type = boundary
                    
                    # Wenn die Gruppe leer ist oder dieser Anfang nahe am vorherigen ist
                    if not current_group or abs(start - current_group[-1][0]) <= 1:
                        current_group.append(boundary)
                    else:
                        # Neue Gruppe beginnen
                        grouped_boundaries.append(current_group)
                        current_group = [boundary]
                
                # Letzte Gruppe hinzufügen
                if current_group:
                    grouped_boundaries.append(current_group)
                
                # Für jede Gruppe, bestimme den gemeinsamen Anfang/Ende
                self.phrase_boundaries = []  # Initialisiere als leere Liste
                for group in grouped_boundaries:
                    if len(group) >= max(1, len(voices) // 3):  # Mindestens 1/3 der Stimmen
                        # Berechne durchschnittliche Grenzen
                        avg_start = sum(start for start, _, _, _ in group) / len(group)
                        avg_end = sum(end for _, end, _, _ in group) / len(group)
                        
                        # Runde auf ganze Taktnummern
                        phrase_start = round(avg_start)
                        phrase_end = round(avg_end)
                        
                        # Füge zu globalem Phrasenverständnis hinzu
                        self.phrase_boundaries.append((phrase_start, phrase_end))
                        
                        # Ende einer Phrase könnte eine Kadenz sein
                        cadence_likelihood = len(group) / len(voices)
                        if cadence_likelihood >= 0.5:  # Wenn mindestens 50% der Stimmen hier enden
                            self.cadences.append(phrase_end)
                            # Starkes Gravitationszentrum am Kadenzpunkt
                            self.gravity_centers[phrase_end] = min(1.0, 0.7 + cadence_likelihood * 0.3)
                            logger.debug(f"Kadenz bei Takt {phrase_end} erkannt (Wahrscheinlichkeit: {cadence_likelihood:.2f})")
                
                # Aktualisiere Statistiken
                self.stats['phrase_count'] = len(self.phrase_boundaries)
                self.stats['cadence_count'] = len(self.cadences)
                
                logger.info(f"Strukturanalyse abgeschlossen: {self.stats['phrase_count']} Phrasen, "
                          f"{self.stats['cadence_count']} Kadenzen erkannt")
            else:
                logger.warning("Keine Phraseninformationen in den Stimmen gefunden, erstelle Standard-Phrasen")
                self._create_default_structure_from_voices(voices, max_measure_found)
                
        except Exception as e:
            logger.error(f"Fehler in der Strukturanalyse: {e}")
            logger.error("Erstelle Standard-Fallback-Struktur")
            import traceback
            logger.error(traceback.format_exc())
            
            # Fallback: Verwende eine einfache Standardstruktur
            self._create_default_structure(max(16, max_measure_found + 1))
    
    def _create_default_structure_from_voices(self, voices, max_measure):
        """
        Erstellt eine Standard-Phrasenstruktur basierend auf der maximalen Taktzahl.
        
        Args:
            voices: Liste der Stimmen
            max_measure: Maximale gefundene Taktnummer
        """
        if max_measure <= 0:
            # Schätze die maximale Anzahl an Takten
            max_measure = 0
            for voice in voices:
                if hasattr(voice, 'notes') and voice.notes:
                    try:
                        last_note = voice.notes[-1]
                        measure = self._estimate_measure_number(last_note)
                        max_measure = max(max_measure, measure)
                    except Exception as e:
                        logger.warning(f"Fehler bei der Bestimmung der maximalen Taktnummer: {e}")
        
        # Sicherheitsprüfung: Mindestens 16 Takte
        max_measure = max(16, max_measure)
        
        # Erstelle Standardphrasen (8 Takte)
        self.stats['measure_count'] = max_measure + 1
        self.phrase_boundaries = []  # Initialisiere als leere Liste
        self.cadences = []          # Initialisiere als leere Liste
        self.gravity_centers = {}   # Initialisiere als leeres Dictionary
        
        for i in range(0, max_measure, 8):
            end = min(i+7, max_measure)
            self.phrase_boundaries.append((i, end))
            
            # Jedes Ende einer 8-Takt-Phrase ist eine leichte Kadenz
            self.cadences.append(end)
            self.gravity_centers[end] = 0.6  # Moderate Gravitationsstärke
            
            # Auch die Mitte einer Phrase hat eine gewisse Gravitation
            mid = i + 4
            if mid < end:
                self.gravity_centers[mid] = 0.3  # Schwächere Gravitationsstärke
        
        self.stats['phrase_count'] = len(self.phrase_boundaries)
        self.stats['cadence_count'] = len(self.cadences)
        
        logger.info(f"Standard-Phrasenstruktur erstellt: {self.stats['phrase_count']} 8-Takt-Phrasen "
                  f"für {self.stats['measure_count']} Takte")
    
    def _create_default_structure(self, measure_count):
        """
        Erstellt eine einfache Standard-Phrasenstruktur mit 8-Takt-Phrasen.
        
        Args:
            measure_count: Anzahl der Takte
        """
        # Stelle sicher, dass measure_count eine gültige Zahl ist
        if not isinstance(measure_count, int) or measure_count <= 0:
            measure_count = 16  # Standardwert
        
        self.stats['measure_count'] = measure_count
        self.phrase_boundaries = []  # Initialisiere als leere Liste
        self.cadences = []          # Initialisiere als leere Liste
        self.gravity_centers = {}   # Initialisiere als leeres Dictionary
        
        for i in range(0, measure_count, 8):
            end = min(i+7, measure_count-1)
            self.phrase_boundaries.append((i, end))
            
            # Jedes Ende einer 8-Takt-Phrase ist eine leichte Kadenz
            self.cadences.append(end)
            self.gravity_centers[end] = 0.6  # Moderate Gravitationsstärke
            
            # Auch die Mitte einer Phrase hat eine gewisse Gravitation
            mid = i + 4
            if mid < end:
                self.gravity_centers[mid] = 0.3  # Schwächere Gravitationsstärke
        
        self.stats['phrase_count'] = len(self.phrase_boundaries)
        self.stats['cadence_count'] = len(self.cadences)
        
        logger.info(f"Fallback-Phrasenstruktur erstellt: {self.stats['phrase_count']} 8-Takt-Phrasen "
                  f"für {measure_count} Takte")
    
    def create_agogic_map(self) -> None:
        """
        Erzeugt die agogische Landkarte (Timing-Richtungen pro Takt)
        basierend auf der Strukturanalyse.
        Implementiert robuste Fehlerbehandlung.
        """
        try:
            measure_count = self.stats.get('measure_count', 0)
            if measure_count <= 0:
                logger.warning("Keine Takte für Agogik-Map vorhanden, erstelle Standard-Map für 16 Takte")
                measure_count = 16
                self.stats['measure_count'] = measure_count
            
            logger.info(f"Erstelle agogische Landkarte für {measure_count} Takte")
            
            # 1. Erzeuge Basiswellenfunktion
            try:
                base_wave = self._generate_wave_function(
                    length=measure_count,
                    amplitude=self.wave_strength,
                    frequency=0.15,  # Ca. alle 6-7 Takte ein Zyklus
                    complexity=self.wave_complexity
                )
            except Exception as e:
                logger.error(f"Fehler beim Erzeugen der Basiswellenfunktion: {e}")
                # Fallback: Einfachere Wellenfunktion ohne Fehler
                base_wave = self._generate_simple_wave(measure_count, self.wave_strength)
            
            # 2. Modifiziere die Welle basierend auf strukturellen Merkmalen
            modified_wave = list(base_wave)  # Kopie erstellen
            
            # Sicherheitsprüfung für phrase_boundaries
            if not isinstance(self.phrase_boundaries, list):
                logger.warning("phrase_boundaries ist kein Liste, setze auf leere Liste")
                self.phrase_boundaries = []
            
            # Sicherheitsprüfung für cadences
            if not isinstance(self.cadences, list):
                logger.warning("cadences ist keine Liste, setze auf leere Liste")
                self.cadences = []
            
            # Sicherheitsprüfung für gravity_centers
            if not isinstance(self.gravity_centers, dict):
                logger.warning("gravity_centers ist kein Dictionary, setze auf leeres Dictionary")
                self.gravity_centers = {}
            
            # A. Phrasengrenzen betonen
            for start, end in self.phrase_boundaries:
                if 0 <= end < measure_count:
                    # Ritardando am Phrasenende
                    phrase_end_factor = min(1.0, 0.6 + self.expressiveness * 0.4)
                    if end > 0 and end < measure_count - 1:
                        # Vorletzter Takt: moderate Verzögerung
                        modified_wave[end-1] = min(modified_wave[end-1] + 0.3 * phrase_end_factor, 1.0)
                        # Letzter Takt: stärkere Verzögerung
                        modified_wave[end] = min(modified_wave[end] + 0.6 * phrase_end_factor, 1.0)
                    
                if 0 <= start < measure_count:
                    # Leichte Beschleunigung nach Phrasenanfang
                    if start+1 < measure_count:
                        modified_wave[start+1] = max(modified_wave[start+1] - 0.25 * self.expressiveness, -1.0)
            
            # B. Kadenzen stark betonen
            for cadence in self.cadences:
                if 0 <= cadence < measure_count:
                    # Starkes Ritardando bei Kadenzen
                    cadence_factor = min(1.0, 0.8 + self.expressiveness * 0.2)
                    modified_wave[cadence] = min(modified_wave[cadence] + 0.8 * cadence_factor, 1.0)
                    
                    # Auch den Takt davor betonen, aber weniger stark
                    if cadence > 0:
                        modified_wave[cadence-1] = min(modified_wave[cadence-1] + 0.5 * cadence_factor, 1.0)
            
            # C. Gravitationszentren verstärken vorhandene Tendenzen
            for measure, strength in self.gravity_centers.items():
                if 0 <= measure < measure_count:
                    # Verstärke die vorhandene Tendenz proportional zur Gravitationsstärke
                    gravity_effect = strength * self.expressiveness * 0.4
                    if modified_wave[measure] > 0:
                        modified_wave[measure] = min(modified_wave[measure] + gravity_effect, 1.0)
                    elif modified_wave[measure] < 0:
                        modified_wave[measure] = max(modified_wave[measure] - gravity_effect, -1.0)
            
            # 3. Fülle die agogische Landkarte
            self.agogic_map = {i: modified_wave[i] for i in range(measure_count)}
            
            # 4. Aktualisiere Statistiken
            self.stats['avg_wave_amplitude'] = sum(abs(v) for v in modified_wave) / measure_count
            self.stats['max_acceleration'] = abs(min(modified_wave)) if min(modified_wave) < 0 else 0
            self.stats['max_delay'] = max(modified_wave) if max(modified_wave) > 0 else 0
            
            logger.info(f"Agogische Landkarte erstellt: "
                      f"durchschnittliche Amplitude={self.stats['avg_wave_amplitude']:.2f}, "
                      f"max. Beschleunigung={self.stats['max_acceleration']:.2f}, "
                      f"max. Verzögerung={self.stats['max_delay']:.2f}")
            # EXTRA-ABSICHERUNG - STELLE SICHER, DASS agogic_map EIN GÜLTIGES DICTIONARY IST
            if not hasattr(self, 'agogic_map') or self.agogic_map is None:
                logger.critical("KRITISCH: agogic_map existiert nicht oder ist None am Ende von create_agogic_map!")
                self.agogic_map = {0: 0}  # Minimales gültiges Dictionary
            elif not isinstance(self.agogic_map, dict):
                logger.critical(f"KRITISCH: agogic_map hat falschen Typ: {type(self.agogic_map)}")
                self.agogic_map = {0: 0}  # Minimales gültiges Dictionary     


        except Exception as e:
            logger.error(f"Fehler beim Erstellen der agogischen Landkarte: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # Fallback: Erstelle eine sehr einfache agogische Landkarte
            logger.warning("Erstelle Fallback-agogische Landkarte")
            self._create_fallback_agogic_map()
    
    def _create_fallback_agogic_map(self):
        """
        Erstellt eine sehr einfache Fallback-agogische Landkarte bei Fehlern.
        """
        measure_count = self.stats.get('measure_count', 16)
        if measure_count <= 0:
            measure_count = 16
        
        # Erstelle eine einfache Sinuswelle als Fallback
        simple_wave = self._generate_simple_wave(measure_count, self.wave_strength * 0.7)
        
        # Fülle die agogische Landkarte
        self.agogic_map = {i: simple_wave[i] for i in range(measure_count)}
        
        # Aktualisiere Statistiken
        self.stats['avg_wave_amplitude'] = sum(abs(v) for v in simple_wave) / measure_count
        self.stats['max_acceleration'] = abs(min(simple_wave)) if min(simple_wave) < 0 else 0
        self.stats['max_delay'] = max(simple_wave) if max(simple_wave) > 0 else 0
        
        logger.info(f"Fallback-agogische Landkarte erstellt: "
                  f"durchschnittliche Amplitude={self.stats['avg_wave_amplitude']:.2f}")
    
    def _generate_simple_wave(self, length, amplitude=0.5):
        """
        Erzeugt eine einfache Sinuswelle ohne komplexe Berechnungen.
        
        Args:
            length: Anzahl der Takte
            amplitude: Maximale Stärke der Tempo-Änderung (0-1)
            
        Returns:
            List[float]: Einfache Sinuswellenfunktion
        """
        try:
            # Grundlegende Überprüfungen
            if length <= 0:
                length = 16
            if amplitude <= 0:
                amplitude = 0.5
                
            # Einfache Sinuswelle
            result = []
            for i in range(length):
                # Einfache Sinusfunktion mit Periode von 8 Takten
                value = amplitude * np.sin(2 * np.pi * i / 8)
                result.append(value)
            return result
        except Exception as e:
            logger.error(f"Fehler beim Erzeugen der einfachen Welle: {e}")
            # Noch einfacherer Fallback: Alternierende Werte
            return [amplitude * (0.5 if i % 2 == 0 else -0.5) for i in range(length)]
    
    def get_timing_direction(self, measure_number: int, beat_position: Optional[float] = None) -> float:
        """
        Gibt die Timing-Richtung für einen bestimmten Takt zurück.
        
        Args:
            measure_number: Taktnummer
            beat_position: Position im Takt (0.0 - 1.0, optional)
            
        Returns:
            Float zwischen -1.0 (starke Beschleunigung) und 1.0 (starke Verzögerung)
        """
        try:
            # Grundlegende Überprüfungen
            if not isinstance(self.agogic_map, dict):
                logger.warning("agogic_map ist kein Dictionary, erstelle neue Map")
                self._create_fallback_agogic_map()
                
            if not self.agogic_map:
                # Keine Agogik-Map vorhanden, verwende neutralen Wert
                logger.warning("Agogische Landkarte leer, verwende neutralen Wert")
                return 0.0
            
            # Begrenze auf verfügbare Takte
            max_measure = max(self.agogic_map.keys()) if self.agogic_map else 0
            measure_number = max(0, min(measure_number, max_measure))
            
            # Grundwert aus der agogischen Landkarte
            base_direction = self.agogic_map.get(measure_number, 0.0)
            
            # Falls Beat-Position angegeben, verfeinere den Wert
            if beat_position is not None:
                # Validiere beat_position
                if not isinstance(beat_position, (int, float)) or beat_position < 0 or beat_position > 1:
                    beat_position = 0.5  # Standardwert in der Mitte
                
                # Kadenz- oder Phrasenendeneffekt verstärken gegen Ende des Taktes
                if measure_number in self.cadences or any(end == measure_number for _, end in self.phrase_boundaries):
                    if beat_position > 0.5:
                        # Verstärke Ritardando in der zweiten Takthälfte
                        enhancement = (beat_position - 0.5) * 2 * 0.3  # Max +0.3 am Taktende
                        return min(base_direction + enhancement, 1.0)
                
                # Bei Gravitationszentren, Effekt zur Taktmitte hin verstärken
                if measure_number in self.gravity_centers:
                    center_distance = abs(beat_position - 0.5)  # 0 in der Mitte, 0.5 an den Rändern
                    center_effect = (0.5 - center_distance) * 2 * 0.2  # Max +0.2 in der Mitte
                    if base_direction > 0:
                        return min(base_direction + center_effect, 1.0)
                    elif base_direction < 0:
                        return max(base_direction - center_effect, -1.0)
            
            return base_direction
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Timing-Richtung: {e}")
            return 0.0  # Neutraler Wert als Fallback
    
    def _generate_wave_function(self, length: int, amplitude: float = 0.8, 
                               frequency: float = 0.2, complexity: float = 1.0) -> List[float]:
        """
        Erzeugt eine Wellenfunktion für Tempo-Modulationen.
        
        Args:
            length: Anzahl der Takte
            amplitude: Maximale Stärke der Tempo-Änderung (0-1)
            frequency: Frequenz der Welle (höhere Werte = mehr Schwankungen)
            complexity: Komplexität der Überlagerungen (0-1)
            
        Returns:
            List[float]: Timing-Richtungsfaktoren pro Takt (-1.0 bis 1.0)
        """
        # Grundlegende Überprüfungen
        if length <= 0:
            length = 16
        if amplitude <= 0:
            amplitude = 0.5
        if frequency <= 0:
            frequency = 0.2
        if complexity < 0 or complexity > 1:
            complexity = 0.5
            
        try:
            # Basiswelle mit Sinus
            x = np.linspace(0, 2*np.pi*frequency*length, length)
            wave = amplitude * np.sin(x)
            
            if complexity > 0:
                # Füge Variationen hinzu für mehr Natürlichkeit, skaliert mit Komplexität
                # Kurze, mittlere und lange Wellen überlagern
                short_waves = 0.3 * amplitude * complexity * np.sin(x * 3.1 + np.random.rand() * np.pi)
                medium_waves = 0.2 * amplitude * complexity * np.sin(x * 1.7 + np.random.rand() * np.pi)
                long_waves = 0.1 * amplitude * complexity * np.sin(x * 0.5 + np.random.rand() * np.pi)
                
                # Kombiniere zu einer komplexen Welle
                combined_wave = wave + short_waves + medium_waves + long_waves
            else:
                combined_wave = wave
            
            # Normalisiere auf Bereich [-amplitude, amplitude]
            max_val = max(abs(np.max(combined_wave)), abs(np.min(combined_wave)))
            if max_val > 0:
                normalized_wave = combined_wave / max_val * amplitude
            else:
                normalized_wave = combined_wave
            
            return normalized_wave.tolist()
        except Exception as e:
            logger.error(f"Fehler beim Erzeugen der komplexen Wellenfunktion: {e}")
            # Fallback zu einfacherer Funktion
            return self._generate_simple_wave(length, amplitude)
    
    def _get_measure_from_note_index(self, voice: Any, note_index: int) -> Optional[int]:
        """
        Ermittelt die Taktnummer für eine Note basierend auf ihrem Index in der Stimme.
        
        Args:
            voice: Die Stimme
            note_index: Index der Note in der Stimme
            
        Returns:
            Taktnummer oder None, wenn nicht ermittelbar
        """
        try:
            if not hasattr(voice, 'notes') or not voice.notes or note_index >= len(voice.notes):
                return None
                
            note = voice.notes[note_index]
            return self._estimate_measure_number(note)
        except Exception as e:
            logger.error(f"Fehler beim Ermitteln der Taktnummer aus Note {note_index}: {e}")
            return None
    def as_dict(self) -> dict:
        """
        Gibt eine Dictionary-Repräsentation des Dirigenten zurück.
        Dadurch wird sichergestellt, dass agogic_map, phrase_boundaries etc. im richtigen Format vorliegen.
        """
        return {
            'agogic_map': self.agogic_map if isinstance(self.agogic_map, dict) else {},
            'phrase_boundaries': self.phrase_boundaries if isinstance(self.phrase_boundaries, list) else [],
            'cadences': self.cadences if isinstance(self.cadences, list) else [],
            'gravity_centers': self.gravity_centers if isinstance(self.gravity_centers, dict) else {},
            'stats': self.stats if isinstance(self.stats, dict) else {}
        }
    
    def _estimate_measure_number(self, note: Any) -> int:
        """
        Schätzt die Taktnummer einer Note basierend auf ihren Zeitinformationen.
        
        Args:
            note: Die Note
            
        Returns:
            Geschätzte Taktnummer
        """
        try:
            # Diese Funktion müsste an die spezifischen Zeitinformationen in den Noten angepasst werden
            if hasattr(note, 'measure_number'):
                return note.measure_number
                
            # Fallback: Grobe Schätzung basierend auf der Startzeit (480 Ticks pro Viertel, 4/4-Takt)
            if hasattr(note, 'original_start_time'):
                # Annahme: 4/4-Takt mit 1920 Ticks pro Takt (480*4)
                ticks_per_measure = 1920  # Anpassbar je nach tatsächlichem Takt
                return note.original_start_time // ticks_per_measure
            elif hasattr(note, 'start_time'):
                # Alternative Fallback-Methode
                ticks_per_measure = 1920
                return note.start_time // ticks_per_measure
            
            # Kein geeignetes Attribut gefunden
            return 0
        except Exception as e:
            logger.error(f"Fehler bei der Schätzung der Taktnummer: {e}")
            return 0  # Standardwert im Fehlerfall