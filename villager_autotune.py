"""Sample-based Villager voice overlay for VoiceForge.

This layers the user's live, processed microphone signal with the 17-ish
Minecraft Villager voice clips placed in the VoiceForge sounds folder.
It is a sample overlay, not neural speech conversion: words remain from the
microphone while Villager grunts are mixed in time with detected speech.
"""
from pathlib import Path
import threading

import numpy as np
import miniaudio


class VillagerOverlay:
    def __init__(self, sounds_dir):
        self.sounds_dir = Path(sounds_dir)
        self.samples = []
        self.cursor = 0
        self.active = np.zeros(0, dtype=np.float32)
        self.offset = 0
        self.cooldown = 0
        self.last_files = ()
        self.lock = threading.Lock()

    def load_samples(self, sample_rate):
        # Match only the Villager clips, not unrelated soundboard files.
        extensions = {".wav", ".ogg", ".mp3"}
        files = tuple(sorted(
            (p for p in self.sounds_dir.iterdir()
             if p.is_file() and p.suffix.lower() in extensions
             and "villager" in p.stem.casefold()),
            key=lambda p: p.name.casefold(),
        ))
        signature = tuple((p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in files)
        if signature == self.last_files:
            return
        loaded = []
        for path in files:
            try:
                decoded = miniaudio.decode_file(
                    str(path),
                    output_format=miniaudio.SampleFormat.FLOAT32,
                    nchannels=1,
                    sample_rate=int(sample_rate),
                )
                data = np.frombuffer(decoded.samples, dtype=np.float32).copy()
                if data.size:
                    peak = float(np.max(np.abs(data)))
                    if peak > 1e-6:
                        data = (data / max(peak, 1.0)).astype(np.float32)
                        loaded.append(data)
            except Exception as exc:
                # Some Minecraft assets have misleading extensions. Skip a
                # file that the decoder cannot read without breaking the mic.
                print(f"Villager sample skipped ({path.name}): {exc}")
        with self.lock:
            self.samples = loaded
            self.last_files = signature
            self.cursor = 0
            self.active = np.zeros(0, dtype=np.float32)
            self.offset = 0
            self.cooldown = 0

    def mix(self, mic, sample_rate, voice_reference=None):
        if not self.samples or not len(mic):
            return mic
        # Measure raw input activity, not the filtered output, so clips are
        # triggered by the user's speech rather than by their own tails.
        reference = voice_reference if voice_reference is not None else mic
        level = float(np.sqrt(np.mean(np.square(reference, dtype=np.float64)) + 1e-12))
        voiced = level > 0.012
        result = mic.copy()
        n = len(result)
        i = 0
        while i < n:
            if self.offset >= len(self.active):
                self.active = np.zeros(0, dtype=np.float32)
                self.offset = 0
                if not voiced or self.cooldown > 0:
                    take = min(n - i, max(1, self.cooldown))
                    self.cooldown = max(0, self.cooldown - take)
                    i += take
                    continue
                self.active = self.samples[self.cursor % len(self.samples)]
                self.cursor += 1
                self.offset = 0
                # A tiny gap stops long continuous speech from turning into
                # an unbroken loop of grunts; another clip can start shortly.
                self.cooldown = int(sample_rate * 0.08)
            take = min(n - i, len(self.active) - self.offset)
            if take <= 0:
                break
            clip = self.active[self.offset:self.offset + take]
            # Speech-locked gain: clear when speaking, quickly fade in silence.
            gain = min(0.34, 0.10 + level * 1.25) if voiced else 0.0
            result[i:i + take] += clip * gain
            i += take
            self.offset += take
        return np.clip(result, -0.98, 0.98).astype(np.float32)


def install_villager_autotune(engine_class, sounds_dir):
    """Wrap the DSP engine without changing its other voice effects."""
    original_init = engine_class.__init__
    original_start = engine_class.start
    original_process = engine_class.process

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.villager_overlay = VillagerOverlay(sounds_dir)

    def start(self, inp, out):
        result = original_start(self, inp, out)
        self.villager_overlay.load_samples(self.input_rate)
        return result

    def process(self, samples):
        raw_voice = samples.copy()
        effect = self.effect
        result = original_process(self, samples)
        if effect == "Villager":
            # Reload if the user has added/replaced Villager clips while the
            # app is open; the directory scan is cheap and decoding only occurs
            # when the file list changes.
            self.villager_overlay.load_samples(self.input_rate)
            result = self.villager_overlay.mix(result, self.input_rate, raw_voice)
        return result

    engine_class.__init__ = init
    engine_class.start = start
    engine_class.process = process
