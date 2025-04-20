"""
Interpretationsregeln für innere Stimmen im Digital Dirigenten
------------------------------------------------------------
Enthält Regeln speziell für innere Stimmen.
"""

import logging
import random
from .rule_base import InterpretationRule, InterpretationContext

logger = logging.getLogger(__name__)

class InnerVoiceBaseVelocityRule(InterpretationRule):
    """Grundlegende Dynamikanpassung für innere Stimmen."""
    
    def __init__(self, enabled=True, params=None):
        default_params = {
            "velocity_decrease_factor": 0.05  # Innere Stimmen generell etwas leiser
        }
        
        if params:
            default_params.update(params)
        
        super().__init__(
            name="inner_base_velocity",
            description="Grundlegende Dynamikanpassung für innere Stimmen",
            enabled=enabled,
            params=default_params
        )
    
    def apply(self, note, voice, context):
        # Parameter holen
        velocity_factor = self.get_param("velocity_decrease_factor")
        
        # Anpassungen vornehmen - stets anwenden für alle Noten in inneren Stimmen
        note.adjusted_velocity = max(1, int(note.velocity * (1 - velocity_factor * context.dynamics_strength)))
        
        return True  # Immer anwenden


class InnerContourRule(InterpretationRule):
    """Hebt melodische Konturen in inneren Stimmen leicht hervor."""
    
    def __init__(self, enabled=True, params=None):
        default_params = {
            "velocity_increase_factor": 0.08  # Moderater als bei Melodiestimmen
        }
        
        if params:
            default_params.update(params)
        
        super().__init__(
            name="inner_contour",
            description="Hebt melodische Konturen in inneren Stimmen hervor",
            enabled=enabled,
            params=default_params
        )
    
    def apply(self, note, voice, context):
        # Prüfe, ob die Note einen lokalen Höhe- oder Tiefpunkt darstellt
        if note.prev_note and note.next_note:
            is_peak = (note.pitch > note.prev_note.pitch and note.pitch > note.next_note.pitch)
            is_valley = (note.pitch < note.prev_note.pitch and note.pitch < note.next_note.pitch)
            
            if is_peak or is_valley:
                # Parameter holen
                velocity_factor = self.get_param("velocity_increase_factor")
                
                # Anpassungen vornehmen
                note.adjusted_velocity = min(127, int(note.adjusted_velocity * (1 + velocity_factor * context.dynamics_strength)))
                
                return True
        
        return False


class InnerConsonantRule(InterpretationRule):
    """Hält konsonante Intervalle in inneren Stimmen länger."""
    
    def __init__(self, enabled=True, params=None):
        default_params = {
            "length_increase_factor": 0.05,  # Moderate Verlängerung
            "consonant_intervals": [3, 4, 7, 8, 9]  # Terz, Quarte, Quinte, Sexte
        }
        
        if params:
            default_params.update(params)
        
        super().__init__(
            name="inner_consonant",
            description="Hält konsonante Intervalle in inneren Stimmen länger",
            enabled=enabled,
            params=default_params
        )
    
    def apply(self, note, voice, context):
        # Prüfe auf konsonante Intervalle zur vorherigen Note
        if note.prev_note:
            interval = abs(note.pitch - note.prev_note.pitch) % 12  # Oktaväquivalent
            consonant_intervals = self.get_param("consonant_intervals")
            
            if interval in consonant_intervals:
                # Parameter holen
                length_factor = self.get_param("length_increase_factor")
                
                # Anpassungen vornehmen
                note.adjusted_duration = int(note.adjusted_duration * (1 + length_factor * context.articulation_strength))
                
                return True
        
        return False


class InnerFlowTimingRule(InterpretationRule):
    """Erzeugt minimale Timing-Variationen für natürlichen Fluss in inneren Stimmen."""
    
    def __init__(self, enabled=True, params=None):
        default_params = {
            "max_variation_factor": 0.5  # Max. 50% der normalen Timing-Variation
        }
        
        if params:
            default_params.update(params)
        
        super().__init__(
            name="inner_timing_flow",
            description="Minimale Timing-Variationen für natürlichen Fluss",
            enabled=enabled,
            params=default_params
        )
    
    def apply(self, note, voice, context):
        # Parameter holen
        variation_factor = self.get_param("max_variation_factor")
        
        # Berechne den maximalen Timing-Effekt
        max_effect = int(context.max_timing_change * variation_factor)
        
        # Erzeuge eine sehr geringe zufällige Timing-Variation
        timing_variation = int(random.uniform(-max_effect, max_effect))
        
        # Anpassungen vornehmen
        note.adjusted_start_time += timing_variation
        
        # Nur als angewendet markieren, wenn die Variation signifikant war
        return abs(timing_variation) > 0


class InnerShortNoteRule(InterpretationRule):
    """Besondere Behandlung für kurze Noten in inneren Stimmen."""
    
    def __init__(self, enabled=True, params=None):
        default_params = {
            "very_short_reduction": 0.02,  # Praktisch keine Verkürzung für sehr kurze Noten
            "short_reduction": 0.05,       # Minimale Verkürzung für kurze Noten
            "min_duration_factor": 0.15,   # Mindestens 15% der Originaldauer
            "min_duration": 5              # Absolute Mindestdauer in Ticks
        }
        
        if params:
            default_params.update(params)
        
        super().__init__(
            name="inner_short_note",
            description="Besondere Behandlung für kurze Noten in inneren Stimmen",
            enabled=enabled,
            params=default_params
        )
    
    def apply(self, note, voice, context):
        # Nur für kurze Noten anwenden
        if note.original_duration < context.ticks_per_beat / 4:  # Kürzer als 16tel
            # Parameter holen
            very_short_reduction = self.get_param("very_short_reduction")
            short_reduction = self.get_param("short_reduction")
            min_duration_factor = self.get_param("min_duration_factor")
            min_duration = self.get_param("min_duration")
            
            # Berechnete Mindestdauer
            calculated_min = max(min_duration, int(note.original_duration * min_duration_factor))
            
            # Wähle den passenden Reduktionsfaktor basierend auf der Notenlänge
            if note.original_duration < context.ticks_per_beat / 8:  # 32stel oder kürzer
                reduction_factor = 1.0 - (very_short_reduction * context.articulation_strength)
            else:  # 16tel
                reduction_factor = 1.0 - (short_reduction * context.articulation_strength)
            
            # Anpassungen vornehmen
            note.adjusted_duration = max(calculated_min, int(note.adjusted_duration * reduction_factor))
            
            return True
        
        return False
