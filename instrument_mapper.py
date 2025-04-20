import music21 as m21
import json
import re
import os
import logging

logger = logging.getLogger(__name__)

class InstrumentMapper:
    """
    Automatische Erkennung und Zuordnung von Instrumenten in MusicXML-Dateien
    zu Miroire/Berlin-Sampler-Instrumenten.
    """
    
    def __init__(self, config_file=None):
        """
        Initialisiert den InstrumentMapper.
        
        Args:
            config_file: Optionaler Pfad zu einer Konfigurationsdatei mit benutzerdefinierten Mappings
        """
        # Standard-Namenserkennungen für Barockstücke
        self.instrument_patterns = {
            "Baroque Violin": [
                r"viol[io]n[oi]?\s*[1I]", r"vln\.?\s*[1I]", r"v\.\s*[1I]", 
                r"violin[oi]", r"violine", r"geige", r"violini", r"fiddle"
            ],
            "Baroque Viola": [
                r"viola", r"vla\.?", r"bratsche", r"alto"
            ],
            "Basso Continuo": [
                r"[cC]ontinuo", r"bass[eo]", r"basso continuo", r"b\.c\.", 
                r"violoncell[eo]", r"cello", r"vcl\.?", r"vc\.?"
            ],
            "French Harpsichord": [
                r"[cC]embalo", r"harpsichord", r"clavecin", 
                r"clav\.?", r"clavicembalo", r"cemb\.?"
            ],
            "Baroque Flute": [
                r"fl[uö]te", r"flute", r"flauto", r"fl\.?"
            ],
            "Baroque Oboe": [
                r"oboe", r"hautbois", r"ob\.?"
            ]
        }
        
        # Laden benutzerdefinierter Konfiguration, falls vorhanden
        self.custom_mappings = {}
        if config_file and os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    if 'custom_mappings' in config:
                        self.custom_mappings = config['custom_mappings']
                    if 'instrument_patterns' in config:
                        # Benutzerdefinierte Muster ergänzen die Standard-Patterns
                        for instr, patterns in config['instrument_patterns'].items():
                            if instr in self.instrument_patterns:
                                self.instrument_patterns[instr].extend(patterns)
                            else:
                                self.instrument_patterns[instr] = patterns
                logger.info(f"Benutzerdefinierte Mappings aus {config_file} geladen")
            except Exception as e:
                logger.warning(f"Fehler beim Laden der Konfiguration: {e}")
    
    def detect_instrument(self, part_name, clef_type=None, range_info=None):
        """
        Erkennt das Instrument basierend auf seinem Namen, Notenschlüssel und Tonhöhenbereich.
        
        Args:
            part_name: Name des Parts/der Stimme
            clef_type: Optional, Typ des Notenschlüssels (z.B. 'G', 'F', 'C')
            range_info: Optional, Tonhöhenbereich als (min_midi, max_midi) Tupel
            
        Returns:
            Erkannter Instrumentenname für Miroire/Berlin
        """
        # Zuerst prüfen, ob es ein benutzerdefiniertes Mapping gibt
        if part_name in self.custom_mappings:
            return self.custom_mappings[part_name]
        
        # Normalisiere den Namen für besseren Vergleich
        part_name_lower = part_name.lower()
        
        # Versuche, ein Muster zu finden
        for instrument, patterns in self.instrument_patterns.items():
            for pattern in patterns:
                if re.search(pattern, part_name_lower, re.IGNORECASE):
                    return instrument
        
        # Wenn kein direktes Muster gefunden wurde, versuche es mit Schlüsseln und Bereichen
        if clef_type or range_info:
            if clef_type == 'G' or (range_info and range_info[0] > 55):
                # Violinschlüssel oder hoher Bereich - wahrscheinlich Violine
                return "Baroque Violin"
            elif clef_type == 'C' or (range_info and 48 <= range_info[0] <= 60):
                # C-Schlüssel oder mittlerer Bereich - wahrscheinlich Viola
                return "Baroque Viola"
            elif clef_type == 'F' or (range_info and range_info[0] < 48):
                # Bassschlüssel oder tiefer Bereich - wahrscheinlich Bass/Cello
                return "Basso Continuo"
        
        # Fallback für unbekannte Instrumente
        return "Default"
    
    def create_mapping_for_score(self, score):
        """
        Erstellt ein Mapping für alle Parts in einem Score.
        
        Args:
            score: Ein music21 Score-Objekt
            
        Returns:
            Dictionary mit Part-Index als Schlüssel und Instrumentenname als Wert
        """
        mapping = {}
        parts = score.getElementsByClass(m21.stream.Part)
        
        for idx, part in enumerate(parts):
            # Versuche, den Instrumentennamen zu erhalten
            part_name = ""
            instr = part.getInstrument()
            if instr and instr.partName:
                part_name = instr.partName
            elif hasattr(part, 'partName') and part.partName:
                part_name = part.partName
            elif hasattr(part, 'id') and part.id:
                part_name = part.id
            
            # Bestimme den Schlüsseltyp (falls vorhanden)
            clef_type = None
            clefs = part.flatten().getElementsByClass(m21.clef.Clef)
            if clefs:
                clef = clefs[0]
                if isinstance(clef, m21.clef.TrebleClef):
                    clef_type = 'G'
                elif isinstance(clef, m21.clef.BassClef):
                    clef_type = 'F'
                elif isinstance(clef, m21.clef.AltoClef) or isinstance(clef, m21.clef.TenorClef):
                    clef_type = 'C'
            
            # Bestimme den Tonhöhenbereich
            range_info = None
            notes = part.flatten().getElementsByClass(m21.note.Note)
            if notes:
                pitches = [n.pitch.midi for n in notes]
                range_info = (min(pitches), max(pitches))
            
            # Erkenne das Instrument
            instrument_name = self.detect_instrument(part_name, clef_type, range_info)
            mapping[str(idx)] = instrument_name
            
            logger.info(f"Part {idx} ({part_name}): Erkannt als {instrument_name}")
        
        return mapping
    
    def save_mapping(self, mapping, output_file):
        """
        Speichert ein Mapping in einer JSON-Datei.
        """
        with open(output_file, 'w') as f:
            json.dump({"part_mapping": mapping}, f, indent=2)
        logger.info(f"Mapping in {output_file} gespeichert")
        return output_file
    
    def process_file(self, xml_file, output_file=None):
        """
        Verarbeitet eine MusicXML-Datei und erstellt ein Instrument-Mapping.
        
        Args:
            xml_file: Pfad zur MusicXML-Datei
            output_file: Optional, Pfad zur Ausgabe-JSON-Datei
            
        Returns:
            Das erstellte Mapping als Dictionary
        """
        try:
            score = m21.converter.parse(xml_file)
            mapping = self.create_mapping_for_score(score)
            
            if output_file:
                self.save_mapping(mapping, output_file)
            
            return mapping
            
        except Exception as e:
            logger.error(f"Fehler bei der Verarbeitung von {xml_file}: {e}")
            return {}

# Beispiel für die Nutzung
def get_mapping_for_file(xml_file, config_file=None):
    """
    Hilfsfunktion zum Erhalten eines Instrument-Mappings für eine MusicXML-Datei.
    
    Args:
        xml_file: Pfad zur MusicXML-Datei
        config_file: Optional, Pfad zur Konfigurationsdatei
        
    Returns:
        Dictionary mit Part-Indizes und zugeordneten Instrumenten
    """
    mapper = InstrumentMapper(config_file)
    return mapper.process_file(xml_file)

# Funktion für direkten Aufruf
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print(f"Verwendung: {sys.argv[0]} <xml_file> [config_file] [output_file]")
        sys.exit(1)
    
    xml_file = sys.argv[1]
    config_file = sys.argv[2] if len(sys.argv) > 2 else None
    output_file = sys.argv[3] if len(sys.argv) > 3 else None
    
    mapper = InstrumentMapper(config_file)
    mapping = mapper.process_file(xml_file, output_file)
    
    print("Erkanntes Instrument-Mapping:")
    for part_idx, instrument in mapping.items():
        print(f"  Part {part_idx}: {instrument}")
