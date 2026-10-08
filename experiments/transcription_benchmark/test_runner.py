from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from run import Faster


class RunnerTests(unittest.TestCase):
    def test_missing_cuda_never_constructs_cpu_fallback(self):
        constructor = Mock()
        with patch.dict(sys.modules, {
            "ctranslate2": SimpleNamespace(get_cuda_device_count=lambda: 0),
            "faster_whisper": SimpleNamespace(WhisperModel=constructor),
        }):
            with self.assertRaisesRegex(RuntimeError, "refusing CPU fallback"):
                Faster(SimpleNamespace(device="cuda"))
        constructor.assert_not_called()

    def test_actual_device_mismatch_fails_measurement(self):
        args = SimpleNamespace(device="cpu", compute_type="int8", threads=6, model_path=Path("synthetic"))
        constructor = Mock(return_value=SimpleNamespace(model=SimpleNamespace(device="cuda")))
        with patch.dict(sys.modules, {
            "ctranslate2": SimpleNamespace(get_cuda_device_count=lambda: 1),
            "faster_whisper": SimpleNamespace(WhisperModel=constructor),
        }):
            with self.assertRaisesRegex(RuntimeError, "Unexpected actual device"):
                Faster(args)

    def test_lazy_inference_is_consumed_before_return(self):
        observed = []
        def segments():
            observed.append("inference")
            yield SimpleNamespace(start=0, end=1, text=" fala")
        backend = Faster.__new__(Faster)
        backend.model = SimpleNamespace(transcribe=lambda *args, **kwargs: (
            segments(), SimpleNamespace(language="pt", language_probability=1)))
        result = backend.infer(Path("synthetic.wav"))
        self.assertEqual(observed, ["inference"])
        self.assertEqual(result["transcript"], "fala")


if __name__ == "__main__":
    unittest.main()
