"""
Dynamics Modul für den Barockmusik MIDI-Prozessor
-------------------------------------------------
Dieses Modul enthält Funktionen zur Erzeugung von dynamischen Konturen (CC1) 
basierend auf der musikalischen Analyse des Scores.
"""

import numpy as np
import music21 as m21
import logging
from collections import defaultdict

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DYNAMICS_MAPPING = {
    'ppp': 10,
    'pp': 20,
    'p': 40,
    'mp': 60,
    'mf': 80,
    'f': 100,
    'ff': 120,
    'fff': 127
}

def extract_dynamic_points_baroque(score):
    """
    Extrahiert dynamische Konturen basierend auf musikalisch sinnvollen Merkmalen für Barockmusik.
    Berücksichtigt melodische Konturen, Phrasierung und barocke Spielpraxis.
    Erzeugt ausdrucksstärkere Dynamikkurven mit kontrolliertem Wertebereich.
    
    Args:
        score: music21 Score-Objekt
        
    Returns:
        Dictionary mit Stimmenindex als Schlüssel und Listen von (offset, dynamic_value) als Werte
    """
    voice_dynamics = defaultdict(list)
    parts = score.getElementsByClass(m21.stream.Part)
    
    # Analysiere zuerst den Gesamtstil
    time_signatures = score.getTimeSignatures()
    has_4_4 = any(ts.ratioString == '4/4' for ts in time_signatures)
    has_3_4 = any(ts.ratioString == '3/4' for ts in time_signatures)
    
    # Bestimme Taktart-abhängige Betonungsschemata
    if has_3_4:
        # 3/4 (Menuett, etc.): Betont auf 1, leichter auf 2 und 3
        beat_weights = {1.0: 1.2, 2.0: 0.7, 3.0: 0.6}  # Stärkere Betonung auf 1
    else:
        # 4/4 oder andere: Betont auf 1 und 3
        beat_weights = {1.0: 1.2, 2.0: 0.6, 3.0: 0.9, 4.0: 0.7}  # Stärkere Betonungen
    
    # Analysiere jede Stimme separat
    for idx, part in enumerate(parts):
        # Standard-Dynamikpunkte (Start und Ende)
        total_duration = score.highestTime
        voice_dynamics[idx].append((0, 70))  # Starte mit mf
        voice_dynamics[idx].append((total_duration, 65))  # Ende etwas leiser
        
        # SCHRITT 1: Erkenne Phrasen und Höhepunkte
        measures = list(part.getElementsByClass(m21.stream.Measure))
        if not measures:
            continue
            
        # Finde den Ambitus (Tonhöhenbereich) dieser Stimme
        notes = list(part.flatten().getElementsByClass(m21.note.Note))
        if not notes:
            continue
            
        pitches = [n.pitch.midi for n in notes]
        min_pitch = min(pitches)
        max_pitch = max(pitches)
        pitch_range = max_pitch - min_pitch
        
        # SCHRITT 2: Definiere harmonische/melodische Höhepunkte
        # VERBESSERT: Größere Mindestabstände zwischen Phrasen einführen
        phrase_starts = []
        phrase_peaks = []
        phrase_ends = []
        
        # Wir erkennen Phrasen anhand von langen Noten, Pausen und melodischen Konturen
        current_phrase_notes = []
        
        for i, note in enumerate(notes):
            # Neue Phrase starten, falls nötig
            if not current_phrase_notes:
                current_phrase_notes.append(note)
                try:
                    phrase_starts.append((note.getOffsetInHierarchy(score), note))
                except:
                    # Fallback, wenn getOffsetInHierarchy scheitert
                    measure = note.getContextByClass('Measure')
                    if measure:
                        measure_offset = measure.getOffsetBySite(part)
                        note_offset = note.getOffsetBySite(measure)
                        phrase_starts.append((measure_offset + note_offset, note))
                    else:
                        phrase_starts.append((note.offset, note))
                continue
            
            # Prüfe, ob eine Phrase endet
            phrase_ended = False
            
            # Nach langer Note - VERBESSERT: Längere Schwellenwerte für klarere Phrasentrennung
            if i > 0 and hasattr(notes[i-1], 'duration') and notes[i-1].duration.quarterLength >= 2.5:  # Erhöht von 2.0
                phrase_ended = True
                
            # Nach einer Pause (diese liegt zwischen den Noten) - VERBESSERT: Längere Pausen erkennen
            elif i > 0:
                prev_end = notes[i-1].offset + notes[i-1].duration.quarterLength
                this_start = note.offset
                if this_start - prev_end >= 1.5:  # Erhöht von 1.0 - Pausen >= 1.5 Viertelnoten
                    phrase_ended = True
            
            # Nach großem Intervallsprung - VERBESSERT: Größere Intervalle für Phrasentrennung
            elif i > 0 and hasattr(note, 'pitch') and hasattr(notes[i-1], 'pitch'):
                interval = abs(note.pitch.midi - notes[i-1].pitch.midi)
                if interval > 9:  # Erhöht von 7 - Größer als eine Sexte
                    phrase_ended = True
            
            # Bei Taktanfang, wenn die Phrase schon länger ist
            elif hasattr(note, 'beat') and note.beat == 1.0 and len(current_phrase_notes) >= 6:  # Erhöht von 4
                phrase_ended = True
            
            # Wenn die Phrase endet, finde den melodischen Höhepunkt
            if phrase_ended and current_phrase_notes:
                # Finde die höchste Note der Phrase als dynamischen Höhepunkt
                phrase_highest = max(current_phrase_notes, key=lambda n: n.pitch.midi if hasattr(n, 'pitch') else 0)
                try:
                    phrase_peaks.append((phrase_highest.getOffsetInHierarchy(score), phrase_highest))
                except:
                    # Fallback
                    measure = phrase_highest.getContextByClass('Measure')
                    if measure:
                        measure_offset = measure.getOffsetBySite(part)
                        note_offset = phrase_highest.getOffsetBySite(measure)
                        phrase_peaks.append((measure_offset + note_offset, phrase_highest))
                    else:
                        phrase_peaks.append((phrase_highest.offset, phrase_highest))
                
                # Die letzte Note der Phrase ist das Phrasenende
                last_note = current_phrase_notes[-1]
                try:
                    last_offset = last_note.getOffsetInHierarchy(score)
                except:
                    # Fallback
                    measure = last_note.getContextByClass('Measure')
                    if measure:
                        measure_offset = measure.getOffsetBySite(part)
                        note_offset = last_note.getOffsetBySite(measure)
                        last_offset = measure_offset + note_offset
                    else:
                        last_offset = last_note.offset
                
                phrase_ends.append((last_offset + last_note.duration.quarterLength, last_note))
                
                # Beginne eine neue Phrase
                current_phrase_notes = [note]
                try:
                    phrase_starts.append((note.getOffsetInHierarchy(score), note))
                except:
                    # Fallback
                    measure = note.getContextByClass('Measure')
                    if measure:
                        measure_offset = measure.getOffsetBySite(part)
                        note_offset = note.getOffsetBySite(measure)
                        phrase_starts.append((measure_offset + note_offset, note))
                    else:
                        phrase_starts.append((note.offset, note))
            else:
                # Füge die Note zur aktuellen Phrase hinzu
                current_phrase_notes.append(note)
        
        # Verarbeite die letzte Phrase, falls vorhanden
        if current_phrase_notes:
            phrase_highest = max(current_phrase_notes, key=lambda n: n.pitch.midi if hasattr(n, 'pitch') else 0)
            try:
                phrase_peaks.append((phrase_highest.getOffsetInHierarchy(score), phrase_highest))
            except:
                # Fallback
                measure = phrase_highest.getContextByClass('Measure')
                if measure:
                    measure_offset = measure.getOffsetBySite(part)
                    note_offset = phrase_highest.getOffsetBySite(measure)
                    phrase_peaks.append((measure_offset + note_offset, phrase_highest))
                else:
                    phrase_peaks.append((phrase_highest.offset, phrase_highest))
            
            last_note = current_phrase_notes[-1]
            try:
                last_offset = last_note.getOffsetInHierarchy(score)
            except:
                # Fallback
                measure = last_note.getContextByClass('Measure')
                if measure:
                    measure_offset = measure.getOffsetBySite(part)
                    note_offset = last_note.getOffsetBySite(measure)
                    last_offset = measure_offset + note_offset
                else:
                    last_offset = last_note.offset
                    
            phrase_ends.append((last_offset + last_note.duration.quarterLength, last_note))
        
        # SCHRITT 3: Erzeuge dynamische Punkte für Phrasierung - VERBESSERT: Weniger, aber musikalisch wichtigere Punkte
        for i, (peak_offset, peak_note) in enumerate(phrase_peaks):
            # Bestimme den dynamischen Wert basierend auf der relativen Tonhöhe
            pitch_factor = (peak_note.pitch.midi - min_pitch) / pitch_range if pitch_range > 0 else 0.5
            
            # Je höher die Note, desto stärker (typisch für Barockinterpretation)
            peak_value = 60 + int(pitch_factor * 45)  # Reduzierter Bereich für gleichmäßigeren Verlauf
            
            # Taktposition berücksichtigen - Noten auf betonten Zählzeiten stärker
            if hasattr(peak_note, 'beat'):
                beat = peak_note.beat
                beat_weight = beat_weights.get(beat, 0.8)
                peak_value = int(peak_value * beat_weight)
            
            # Position in der Gesamtform berücksichtigen
            if i == len(phrase_peaks) // 2:  # Zentraler Höhepunkt
                peak_value += 10  # Reduziert von 15 für weniger extreme Sprünge
            
            # Begrenze auf gültige MIDI-Werte mit engerer Begrenzung
            peak_value = max(min(peak_value, 110), 45)
            
            # Füge den dynamischen Höhepunkt hinzu
            voice_dynamics[idx].append((peak_offset, peak_value))
            
            # Füge Punkte für Phrasenanfang und -ende hinzu, wenn sie existieren
            if i < len(phrase_starts):
                start_offset = phrase_starts[i][0]
                # Phrasenanfang leicht betont
                start_value = max(55, peak_value - 20)  # Reduzierter Kontrast für sanftere Übergänge
                voice_dynamics[idx].append((start_offset, start_value))
            
            if i < len(phrase_ends):
                end_offset = phrase_ends[i][0]
                # Phrasenende abfallend
                end_value = max(45, peak_value - 25)  # Reduzierter Kontrast für sanftere Übergänge
                voice_dynamics[idx].append((end_offset, end_value))
                
            # ÜBERARBEITET: Nur noch wichtige strukturelle Noten innerhalb der Phrase hinzufügen
            if i < len(current_phrase_notes) and len(current_phrase_notes) > 5:
                # Wähle nur wenige strukturell wichtige Noten aus der Phrase für zusätzliche Dynamikpunkte
                phrase_length = len(current_phrase_notes)
                
                # NEU: Nur 1-2 zusätzliche Punkte pro Phrase für wichtige strukturelle Noten
                important_positions = []
                if phrase_length >= 10:
                    important_positions = [phrase_length // 3, phrase_length * 2 // 3]
                elif phrase_length >= 5:
                    important_positions = [phrase_length // 2]
                
                for pos in important_positions:
                    if 0 <= pos < phrase_length:
                        note = current_phrase_notes[pos]
                        try:
                            note_offset = note.getOffsetInHierarchy(score)
                        except:
                            # Fallback
                            measure = note.getContextByClass('Measure')
                            if measure:
                                measure_offset = measure.getOffsetBySite(part)
                                note_offset = note.getOffsetBySite(measure)
                            else:
                                note_offset = note.offset
                        
                        # Mittelpunkt zwischen Start und Peak oder zwischen Peak und Ende
                        if hasattr(note, 'pitch'):
                            note_pitch_factor = (note.pitch.midi - min_pitch) / pitch_range if pitch_range > 0 else 0.5
                            if note_offset < peak_offset:
                                # Zwischen Start und Peak
                                position_factor = (note_offset - start_offset) / (peak_offset - start_offset) if peak_offset > start_offset else 0.5
                                note_value = int(start_value + (peak_value - start_value) * position_factor)
                            else:
                                # Zwischen Peak und Ende
                                position_factor = (note_offset - peak_offset) / (end_offset - peak_offset) if end_offset > peak_offset else 0.5
                                note_value = int(peak_value - (peak_value - end_value) * position_factor)
                            
                            voice_dynamics[idx].append((note_offset, note_value))
        
        # VERBESSERT: Filtere Punkte, die zu nah beieinander liegen
        voice_dynamics[idx].sort(key=lambda x: x[0])
        filtered_points = []
        last_time = -float('inf')
        min_time_distance = 1.0  # Mindestabstand in Beats zwischen Dynamikpunkten
        
        for time, value in voice_dynamics[idx]:
            if time - last_time >= min_time_distance:
                filtered_points.append((time, value))
                last_time = time
            else:
                # Wenn ein Punkt zu nah am letzten ist, aber wichtiger (z.B. höhere/tiefere Dynamik),
                # ersetze den letzten Punkt
                if filtered_points and abs(filtered_points[-1][1] - value) > 10:
                    filtered_points[-1] = (time, value)
                    last_time = time
        
        voice_dynamics[idx] = filtered_points
        
        # SCHRITT 4: Füge nur noch wenige Konturpunkte für fließende Übergänge hinzu
        voice_dynamics[idx].sort(key=lambda x: x[0])
        interpolated_points = []
        
        for i in range(1, len(voice_dynamics[idx])):
            curr_offset, curr_value = voice_dynamics[idx][i]
            prev_offset, prev_value = voice_dynamics[idx][i-1]
            
            # Nur für sehr große Abstände zusätzliche Punkte einfügen
            if curr_offset - prev_offset > 8.0:  # Erhöht von 4.0 auf 8.0 Viertelnoten
                # Füge einen Zwischenpunkt in der Mitte ein
                mid_offset = prev_offset + (curr_offset - prev_offset) / 2
                mid_value = int(prev_value + (curr_value - prev_value) / 2)
                interpolated_points.append((mid_offset, mid_value))
        
        # Füge die interpolierten Punkte hinzu
        voice_dynamics[idx].extend(interpolated_points)
        voice_dynamics[idx].sort(key=lambda x: x[0])
    
    return voice_dynamics

def extract_dynamic_points(score):
    """
    Extrahiere dynamische Markierungen aus dem Score und gib ein Dictionary zurück,
    das für jede Stimme eine Liste von (Offset, Wert)-Tupeln enthält.
    
    Args:
        score: music21 Score-Objekt
        
    Returns:
        Dictionary mit Stimmenindex als Schlüssel und Listen von (offset, dynamic_value) als Werte
    """
    # NEUE IMPLEMENTIERUNG FÜR BAROCKE DYNAMIK
    return extract_dynamic_points_baroque(score)

def non_linear_interpolate_dynamics(voice_dynamics_dict, total_duration, resolution=0.1, k=0.1, x0=70, smoothing_passes=2):
    """
    Interpoliert dynamische Werte mit wesentlich größerem Dynamikumfang und klareren Konturen.
    """
    result = {}
    resolution = max(0.1, resolution)
    times = np.arange(0, total_duration + resolution, resolution)
    
    # Stelle sicher, dass die Kurven nicht über die Dauer des Stücks hinausgehen
    for part_idx, points in voice_dynamics_dict.items():
        if points:
            points = sorted(points, key=lambda x: x[0])
            if points[-1][0] < total_duration:
                end_value = max(40, points[-1][1] - 10)
                points.append((total_duration, end_value))
            points = [(t, v) for t, v in points if t <= total_duration]
            voice_dynamics_dict[part_idx] = points
    
    for part_idx, points in voice_dynamics_dict.items():
        if not points:
            interp_values = np.full_like(times, 60, dtype=float)
        else:
            measured_times = [pt[0] for pt in points]
            measured_values = [pt[1] for pt in points]
            
            if len(measured_times) == 1:
                measured_times.append(total_duration)
                measured_values.append(measured_values[0])
            
            # WICHTIGSTE ÄNDERUNG: Erhöhe den Dynamikumfang DRASTISCH
            # Erweitere den Bereich von ~52-93 auf ~30-115
            min_value = min(measured_values)
            max_value = max(measured_values)
            range_size = max_value - min_value
            
            if range_size < 50:  # Wenn der Bereich zu klein ist
                # Berechne neue Werte mit vergrößertem Bereich
                expanded_values = []
                for val in measured_values:
                    # Normalisieren (0-1) und dann auf größeren Bereich abbilden
                    normalized = (val - min_value) / max(1, range_size)
                    # Abbildung auf 30-115 für viel mehr Kontrast
                    expanded = 30 + normalized * 85
                    expanded_values.append(expanded)
                measured_values = expanded_values
            
            # NEU: Füge Zwischenpunkte ein für weichere Übergänge
            if len(measured_times) >= 3:
                smooth_times = []
                smooth_values = []
                
                for i in range(len(measured_times) - 1):
                    # Originalpunkt hinzufügen
                    smooth_times.append(measured_times[i])
                    smooth_values.append(measured_values[i])
                    
                    # Abstand zum nächsten Punkt
                    time_diff = measured_times[i+1] - measured_times[i]
                    value_diff = measured_values[i+1] - measured_values[i]
                    
                    # Nur Zwischenpunkte bei größeren Abständen und Werteänderungen
                    if time_diff > 2.0 and abs(value_diff) > 10:
                        # Füge zwei Zwischenpunkte ein für weicheren Übergang
                        # Erster Zwischenpunkt: 30% des Weges, näher am Ausgangswert
                        t1 = measured_times[i] + time_diff * 0.3
                        v1 = measured_values[i] + value_diff * 0.15  # Langsamerer Start der Änderung
                        
                        # Zweiter Zwischenpunkt: 70% des Weges, näher am Zielwert
                        t2 = measured_times[i] + time_diff * 0.7
                        v2 = measured_values[i] + value_diff * 0.85  # Schnellerer Abschluss der Änderung
                        
                        smooth_times.extend([t1, t2])
                        smooth_values.extend([v1, v2])
                
                # Letzten Originalpunkt hinzufügen
                smooth_times.append(measured_times[-1])
                smooth_values.append(measured_values[-1])
                
                measured_times = smooth_times
                measured_values = smooth_values
            
            # Lineare Interpolation zwischen den Punkten
            interp_values = np.interp(times, measured_times, measured_values)
            
            # Entferne kleine Schwankungen und betone musikalisch wichtige Bögen
            # Identifiziere wichtige Punkte (lokale Maxima und Minima)
            important_points = set()
            window_size = 10  # Größeres Fenster für bedeutsamere Punkte
            
            for i in range(window_size, len(measured_times) - window_size):
                values_before = measured_values[i-window_size:i]
                values_after = measured_values[i+1:i+window_size+1]
                
                # Ist dieser Punkt ein lokales Maximum oder Minimum?
                is_max = measured_values[i] > max(values_before + values_after)
                is_min = measured_values[i] < min(values_before + values_after)
                
                if is_max or is_min:
                    idx = np.abs(times - measured_times[i]).argmin()
                    important_points.add(idx)
                    
                    # Verstärke für größeren Kontrast
                    if is_max:
                        # NEU: Stärkere Betonung der Höhepunkte
                        interp_values[idx] = min(115, interp_values[idx] * 1.15)
                        
                        # NEU: Verstärke allmählich zum Höhepunkt hin
                        ramp_width = 5  # Anzahl der Punkte vor/nach dem Höhepunkt
                        for j in range(1, ramp_width + 1):
                            if idx - j >= 0:
                                boost_factor = 1 + (0.15 * (ramp_width - j) / ramp_width)
                                interp_values[idx - j] = min(115, interp_values[idx - j] * boost_factor)
                            if idx + j < len(interp_values):
                                fade_factor = 1 + (0.05 * (ramp_width - j) / ramp_width)
                                interp_values[idx + j] = min(115, interp_values[idx + j] * fade_factor)
                    
                    if is_min:
                        # NEU: Stärkere Absenkung der Tiefpunkte
                        interp_values[idx] = max(30, interp_values[idx] * 0.85)
                        
                        # NEU: Sanftere Absenkung zu Minima
                        ramp_width = 4  # Anzahl der Punkte vor/nach dem Minimum
                        for j in range(1, ramp_width + 1):
                            if idx - j >= 0:
                                reduce_factor = 1 - (0.05 * (ramp_width - j) / ramp_width)
                                interp_values[idx - j] = max(30, interp_values[idx - j] * reduce_factor)
                            if idx + j < len(interp_values):
                                recover_factor = 1 - (0.03 * (ramp_width - j) / ramp_width)
                                interp_values[idx + j] = max(30, interp_values[idx + j] * recover_factor)
            
            # Glättere Übergänge, aber behalte wichtige Punkte bei
            smoothing_passes = 2  # Reduziert für weniger Verwässerung
            for _ in range(smoothing_passes):
                smoothed = np.copy(interp_values)
                for i in range(1, len(interp_values) - 1):
                    if i not in important_points:
                        # Stärkere Gewichtung des aktuellen Werts
                        smoothed[i] = 0.6 * interp_values[i] + 0.2 * interp_values[i-1] + 0.2 * interp_values[i+1]
                interp_values = smoothed
        
        # Runden und Begrenzen auf gültige MIDI CC-Werte
        cc_values = [int(min(max(val, 0), 127)) for val in interp_values]
        
        # NEU: Verbessertes Filtern, um sowohl unnötige Punkte zu entfernen als auch
        # musikalisch wichtige Punkte zu behalten
        filtered_cc = []
        prev_value = None
        prev_time = -999
        
        for i, (t, v) in enumerate(zip(times, cc_values)):
            # NEU: Adaptive Filterung basierend auf Werteänderung
            min_change_threshold = 3  # Kleine Änderungen werden gefiltert
            
            # Berechne die Änderungsrate
            if prev_value is not None:
                change_rate = abs(v - prev_value) / max(0.1, t - prev_time)
                
                # Bei starker Änderungsrate (steiler Anstieg/Abfall) benötigen wir mehr Punkte
                if change_rate > 20:  # Steile Änderung
                    min_change_threshold = 2  # Mehr Punkte behalten
                    min_time_gap = 0.3  # Punkte können näher beieinander liegen
                elif change_rate > 10:  # Moderate Änderung
                    min_change_threshold = 3
                    min_time_gap = 0.5
                else:  # Allmähliche Änderung
                    min_change_threshold = 4
                    min_time_gap = 0.8
            else:
                # Standardwerte für den ersten Punkt
                min_time_gap = 0.5
            
            # Entscheidungskriterien
            value_change = prev_value is None or abs(v - prev_value) >= min_change_threshold
            time_gap = prev_time is None or t - prev_time > min_time_gap
            
            # Behalte auch Kurvenkrümmungspunkte, wo sich die Richtung ändert
            direction_change = False
            if i > 1 and i < len(cc_values) - 1:
                prev_direction = cc_values[i-1] - cc_values[i-2]
                current_direction = cc_values[i] - cc_values[i-1]
                next_direction = cc_values[i+1] - cc_values[i]
                
                # Wenn sich die Richtung ändert, ist dies ein wichtiger Punkt
                if (prev_direction * current_direction <= 0) or (current_direction * next_direction <= 0):
                    direction_change = True
            
            # Behalte den Punkt, wenn er wichtig ist
            if value_change or time_gap or direction_change or i == 0 or i == len(cc_values) - 1:
                filtered_cc.append((t, v))
                prev_value = v
                prev_time = t
        
        result[part_idx] = filtered_cc
    
    return result