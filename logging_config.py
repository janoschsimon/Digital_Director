"""
Zentrale Logging-Konfiguration für den Barockmusik MIDI-Prozessor
-----------------------------------------------------------------
Stellt eine einheitliche Logging-Konfiguration für alle Module bereit.
Mit GUI-Unterstützung, sodass Logs sowohl in der Konsole als auch im GUI erscheinen.
"""

import logging
import os
import sys
from datetime import datetime
from typing import List, Callable, Optional

# Globale Variable für den Debug-Modus
DEBUG_MODE = False

# Globale Variable für GUI-Callback-Funktionen
_LOG_CALLBACKS = []

class GUILogHandler(logging.Handler):
    """Ein spezieller Handler, der Log-Nachrichten an registrierte GUI-Callbacks sendet."""
    
    def __init__(self):
        super().__init__()
        self.callbacks = []
    
    def emit(self, record):
        """Sendet Log-Einträge an alle registrierten GUI-Callbacks."""
        message = self.format(record)
        for callback in self.callbacks:
            try:
                callback(message)
            except Exception:
                pass
    
    def register_callback(self, callback: Callable[[str], None]):
        """Registriert eine Callback-Funktion für Log-Nachrichten."""
        if callback not in self.callbacks:
            self.callbacks.append(callback)
            return True
        return False
    
    def unregister_callback(self, callback: Callable[[str], None]):
        """Entfernt eine Callback-Funktion."""
        if callback in self.callbacks:
            self.callbacks.remove(callback)
            return True
        return False

# Globaler Handler für GUI-Logging
_gui_handler = GUILogHandler()

def register_log_callback(callback: Callable[[str], None]) -> bool:
    """
    Registriert eine Callback-Funktion, die bei neuen Log-Nachrichten aufgerufen wird.
    
    Args:
        callback: Die Funktion, die aufgerufen werden soll. Akzeptiert einen String-Parameter.
        
    Returns:
        True, wenn die Registrierung erfolgreich war, sonst False.
    """
    global _gui_handler
    return _gui_handler.register_callback(callback)

def unregister_log_callback(callback: Callable[[str], None]) -> bool:
    """
    Entfernt eine registrierte Callback-Funktion.
    
    Args:
        callback: Die zu entfernende Funktion.
        
    Returns:
        True, wenn die Entfernung erfolgreich war, sonst False.
    """
    global _gui_handler
    return _gui_handler.unregister_callback(callback)

def configure_logging(debug_mode=False, log_file=None):
    """
    Konfiguriert das Logging-System mit einheitlichen Einstellungen.
    
    Args:
        debug_mode: Wenn True, werden DEBUG-Nachrichten angezeigt
        log_file: Optional, Pfad zu einer Log-Datei
    """
    global DEBUG_MODE, _gui_handler
    DEBUG_MODE = debug_mode
    
    # Bestimme Log-Level basierend auf Debug-Modus
    log_level = logging.DEBUG if debug_mode else logging.INFO
    
    # Formatierung mit präzisen Zeitstempeln (inkl. Millisekunden)
    log_format = '%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    formatter = logging.Formatter(log_format, datefmt=date_format)
    
    # Zurücksetzen der Root-Logger-Handler, um doppelte Einträge zu vermeiden
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    if root_logger.handlers:
        for handler in root_logger.handlers:
            root_logger.removeHandler(handler)
    
    # Konfiguriere Konsolen-Handler
    console = logging.StreamHandler()
    console.setLevel(log_level)
    console.setFormatter(formatter)
    root_logger.addHandler(console)
    
    # Konfiguriere GUI-Handler
    _gui_handler.setLevel(log_level)
    _gui_handler.setFormatter(formatter)
    root_logger.addHandler(_gui_handler)
    
    # Konfiguriere Datei-Handler, wenn eine Log-Datei angegeben wurde
    if log_file:
        file_handler = logging.FileHandler(log_file, 'a', 'utf-8')
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Reduziere Logging für bestimmte Module
    logging.getLogger('music21').setLevel(logging.WARNING)
    logging.getLogger('mido').setLevel(logging.WARNING)
    
    # Starten-Nachricht protokollieren
    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialisiert - Debug-Modus: {debug_mode}")
    
    return logger

def get_process_id():
    """Erzeugt eine eindeutige Prozess-ID für das Logging."""
    now = datetime.now()
    return f"process_{now.strftime('%Y%m%d_%H%M%S')}"

def create_log_file(base_dir=None):
    """Erstellt eine Log-Datei mit Zeitstempel."""
    if not base_dir:
        base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    
    os.makedirs(base_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(base_dir, f"barock_processor_{timestamp}.log")
    
    return log_file

def is_debug_mode():
    """Gibt zurück, ob der Debug-Modus aktiv ist."""
    return DEBUG_MODE

def log_module_import(module_name):
    """Protokolliert, wenn ein Modul importiert wird (nur im Debug-Modus)."""
    if DEBUG_MODE:
        logger = logging.getLogger(module_name)
        logger.debug(f"Modul {module_name} wird importiert")

def log_function_entry(func_name, module_name=None):
    """Protokolliert den Eintritt in eine Funktion (nur im Debug-Modus)."""
    if DEBUG_MODE:
        logger_name = module_name if module_name else __name__
        logger = logging.getLogger(logger_name)
        logger.debug(f"Betrete Funktion: {func_name}")

def log_function_exit(func_name, module_name=None, execution_time=None):
    """Protokolliert das Verlassen einer Funktion (nur im Debug-Modus)."""
    if DEBUG_MODE:
        logger_name = module_name if module_name else __name__
        logger = logging.getLogger(logger_name)
        time_info = f" (Ausführungszeit: {execution_time:.3f}s)" if execution_time else ""
        logger.debug(f"Verlasse Funktion: {func_name}{time_info}")