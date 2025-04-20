"""
Bass-Interpretationsregeln für den Digital Dirigenten
---------------------------------------------------
Enthält Regeln speziell für Bassstimmen.
"""

import logging
import random
from .rule_base import InterpretationRule, InterpretationContext

logger = logging.getLogger(__name__)

class BassDownbeatRule(InterpretationRule):
    """Stabilität auf starken Zählzeiten für Bassstimmen."""
    
    def __init__(self, enabled=True, params=None):
        default_params = {
            "timing_delay_factor": 0.3,  # Weniger Verzögerung als bei Melodien
            "velocity_increase_factor": 0.08  # Moderate Betonung
        }
        
        if params:
            default_params.update(params)
        
        super().__init__(
            name="bass_downbeat",
            description="Stabilität auf starken Zählzeiten (Taktschlägen) für Bassstimmen",
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


class BassShortNoteRule(InterpretationRule):
    """Spezielle Behandlung kurzer Noten in Bassstimmen."""
    
    def __init__(self, enabled=True, params=None):
        default_params = {
            "very_short_reduction": 0.06,  # Weniger Verkürzung als in Melodiestimmen
            "short_reduction": 0.08,
            "min_duration_factor": 0.12,  # Mindestens 12% der Originaldauer
            "min_duration_absolute": 4     # Absolute Mindestdauer in Ticks
        }
        
        if params:
            default_params.update(params)
        
        super().__init__(
            name="bass_short",
            description="Spezielle Behandlung kurzer Noten in Bassstimmen",
            enabled=enabled,
            params=default_params
        )
    
    def apply(self, note, voice, context):
        # Nur für kurze Noten anwenden
        if note.original_duration < context.ticks_per_beat / 2:  # Kürzer als Achtelnote
            # Parameter holen
            very_short_reduction = self.get_param("very_short_reduction")
            short_reduction = self.get_param("short_reduction")
            min_duration_factor = self.get_param("min_duration_factor")
            min_duration_absolute = self.get_param("min_duration_absolute")
            
            # Berechnete Mindestdauer
            min_duration = max(min_duration_absolute, int(note.original_duration * min_duration_factor))
            
            # Wähle den passenden Reduktionsfaktor basierend auf der Notenlänge
            if note.original_duration < context.ticks_per_beat / 4:  # 16tel oder kürzer
                reduction_factor = 1.0 - (very_short_reduction * context.articulation_strength)
            else:  # 8tel
                reduction_factor = 1.0 - (short_reduction * context.articulation_strength)
            
            # Anpassungen vornehmen
            note.adjusted_duration = max(min_duration, int(note.adjusted_duration * reduction_factor))
            
            return True
        
        return False


class BassRepeatedNotesRule(InterpretationRule):
    """Erzeugt Pulsation im Bass bei wiederholten Tönen - variiert Timing und beschleunigt bei längeren Wiederholungen."""
    
    def __init__(self, enabled=True, params=None):
        default_params = {
            "velocity_variation": 0.05,       # Max. prozentuale Schwankung der Velocity
            "duration_variation": 0.03,       # Max. prozentuale Schwankung der Dauer
            "min_duration_factor": 0.15,      # Mindestens 15% der Originaldauer
            "min_duration_absolute": 4,       # Absolute Mindestdauer in Ticks
            "acceleration_factor": -0.04,      # NEU: Beschleunigungsfaktor pro wiederholtem Ton
            "max_acceleration": -0.2,          # NEU: Maximale Beschleunigung
            "repetition_threshold": 3          # NEU: Ab wievielen Wiederholungen Beschleunigung einsetzt
        }
        
        if params:
            default_params.update(params)
        
        super().__init__(
            name="bass_repeated",
            description="Pulsation und Beschleunigung bei wiederholten Tönen in Bassstimmen",
            enabled=enabled,
            params=default_params
        )
        
        # Interner Zustand zur Verfolgung von Wiederholungen
        self.current_repetitions = {}  # {(track, channel, pitch): count}
    
    def apply(self, note, voice, context):
        # Nur anwenden, wenn die vorherige Note den gleichen Ton hat
        if note.prev_note and note.pitch == note.prev_note.pitch:
            # Parameter holen
            velocity_variation = self.get_param("velocity_variation")
            duration_variation = self.get_param("duration_variation")
            min_duration_factor = self.get_param("min_duration_factor")
            min_duration_absolute = self.get_param("min_duration_absolute")
            
            # Schlüssel für diese Tonwiederholung
            repetition_key = (note.track, note.channel, note.pitch)
            
            # Anzahl der Wiederholungen verfolgen
            if repetition_key not in self.current_repetitions:
                self.current_repetitions[repetition_key] = 1
            else:
                self.current_repetitions[repetition_key] += 1
            
            repetition_count = self.current_repetitions[repetition_key]
            
            # Berechnete Mindestdauer
            min_duration = max(min_duration_absolute, int(note.original_duration * min_duration_factor))
            
            # Zufällige Variationen für erste Wiederholungen
            import random
            random_vel_factor = random.uniform(-velocity_variation, velocity_variation) * context.dynamics_strength
            
            # Anpassungen vornehmen
            note.adjusted_velocity = min(127, max(1, int(note.velocity * (1 + random_vel_factor))))
            
            # NEU: Beschleunigung für längere Wiederholungssequenzen
            repetition_threshold = self.get_param("repetition_threshold")
            if repetition_count >= repetition_threshold:
                # Berechne Beschleunigung basierend auf Wiederholungen
                accel_base = self.get_param("acceleration_factor")
                # Verstärke Beschleunigung mit weiteren Wiederholungen
                repetition_factor = min(1.0, (repetition_count - repetition_threshold + 1) * 0.2)
                acceleration = accel_base * repetition_factor * context.rubato_strength
                
                # Begrenze auf maximale Beschleunigung
                max_accel = self.get_param("max_acceleration")
                acceleration = max(acceleration, max_accel)
                
                # Wende Beschleunigung an
                time_change = int(context.max_timing_change * acceleration)
                note.adjusted_start_time += time_change
                
                # Verstärke Dynamik leicht mit zunehmender Beschleunigung
                if repetition_count > repetition_threshold + 1:
                    dynamic_boost = min(0.15, 0.03 * (repetition_count - repetition_threshold))
                    current_velocity = note.adjusted_velocity
                    note.adjusted_velocity = min(127, int(current_velocity * (1 + dynamic_boost)))
            
            # Nur bei längeren Noten auch die Dauer variieren
            if note.original_duration > context.ticks_per_beat / 4:  # Länger als 16tel
                random_dur_factor = random.uniform(-duration_variation, duration_variation) * context.articulation_strength
                variation_factor = 1.0 + random_dur_factor
                note.adjusted_duration = max(min_duration, int(note.adjusted_duration * variation_factor))
            
            return True
        else:
            # Zurücksetzen der Wiederholungszählung, wenn die Tonfolge unterbrochen wird
            repetition_key = (note.track, note.channel, note.pitch)
            if repetition_key in self.current_repetitions:
                del self.current_repetitions[repetition_key]
        
        return False


class BassPhraseEndRule(InterpretationRule):
    """Spezielles Verhalten für Basstöne am Phrasenende."""
    
    def __init__(self, enabled=True, params=None):
        default_params = {
            "length_increase_factor": 0.15,  # Mehr Verlängerung als bei Melodien
            "min_duration_threshold": 1.0  # Nur für Noten länger als eine Viertelnote
        }
        
        if params:
            default_params.update(params)
        
        super().__init__(
            name="bass_phrase_end",
            description="Spezielles Verhalten für Basstöne am Phrasenende",
            enabled=enabled,
            params=default_params
        )
    
    def apply(self, note, voice, context):
        if hasattr(note, 'phrase_position') and note.phrase_position > 0.9:
            # Parameter holen
            length_increase_factor = self.get_param("length_increase_factor")
            min_duration_threshold = self.get_param("min_duration_threshold")
            
            # Nur für längere Noten anwenden
            min_duration_ticks = int(context.ticks_per_beat * min_duration_threshold)
            if note.original_duration > min_duration_ticks:
                # Längere Haltedauer am Phrasenende
                note.adjusted_duration = int(note.adjusted_duration * (1 + length_increase_factor * context.articulation_strength))
                return True
        
        return False