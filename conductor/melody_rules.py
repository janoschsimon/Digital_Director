"""
Melodische Interpretationsregeln für den Digital Dirigenten
---------------------------------------------------------
Enthält Regeln speziell für Melodiestimmen.
"""

import logging
from .rule_base import InterpretationRule, InterpretationContext

logger = logging.getLogger(__name__)

class PhraseStartRule(InterpretationRule):
    """Passt Noten am Phrasenanfang an: Verzögert erste, aber beschleunigt zweite Note."""
    
    def __init__(self, enabled=True, params=None):
        default_params = {
            "first_note_timing_factor": 0.7,     # Verzögerung für erste Note
            "second_note_timing_factor": -0.3,   # Beschleunigung für zweite Note (NEU)
            "velocity_increase_factor": 0.07,    # Velocity-Erhöhung
            "min_duration": 3,                   # Minimale Notendauer nach Anpassung
            "phrase_position_threshold": 0.1     # Position innerhalb der Phrase für Anwendung
        }
        
        if params:
            default_params.update(params)
        
        super().__init__(
            name="phrase_start",
            description="Passt Noten am Phrasenanfang an",
            enabled=enabled,
            params=default_params
        )
    
    def apply(self, note, voice, context):
        # Nur anwenden, wenn die Note einen Phrasenpositionswert hat
        if hasattr(note, 'phrase_position') and note.phrase_position is not None:
            threshold = self.get_param("phrase_position_threshold")
            
            # Erste Note in der Phrase
            if note.phrase_position < threshold:
                # Parameter für die erste Note
                delay_factor = self.get_param("first_note_timing_factor")
                velocity_factor = self.get_param("velocity_increase_factor")
                min_duration = self.get_param("min_duration")
                
                # Berechne die tatsächliche Verzögerung
                delay = int(context.max_timing_change * delay_factor)
                
                # Anpassungen vornehmen
                note.adjusted_start_time += delay
                note.adjusted_duration = max(min_duration, note.adjusted_duration - delay)
                note.adjusted_velocity = min(127, int(note.velocity * (1 + velocity_factor)))
                
                return True
            
            # Zweite Note in der Phrase (neue Behandlung)
            elif note.phrase_position < (threshold * 2) and note.prev_note:
                # Parameter für die zweite Note
                accel_factor = self.get_param("second_note_timing_factor")
                
                # Beschleunigung für zweite Note
                accel = int(context.max_timing_change * accel_factor)
                
                # Anpassungen vornehmen
                note.adjusted_start_time += accel
                
                # Leichte Dynamik-Boost für vorwärtsdrängendes Gefühl
                note.adjusted_velocity = min(127, int(note.adjusted_velocity * 1.03))
                
                return True
        
        return False


class PhraseEndRule(InterpretationRule):
    """Verzögert und dämpft Noten am Phrasenende, lange Noten werden verlängert."""
    
    def __init__(self, enabled=True, params=None):
        default_params = {
            "timing_delay_factor": 0.8,
            "velocity_decrease_factor": 0.05,
            "length_increase_factor": 0.1,
            "length_increase_threshold": 480  # Halbe Note (bei 480 Ticks pro Beat)
        }
        
        if params:
            default_params.update(params)
        
        super().__init__(
            name="phrase_end",
            description="Verzögert und dämpft Noten am Phrasenende",
            enabled=enabled,
            params=default_params
        )
    
    def apply(self, note, voice, context):
        if hasattr(note, 'phrase_position') and note.phrase_position is not None:
            # Nur für Noten am Phrasenende (letzte 10%)
            if note.phrase_position > 0.9:
                # Parameter holen
                delay_factor = self.get_param("timing_delay_factor")
                velocity_factor = self.get_param("velocity_decrease_factor")
                length_factor = self.get_param("length_increase_factor")
                length_threshold = self.get_param("length_increase_threshold")
                
                # Berechne die tatsächliche Verzögerung
                delay = int(context.max_timing_change * delay_factor)
                
                # Anpassungen vornehmen
                note.adjusted_start_time += delay
                
                # Lange Noten werden länger gehalten
                if note.original_duration > length_threshold:
                    length_increase = 1 + length_factor * context.articulation_strength
                    note.adjusted_duration = int(note.adjusted_duration * length_increase)
                
                # Leiser spielen
                note.adjusted_velocity = max(1, int(note.velocity * (1 - velocity_factor * context.dynamics_strength)))
                
                return True
        
        return False


class PreLeapRule(InterpretationRule):
    """Passt Noten vor großen Intervallsprüngen an - verkürzt vor aufsteigenden, verlangsamt vor absteigenden."""
    
    def __init__(self, enabled=True, params=None):
        default_params = {
            "up_acceleration_factor": -0.12,  # Beschleunigung vor aufsteigenden Sprüngen (neu)
            "down_delay_factor": 0.15,       # Verzögerung vor absteigenden Sprüngen (verstärkt)
            "reduction_factor": 0.12,        # Dauerverkürzung (bestehendes Verhalten)
            "interval_threshold": 4,         # Mindestintervall in Halbtonschritten
            "min_duration": 3                # Minimale Notendauer nach Verkürzung
        }
        
        if params:
            default_params.update(params)
        
        super().__init__(
            name="pre_leap",
            description="Passt Noten vor großen Intervallsprüngen an",
            enabled=enabled,
            params=default_params
        )
    
    def apply(self, note, voice, context):
        # Prüfe, ob die Note ein Intervall zur nächsten hat
        if hasattr(note, 'interval_to_next') and note.interval_to_next is not None:
            interval = note.interval_to_next
            threshold = self.get_param("interval_threshold")
            
            # Nur bei großen Intervallen
            if abs(interval) > threshold and note.next_note:
                # Parameter holen
                reduction_factor = self.get_param("reduction_factor")
                min_duration = self.get_param("min_duration")
                
                # Unterschiedliches Timing je nach Richtung des Sprungs
                if interval > 0:  # Aufsteigender Sprung
                    # Beschleunigung vor aufsteigenden Sprüngen
                    timing_factor = self.get_param("up_acceleration_factor")
                    timing_change = int(context.max_timing_change * timing_factor)
                    note.adjusted_start_time += timing_change
                else:  # Absteigender Sprung
                    # Verzögerung vor absteigenden Sprüngen
                    timing_factor = self.get_param("down_delay_factor")
                    timing_change = int(context.max_timing_change * timing_factor)
                    note.adjusted_start_time += timing_change
                
                # Berechne den Verkürzungsfaktor
                factor = 1.0 - (reduction_factor * context.articulation_strength)
                
                # Notendauer anpassen
                original_duration = note.adjusted_duration
                note.adjusted_duration = max(min_duration, int(note.adjusted_duration * factor))
                
                # Zweiter Ton: Zielton des Sprungs betonen (ohne Artikulation zu setzen!)
                if note.next_note:
                    note.next_note.adjusted_velocity = min(127, 
                        int(note.next_note.velocity * (1 + 0.12 * context.dynamics_strength)))
                
                return True
        
        return False


class LocalPeakRule(InterpretationRule):
    """Betont lokale melodische Höhepunkte durch Verzögerung und Dynamik."""
    
    def __init__(self, enabled=True, params=None):
        default_params = {
            "timing_delay_factor": 0.9,
            "velocity_increase_factor": 0.15
        }
        
        if params:
            default_params.update(params)
        
        super().__init__(
            name="local_peak",
            description="Betont lokale melodische Höhepunkte",
            enabled=enabled,
            params=default_params
        )
    
    def apply(self, note, voice, context):
        # Prüfe, ob die Note einen lokalen Höhepunkt darstellt
        if (note.prev_note and note.next_note and 
            note.pitch > note.prev_note.pitch and 
            note.pitch > note.next_note.pitch):
            
            # Parameter holen
            delay_factor = self.get_param("timing_delay_factor")
            velocity_factor = self.get_param("velocity_increase_factor")
            
            # Berechne die tatsächliche Verzögerung
            delay = int(context.max_timing_change * delay_factor)
            
            # Anpassungen vornehmen
            note.adjusted_start_time += delay
            note.adjusted_velocity = min(127, int(note.velocity * (1 + velocity_factor * context.dynamics_strength)))
            
            return True
        
        return False


class DownbeatRule(InterpretationRule):
    """Betont Noten auf betonten Zählzeiten (Taktschläge)."""
    
    def __init__(self, enabled=True, params=None):
        default_params = {
            "timing_delay_factor": 0.5,
            "velocity_increase_factor": 0.1
        }
        
        if params:
            default_params.update(params)
        
        super().__init__(
            name="downbeat",
            description="Betont Noten auf betonten Zählzeiten",
            enabled=enabled,
            params=default_params
        )
    
    def apply(self, note, voice, context):
        if note.is_downbeat:
            # Parameter holen
            delay_factor = self.get_param("timing_delay_factor")
            velocity_factor = self.get_param("velocity_increase_factor")
            
            # Berechne die tatsächliche Verzögerung
            delay = int(context.max_timing_change * delay_factor)
            
            # Anpassungen vornehmen
            note.adjusted_start_time += delay
            note.adjusted_velocity = min(127, int(note.velocity * (1 + velocity_factor * context.dynamics_strength)))
            
            return True
        
        return False


class ShortNoteRule(InterpretationRule):
    """Differenzierte Behandlung kurzer Noten für klarere Artikulation."""
    
    def __init__(self, enabled=True, params=None):
        default_params = {
            "very_short_reduction": 0.05,  # Für extrem kurze Noten (32stel oder kürzer)
            "short_reduction": 0.08,       # Für kurze Noten (16tel)
            "velocity_increase": 0.06,     # Velocity-Erhöhung für Klarheit
            "very_short_threshold": 0.0625,  # Relative Dauer für sehr kurze Noten (32stel)
            "short_threshold": 0.125         # Relative Dauer für kurze Noten (16tel)
        }
        
        if params:
            default_params.update(params)
        
        super().__init__(
            name="short_note",
            description="Spezielle Behandlung kurzer Noten",
            enabled=enabled,
            params=default_params
        )
    
    def apply(self, note, voice, context):
        # Berechne die relative Dauer (z.B. 1/4, 1/8, 1/16 Note etc.)
        relative_duration = note.original_duration / context.ticks_per_beat
        
        # Nur für kürzere Noten anwenden (kürzer als eine Viertelnote)
        if relative_duration < 0.25:
            # Parameter holen
            very_short_reduction = self.get_param("very_short_reduction")
            short_reduction = self.get_param("short_reduction")
            velocity_increase = self.get_param("velocity_increase")
            very_short_threshold = self.get_param("very_short_threshold")
            short_threshold = self.get_param("short_threshold")
            
            # Wähle den passenden Reduktionsfaktor basierend auf der Notenlänge
            if relative_duration <= very_short_threshold:  # 32stel oder kürzer
                reduction_factor = 1.0 - (very_short_reduction * context.articulation_strength)
            elif relative_duration <= short_threshold:  # 16tel
                reduction_factor = 1.0 - (short_reduction * context.articulation_strength)
            else:  # 8tel
                reduction_factor = 1.0 - ((short_reduction * 0.75) * context.articulation_strength)
            
            # Absolute Mindestdauer berechnen
            min_duration = max(2, int(context.ticks_per_beat * relative_duration * 0.5))
            
            # Anpassungen vornehmen
            note.adjusted_duration = max(min_duration, int(note.adjusted_duration * reduction_factor))
            note.adjusted_velocity = min(127, int(note.velocity * (1 + velocity_increase * context.dynamics_strength)))
            
            return True
        
        return False


class LongNoteRule(InterpretationRule):
    """Spezielle Behandlung für lange Noten, die mehr Gewicht erhalten."""
    
    def __init__(self, enabled=True, params=None):
        default_params = {
            "velocity_increase": 0.05,
            "threshold": 1.0  # Schwellenwert in Beats (z.B. Viertelnote)
        }
        
        if params:
            default_params.update(params)
        
        super().__init__(
            name="long_note",
            description="Spezielle Behandlung langer Noten",
            enabled=enabled,
            params=default_params
        )
    
    def apply(self, note, voice, context):
        # Schwellenwert in Ticks umrechnen
        threshold_ticks = int(context.ticks_per_beat * self.get_param("threshold"))
        
        # Nur für lange Noten anwenden
        if note.original_duration > threshold_ticks:
            # Parameter holen
            velocity_increase = self.get_param("velocity_increase")
            
            # Anpassungen vornehmen
            note.adjusted_velocity = min(127, int(note.velocity * (1 + velocity_increase * context.dynamics_strength)))
            
            return True
        
        return False


class AccelerandoRule(InterpretationRule):
    """Beschleunigt aufsteigende melodische Linien für Spannungsaufbau."""
    
    def __init__(self, enabled=True, params=None):
        default_params = {
            "timing_acceleration_factor": -0.7,  # Negative Werte für Beschleunigung
            "min_notes_sequence": 3,  # Minimale Anzahl aufsteigender Noten
            "interval_threshold": 2    # Minimale Anzahl aufsteigender Halbtonschritte
        }
        
        if params:
            default_params.update(params)
        
        super().__init__(
            name="accelerando",
            description="Beschleunigt aufsteigende melodische Linien",
            enabled=enabled,
            params=default_params
        )
    
    def apply(self, note, voice, context):
        # Prüfe auf aufsteigende Linie
        if not (note.prev_note and note.next_note):
            return False
            
        # Prüfe auf aufsteigende Sequenz
        is_ascending = (note.pitch > note.prev_note.pitch and 
                        note.next_note.pitch > note.pitch)
        
        # Prüfe auf Mindest-Intervallgröße
        interval_threshold = self.get_param("interval_threshold")
        interval_size = (note.pitch - note.prev_note.pitch) + (note.next_note.pitch - note.pitch)
        
        if is_ascending and interval_size >= interval_threshold:
            # Parameter holen
            accel_factor = self.get_param("timing_acceleration_factor")
            
            # Negative Timing-Änderung für Beschleunigung
            timing_change = int(context.max_timing_change * accel_factor)
            
            # Anpassungen vornehmen (negatives timing = früher spielen)
            note.adjusted_start_time += timing_change
            
            # Bei Beschleunigung oft auch etwas stärkere Dynamik
            dynamic_boost = 0.05 * context.dynamics_strength
            note.adjusted_velocity = min(127, int(note.adjusted_velocity * (1 + dynamic_boost)))
            
            return True
        
        return False


class SequenceAccelerationRule(InterpretationRule):
    """Beschleunigt wiederholte musikalische Muster und Sequenzen."""
    
    def __init__(self, enabled=True, params=None):
        default_params = {
            "acceleration_factor": -0.6,  # Negative Werte für Beschleunigung
            "pattern_detection_window": 5,  # Anzahl der Noten für Mustererkennung
            "max_acceleration": -0.9,      # Maximale Beschleunigung
            "dynamic_increase": 0.05       # Dynamiksteigerung pro Sequenzposition
        }
        
        if params:
            default_params.update(params)
        
        super().__init__(
            name="sequence_accel",
            description="Beschleunigt wiederholte Muster",
            enabled=enabled,
            params=default_params
        )
        
        # Interner Zustand zur Sequenzverfolgung
        self.current_sequence = []
        self.sequence_positions = {}  # note_id -> position
    
    def apply(self, note, voice, context):
        # Wir brauchen benachbarte Noten für Mustererkennung
        if not (hasattr(note, 'prev_note') and note.prev_note):
            return False
            
        # Einfache Sequenzerkennung: Wiederholte Intervallmuster
        # Für vollständige Implementierung müsste eine komplexere 
        # Mustererkennung implementiert werden
        
        # Eindeutige ID für diese Note
        note_id = f"{note.track}_{note.channel}_{note.original_start_time}_{note.pitch}"
        
        # Intervallmuster zu vorherigen Noten
        if hasattr(note, 'interval_to_prev') and note.interval_to_prev is not None:
            # Füge aktuelles Intervall zum Muster hinzu
            self.current_sequence.append(note.interval_to_prev)
            
            # Beschränke die Länge der Sequenz
            window = self.get_param("pattern_detection_window")
            if len(self.current_sequence) > window:
                self.current_sequence.pop(0)
            
            # Prüfe auf wiederholtes Muster (einfache Version)
            # In einer vollständigen Implementierung würde hier eine 
            # komplexere Mustererkennung stattfinden
            sequence_detected = False
            sequence_position = 0
            
            # Einfache Erkennung: Gleiche Intervalle in Folge
            if len(self.current_sequence) >= 3:
                # Prüfe auf wiederholte gleiche Intervalle
                if self.current_sequence[-1] == self.current_sequence[-2]:
                    sequence_detected = True
                    # Zähle, wie viele gleiche Intervalle in Folge
                    for i in range(3, len(self.current_sequence) + 1):
                        if len(set(self.current_sequence[-i:])) == 1:
                            sequence_position = i - 1
                        else:
                            break
            
            # Wenn eine Sequenz erkannt wurde
            if sequence_detected:
                # Speichere Position für diese Note
                self.sequence_positions[note_id] = sequence_position
                
                # Stärkere Beschleunigung je weiter in der Sequenz
                accel_factor = self.get_param("acceleration_factor") * (1 + sequence_position * 0.1)
                
                # Begrenze auf maximale Beschleunigung
                accel_factor = max(accel_factor, self.get_param("max_acceleration"))
                
                # Anpassungen vornehmen
                timing_change = int(context.max_timing_change * accel_factor)
                note.adjusted_start_time += timing_change
                
                # Dynamik erhöhen für vorwärtsdrängendes Gefühl
                dynamic_increase = self.get_param("dynamic_increase") * sequence_position
                note.adjusted_velocity = min(127, int(note.adjusted_velocity * (1 + dynamic_increase)))
                
                return True
        
        return False


class DirectionalRule(InterpretationRule):
    """Passt Timing basierend auf melodischer Richtung an (aufwärts = schneller, abwärts = langsamer)."""
    
    def __init__(self, enabled=True, params=None):
        default_params = {
            "up_acceleration_factor": -0.5,  # Negative Werte für Beschleunigung bei aufsteigenden Linien
            "down_delay_factor": 0.4,        # Positive Werte für Verzögerung bei absteigenden Linien
            "interval_threshold": 2,         # Mindestintervall in Halbtonschritten
            "velocity_adjustment": 0.04      # Dynamikanpassung je nach Richtung
        }
        
        if params:
            default_params.update(params)
        
        super().__init__(
            name="directional_timing",
            description="Passt Timing basierend auf melodischer Richtung an",
            enabled=enabled,
            params=default_params
        )
    
    def apply(self, note, voice, context):
        # Wir brauchen die vorherige Note für Richtungsbestimmung
        if not hasattr(note, 'interval_to_prev') or note.interval_to_prev is None:
            return False
            
        # Bestimme die melodische Richtung
        interval = note.interval_to_prev
        interval_threshold = self.get_param("interval_threshold")
        
        # Nur anwenden bei signifikanten Intervallen
        if abs(interval) < interval_threshold:
            return False
            
        timing_factor = 0
        velocity_adjustment = 0
        
        if interval > 0:  # Aufsteigende Melodie
            timing_factor = self.get_param("up_acceleration_factor")
            velocity_adjustment = self.get_param("velocity_adjustment")
        else:  # Absteigende Melodie
            timing_factor = self.get_param("down_delay_factor")
            velocity_adjustment = -self.get_param("velocity_adjustment")
        
        # Größere Intervalle führen zu stärkeren Anpassungen (proportional)
        strength_multiplier = min(1.5, abs(interval) / 7)  # Max 1.5x für Septimen oder größer
        adjusted_factor = timing_factor * strength_multiplier
        
        # GEÄNDERT: Verwende context.get_timing_adjustment statt direkter Berechnung
        # timing_change = int(context.max_timing_change * adjusted_factor)
        timing_change = context.get_timing_adjustment(adjusted_factor)
        
        note.adjusted_start_time += timing_change
        
        # Debug-Logging hinzufügen
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"DirectionalRule angewendet auf Note {note.pitch}: Intervall={interval}, "
                    f"Faktor={adjusted_factor}, Timing-Änderung={timing_change}")
        
        # Dynamikanpassung: Aufsteigende Linien etwas stärker, absteigende etwas schwächer
        dynamic_change = velocity_adjustment * strength_multiplier * context.dynamics_strength
        current_velocity = note.adjusted_velocity
        note.adjusted_velocity = min(127, max(1, int(current_velocity * (1 + dynamic_change))))
        
        return True