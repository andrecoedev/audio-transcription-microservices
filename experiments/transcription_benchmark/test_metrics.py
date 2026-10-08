import unittest

from metrics import cpp_transcript, dispersion, quality


class MetricsTests(unittest.TestCase):
    def test_cpp_display_wrapping_is_not_a_word_error(self):
        raw = {"text": "fal\nantes", "segments": [{"text": "fal"}, {"text": "antes"}]}
        self.assertEqual(cpp_transcript(raw), "falantes")
        self.assertEqual(quality("falantes", cpp_transcript(raw))["wer"], 0)

    def test_cpp_native_whitespace_is_preserved(self):
        self.assertEqual(cpp_transcript({"segments": [{"text": "Olá"}, {"text": " mundo."}]}), "Olá mundo.")

    def test_human_reference_normalization(self):
        result = quality("A reunião, começou!", "a reunião começou")
        self.assertEqual(result["wer"], 0)
        self.assertEqual(result["cer"], 0)
        self.assertFalse(result["literal_match"])

    def test_insertions_can_exceed_one(self):
        self.assertEqual(quality("sim", "não nunca talvez")["wer"], 3)

    def test_missing_reference_is_not_zero_error(self):
        with self.assertRaises(ValueError):
            quality("", "texto")

    def test_dispersion(self):
        self.assertEqual(dispersion([1, 2, 9]),
                         {"median": 2, "min": 1, "max": 9, "mad": 1, "n": 3})


if __name__ == "__main__":
    unittest.main()
