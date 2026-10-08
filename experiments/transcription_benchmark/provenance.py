"""Hash public model artifacts, including Linux HF-cache symlinks, without ML."""

import argparse
import hashlib
import json
from pathlib import Path
import re


def artifact(file):
    digest = hashlib.sha256()
    with file.open("rb") as stream:
        for chunk in iter(lambda: stream.read(2**20), b""):
            digest.update(chunk)
    return {"artifact": file.name, "bytes": file.stat().st_size, "sha256": digest.hexdigest()}


def revision(file):
    if not file.is_file():
        return None
    value = file.read_text(encoding="utf-8").splitlines()[0]
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("Expected a public Hugging Face commit revision")
    return value


def collect(models):
    faster = []
    for directory in sorted(models.glob("faster-*")):
        files = [file for file in sorted(directory.iterdir()) if file.is_file() and
                 re.fullmatch(r"model.bin|config.json|tokenizer.json|vocabulary\..*|preprocessor_config.json", file.name)]
        faster.append({"model": directory.name,
                       "source": "https://huggingface.co/Systran/faster-whisper-" + directory.name[7:],
                       "revision": revision(directory / ".cache/huggingface/download/model.bin.metadata"),
                       "artifacts": [artifact(file) for file in files]})
    pyannote = []
    for directory in sorted((models / "pyannote").glob("models--pyannote--*")):
        commit = revision(directory / "refs/main")
        if commit is None:
            raise ValueError("Missing cached Pyannote revision")
        files = [file for file in sorted((directory / "snapshots" / commit).iterdir())
                 if file.name in {"config.json", "config.yaml", "pytorch_model.bin"}]
        pyannote.append({"model": directory.name.replace("models--pyannote--", "pyannote/"),
                         "revision": commit, "artifacts": [artifact(file) for file in files]})
    return {"schema_version": 1, "faster_models": faster,
            "ggml_models": [{"model": file.stem, "source": "https://huggingface.co/ggerganov/whisper.cpp",
                             "download_ref": "main", **artifact(file)}
                            for file in sorted(models.glob("ggml-*.bin"))],
            "pyannote_models": pyannote}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(collect(args.models), indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "public_artifacts_hashed"}))


if __name__ == "__main__":
    main()
