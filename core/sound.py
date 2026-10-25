"""
Geely ADB Unlock Master - Retro Audio Engine
Plays background chiptune track (core/zelda.mp3)
across Windows, macOS, and Linux with Zero External Dependencies.
- Windows: Native Windows .NET WPF Media Engine (System.Windows.Media.MediaPlayer)
  via silent background worker - eliminates all MCI bugs and speaker scratching.
- macOS: Native afplay (/usr/bin/afplay)
- Linux: Native audio tools (mpg123, mpv, ffplay, cvlc, play)
Completely removes low-level hardware piezo beeps (no speaker pops or scratches).
"""

import sys
import os
import time
import shutil
import threading
import subprocess

SOUND_ENABLED = True
_lock = threading.Lock()
_bgm_process = None


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
    global _bgm_process
    return _bgm_process is not None and _bgm_process.poll() is None


def set_sound_enabled(enabled):
    global SOUND_ENABLED
    with _lock:
        SOUND_ENABLED = bool(enabled)
    if not SOUND_ENABLED:
        stop_bgm()


def play_bgm(loop=True, volume=0.55):
    """
    Plays the Zelda background soundtrack in a hidden background process
    across Windows, macOS, and Linux without third-party pip libraries.
    """
    global _bgm_process
    if not SOUND_ENABLED or is_bgm_playing():
        return

    mp3_path = _get_mp3_path()
    if not mp3_path or not os.path.exists(mp3_path):
        return

    stop_bgm()

    def _worker():
        global _bgm_process
        if sys.platform == "win32":
            try:
                escaped_path = mp3_path.replace("'", "''")
                vol_str = str(volume)
                loop_logic = """
$player.Play()
Register-ObjectEvent -InputObject $player -EventName MediaEnded -Action {
    $player.Position = [System.TimeSpan]::Zero
    $player.Play()
} | Out-Null
""" if loop else "$player.Play()"

                ps_command = f"""
$ErrorActionPreference = 'SilentlyContinue'
Add-Type -AssemblyName presentationCore
$player = New-Object System.Windows.Media.MediaPlayer
$player.Open([System.Uri]::new('{escaped_path}'))
$player.Volume = {vol_str}
{loop_logic}
while ($true) {{
    Start-Sleep -Milliseconds 500
}}
"""
                creationflags = 0x08000000  # CREATE_NO_WINDOW
                _bgm_process = subprocess.Popen(
                    ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps_command],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags
                )
            except Exception:
                pass
        elif sys.platform == "darwin":
            try:
                cmd = ["afplay", "-v", str(volume), mp3_path]
                _bgm_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
        else:
            for player in ["mpg123", "mpv", "ffplay", "cvlc", "play"]:
                if shutil.which(player):
                    try:
                        if player == "mpg123":
                            cmd = ["mpg123", "-q", mp3_path]
                        elif player == "mpv":
                            cmd = ["mpv", "--no-video", f"--volume={int(volume * 100)}", mp3_path]
                        elif player == "ffplay":
                            cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", mp3_path]
                        elif player == "cvlc":
                            cmd = ["cvlc", "--play-and-exit", mp3_path]
                        else:
                            cmd = ["play", "-q", mp3_path]
                        _bgm_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        break
                    except Exception:
                        pass

    threading.Thread(target=_worker, daemon=True).start()


def stop_bgm():
    """Immediately stops background audio on any OS."""
    global _bgm_process
    if _bgm_process is not None:
        try:
            _bgm_process.terminate()
            _bgm_process.wait(timeout=0.4)
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
        play_bgm(loop=True)
    else:
        stop_bgm()
    return state


def play_sound(event):
    """
    Audio event router. Hardware beeping is disabled to prevent
    speaker pops, clicks, or scratch sounds on sound cards.
    """
    pass
