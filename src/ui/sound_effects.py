"""
Sound Effects System for FaceGATE-Linux.

Provides soft, gentle, low-volume audio feedback for authentication events:
- Success: Soft warm acoustic chime (E4 -> G4 -> B4)
- Failure: Soft low muted thud
- Lock: Soft descending click

Features:
- Master volume control (default soft 15% volume)
- Smooth exponential decay envelopes to eliminate harshness
- Configurable via behavior.sound_effects and behavior.sound_volume

Usage:
    from ui.sound_effects import SoundManager
    SoundManager.play_success()
    SoundManager.play_failure()
    SoundManager.play_lock()
"""

import os
import wave
import math
import struct
import logging
from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QSoundEffect


_SOUND_CACHE = {}
_WAV_VERSION = "v2_soft"  # Cache breaker for smooth regenerated audio


def _generate_soft_wav(filename: str, notes: list, duration_sec: float = 0.22, max_amp: float = 0.08):
    """
    Synthesizes a soft, warm chime using exponential decay envelopes.
    `notes`: list of (freq_hz, start_t, end_t) tuples.
    """
    sample_rate = 44100
    n_samples = int(sample_rate * duration_sec)

    try:
        with wave.open(filename, 'w') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)

            samples = []
            for i in range(n_samples):
                t = i / sample_rate
                val = 0.0

                for freq, st, et in notes:
                    if st <= t <= et:
                        dt = t - st
                        note_len = et - st
                        # Soft attack (4ms) + gentle exponential decay
                        attack = min(1.0, dt / 0.004)
                        decay = math.exp(-6.0 * (dt / note_len))
                        env = attack * decay
                        # Add a tiny second harmonic for warmth
                        fundamental = math.sin(2 * math.pi * freq * dt)
                        harmonic = 0.2 * math.sin(4 * math.pi * freq * dt)
                        val += (fundamental + harmonic) * env

                sample_int = int(val * max_amp * 32767.0)
                sample_int = max(-32768, min(32767, sample_int))
                samples.append(struct.pack('<h', sample_int))

            wav_file.writeframes(b''.join(samples))
    except Exception as e:
        logging.error(f"Error generating soft WAV chime: {e}")


def _get_chime_url(chime_type: str) -> QUrl:
    """Returns QUrl for requested chime type, regenerating soft WAV if missing or old."""
    assets_dir = os.path.expanduser("~/.config/facegate/sounds")
    os.makedirs(assets_dir, exist_ok=True)
    wav_path = os.path.join(assets_dir, f"{chime_type}_{_WAV_VERSION}.wav")

    if not os.path.exists(wav_path):
        if chime_type == "success":
            # Soft warm E4 -> G4 -> B4 swell
            notes = [(329.63, 0.0, 0.12), (392.00, 0.06, 0.18), (493.88, 0.12, 0.22)]
            _generate_soft_wav(wav_path, notes, duration_sec=0.24, max_amp=0.07)
        elif chime_type == "failure":
            # Soft low muted thud: 110Hz -> 90Hz
            notes = [(110.0, 0.0, 0.12), (90.0, 0.08, 0.18)]
            _generate_soft_wav(wav_path, notes, duration_sec=0.20, max_amp=0.06)
        elif chime_type == "lock":
            # Soft descending click: 392Hz -> 329Hz
            notes = [(392.00, 0.0, 0.08), (329.63, 0.06, 0.14)]
            _generate_soft_wav(wav_path, notes, duration_sec=0.16, max_amp=0.06)

    return QUrl.fromLocalFile(wav_path)


class SoundManager:
    """
    Plays soft audio feedback chimes for authentication events.
    Checks config options `behavior.sound_effects` and `behavior.sound_volume`.
    """

    @staticmethod
    def _is_enabled() -> bool:
        try:
            from utils.config_loader import get_config
            return bool(get_config().get("behavior.sound_effects", True))
        except Exception:
            return True

    @staticmethod
    def _get_volume() -> float:
        try:
            from utils.config_loader import get_config
            vol = float(get_config().get("behavior.sound_volume", 0.15))
            return max(0.0, min(1.0, vol))
        except Exception:
            return 0.15

    @classmethod
    def _play_chime(cls, chime_type: str):
        if not cls._is_enabled():
            return

        vol = cls._get_volume()
        if vol <= 0.001:
            return

        try:
            url = _get_chime_url(chime_type)
            effect = QSoundEffect()
            effect.setSource(url)
            # Scale volume cleanly (0.15 default is soft & non-intrusive)
            effect.setVolume(vol)

            # Keep reference in process cache until playback completes
            _SOUND_CACHE[chime_type] = effect
            effect.play()
        except Exception as e:
            logging.debug(f"Sound effect playback skipped: {e}")

    @classmethod
    def play_success(cls):
        """Plays soft warm success chime."""
        cls._play_chime("success")

    @classmethod
    def play_failure(cls):
        """Plays soft muted failure thud."""
        cls._play_chime("failure")

    @classmethod
    def play_lock(cls):
        """Plays soft descending lock click."""
        cls._play_chime("lock")
