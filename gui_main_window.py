"""
Hauptfenster-Modul für den Barockmusik MIDI-Prozessor
-----------------------------------------------------
Enthält die Hauptfenster-Klasse für die GUI-Anwendung.
Optimierte Version mit zuverlässiger MuseScore-Erkennung und reduziertem Log-Output.
"""

import os
import sys
import webbrowser
import gc
import traceback
from PyQt6.QtWidgets import (QMainWindow, QFileDialog, QPushButton, 
                            QLabel, QListWidget, QVBoxLayout, QHBoxLayout, QWidget, 
                            QTextEdit, QCheckBox, QGroupBox, QMessageBox, QComboBox,
                            QSlider, QRadioButton, QButtonGroup)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QColor

from worker import AnalysisWorker

import music21 as m21
from conductor.note_manipulator import NoteLevelInterpreter

class AnalysisApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Baroque Music MIDI Processor")
        self.setGeometry(100, 100, 900, 700)
        
        # Dateiliste initialisieren
        self.files = []
        
        # Counter für gefilterte Log-Nachrichten
        self.filtered_message_count = 0
        
        # Hauptlayout
        main_layout = QVBoxLayout()
        
        # Dateiauswahl-Bereich
        file_group = QGroupBox("Dateien")
        file_layout = QVBoxLayout()
        
        self.label = QLabel("Wähle Musikdateien zur Verarbeitung:")
        file_layout.addWidget(self.label)
        
        self.file_list = QListWidget()
        file_layout.addWidget(self.file_list)
        
        button_layout = QHBoxLayout()
        self.load_button = QPushButton("Dateien auswählen")
        self.load_button.clicked.connect(self.load_files)
        button_layout.addWidget(self.load_button)
        
        self.remove_button = QPushButton("Ausgewählte entfernen")
        self.remove_button.clicked.connect(self.remove_selected_files)
        button_layout.addWidget(self.remove_button)
        
        file_layout.addLayout(button_layout)
        file_group.setLayout(file_layout)
        main_layout.addWidget(file_group)
        
        # Verarbeitungsoptionen-Bereich
        options_group = QGroupBox("Verarbeitungsoptionen")
        options_layout = QVBoxLayout()
        
        # XML zu MIDI Konvertierung
        self.conversion_checkbox = QCheckBox("XML zu MIDI konvertieren (mit Wiederholungsexpansion, Tempowechseln und CC1-Kurven)")
        self.conversion_checkbox.setChecked(True)
        options_layout.addWidget(self.conversion_checkbox)
        
        # Digital Dirigent Checkbox
        self.conductor_checkbox = QCheckBox("Digital Dirigent aktivieren (Note-für-Note Interpretation)")
        self.conductor_checkbox.setChecked(True)
        self.conductor_checkbox.setToolTip("Musikalisch intuitive Interpretation auf Note-für-Note Basis")
        options_layout.addWidget(self.conductor_checkbox)
        
        # Tempo-Änderungen RadioButtons
        tempo_changes_layout = QHBoxLayout()
        tempo_changes_layout.setContentsMargins(20, 0, 0, 0)  # Einrückung
        
        self.tempo_changes_group = QButtonGroup(self)
        
        self.subtle_tempo_radio = QRadioButton("Nur subtile Änderungen (max. ±5%)")
        self.moderate_tempo_radio = QRadioButton("Moderate Änderungen (max. ±10%)")
        self.standard_tempo_radio = QRadioButton("Standard Änderungen (max. ±15%)")
        
        self.tempo_changes_group.addButton(self.subtle_tempo_radio)
        self.tempo_changes_group.addButton(self.moderate_tempo_radio)
        self.tempo_changes_group.addButton(self.standard_tempo_radio)
        
        # Standard ist moderate Änderungen
        self.moderate_tempo_radio.setChecked(True)
        
        tempo_changes_layout.addWidget(self.subtle_tempo_radio)
        tempo_changes_layout.addWidget(self.moderate_tempo_radio)
        tempo_changes_layout.addWidget(self.standard_tempo_radio)
        
        options_layout.addLayout(tempo_changes_layout)
        
        # Expressivitäts-Slider
        expressivity_layout = QHBoxLayout()
        expressivity_layout.addWidget(QLabel("Expressivität:"))
        self.expressivity_slider = QSlider(Qt.Orientation.Horizontal)
        self.expressivity_slider.setRange(1, 10)
        self.expressivity_slider.setValue(5)
        self.expressivity_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.expressivity_slider.setTickInterval(1)
        expressivity_layout.addWidget(self.expressivity_slider)
        self.expressivity_label = QLabel("5")
        expressivity_layout.addWidget(self.expressivity_label)
        options_layout.addLayout(expressivity_layout)
        
        # Verbinde Slider mit Label-Update
        self.expressivity_slider.valueChanged.connect(self.update_expressivity_label)
        
        # Interpretationsstil-Combo
        style_layout = QHBoxLayout()
        style_layout.addWidget(QLabel("Interpretationsvorlage:"))
        self.style_combo = QComboBox()
        self.style_combo.addItems(["Ausgewogen", "HIP (Historisch)", "Modern", "Romantisch", "Minimalistisch"])
        style_layout.addWidget(self.style_combo)
        options_layout.addLayout(style_layout)
        
        # CC1-Dynamik Checkbox
        self.cc1_checkbox = QCheckBox("CC1-Dynamikkurven hinzufügen")
        self.cc1_checkbox.setChecked(True)
        self.cc1_checkbox.setToolTip("Fügt automatisch generierte CC1-Dynamikkurven für ausdrucksvolle Wiedergabe hinzu")
        options_layout.addWidget(self.cc1_checkbox)
        
        # Keyswitch-Checkbox
        self.keyswitches_checkbox = QCheckBox("Keyswitches automatisch hinzufügen (OT Miroire)")
        self.keyswitches_checkbox.setChecked(True)
        self.keyswitches_checkbox.setToolTip("Fügt automatisch Keyswitches basierend auf musikalischem Kontext für Orchestral Tools Miroire hinzu")
        options_layout.addWidget(self.keyswitches_checkbox)
        
        # Debug-Ausgabe-Checkbox
        self.debug_checkbox = QCheckBox("Reduzierte Log-Ausgabe (nur wichtige Meldungen)")
        self.debug_checkbox.setChecked(True)
        self.debug_checkbox.setToolTip("Aktivieren für weniger detaillierte Logs und bessere Übersichtlichkeit")
        options_layout.addWidget(self.debug_checkbox)
        
        options_group.setLayout(options_layout)
        main_layout.addWidget(options_group)
        
        # Info-Bereich
        info_group = QGroupBox("🎼 Digital Dirigent Info")
        info_layout = QVBoxLayout()
        
        info_text = QLabel(
            "Der digitale Dirigent analysiert den Score aus musikalischer Perspektive "
            "und erzeugt eine ausdrucksvolle, organische Interpretation. Die Intensität "
            "der Tempoveränderungen kann über die Optionen angepasst werden.\n\n"
            "Die Expressivität und der Interpretationsstil beeinflussen die Parameter "
            "für Rubato, Artikulation und Dynamik."
        )
        info_text.setWordWrap(True)
        info_layout.addWidget(info_text)
        
        info_group.setLayout(info_layout)
        main_layout.addWidget(info_group)
        
        # Aktions-Bereich
        action_layout = QHBoxLayout()
        
        self.process_button = QPushButton("Verarbeitung starten")
        self.process_button.clicked.connect(self.start_processing)
        self.process_button.setMinimumHeight(40)
        action_layout.addWidget(self.process_button)
        
        main_layout.addLayout(action_layout)
        
        # Log-Bereich
        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout()
        
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setAcceptRichText(True)  # Erlaube Rich-Text für farbige Warnungen
        log_layout.addWidget(self.log_area)
        
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)
        
        # Setze Größenverhältnisse
        main_layout.setStretch(0, 2)  # Dateien
        main_layout.setStretch(1, 2)  # Optionen
        main_layout.setStretch(2, 1)  # Info
        main_layout.setStretch(4, 3)  # Log
        
        # Hauptwidget
        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)
        
        # Begrüßungsnachricht und Systemcheck
        self.log_message("🎵 Barockmusik MIDI-Prozessor gestartet")
        self.log_message("🆕 Verbesserte Version mit korrekter Verarbeitung von Wiederholungen und Tempowechseln")
        self.log_message("✨ NEU: Digital Dirigent für musikalisch intuitive Interpretationen")
        self.log_message("✨ NEU: MIDI-Humanisierungsfunktion für natürlicheren, weniger maschinellen Klang")
        self.log_message("✨ NEU: Automatische Keyswitch-Einfügung für Orchestral Tools Miroire")
        self.check_components()

    def update_expressivity_label(self):
        """Aktualisiert das Label des Expressivitäts-Sliders."""
        self.expressivity_label.setText(str(self.expressivity_slider.value()))

    def get_selected_files(self):
        """Gibt die ausgewählten Dateien zurück."""
        selected_items = self.file_list.selectedItems()
        
        if not selected_items:
            # Falls nichts ausgewählt ist, gib alle Dateien zurück
            if self.files:
                return self.files
            else:
                return []
        
        # Andernfalls gib nur die ausgewählten Dateien zurück
        selected_files = []
        
        for item in selected_items:
            index = self.file_list.row(item)
            if 0 <= index < len(self.files):
                selected_files.append(self.files[index])
        
        return selected_files

    def get_tempo_change_value(self):
        """Gibt den ausgewählten Wert für Tempoänderungen zurück."""
        if self.subtle_tempo_radio.isChecked():
            return 0.05  # ±5%
        elif self.moderate_tempo_radio.isChecked():
            return 0.10  # ±10%
        elif self.standard_tempo_radio.isChecked():
            return 0.15  # ±15%
        else:
            return 0.10  # Standardwert: ±10%

    def check_components(self):
        """Prüft, ob alle Komponenten vorhanden sind."""
        components = [
            ("dynamics.py", "Dynamikkurven-Generator"),
            ("midi_utils.py", "MIDI-Hilfsfunktionen"),
            ("instrument_mapper.py", "Instrumenterkennung"),
            ("musescore_helper.py", "MuseScore-Integration"),
            ("keyswitches.py", "Keyswitch-Automatik"),
            ("articulations_config.json", "Artikulationskonfiguration"),
            ("conductor/note_manipulator.py", "Digital Dirigent")
        ]
        
        for filename, description in components:
            if os.path.exists(filename):
                self.log_message(f"✅ {description} gefunden: {filename}")
            else:
                self.log_message(f"⚠️ {description} nicht gefunden: {filename}", warning=True)
        
        # Prüfe, ob MuseScore installiert ist
        musescore_path = self.find_musescore_path()
        if musescore_path:
            self.log_message(f"✅ MuseScore gefunden: {musescore_path}")
        else:
            self.log_message("⚠️ MuseScore konnte nicht gefunden werden! Bitte installieren Sie MuseScore 3 oder 4.", warning=True)
            self.log_message("⚠️ Download: https://musescore.org/de", warning=True)
    
    def find_musescore_path(self):
        """Sucht nach MuseScore auf dem System - konsolidierte Funktion."""
        import sys
        musescore_path = None
        
        # Betriebssystemspezifische Pfade
        if sys.platform.startswith('win'):
            # Windows-Pfade für MuseScore
            musescore_paths = [
                r"C:\Program Files\MuseScore 4\bin\MuseScore4.exe",
                r"C:\Program Files\MuseScore 3\bin\MuseScore3.exe",
                r"C:\Program Files (x86)\MuseScore 4\bin\MuseScore4.exe",
                r"C:\Program Files (x86)\MuseScore 3\bin\MuseScore3.exe"
            ]
        elif sys.platform.startswith('darwin'):
            # MacOS-Pfade für MuseScore
            musescore_paths = [
                "/Applications/MuseScore 4.app/Contents/MacOS/mscore",
                "/Applications/MuseScore 3.app/Contents/MacOS/mscore",
                "/Applications/MuseScore.app/Contents/MacOS/mscore"
            ]
        else:
            # Linux-Pfade
            musescore_paths = [
                "/usr/bin/mscore",
                "/usr/bin/musescore",
                "/usr/local/bin/mscore",
                "/usr/local/bin/musescore"
            ]
        
        for path in musescore_paths:
            if os.path.exists(path):
                musescore_path = path
                break
                
        return musescore_path

    def load_files(self):
        """Öffnet den Dateiauswahldialog und lädt die ausgewählten Dateien."""
        files, _ = QFileDialog.getOpenFileNames(
            self, 
            "Wähle Musikdateien", 
            "", 
            "Music Files (*.mid *.xml *.musicxml)"
        )
        if files:
            self.files.extend(files)
            self.file_list.clear()
            self.file_list.addItems([os.path.basename(f) for f in self.files])
            self.log_message(f"✅ {len(files)} Dateien geladen.")

    def remove_selected_files(self):
        """Entfernt die ausgewählten Dateien aus der Liste."""
        selected_items = self.file_list.selectedItems()
        if not selected_items:
            self.log_message("⚠️ Keine Datei ausgewählt zum Entfernen!", warning=True)
            return
        
        # Wir müssen rückwärts entfernen, um die Indizes nicht zu verschieben
        for item in reversed(selected_items):
            index = self.file_list.row(item)
            if 0 <= index < len(self.files):  # Sicherheitsprüfung
                filename = self.files[index]
                self.log_message(f"🗑️ Entferne {os.path.basename(filename)}...")
                self.files.pop(index)
                self.file_list.takeItem(index)
        
        self.log_message("✅ Ausgewählte Dateien entfernt.")

    def log_message(self, message, warning=False):
        """Fügt eine Nachricht zum Log-Bereich hinzu."""
        if warning:
            # Rote Warnung mit HTML formatieren
            message = f'<span style="color: red; font-weight: bold;">{message}</span>'
            self.log_area.append(message)
        else:
            # Normale Nachricht
            self.log_area.append(message)
        
        # Scrolle automatisch nach unten
        scrollbar = self.log_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    @pyqtSlot(str)
    def filter_and_log(self, message):
        """
        Filtert und protokolliert Nachrichten vom Worker.
        Diese Funktion reduziert den übermäßigen Output.
        """
        # Wenn reduzierte Logs aktiviert sind, filtere viele der detaillierten Nachrichten
        if self.debug_checkbox.isChecked():
            # Diese Muster immer anzeigen (wichtige Statusmeldungen)
            important_patterns = [
                "✅", "⚠️", "❌", "🔄", "🚀", "🎵", "🆕", "✨", 
                "Verarbeite Datei:", "Analysiere", "Erstelle",
                "Konvertiere", "Fertig", "Abgeschlossen", "Übertragen",
                "MIDI-Datei", "Tempowechsel", "CC1", "Keyswitches",
                "Digital Dirigent"
            ]
            
            # Diese Muster immer ignorieren (detaillierte Notendebug-Informationen)
            ignore_patterns = [
                "Note ", "Gesammelte Noten:", "Pitch", "Velocity",
                "Start=", "Dauer=", "Track ", "Kanal ", "MIDI Ticks", 
                "Stimme erstellt:", "Noten gesammelt", "Debug-Protokollierung",
                "Stack Trace:", "  - ", "Debug-Modus", "Original Score:",
                "  Durchschnittliche Tonhöhe", "  Rolle:", "  Tonhöhenbereich:",
                "  Track enthält", "  Phrasen erkannt", "MIDI-Struktur", 
                "Keine Noten zum Analysieren", "Min:", "Max:", "Durchschnitt:",
                "Erstellt:", "Keyswitch", "Dynamikpunkte", "Artikulation"
            ]
            
            # Prüfe, ob die Nachricht wichtig ist oder ignoriert werden soll
            is_important = any(pattern in message for pattern in important_patterns)
            should_ignore = any(pattern in message for pattern in ignore_patterns)
            
            if is_important or not should_ignore:
                self.log_message(message)
            else:
                # Zähle die unterdrückten Nachrichten
                self.filtered_message_count += 1
                # Aktualisiere gelegentlich die Anzahl der gefilterten Nachrichten
                if self.filtered_message_count % 100 == 0:
                    self.log_message(f"ℹ️ {self.filtered_message_count} detaillierte Logmeldungen gefiltert...")

        else:
            # Wenn keine Reduzierung gewünscht ist, zeige alle Nachrichten
            self.log_message(message)

    def start_processing(self):
        """Startet die Verarbeitung der ausgewählten Dateien."""
        if not self.files:
            self.log_message("⚠️ Keine Dateien ausgewählt!", warning=True)
            return
        
        # Reset der gefilterten Nachrichten
        self.filtered_message_count = 0
        
        do_conversion = self.conversion_checkbox.isChecked()
        do_conductor = self.conductor_checkbox.isChecked()
        do_cc1 = self.cc1_checkbox.isChecked()
        do_keyswitches = self.keyswitches_checkbox.isChecked()
        reduced_logging = self.debug_checkbox.isChecked()
        
        # Hole den Wert für Tempoänderungen
        tempo_change = self.get_tempo_change_value()
        
        self.log_message("🚀 Verarbeitung startet...")
        if do_conversion:
            self.log_message("ℹ️ XML zu MIDI Konvertierung aktiv (inkl. Wiederholungen und Tempi)")
        if do_conductor:
            tempo_str = "±5%" if tempo_change == 0.05 else "±10%" if tempo_change == 0.10 else "±15%"
            self.log_message(f"ℹ️ Digital Dirigent aktiv (Note-für-Note Interpretation, Tempo: {tempo_str})")
        
        if do_cc1:
            self.log_message("ℹ️ CC1-Dynamikkurven-Generator aktiv")
        else:
            self.log_message("ℹ️ CC1-Dynamikkurven-Generator inaktiv")
            
        if do_keyswitches:
            self.log_message("ℹ️ Miroire Keyswitch-Automatik aktiv")
        else:
            self.log_message("ℹ️ Miroire Keyswitch-Automatik inaktiv")
        
        # Prüfe mit der verbesserten Methode, ob MuseScore verfügbar ist
        musescore_path = self.find_musescore_path()
        if not musescore_path:
            self.log_message("⚠️ ACHTUNG: MuseScore konnte nicht gefunden werden! Fallback auf music21 (geringere Qualität)!", warning=True)
            self.log_message("⚠️ Bitte installieren Sie MuseScore für optimale Ergebnisse: https://musescore.org/de", warning=True)
        else:
            self.log_message(f"✅ MuseScore wird verwendet: {musescore_path}")
        
        # Starte den Worker mit den aktiven Optionen
        self.worker = AnalysisWorker(
            self.files, 
            do_conversion=do_conversion,
            do_conductor=do_conductor,
            do_cc1=do_cc1,
            do_keyswitches=do_keyswitches,
            expressivity=self.expressivity_slider.value() / 10.0,
            style=self.style_combo.currentText(),
            tempo_change=tempo_change
        )
        
        # Verbinde mit dem gefilterten Logger statt direkt mit log_message
        self.worker.progress_signal.connect(self.filter_and_log)
        self.worker.start()
        
        # Hinweis auf laufende Verarbeitung
        self.log_message("🔄 Verarbeitung läuft... Bitte warten Sie. Dies kann einige Minuten dauern.")
        self.log_message("✅ Die Ergebnisse werden im Ordner 'results' gespeichert.")