import numpy as np
import librosa
from pathlib import Path


def find_peak_timestamp(video_path: Path, hop_seconds: float = 0.1) -> float:
    y, sr = librosa.load(str(video_path), mono=True)
    duration = librosa.get_duration(y=y, sr=sr)
    hop_length = int(sr * hop_seconds)
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    # Smooth over 1s to remove micro-spikes (door slams, menu clicks)
    smoothed = np.convolve(rms, np.ones(10) / 10, mode="same")
    # Find center of the 3-second window with highest cumulative energy
    # Catches sustained action (gunfight, clutch) not single loud frames
    window_frames = int(3.0 / hop_seconds)
    window_energy = np.convolve(smoothed, np.ones(window_frames), mode="same")
    peak_frame = int(np.argmax(window_energy))
    peak_time = peak_frame * hop_seconds

    # Clamp: need 4s lead-in before peak, at least 5s of tail
    lead = min(4.0, duration * 0.2)
    peak_time = max(lead, min(peak_time, max(lead, duration - 5.0)))
    return float(peak_time)
