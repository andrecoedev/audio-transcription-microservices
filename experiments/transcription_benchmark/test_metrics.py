import unittest

from metrics import dispersion, quality


class MetricsTests(unittest.TestCase):
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
