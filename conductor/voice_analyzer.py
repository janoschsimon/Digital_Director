"""
Stimmenanalyse Modul für den Digital Dirigenten
-----------------------------------------------
Enthält Klassen für die Analyse und Klassifikation von Stimmen und Noten.
"""

import logging
from typing import List, Tuple, Dict, Any, Optional

# Konfiguriere Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NoteProperties:
    """
    Eigenschaften einer Note für die musikalische Interpretation.
    Speichert sowohl originale als auch angepasste Notenwerte.
    """
    
    def __init__(self, pitch, velocity, start_time, duration, track, channel):
        # Originale MIDI-Eigenschaften
        self.pitch = pitch
        self.velocity = velocity
        
        # Beide Attribut-Versionen anbieten für vollständige Kompatibilität
        # Alte Namen für Abwärtskompatibilität
        self.start_time = start_time
        self.duration = duration
        
        # Korrekte Bezeichnungen, die im Rest des Codes erwartet werden
        self.original_start_time = start_time
        self.original_duration = duration
        
        self.track = track
        self.channel = channel
        
        # Angepasste Werte (werden durch den Interpreter gesetzt)
        self.adjusted_start_time = start_time
        self.adjusted_duration = duration
        self.adjusted_velocity = velocity
        
        # Musikalische Eigenschaften (werden durch die Analyse gesetzt)
        self.is_melody = False
        self.is_bass = False
        self.is_inner_voice = False
        self.metric_position = 0.0  # 0.0 = Taktanfang, 0.25 = Viertel, etc.
        self.phrase_position = 0.0  # 0.0 = Phrasenanfang, 1.0 = Phrasenende
        self.harmonic_importance = 0.0  # 0.0 = unwichtig, 1.0 = sehr wichtig
        self.is_downbeat = False  # Ob die Note auf einer betonten Zählzeit liegt
        
        # Artikulationsinformationen
        self.articulation = None  # 'staccato', 'legato', 'accent', etc.
        
        # Beziehung zu anderen Noten
        self.next_note = None  # Nächste Note in der Stimme (falls vorhanden)
        self.prev_note = None  # Vorherige Note in der Stimme (falls vorhanden)
        self.interval_to_next = 0  # Intervall zur nächsten Note (in Halbtonschritten)
        self.interval_to_prev = 0  # Intervall zur vorherigen Note
    
    def calculate_intervals(self):
        """Berechnet Intervalle zu benachbarten Noten."""
        if self.next_note:
            self.interval_to_next = self.next_note.pitch - self.pitch
        if self.prev_note:
            self.interval_to_prev = self.pitch - self.prev_note.pitch

class MusicalVoice:
    """
    Repräsentiert eine musikalische Stimme mit ihren Eigenschaften.
    Analysiert die Rolle und charakteristischen Merkmale.
    """
    
    def __init__(self, track_index, channel):
        self.track_index = track_index
        self.channel = channel
        self.notes = []  # Liste von NoteProperties
        self.role = "unknown"  # 'melody', 'bass', 'inner_voice'
        self.instrument_type = "unknown"
        self.avg_pitch = 0
        self.pitch_range = (0, 0)
        self.rhythmic_density = 0  # Noten pro Takt (approximativ)
        
        # Phrasen-Informationen
        self.phrases = []  # Liste von (start_idx, end_idx, type)
    
    def analyze(self, ticks_per_beat=480):
        """
        Analysiert die Eigenschaften dieser Stimme.
        
        Args:
            ticks_per_beat: MIDI-Ticks pro Viertelnote
        """
        if not self.notes:
            logger.warning("Keine Noten zum Analysieren vorhanden")
            return
            
        # Sortiere die Noten nach Startzeit
        self.notes.sort(key=lambda n: n.original_start_time)
        
        # Verbinde aufeinanderfolgende Noten
        for i in range(len(self.notes) - 1):
            self.notes[i].next_note = self.notes[i+1]
            self.notes[i+1].prev_note = self.notes[i]
        
        # Berechne Intervalle
        for note in self.notes:
            note.calculate_intervals()
        
        # Analysiere Tonhöhen
        pitches = [note.pitch for note in self.notes]
        if pitches:
            self.avg_pitch = sum(pitches) / len(pitches)
            self.pitch_range = (min(pitches), max(pitches))
        
        # Bestimme Rolle basierend auf Tonhöhen und anderen Merkmalen
        if self.avg_pitch > 70:  # Hohe Töne
            self.role = "melody"
        elif self.avg_pitch < 50:  # Tiefe Töne
            self.role = "bass"
        else:
            self.role = "inner_voice"
        
        # Setze Rolleninformation für jede Note
        for note in self.notes:
            if self.role == "melody":
                note.is_melody = True
            elif self.role == "bass":
                note.is_bass = True
            else:
                note.is_inner_voice = True
        
        # Berechne rhythmische Dichte
        if self.notes:
            first_time = self.notes[0].original_start_time
            last_time = self.notes[-1].original_start_time + self.notes[-1].original_duration
            duration_in_beats = (last_time - first_time) / ticks_per_beat
            if duration_in_beats > 0:
                self.rhythmic_density = len(self.notes) / duration_in_beats
        
        # Erkenne Phrasen
        self._detect_phrases(ticks_per_beat)
        
        # Berechne metrische Positionen
        self._calculate_metric_positions(ticks_per_beat)
        
        # Weise Phrasenpositionen zu
        self._assign_phrase_positions()
        
        logger.info(f"Stimme (Track {self.track_index}, Kanal {self.channel}) analysiert: "
                   f"Rolle={self.role}, Tonhöhe={self.avg_pitch:.1f}, "
                   f"Bereich={self.pitch_range}, {len(self.phrases)} Phrasen")
    
    def _detect_phrases(self, ticks_per_beat):
        """
        Erkennt Phrasen basierend auf Pausen und langen Noten.
        
        Args:
            ticks_per_beat: MIDI-Ticks pro Viertelnote
        """
        if not self.notes:
            return
            
        # Sortiere Noten nach Startzeit
        sorted_notes = sorted(self.notes, key=lambda n: n.original_start_time)
        
        # Phrasenstart markieren
        current_phrase_start = 0
        
        for i in range(1, len(sorted_notes)):
            # Prüfe auf Pause zwischen Noten
            prev_end = sorted_notes[i-1].original_start_time + sorted_notes[i-1].original_duration
            current_start = sorted_notes[i].original_start_time
            gap = current_start - prev_end
            
            # Kriterien für das Ende einer Phrase:
            # 1. Signifikante Pause (> Länge einer Viertelnote)
            is_gap = gap > ticks_per_beat
            
            # 2. Lange Note (länger als eine halbe Note)
            is_long_note = sorted_notes[i-1].original_duration > ticks_per_beat * 2
            
            # 3. Großes Intervall (> Quinte)
            is_large_interval = abs(sorted_notes[i].pitch - sorted_notes[i-1].pitch) > 7
            
            if is_gap or is_long_note or is_large_interval:
                # Ende der Phrase gefunden
                if i - current_phrase_start > 2:  # Mindestens 3 Noten für eine Phrase
                    self.phrases.append((current_phrase_start, i-1, "standard"))
                
                # Neue Phrase beginnt
                current_phrase_start = i
        
        # Letzte Phrase hinzufügen, wenn sie lang genug ist
        if len(sorted_notes) - current_phrase_start > 2:
            self.phrases.append((current_phrase_start, len(sorted_notes)-1, "final"))
        
        logger.debug(f"Phrasen erkannt: {self.phrases}")
    
    def _assign_phrase_positions(self):
        """Weist jeder Note eine Position innerhalb ihrer Phrase zu."""
        if not self.phrases:
            return
            
        # Weise jedem Noten-Index eine Phrase zu
        note_to_phrase = {}
        for phrase_idx, (start_idx, end_idx, phrase_type) in enumerate(self.phrases):
            for note_idx in range(start_idx, end_idx + 1):
                if 0 <= note_idx < len(self.notes):
                    note_to_phrase[note_idx] = (phrase_idx, start_idx, end_idx, phrase_type)
        
        # Setze Phrasenposition für jede Note
        for i in range(len(self.notes)):
            if i in note_to_phrase:
                phrase_idx, start_idx, end_idx, phrase_type = note_to_phrase[i]
                phrase_length = end_idx - start_idx + 1
                position_in_phrase = (i - start_idx) / max(1, phrase_length)
                self.notes[i].phrase_position = position_in_phrase
    
    def _calculate_metric_positions(self, ticks_per_beat):
        """
        Berechnet die metrische Position jeder Note (im Takt).
        
        Args:
            ticks_per_beat: MIDI-Ticks pro Viertelnote
        """
        if not self.notes:
            return
            
        # Annahmen für 4/4-Takt (kann später verbessert werden)
        ticks_per_measure = 4 * ticks_per_beat  # 4/4-Takt
        
        for note in self.notes:
            # Berechne Taktposition (0.0 - 1.0)
            note.metric_position = (note.original_start_time % ticks_per_measure) / ticks_per_measure
            
            # Markiere Noten auf betonten Zählzeiten (1 und 3 in 4/4)
            beat_in_measure = (note.original_start_time % ticks_per_measure) / ticks_per_beat
            note.is_downbeat = (beat_in_measure < 0.1) or (abs(beat_in_measure - 2.0) < 0.1)