"""Offline metrics. Never treats a model hypothesis as a reference."""

import re
import statistics
import unicodedata


def normalize(text):
    text = unicodedata.normalize("NFC", text).lower()
    return " ".join(re.findall(r"[^\W_]+(?:-[^\W_]+)*", text))


def distance(left, right):
    previous = list(range(len(right) + 1))
    for item in left:
        current = [previous[0] + 1]
        for index, other in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[index] + 1,
                               previous[index - 1] + (item != other)))
        previous = current
    return previous[-1]


def quality(reference, hypothesis):
    ref, hyp = normalize(reference), normalize(hypothesis)
    words, chars = ref.split(), list(ref.replace(" ", ""))
    if not words or not chars:
        raise ValueError("A nonempty human reference is required")
    return {
        "wer": distance(words, hyp.split()) / len(words),
        "cer": distance(chars, list(hyp.replace(" ", ""))) / len(chars),
        "reference_words": len(words),
        # Punctuation/case differences are deliberately not hidden by WER/CER.
        "literal_match": reference.strip() == hypothesis.strip(),
    }


def dispersion(values):
    if not values:
        raise ValueError("No successful measurements")
    median = statistics.median(values)
    return {"median": median, "min": min(values), "max": max(values),
            "mad": statistics.median(abs(value - median) for value in values),
            "n": len(values)}
