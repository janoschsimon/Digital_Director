"""
Basismodul für die Plugin-Architektur des Digital Dirigenten
-----------------------------------------------------------
Enthält die Basisklassen für das regelbasierte Interpretationssystem.
"""

import logging
import json
import os
from typing import Dict, Any, List, Optional

# Konfiguriere Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class InterpretationContext:
    """Enthält Kontextinformationen für die Regelanwendung mit bidirektionaler Timing-Unterstützung."""
    
    def __init__(self, ticks_per_beat=480, expressiveness=0.5, 
                 rubato_strength=0.6, articulation_strength=0.7, 
                 dynamics_strength=0.7, timing_direction_bias=0.0):
        self.ticks_per_beat = ticks_per_beat
        self.expressiveness = expressiveness
        self.rubato_strength = rubato_strength
        self.articulation_strength = articulation_strength
        self.dynamics_strength = dynamics_strength
        
        # Neuer Parameter: bestimmt Tendenz zu Verzögerung oder Beschleunigung
        # 0.0 = ausgeglichen, 1.0 = nur Verzögerung, -1.0 = nur Beschleunigung
        self.timing_direction_bias = timing_direction_bias
        
        # Abgeleitete Werte für häufig verwendete Berechnungen
        # Ermöglicht nun sowohl positive als auch negative Werte
        self.max_timing_change = int(ticks_per_beat * 0.1 * rubato_strength)
        self.max_velocity_change = int(dynamics_strength * 15)
        
        # Neue abgeleitete Werte für Beschleunigung und Verzögerung
        # Diese Werte können von Regeln verwendet werden, um das Timing-Verhalten zu steuern
        self.max_acceleration = int(ticks_per_beat * 0.1 * rubato_strength * -1)  # Negative Werte für Beschleunigung
        self.max_delay = int(ticks_per_beat * 0.1 * rubato_strength)  # Positive Werte für Verzögerung
        
        # Anpassungsfaktoren basierend auf timing_direction_bias
        if self.timing_direction_bias != 0.0:
            # Beschränke Beschleunigung, wenn bias positiv ist (Tendenz zu Verzögerung)
            if self.timing_direction_bias > 0:
                self.max_acceleration = int(self.max_acceleration * (1.0 - self.timing_direction_bias))
            
            # Beschränke Verzögerung, wenn bias negativ ist (Tendenz zu Beschleunigung)
            if self.timing_direction_bias < 0:
                self.max_delay = int(self.max_delay * (1.0 + self.timing_direction_bias))
    
    def get_timing_adjustment(self, factor):
        """
        Berechnet eine Timing-Anpassung basierend auf dem gegebenen Faktor und dem Kontext.
        
        Args:
            factor: Timing-Faktor (-1.0 bis 1.0): 
                   - Negative Werte bewirken Beschleunigung
                   - Positive Werte bewirken Verzögerung
        
        Returns:
            Timing-Änderung in Ticks
        """
        if factor < 0:
            # Beschleunigung (negative Werte)
            return int(self.max_acceleration * (factor / -1.0))
        else:
            # Verzögerung (positive Werte)
            return int(self.max_delay * factor)
    
    def get_style_info(self):
        """Gibt einen String mit Informationen über den aktuellen Interpretationsstil zurück."""
        style_info = (
            f"Expressivität: {self.expressiveness:.2f}, "
            f"Rubato: {self.rubato_strength:.2f}, "
            f"Artikulation: {self.articulation_strength:.2f}, "
            f"Dynamik: {self.dynamics_strength:.2f}"
        )
        
        if self.timing_direction_bias != 0:
            style_info += f", Timing-Tendenz: "
            if self.timing_direction_bias > 0:
                style_info += f"ritardando ({self.timing_direction_bias:.2f})"
            else:
                style_info += f"accelerando ({self.timing_direction_bias:.2f})"
        
        return style_info

class InterpretationRule:
    """Basisklasse für alle Interpretationsregeln."""
    
    def __init__(self, name: str, description: str, enabled: bool = True, params: Optional[Dict] = None):
        self.name = name
        self.description = description
        self.enabled = enabled
        self.params = params or {}
    
    def apply(self, note, voice, context: InterpretationContext) -> bool:
        """
        Wendet die Regel auf eine Note an.
        
        Args:
            note: Die zu interpretierende Note
            voice: Die Stimme, zu der die Note gehört
            context: Interpretationskontext
            
        Returns:
            True, wenn die Regel angewendet wurde, sonst False
        """
        raise NotImplementedError("Regel-Klassen müssen apply() implementieren")
    
    def get_param(self, key: str, default: Any = None) -> Any:
        """Holt einen Parameter mit Fallback-Wert."""
        return self.params.get(key, default)

class RuleManager:
    """Verwaltet und wendet Interpretationsregeln an."""
    
    def __init__(self):
        self.rule_sets = {
            "melody": [],  # Regeln für Melodiestimmen
            "bass": [],    # Regeln für Bassstimmen
            "inner": []    # Regeln für innere Stimmen
        }
        self.stats = {
            "melody": {},
            "bass": {},
            "inner": {}
        }
    
    def register_rule(self, voice_type: str, rule: InterpretationRule) -> None:
        """
        Registriert eine Regel für einen Stimmentyp.
        
        Args:
            voice_type: "melody", "bass" oder "inner"
            rule: Die zu registrierende Regel
        """
        if voice_type in self.rule_sets:
            self.rule_sets[voice_type].append(rule)
            logger.info(f"Regel '{rule.name}' für Stimmentyp '{voice_type}' registriert")
        else:
            logger.warning(f"Unbekannter Stimmentyp '{voice_type}' - Regel nicht registriert")
    
    def apply_rules(self, voice, context: InterpretationContext) -> int:
        """
        Wendet alle aktivierten Regeln auf eine Stimme an.
        
        Args:
            voice: Die zu interpretierende Stimme
            context: Interpretationskontext
            
        Returns:
            Anzahl der angewendeten Regeln
        """
        voice_type = "melody"  # Standardtyp
        
        # Bestimme den richtigen Typ basierend auf voice.role
        if voice.role == "bass":
            voice_type = "bass"
        elif voice.role == "inner_voice":
            voice_type = "inner"
            
        logger.info(f"Wende Regeln auf Stimme vom Typ '{voice_type}' an")
        
        # Keine Regeln für diesen Typ vorhanden
        if voice_type not in self.rule_sets:
            logger.warning(f"Keine Regeln für Stimmentyp '{voice_type}' definiert")
            return 0
            
        # Zähle angewendete Regeln
        applied_count = 0
        
        # Wende jede Regel auf jede Note an
        for note in voice.notes:
            for rule in self.rule_sets[voice_type]:
                if not rule.enabled:
                    continue
                    
                try:
                    if rule.apply(note, voice, context):
                        applied_count += 1
                        
                        # Statistik aktualisieren
                        if rule.name in self.stats[voice_type]:
                            self.stats[voice_type][rule.name] += 1
                        else:
                            self.stats[voice_type][rule.name] = 1
                except Exception as e:
                    logger.error(f"Fehler bei Anwendung der Regel '{rule.name}': {e}")
        
        logger.info(f"{applied_count} Regelanwendungen für Stimmentyp '{voice_type}'")
        return applied_count
    
    def load_from_config(self, config_file: str) -> bool:
        """
        Lädt Regeln aus einer JSON-Konfigurationsdatei.
        
        Args:
            config_file: Pfad zur JSON-Konfigurationsdatei
            
        Returns:
            True bei Erfolg, False bei Fehler
        """
        if not os.path.exists(config_file):
            logger.error(f"Konfigurationsdatei '{config_file}' nicht gefunden")
            return False
            
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            # Importiere verfügbare Regelklassen
            available_rules = self._get_available_rules()
            
            # Verarbeite die Konfiguration
            if "rules" in config:
                for voice_type, rules in config["rules"].items():
                    if voice_type not in self.rule_sets:
                        logger.warning(f"Unbekannter Stimmentyp '{voice_type}' in Konfiguration - wird übersprungen")
                        continue
                        
                    for rule_name, rule_config in rules.items():
                        # Finde die passende Regelklasse
                        if rule_name in available_rules:
                            rule_class = available_rules[rule_name]
                            
                            # Erstelle eine Instanz mit den Parametern aus der Konfiguration
                            enabled = rule_config.get("enabled", True)
                            params = rule_config.get("params", {})
                            
                            rule = rule_class(enabled=enabled, params=params)
                            self.register_rule(voice_type, rule)
                        else:
                            logger.warning(f"Unbekannte Regel '{rule_name}' in Konfiguration - wird übersprungen")
            
            logger.info(f"Regeln aus '{config_file}' geladen")
            return True
                
        except Exception as e:
            logger.error(f"Fehler beim Laden der Konfiguration: {e}")
            return False
    
    def _get_available_rules(self) -> Dict[str, Any]:
        """
        Sammelt alle verfügbaren Regelklassen aus den Regel-Modulen.
        
        Returns:
            Dictionary mit Regelnamen und Klassen
        """
        rules = {}
        
        # Lade Regeln aus melody_rules
        try:
            from melody_rules import (
                PhraseStartRule, PhraseEndRule, PreLeapRule, 
                LocalPeakRule, DownbeatRule, ShortNoteRule, LongNoteRule,
                AccelerandoRule, SequenceAccelerationRule, DirectionalRule  # Neue Regeln
            )
            rules["phrase_start"] = PhraseStartRule
            rules["phrase_end"] = PhraseEndRule
            rules["pre_leap"] = PreLeapRule
            rules["local_peak"] = LocalPeakRule
            rules["downbeat"] = DownbeatRule
            rules["short_note"] = ShortNoteRule
            rules["long_note"] = LongNoteRule
            # Hinzufügen der neuen Regeln
            rules["accelerando"] = AccelerandoRule
            rules["sequence_accel"] = SequenceAccelerationRule
            rules["directional_timing"] = DirectionalRule
        except ImportError:
            logger.warning("Melody Rules Modul nicht gefunden")
        
        # Lade Regeln aus bass_rules
        try:
            from bass_rules import (
                BassDownbeatRule, BassShortNoteRule, 
                BassRepeatedNotesRule, BassPhraseEndRule
            )
            rules["bass_downbeat"] = BassDownbeatRule
            rules["bass_short"] = BassShortNoteRule
            rules["bass_repeated"] = BassRepeatedNotesRule
            rules["bass_phrase_end"] = BassPhraseEndRule
        except ImportError:
            logger.warning("Bass Rules Modul nicht gefunden")
        
        # Lade Regeln aus inner_voice_rules
        try:
            from inner_voice_rules import (
                InnerVoiceBaseVelocityRule, InnerContourRule, InnerConsonantRule,
                InnerFlowTimingRule, InnerShortNoteRule
            )
            rules["inner_base_velocity"] = InnerVoiceBaseVelocityRule
            rules["inner_contour"] = InnerContourRule
            rules["inner_consonant"] = InnerConsonantRule
            rules["inner_timing_flow"] = InnerFlowTimingRule
            rules["inner_short_note"] = InnerShortNoteRule
        except ImportError:
            logger.warning("Inner Voice Rules Modul nicht gefunden")
        
        return rules
    
    def print_statistics(self):
        """Gibt Statistiken zu allen angewendeten Regeln aus."""
        logger.info("=== Regelanwendungsstatistiken ===")
        
        for voice_type, stats in self.stats.items():
            if not stats:
                continue
                
            logger.info(f"Stimmentyp: {voice_type}")
            for rule_name, count in sorted(stats.items(), key=lambda x: x[1], reverse=True):
                logger.info(f"  {rule_name}: {count} Anwendungen")
