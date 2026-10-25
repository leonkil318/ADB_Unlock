"""
Geely ADB Unlock Master - Retro Audio Engine
Plays native audio effects and background chiptune track (core/zelda.mp3)
across Windows, macOS, and Linux with Zero External Dependencies (no pip packages needed).
- Windows: Native WinMM MCI subsystem (winmm.dll)
- macOS: Native afplay (/usr/bin/afplay)
- Linux: Native audio tools (mpg123, mpv, ffplay, cvlc, play)
Volume is comfortably balanced (35%) so it never deafens or pierces ears.
"""

import sys
import os
import time
import shutil
import threading
import subprocess

SOUND_ENABLED = True
_lock = threading.Lock()
_bgm_playing = False
_bgm_process = None


def _get_mp3_path():
    """Locates the bundled or local zelda.mp3 audio file."""
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


def play_bgm(loop=True, volume=350):
    """
    Plays the Zelda background soundtrack softly (volume=350 out of 1000)
    in a non-blocking background process across Windows, macOS, and Linux.
    """
    global _bgm_playing, _bgm_process
    if not SOUND_ENABLED or _bgm_playing:
        return

    mp3_path = _get_mp3_path()
    if not mp3_path or not os.path.exists(mp3_path):
        return

    def _worker():
        global _bgm_playing, _bgm_process
        if sys.platform == "win32":
            try:
                import ctypes
                mci = ctypes.windll.winmm.mciSendStringW
                mci('close geely_bgm', None, 0, None)
                ret = mci(f'open "{mp3_path}" type mpegvideo alias geely_bgm', None, 0, None)
                if ret == 0:
                    # Set soft pleasant volume (0-1000 scale)
                    mci(f'setaudio geely_bgm volume to {volume}', None, 0, None)
                    cmd = 'play geely_bgm repeat' if loop else 'play geely_bgm'
                    mci(cmd, None, 0, None)
                    _bgm_playing = True
            except Exception:
                pass
        elif sys.platform == "darwin":
            try:
                vol_float = max(0.05, min(1.0, volume / 1000.0))
                cmd = ["afplay", "-v", str(vol_float), mp3_path]
                _bgm_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                _bgm_playing = True
            except Exception:
                pass
        else:
            # Linux native fallbacks
            for player in ["mpg123", "mpv", "ffplay", "cvlc", "play"]:
                if shutil.which(player):
                    try:
                        if player == "mpg123":
                            cmd = ["mpg123", "-q", "--scale", str(int(volume * 32.768)), mp3_path]
                        elif player == "mpv":
                            cmd = ["mpv", "--no-video", f"--volume={int(volume / 10)}", mp3_path]
                        elif player == "ffplay":
                            cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", mp3_path]
                        elif player == "cvlc":
                            cmd = ["cvlc", "--play-and-exit", mp3_path]
                        else:
                            cmd = ["play", "-q", mp3_path]
                        _bgm_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        _bgm_playing = True
                        break
                    except Exception:
                        pass

    threading.Thread(target=_worker, daemon=True).start()


def stop_bgm():
    """Immediately stops background audio on any OS."""
    global _bgm_playing, _bgm_process
    _bgm_playing = False

    if sys.platform == "win32":
        try:
            import ctypes
            mci = ctypes.windll.winmm.mciSendStringW
            mci('stop geely_bgm', None, 0, None)
            mci('close geely_bgm', None, 0, None)
        except Exception:
            pass

    if _bgm_process is not None:
        try:
            _bgm_process.terminate()
            _bgm_process.wait(timeout=0.5)
        except Exception:
            try:
                _bgm_process.kill()
            except Exception:
                pass
        _bgm_process = None


def toggle_sound():
    """Toggles sound on/off and updates playback state."""
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


def _play_soft_click():
    """Subtle, non-ear-piercing micro-click for UI steps."""
    if sys.platform == "win32":
        try:
            import winsound
            winsound.Beep(1200, 25)
        except Exception:
            pass


def _play_sonar_ping():
    """Soft 18ms radar ping for progress spinner."""
    if sys.platform == "win32":
        try:
            import winsound
            winsound.Beep(2200, 15)
        except Exception:
            pass


def _play_fallback_bell():
    try:
        sys.stdout.write('\a')
        sys.stdout.flush()
    except Exception:
        pass


def play_sound(event):
    """
    Plays subtle UI feedback sounds in the background.
    Never plays loud, harsh, or piercing frequencies.
    """
    if not SOUND_ENABLED:
        return

    def _worker():
        if event == "radar":
            _play_sonar_ping()
        elif event == "step":
            _play_soft_click()
        elif event == "catch":
            if sys.platform == "win32":
                try:
                    import winsound
                    winsound.Beep(1046, 50)
                    winsound.Beep(1318, 70)
                except Exception:
                    pass
            else:
                _play_fallback_bell()
        elif event == "success":
            # On success, ensure music is playing or play a gentle two-tone chime
            if sys.platform == "win32":
                try:
                    import winsound
                    winsound.Beep(880, 70)
                    winsound.Beep(1174, 120)
                except Exception:
                    pass
            else:
                _play_fallback_bell()
        elif event == "error":
            if sys.platform == "win32":
                try:
                    import winsound
                    winsound.Beep(330, 100)
                    winsound.Beep(261, 140)
                except Exception:
                    pass
            else:
                _play_fallback_bell()

    threading.Thread(target=_worker, daemon=True).start()
