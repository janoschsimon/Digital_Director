"""
XML Parser Modul für den Barockmusik MIDI-Prozessor
--------------------------------------------------
Dieses Modul enthält Funktionen für das Parsen und Extrahieren von Daten aus MusicXML-Dateien.
"""

import re
import logging
import chardet
import codecs
import xml.etree.ElementTree as ET

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def detect_encoding(file_path):
    """
    Detect the encoding of a file using chardet, with fallback encodings.
    
    Args:
        file_path: Pfad zur zu analysierenden Datei
        
    Returns:
        Erkannte Zeichenkodierung (z.B. 'utf-8', 'latin-1', etc.)
    """
    encodings_to_try = [
        'utf-8', 'latin-1', 'iso-8859-1', 'cp1252', 'utf-16', 'windows-1250', 
        'windows-1252', 'ascii'
    ]
    
    # First, try chardet
    with open(file_path, 'rb') as file:
        raw_data = file.read(10000)  # Read first 10000 bytes
        result = chardet.detect(raw_data)
        if result['confidence'] > 0.8:
            return result['encoding']
    
    # If chardet fails or is uncertain, try manual detection
    for encoding in encodings_to_try:
        try:
            with codecs.open(file_path, 'r', encoding=encoding) as file:
                file.read()
                return encoding
        except (UnicodeDecodeError, IOError):
            continue
    
    return 'utf-8'  # Fallback default

def safe_xml_parse(xml_path):
    """
    Safely parse XML file with robust encoding handling.
    
    Args:
        xml_path: Pfad zur XML-Datei
        
    Returns:
        XML-Element-Tree oder None bei Fehler
    """
    try:
        # Detect encoding
        detected_encoding = detect_encoding(xml_path)
        logger.info(f"Detected encoding: {detected_encoding}")

        # Read the file with the detected encoding
        try:
            with codecs.open(xml_path, 'r', encoding=detected_encoding) as file:
                xml_content = file.read()
        except Exception as e:
            logger.error(f"Error reading file with {detected_encoding} encoding: {e}")
            return None

        # Clean the XML content
        # Remove or replace problematic characters
        xml_content = ''.join(
            char for char in xml_content 
            if ord(char) >= 32 or char in '\n\r\t'
        )

        # Try parsing the XML
        try:
            # Remove XML declaration if it causes issues
            if xml_content.startswith('<?xml'):
                xml_content = xml_content.split('?>', 1)[1]
            
            tree = ET.fromstring(xml_content)
            return tree
        except ET.ParseError as e:
            logger.error(f"XML Parsing error: {e}")
            return None

    except Exception as e:
        logger.error(f"Unexpected error parsing XML: {e}")
        return None

def parse_tempos_from_musicxml(xml_path):
    """
    Liest Tempomarkierungen direkt aus der MusicXML-Datei.
    Verwendet einen gezielten Ansatz, der Duplikate vermeidet.
    
    Args:
        xml_path: Pfad zur MusicXML-Datei
        
    Returns:
        Liste von (offset, bpm) Tupeln
    """
    tempo_changes = []
    
    try:
        # Lese die XML-Datei als Text
        encoding = detect_encoding(xml_path)
        with open(xml_path, 'r', encoding=encoding, errors='replace') as f:
            content = f.read()
        
        # Suche nach <measure> Elementen, die <sound tempo="..."> enthalten
        # Speichert die Taktnummer und den Tempowert
        pattern = r'<measure\s+number="(\d+)"[^>]*>.*?<sound\s+tempo="([^"]+)"'
        matches = re.findall(pattern, content, re.DOTALL)
        
        for measure_number, tempo_value in matches:
            try:
                measure = int(measure_number)
                bpm = float(tempo_value)
                
                # Berechne die ungefähre Position in Viertelnoten (Beats)
                # Annahme: 4 Viertelnoten pro Takt (4/4 Takt ist Standard in Barockmusik)
                offset = (measure - 1) * 4.0
                
                tempo_changes.append((offset, bpm))
                logger.info(f"Tempo in Takt {measure}: {bpm} BPM (Offset {offset})")
            except ValueError:
                logger.warning(f"Ungültiger Tempowert in Takt {measure_number}: {tempo_value}")
        
        # Suche auch nach <metronome> Elementen
        metronome_pattern = r'<measure\s+number="(\d+)"[^>]*>.*?<metronome>.*?<per-minute>([^<]+)</per-minute>'
        metronome_matches = re.findall(metronome_pattern, content, re.DOTALL)
        
        for measure_number, tempo_value in metronome_matches:
            try:
                measure = int(measure_number)
                bpm = float(tempo_value)
                offset = (measure - 1) * 4.0
                
                # Prüfe, ob schon ein Tempo bei diesem Offset existiert
                exists = False
                for i, (existing_offset, _) in enumerate(tempo_changes):
                    if abs(existing_offset - offset) < 0.5:  # Kleine Toleranz
                        exists = True
                        break
                
                if not exists:
                    tempo_changes.append((offset, bpm))
                    logger.info(f"Metronom in Takt {measure}: {bpm} BPM (Offset {offset})")
            except ValueError:
                logger.warning(f"Ungültiger Metronom-Wert in Takt {measure_number}: {tempo_value}")
    
    except Exception as e:
        logger.error(f"Fehler beim Parsen der Tempos aus MusicXML: {e}")
    
    # Sortiere nach Offset
    tempo_changes.sort(key=lambda x: x[0])
    
    return tempo_changes
