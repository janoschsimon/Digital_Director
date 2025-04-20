"""
Haupteinstiegspunkt für den Barockmusik MIDI-Prozessor
-----------------------------------------------------
Startet die GUI-Anwendung.
"""

import os
import sys
import logging
import argparse
import traceback
from PyQt6.QtWidgets import QApplication

def setup_logging(debug=False, log_file=None):
    """Konfiguriert das Logging basierend auf den Befehlszeilenargumenten."""
    log_level = logging.DEBUG if debug else logging.INFO
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Wenn eine Log-Datei angegeben wurde, leite die Logs dorthin um
    if log_file:
        logging.basicConfig(
            filename=log_file,
            level=log_level,
            format=log_format,
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        # Auch auf der Konsole ausgeben
        console = logging.StreamHandler()
        console.setLevel(log_level)
        console.setFormatter(logging.Formatter(log_format))
        logging.getLogger('').addHandler(console)
    else:
        # Nur Konsolenausgabe
        logging.basicConfig(
            level=log_level,
            format=log_format,
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    # Aktiviere Debug-Modus in allen relevanten Modulen
    if debug:
        logging.info("Debug-Modus aktiviert")
        
        # Importiere die notwendigen Module für Debug-Aktivierung
        try:
            # Note manipulator ist im conductor-Unterordner
            from conductor.note_manipulator import enable_debug_logging as enable_note_debug
            enable_note_debug()
            logging.info("Debug-Modus für Note Manipulator aktiviert")
        except ImportError as e:
            logging.warning(f"Konnte note_manipulator nicht importieren: {e}")
        
        try:
            # midi_processor ist im conductor-Unterordner
            from conductor.midi_processor import enable_debug_logging as enable_midi_debug
            enable_midi_debug()
            logging.info("Debug-Modus für MIDI Processor aktiviert")
        except ImportError as e:
            logging.warning(f"Konnte midi_processor nicht importieren: {e}")
        
        
    else:
        logging.info("Normaler Modus (ohne Debug)")
        try:
            from conductor.note_manipulator import disable_debug_logging as disable_note_debug
            disable_note_debug()
        except ImportError:
            pass
        
        try:
            from conductor.midi_processor import disable_debug_logging as disable_midi_debug
            disable_midi_debug()
        except ImportError:
            pass

def parse_arguments():
    """Parst Befehlszeilenargumente."""
    parser = argparse.ArgumentParser(description='Barockmusik MIDI-Prozessor')
    
    # Debug-Optionen
    parser.add_argument('--debug', '-d', action='store_true', 
                        help='Aktiviert detailliertes Debug-Logging')
    parser.add_argument('--log-file', '-l', type=str, 
                        help='Speichert Logs in der angegebenen Datei')
    
    # Modus-Optionen (GUI oder CLI)
    parser.add_argument('--cli', action='store_true',
                        help='Startet im Kommandozeilen-Modus statt GUI')
    
    # Dateioptionen für CLI-Modus
    parser.add_argument('--input', '-i', type=str,
                        help='Eingabedatei (MIDI oder MusicXML) für CLI-Modus')
    parser.add_argument('--output', '-o', type=str,
                        help='Ausgabedatei für CLI-Modus')
    
    # Interpretationsparameter
    parser.add_argument('--expressiveness', '-e', type=float, default=0.5,
                        help='Expressivität (0.0-1.0, Standard: 0.5)')
    parser.add_argument('--rubato', '-r', type=float, default=0.6,
                        help='Rubato-Stärke (0.0-1.0, Standard: 0.6)')
    parser.add_argument('--articulation', '-a', type=float, default=0.7,
                        help='Artikulation (0.0-1.0, Standard: 0.7)')
    parser.add_argument('--dynamics', '-y', type=float, default=0.7,
                        help='Dynamik (0.0-1.0, Standard: 0.7)')
    
    return parser.parse_args()

def run_gui():
    """Startet die GUI-Anwendung."""
    from gui_main_window import AnalysisApp
    
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Konsistentes Aussehen auf allen Plattformen
    window = AnalysisApp()
    window.show()
    sys.exit(app.exec())

def run_cli(args):
    """
    Führt die MIDI-Verarbeitung im Kommandozeilen-Modus aus.
    
    Args:
        args: Befehlszeilenargumente
    """
    logging.info("Starte Verarbeitung im CLI-Modus")
    
    if not args.input:
        logging.error("Keine Eingabedatei angegeben (--input oder -i erforderlich)")
        return
    
    if not os.path.exists(args.input):
        logging.error(f"Eingabedatei nicht gefunden: {args.input}")
        return
    
    # Bestimme Ausgabepfad, falls nicht angegeben
    output_path = args.output
    if not output_path:
        base_dir = os.path.dirname(args.input)
        base_name = os.path.splitext(os.path.basename(args.input))[0]
        output_path = os.path.join(base_dir, f"{base_name}_interpreted.mid")
    
    # Prüfe, ob die Eingabe eine MIDI- oder MusicXML-Datei ist
    input_file = args.input
    input_is_xml = input_file.lower().endswith((".xml", ".musicxml"))
    
    # Falls XML, konvertiere zu MIDI
    if input_is_xml:
        logging.info(f"XML-Datei erkannt: {input_file}")
        try:
            # cc1 ist im Hauptverzeichnis
            from cc1 import process_file
            # Entfernt: enable_humanize Parameter, da veraltet
            midi_file = process_file(input_file, output_midi=None)
            if not midi_file or not os.path.exists(midi_file):
                logging.error("Fehler bei XML-zu-MIDI-Konvertierung")
                return
            logging.info(f"XML zu MIDI konvertiert: {midi_file}")
            input_file = midi_file
        except Exception as e:
            logging.error(f"Fehler bei XML-zu-MIDI-Konvertierung: {e}")
            logging.error(traceback.format_exc())
            return
    
    # Erstelle und verwende den Digital Dirigenten
    try:
        # note_manipulator ist im conductor-Unterordner
        from conductor.note_manipulator import NoteLevelInterpreter
        # midi_processor ist im conductor-Unterordner
        from conductor.midi_processor import process_midi_with_interpretation
        
        interpreter = NoteLevelInterpreter(
            expressiveness=args.expressiveness,
            rubato_strength=args.rubato,
            articulation_strength=args.articulation,
            dynamics_strength=args.dynamics
        )
        
        logging.info(f"Digital Dirigent initialisiert mit: "
                    f"Expressivität={args.expressiveness}, "
                    f"Rubato={args.rubato}, "
                    f"Artikulation={args.articulation}, "
                    f"Dynamik={args.dynamics}")
        
        # Lade die MIDI-Datei und interpretiere sie
        if interpreter.load_midi(input_file):
            interp_results = interpreter.interpret()
            
             # Speichere die interpretierte MIDI-Datei
            final_output = interpreter.save_midi(input_file, output_path)
            
            # Zeige die Statistiken
            stats = interp_results.get('stats', {})
            logging.info(f"Verarbeitung abgeschlossen: {final_output}")
            logging.info(f"Statistik: {stats.get('adjusted_notes', 0)} von "
                        f"{stats.get('total_notes', 0)} Noten angepasst "
                        f"({stats.get('corrected_durations', 0)} Dauern korrigiert)")
            
            # Öffne das Ausgabeverzeichnis, wenn die Verarbeitung erfolgreich war
            if os.path.exists(final_output):
                output_dir = os.path.dirname(final_output)
                logging.info(f"Ausgabedatei gespeichert in: {output_dir}")
                
                # Unter Windows: Explorer öffnen
                if sys.platform.startswith('win'):
                    try:
                        os.startfile(output_dir)
                    except:
                        pass
        else:
            logging.error(f"Fehler beim Laden der MIDI-Datei: {input_file}")
    
    except Exception as e:
        logging.error(f"Fehler bei der Verarbeitung: {e}")
        logging.error(traceback.format_exc())

if __name__ == "__main__":
    # Parse Befehlszeilenargumente
    args = parse_arguments()
    
    # Konfiguriere Logging
    setup_logging(debug=args.debug, log_file=args.log_file)
    
    # Starte die Anwendung im gewünschten Modus
    if args.cli:
        run_cli(args)
    else:
        run_gui()