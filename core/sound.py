"""
Geely ADB Unlock Master - Retro Audio Engine (Smooth In-Memory Synthesizer)
Synthesizes soft UI chimes directly in memory.
Uses standard library (math, wave, struct, winsound) with zero external pip libraries.
Features:
- Smooth ADSR envelopes (no clicks, no pops, no speaker scratches).
- In-memory WAV playback via Windows waveOut / SND_MEMORY.
- Enabled by default for interactive feedback (short non-looping chimes).
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

# Short UI Chimes
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
}


def is_sound_enabled():
    global SOUND_ENABLED
    return SOUND_ENABLED


def is_bgm_playing():
    return False


def set_sound_enabled(enabled):
    global SOUND_ENABLED
    with _lock:
        SOUND_ENABLED = bool(enabled)


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
    """Disabled: background melody removed."""
    pass


def stop_bgm():
    """Disabled: background melody removed."""
    pass


def toggle_sound():
    """Toggles short UI sound effects on/off."""
    global SOUND_ENABLED
    with _lock:
        SOUND_ENABLED = not SOUND_ENABLED
        state = SOUND_ENABLED
    if state:
        play_sound("step")
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
