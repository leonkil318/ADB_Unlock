"""
Geely ADB Unlock Master - Retro Audio Engine
Zero-dependency retro sound effects using standard platform facilities.
- Windows: winsound.Beep (micro-tones, clean retro arpeggios, soft progress beacon)
- macOS / Linux: native system bell / audio alerts
All sounds play in non-blocking daemon threads without freezing UI or ADB operations.
"""

import sys
import time
import threading

SOUND_ENABLED = True
_lock = threading.Lock()


def is_sound_enabled():
    global SOUND_ENABLED
    return SOUND_ENABLED


def set_sound_enabled(enabled):
    global SOUND_ENABLED
    with _lock:
        SOUND_ENABLED = bool(enabled)


def toggle_sound():
    """Toggles retro sounds on/off."""
    global SOUND_ENABLED
    with _lock:
        SOUND_ENABLED = not SOUND_ENABLED
        state = SOUND_ENABLED
    if state:
        play_sound("step")
    return state


def _play_windows_tones(tones):
    """Plays a sequence of (frequency_hz, duration_ms) tuples via winsound."""
    try:
        import winsound
        for freq, dur in tones:
            winsound.Beep(int(freq), int(dur))
    except Exception:
        pass


def _play_fallback_bell():
    """Terminal bell fallback for non-Windows platforms."""
    try:
        sys.stdout.write('\a')
        sys.stdout.flush()
    except Exception:
        pass


def play_sound(event):
    """
    Plays clear, recognizable, pleasant retro 8-bit sound effects.
    Durations are tuned (45-160ms) so they sound like musical retro chimes,
    never speaker scratches or pops.
    """
    if not SOUND_ENABLED:
        return

    def _worker():
        if sys.platform == "win32":
            if event == "radar":
                # Soft, pleasant progress beacon (659Hz E5, 30ms - gentle, musical, no scratch)
                _play_windows_tones([(659, 30)])
            elif event == "step":
                # Quick confirmation chirp on menu / key press (987Hz B5, 40ms)
                _play_windows_tones([(987, 40)])
            elif event == "catch":
                # Dual sci-fi tone on VHAL catch (E6 -> A6)
                _play_windows_tones([(1318, 70), (1760, 110)])
            elif event == "success":
                # Classic triumphant 8-bit victory fanfare: C5 -> E5 -> G5 -> C6
                _play_windows_tones([(523, 75), (659, 75), (784, 75), (1046, 160)])
            elif event == "error":
                # Low dual-tone warning buzzer
                _play_windows_tones([(261, 140), (185, 200)])
        else:
            if event in ("catch", "success"):
                _play_fallback_bell()
                time.sleep(0.1)
                _play_fallback_bell()
            elif event in ("error", "step", "radar"):
                _play_fallback_bell()

    threading.Thread(target=_worker, daemon=True).start()
