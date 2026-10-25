"""
Geely ADB Unlock Master - Retro Audio Engine (Smooth In-Memory Synthesizer)
Synthesizes warm, melodic Zelda chimes and music-box tracks directly in memory.
Uses standard library (math, wave, struct, winsound) with zero external pip libraries.
Features:
- Smooth ADSR envelopes (no clicks, no pops, no speaker scratches).
- Warm Nintendo music-box / retro flute character (sine wave + harmonic overtone).
- In-memory WAV playback via Windows waveOut / SND_MEMORY.
- Background chiptune music loop (Saria's Song / Lost Woods) at comfortable soft volume.
"""

import sys
import os
import math
import struct
import io
import wave
import time
import threading

SOUND_ENABLED = True
_lock = threading.Lock()
_bgm_stop_event = threading.Event()
_bgm_thread = None


def _synthesize_wav(notes, sample_rate=22050, volume=0.22):
    """
    Synthesizes a list of (freq_hz, duration_sec) into 16-bit PCM in-memory WAV bytes
    with soft ADSR envelopes to prevent speaker clicks and harshness.
    """
    all_samples = []
    for freq, dur in notes:
        num_samples = int(sample_rate * dur)
        attack = min(num_samples // 4, int(sample_rate * 0.02))   # 20ms soft attack
        release = min(num_samples // 3, int(sample_rate * 0.035)) # 35ms soft release
        
        for i in range(num_samples):
            if i < attack:
                env = i / attack
            elif i > num_samples - release:
                env = (num_samples - i) / release
            else:
                env = 1.0
                
            t = i / sample_rate
            # Warm retro tone: fundamental sine wave + soft 2nd harmonic
            val = (math.sin(2 * math.pi * freq * t) * 0.8 + 
                   math.sin(2 * math.pi * freq * 2 * t) * 0.2)
            sample = int(val * env * volume * 32767)
            all_samples.append(max(-32767, min(32767, sample)))
            
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(struct.pack(f'<{len(all_samples)}h', *all_samples))
    return buf.getvalue()


# --- Sound Library Definitions ---

# 1. Legendary Zelda Secret Unlock Chime (G4 -> F#4 -> D#4 -> A3 -> G#3 -> E4 -> G#4 -> C5)
_ZELDA_SECRET_NOTES = [
    (392.00, 0.12),
    (369.99, 0.12),
    (311.13, 0.12),
    (220.00, 0.12),
    (207.65, 0.12),
    (329.63, 0.12),
    (415.30, 0.12),
    (523.25, 0.40),
]

# 2. Zelda Item Catch Fanfare (A#4 -> B4 -> C5 -> C#5)
_ZELDA_FANFARE_NOTES = [
    (466.16, 0.10),
    (493.88, 0.10),
    (523.25, 0.10),
    (554.37, 0.35),
]

# 3. Saria's Song (Lost Woods / Zelda Theme) - soothing music-box loop
_ZELDA_LOST_WOODS_NOTES = [
    (349.23, 0.15), (440.00, 0.15), (493.88, 0.30),
    (349.23, 0.15), (440.00, 0.15), (493.88, 0.30),
    (349.23, 0.15), (440.00, 0.15), (493.88, 0.15), (659.25, 0.15), (587.33, 0.30),
    (493.88, 0.15), (523.25, 0.15), (493.88, 0.15), (392.00, 0.15), (329.63, 0.40),
    (293.66, 0.15), (329.63, 0.15), (392.00, 0.15), (440.00, 0.40),
]

# 4. Short UI Chimes
_STEP_NOTES = [(987.77, 0.05)]
_RADAR_NOTES = [(659.25, 0.04)]
_ERROR_NOTES = [(261.63, 0.12), (185.00, 0.18)]

# Pre-synthesize in memory (takes < 0.05s total at startup)
_WAV_CACHE = {
    "success": _synthesize_wav(_ZELDA_SECRET_NOTES, volume=0.28),
    "catch":   _synthesize_wav(_ZELDA_FANFARE_NOTES, volume=0.25),
    "step":    _synthesize_wav(_STEP_NOTES, volume=0.20),
    "radar":   _synthesize_wav(_RADAR_NOTES, volume=0.14),
    "error":   _synthesize_wav(_ERROR_NOTES, volume=0.25),
    "bgm":     _synthesize_wav(_ZELDA_LOST_WOODS_NOTES, volume=0.18),
}


def is_sound_enabled():
    global SOUND_ENABLED
    return SOUND_ENABLED


def is_bgm_playing():
    return _bgm_thread is not None and _bgm_thread.is_alive() and not _bgm_stop_event.is_set()


def set_sound_enabled(enabled):
    global SOUND_ENABLED
    with _lock:
        SOUND_ENABLED = bool(enabled)
    if not SOUND_ENABLED:
        stop_bgm()


def _play_memory_wav(wav_bytes):
    """Plays an in-memory WAV buffer safely in a non-blocking way."""
    if sys.platform == "win32":
        try:
            import winsound
            winsound.PlaySound(wav_bytes, winsound.SND_MEMORY | winsound.SND_NODEFAULT)
        except Exception:
            pass
    else:
        try:
            sys.stdout.write('\a')
            sys.stdout.flush()
        except Exception:
            pass


def play_bgm(loop=True):
    """
    Plays the gentle Zelda music-box loop softly in the background.
    """
    global _bgm_thread, _bgm_stop_event
    if not SOUND_ENABLED or is_bgm_playing():
        return

    _bgm_stop_event.clear()
    bgm_data = _WAV_CACHE.get("bgm")

    def _worker():
        if sys.platform == "win32":
            try:
                import winsound
                while not _bgm_stop_event.is_set() and SOUND_ENABLED:
                    winsound.PlaySound(bgm_data, winsound.SND_MEMORY | winsound.SND_NODEFAULT)
                    if not loop or _bgm_stop_event.is_set():
                        break
                    # Pause between loops
                    for _ in range(15):
                        if _bgm_stop_event.is_set():
                            break
                        time.sleep(0.1)
            except Exception:
                pass

    _bgm_thread = threading.Thread(target=_worker, daemon=True)
    _bgm_thread.start()


def stop_bgm():
    """Immediately stops the background music-box loop."""
    global _bgm_stop_event
    _bgm_stop_event.set()
    if sys.platform == "win32":
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass


def toggle_sound():
    """Toggles retro sounds and music on/off."""
    global SOUND_ENABLED
    with _lock:
        SOUND_ENABLED = not SOUND_ENABLED
        state = SOUND_ENABLED
    if state:
        play_sound("step")
        play_bgm(loop=True)
    else:
        stop_bgm()
    return state


def play_sound(event):
    """
    Plays smooth, musical retro sound effects asynchronously in a background thread.
    No speaker pops, no clicks, no harshness.
    """
    if not SOUND_ENABLED:
        return

    wav_data = _WAV_CACHE.get(event)
    if not wav_data:
        return

    def _worker():
        _play_memory_wav(wav_data)

    threading.Thread(target=_worker, daemon=True).start()
