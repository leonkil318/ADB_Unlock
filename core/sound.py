"""
Geely ADB Unlock Master - Retro Audio Synthesizer (Pure Tone Zero-Dependency Engine)
Synthesizes retro chiptune melodies and sound effects directly via hardware timers.
- Windows: winsound.Beep (hardware micro-tones, 8-bit arpeggios, sonar radar)
- macOS / Linux: native system bell / terminal audio fallback
Total size: 0 bytes of external audio files. 100% pure Python standard library.
"""

import sys
import time
import threading

SOUND_ENABLED = True
_lock = threading.Lock()
_bgm_thread = None
_bgm_stop_event = threading.Event()

# Legendary Zelda 8-bit Soundtracks & Chimes (Frequency in Hz, Duration in ms)
ZELDA_SECRET_CHIME = [
    (392, 120),  # G4
    (370, 120),  # F#4
    (311, 120),  # D#4
    (220, 120),  # A3
    (207, 120),  # G#3
    (330, 120),  # E4
    (415, 120),  # G#4
    (523, 300),  # C5 - The legendary puzzle solved / secret unlock chime!
]

ZELDA_ITEM_FANFARE = [
    (466, 90),   # A#4
    (494, 90),   # B4
    (523, 90),   # C5
    (554, 280),  # C#5 - Item received fanfare
]

ZELDA_LOST_WOODS = [
    # Saria's Song (Lost Woods) - classic retro 8-bit chiptune
    (349, 130), (440, 130), (494, 260),
    (349, 130), (440, 130), (494, 260),
    (349, 130), (440, 130), (494, 130), (659, 130), (587, 260),
    (494, 130), (523, 130), (494, 130), (392, 130), (330, 350),
    (294, 130), (330, 130), (392, 130), (440, 350),
]


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


def _play_windows_tones(tones):
    """Plays a sequence of (frequency_hz, duration_ms) tuples via winsound."""
    try:
        import winsound
        for freq, dur in tones:
            if _bgm_stop_event.is_set() and tones is ZELDA_LOST_WOODS:
                break
            winsound.Beep(freq, dur)
    except Exception:
        pass


def _play_fallback_bell():
    """Terminal bell fallback for non-Windows platforms."""
    try:
        sys.stdout.write('\a')
        sys.stdout.flush()
    except Exception:
        pass


def play_bgm(loop=True):
    """Plays the retro Zelda chiptune melody in a background daemon thread."""
    global _bgm_thread
    if not SOUND_ENABLED or is_bgm_playing():
        return

    _bgm_stop_event.clear()

    def _worker():
        if sys.platform == "win32":
            while not _bgm_stop_event.is_set() and SOUND_ENABLED:
                _play_windows_tones(ZELDA_LOST_WOODS)
                if not loop:
                    break
                # Pause between loops
                for _ in range(15):
                    if _bgm_stop_event.is_set():
                        break
                    time.sleep(0.1)

    _bgm_thread = threading.Thread(target=_worker, daemon=True)
    _bgm_thread.start()


def stop_bgm():
    """Stops background chiptune melody."""
    _bgm_stop_event.set()


def toggle_sound():
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
    Plays a retro sound effect asynchronously in a background thread.
    Supported events:
      - 'radar':   Subtle 18ms sonar ping during scanning / background wait
      - 'step':    Short confirmation chirp on progress advance
      - 'catch':   Zelda item fanfare on VHAL connection catch
      - 'success': Legendary Zelda Secret Unlock chime
      - 'error':   Low dual warning buzz
    """
    if not SOUND_ENABLED:
        return

    def _worker():
        if sys.platform == "win32":
            if event == "radar":
                _play_windows_tones([(2400, 18)])
            elif event == "step":
                _play_windows_tones([(987, 35)])
            elif event == "catch":
                _play_windows_tones(ZELDA_ITEM_FANFARE)
            elif event == "success":
                _play_windows_tones(ZELDA_SECRET_CHIME)
            elif event == "error":
                _play_windows_tones([(220, 140), (150, 190)])
        else:
            if event in ("catch", "success"):
                _play_fallback_bell()
                time.sleep(0.1)
                _play_fallback_bell()
            elif event in ("error", "step"):
                _play_fallback_bell()

    threading.Thread(target=_worker, daemon=True).start()
