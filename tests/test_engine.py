"""Hardware-independent smoke tests for VoiceForge's DSP engine."""
import unittest

import numpy as np

from main import EFFECTS, Engine


class EngineSmokeTests(unittest.TestCase):
    def test_every_effect_returns_finite_clipped_audio(self):
        rng = np.random.default_rng(2026)
        source = (rng.standard_normal(2048) * 0.2).astype(np.float32)

        for effect in EFFECTS:
            with self.subTest(effect=effect):
                engine = Engine()
                engine.effect = effect
                result = engine.process(source.copy())
                self.assertEqual(result.dtype, np.float32)
                self.assertEqual(result.shape, source.shape)
                self.assertTrue(np.isfinite(result).all())
                self.assertLessEqual(float(np.max(np.abs(result))), 0.980001)

    def test_empty_audio_is_safe(self):
        engine = Engine()
        result = engine.process(np.zeros(0, dtype=np.float32))
        self.assertEqual(result.size, 0)

    def test_noise_gate_reduces_quiet_input(self):
        engine = Engine()
        engine.denoise = True
        source = np.full(512, 0.005, dtype=np.float32)
        result = engine.process(source)
        self.assertLess(float(np.max(np.abs(result))), float(np.max(np.abs(source))))


if __name__ == "__main__":
    unittest.main()
