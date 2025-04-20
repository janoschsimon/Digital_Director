"""
Conductor Paket für den Barockmusik MIDI-Prozessor
-------------------------------------------------
Enthält die Module für den neuen Digital Dirigenten, der auf Note-für-Note
Interpretation statt globaler Tempoänderungen basiert.
"""

from conductor.note_manipulator import NoteLevelInterpreter
from conductor.voice_analyzer import MusicalVoice, NoteProperties

__version__ = '2.0.0'
