"""Offline metrics. Never treats a model hypothesis as a reference."""

import re
import statistics
import unicodedata


def verify_cpp_device(log, requested):
    cuda = bool(re.search(r"using CUDA\d+ backend|CUDA\d+\s+(?:compute|total|model)\s+(?:size|buffer)", log, re.I))
    if requested == "cuda" and not cuda:
        raise RuntimeError("No CUDA allocation evidence; refusing GPU label")
    if requested == "cpu" and cuda:
        raise RuntimeError("Unexpected CUDA offload during CPU benchmark")
    return requested


def cpp_transcript(result):
    """Server verbose JSON inserts display newlines, sometimes inside words.

    Native segment text preserves token whitespace. Concatenate it verbatim;
    inserting our own spaces/newlines would change words and bias WER.
    """
    segments = result.get("segments")
    if segments:
        return "".join(segment["text"] for segment in segments)
    return result.get("text", result.get("transcript", ""))


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
