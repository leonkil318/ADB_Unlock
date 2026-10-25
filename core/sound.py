"""
Geely ADB Unlock Master - Retro Audio Synthesizer
Zero-dependency sound module using native platform facilities.
- Windows: winsound.Beep (micro-tones, retro arpeggios, sonar pulses)
- macOS / Linux: native system bell fallbacks
All audio plays in non-blocking daemon threads without freezing UI or ADB operations.
"""

import sys
import os
import time
import threading
import subprocess

SOUND_ENABLED = True
_lock = threading.Lock()
_bgm_playing = False


def _get_mp3_path():
    """Finds bundled or local zelda.mp3 file."""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        p = os.path.join(sys._MEIPASS, 'zelda.mp3')
        if os.path.exists(p):
            return p
    base = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(base, 'zelda.mp3')
    if os.path.exists(p):
        return p
    return None


def is_sound_enabled():
    global SOUND_ENABLED
    return SOUND_ENABLED


def is_bgm_playing():
    global _bgm_playing
    return _bgm_playing


def set_sound_enabled(enabled):
    global SOUND_ENABLED
    with _lock:
        SOUND_ENABLED = bool(enabled)
    if not SOUND_ENABLED:
        stop_bgm()


def play_bgm(loop=True):
    """Plays the retro Zelda MP3 track asynchronously in the background with zero external libraries."""
    global _bgm_playing
    if not SOUND_ENABLED or _bgm_playing:
        return

    mp3_path = _get_mp3_path()
    if not mp3_path:
        return

    def _worker():
        global _bgm_playing
        if sys.platform == "win32":
            try:
                import ctypes
                mci = ctypes.windll.winmm.mciSendStringW
                mci('close geely_bgm', None, 0, None)
                ret = mci(f'open "{mp3_path}" type mpegvideo alias geely_bgm', None, 0, None)
                if ret == 0:
                    cmd = 'play geely_bgm repeat' if loop else 'play geely_bgm'
                    mci(cmd, None, 0, None)
                    _bgm_playing = True
            except Exception:
                pass
        elif sys.platform == "darwin":
            try:
                subprocess.Popen(["afplay", mp3_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                _bgm_playing = True
            except Exception:
                pass

    threading.Thread(target=_worker, daemon=True).start()


def stop_bgm():
    """Stops background MP3 playback."""
    global _bgm_playing
    _bgm_playing = False
    if sys.platform == "win32":
        try:
            import ctypes
            mci = ctypes.windll.winmm.mciSendStringW
            mci('stop geely_bgm', None, 0, None)
            mci('close geely_bgm', None, 0, None)
        except Exception:
            pass


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


def _play_windows_tones(tones):
    """Plays a sequence of (frequency_hz, duration_ms) tuples via winsound."""
    try:
        import winsound
        for freq, dur in tones:
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


def play_sound(event):
    """
    Plays a retro sound effect asynchronously in a background thread.
    Supported events:
      - 'radar':   Subtle 18ms sonar ping during scanning / background wait
      - 'step':    Short confirmation chirp on progress advance
      - 'catch':   Sci-fi dual-tone on VHAL connection catch
      - 'success': 8-bit retro victory fanfare (C5-E5-G5-C6)
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
                _play_windows_tones([(1318, 60), (1760, 90)])
            elif event == "success":
                _play_windows_tones([(523, 65), (659, 65), (784, 65), (1046, 120)])
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
