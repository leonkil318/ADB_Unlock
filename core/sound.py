"""
Geely ADB Unlock Master - Retro Audio Engine
Plays native audio effects and background chiptune track (core/zelda.mp3)
across Windows, macOS, and Linux with Zero External Dependencies (no pip packages needed).
- Windows: Native WinMM MCI subsystem (winmm.dll) with persistent worker thread
- macOS: Native afplay (/usr/bin/afplay)
- Linux: Native audio tools (mpg123, mpv, ffplay, cvlc, play)
Volume is balanced and comfortable (50%).
Progress sounds are soft, warm, low-frequency clicks (440Hz / 12ms) - never piercing or shrill.
"""

import sys
import os
import time
import shutil
import threading
import subprocess

SOUND_ENABLED = True
_lock = threading.Lock()
_bgm_stop_event = threading.Event()
_bgm_thread = None
_bgm_process = None


def _get_short_path(path):
    """Converts a Windows path to an 8.3 short path for 100% reliable MCI command parsing."""
    if sys.platform == "win32":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(512)
            ctypes.windll.kernel32.GetShortPathNameW(path, buf, 512)
            if buf.value:
                return buf.value
        except Exception:
            pass
    return path


def _get_mp3_path():
    """Locates the bundled or local zelda.mp3 audio file across all packaging and dev environments."""
    candidates = []
    
    # PyInstaller temporary extraction folder
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        candidates.append(os.path.join(sys._MEIPASS, 'zelda.mp3'))
        candidates.append(os.path.join(sys._MEIPASS, 'core', 'zelda.mp3'))
    
    # Directory next to executable
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidates.append(os.path.join(exe_dir, 'zelda.mp3'))
        candidates.append(os.path.join(exe_dir, 'core', 'zelda.mp3'))
    
    # Python script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(script_dir, 'zelda.mp3'))
    candidates.append(os.path.join(script_dir, 'core', 'zelda.mp3'))
    candidates.append(os.path.join(os.path.dirname(script_dir), 'core', 'zelda.mp3'))

    for p in candidates:
        if os.path.exists(p):
            return os.path.abspath(p)
    return None


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


def play_bgm(loop=True, volume=500):
    """
    Plays the Zelda background soundtrack in a persistent daemon thread
    across Windows, macOS, and Linux without external libraries.
    """
    global _bgm_thread, _bgm_stop_event
    if not SOUND_ENABLED or is_bgm_playing():
        return

    mp3_path = _get_mp3_path()
    if not mp3_path or not os.path.exists(mp3_path):
        return

    _bgm_stop_event.clear()

    def _worker():
        global _bgm_process
        if sys.platform == "win32":
            try:
                import ctypes
                mci = ctypes.windll.winmm.mciSendStringW
                short_p = _get_short_path(mp3_path)
                mci('close geely_bgm', None, 0, None)
                ret = mci(f'open "{short_p}" type mpegvideo alias geely_bgm', None, 0, None)
                if ret == 0:
                    mci(f'setaudio geely_bgm volume to {volume}', None, 0, None)
                    cmd = 'play geely_bgm repeat' if loop else 'play geely_bgm'
                    mci(cmd, None, 0, None)

                    # CRITICAL: Keep this thread alive so Windows MCI maintains the playback session!
                    while not _bgm_stop_event.is_set():
                        time.sleep(0.2)

                    mci('stop geely_bgm', None, 0, None)
                    mci('close geely_bgm', None, 0, None)
            except Exception:
                pass
        elif sys.platform == "darwin":
            try:
                vol_float = max(0.05, min(1.0, volume / 1000.0))
                cmd = ["afplay", "-v", str(vol_float), mp3_path]
                _bgm_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                while not _bgm_stop_event.is_set() and _bgm_process.poll() is None:
                    time.sleep(0.2)
                if _bgm_process and _bgm_process.poll() is None:
                    _bgm_process.terminate()
            except Exception:
                pass
        else:
            # Linux native audio player tools
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
                        while not _bgm_stop_event.is_set() and _bgm_process.poll() is None:
                            time.sleep(0.2)
                        if _bgm_process and _bgm_process.poll() is None:
                            _bgm_process.terminate()
                        break
                    except Exception:
                        pass

    _bgm_thread = threading.Thread(target=_worker, daemon=True)
    _bgm_thread.start()


def stop_bgm():
    """Immediately stops background audio on any OS."""
    global _bgm_stop_event, _bgm_process
    _bgm_stop_event.set()

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
            _bgm_process.wait(timeout=0.3)
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
    """Subtle, warm, non-ear-piercing micro-click for UI steps (520Hz, 12ms)."""
    if sys.platform == "win32":
        try:
            import winsound
            winsound.Beep(520, 12)
        except Exception:
            pass


def _play_progress_pulse():
    """Comfortable, warm, low-frequency pulse for spinner (440Hz musical A4, only 12ms)."""
    if sys.platform == "win32":
        try:
            import winsound
            winsound.Beep(440, 12)
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
    Uses warm, low frequencies (440-520Hz) - never piercing or shrill.
    """
    if not SOUND_ENABLED:
        return

    def _worker():
        if event == "radar":
            _play_progress_pulse()
        elif event == "step":
            _play_soft_click()
        elif event == "catch":
            if sys.platform == "win32":
                try:
                    import winsound
                    winsound.Beep(523, 40)
                    winsound.Beep(659, 60)
                except Exception:
                    pass
            else:
                _play_fallback_bell()
        elif event == "success":
            if sys.platform == "win32":
                try:
                    import winsound
                    winsound.Beep(523, 50)
                    winsound.Beep(659, 50)
                    winsound.Beep(784, 80)
                except Exception:
                    pass
            else:
                _play_fallback_bell()
        elif event == "error":
            if sys.platform == "win32":
                try:
                    import winsound
                    winsound.Beep(261, 80)
                    winsound.Beep(220, 120)
                except Exception:
                    pass
            else:
                _play_fallback_bell()

    threading.Thread(target=_worker, daemon=True).start()
