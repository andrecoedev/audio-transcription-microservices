"""Isolated, offline transcription benchmark; no imports from the application.

One invocation is a fresh model session: cold inference then resident warm
inference. Run at least three fresh sessions per configuration. 'Cold' does
not imply OS/disk caches were purged. All output is local-only by default.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import tempfile
import threading
import time
import urllib.request
import uuid
import wave

from metrics import cpp_transcript, quality, verify_cpp_device


class Sampler:
    """RSS process tree and sampled whole-GPU usage; not private VRAM."""

    def __init__(self, pid=None):
        import psutil
        self.process = psutil.Process(pid or os.getpid())
        self.stop = threading.Event()
        self.rows = []
        self.thread = threading.Thread(target=self.sample, daemon=True)

    def sample(self):
        import psutil
        processes = {}
        while not self.stop.is_set():
            rss = cpu = 0
            try:
                for proc in [self.process, *self.process.children(recursive=True)]:
                    if proc.pid not in processes:
                        processes[proc.pid] = proc
                        proc.cpu_percent()
                    rss += proc.memory_info().rss
                    cpu += processes[proc.pid].cpu_percent()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            gpu = vram = None
            try:
                flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
                completed = subprocess.run(
                    ["nvidia-smi", "--query-gpu=memory.used,utilization.gpu",
                     "--format=csv,noheader,nounits"], capture_output=True,
                    text=True, timeout=3, **flags)
                if completed.returncode == 0:
                    vram, gpu = map(float, completed.stdout.splitlines()[0].split(","))
            except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
                pass
            self.rows.append((rss / 2**20, cpu, vram, gpu))
            self.stop.wait(0.25)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(timeout=4)

    def result(self):
        def values(column):
            return [row[column] for row in self.rows if row[column] is not None]
        start = values(2)[0] if values(2) else None
        peak = max(values(2), default=None)
        return {
            "ram_peak_mib": max(values(0), default=None),
            "cpu_percent_mean": statistics.mean(values(1)) if values(1) else None,
            "gpu_total_vram_start_mib": start,
            "gpu_total_vram_peak_mib": peak,
            "gpu_total_vram_delta_mib": peak - start if peak is not None else None,
            "gpu_percent_mean": statistics.mean(values(3)) if values(3) else None,
            "resource_samples": len(self.rows),
            "vram_scope": "whole_gpu_not_private",
        }


def decode(audio, target):
    started = time.perf_counter()
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(audio),
                    "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
                    str(target)], capture_output=True, check=True, timeout=300)
    with wave.open(str(target)) as source:
        duration = source.getnframes() / source.getframerate()
    if duration <= 0:
        raise ValueError("Empty audio")
    return duration, time.perf_counter() - started


class Faster:
    def __init__(self, args):
        import ctranslate2
        from faster_whisper import WhisperModel
        if args.device == "cuda" and ctranslate2.get_cuda_device_count() == 0:
            raise RuntimeError("CUDA unavailable; refusing CPU fallback")
        self.model = WhisperModel(str(args.model_path), device=args.device,
                                 compute_type=args.compute_type,
                                 cpu_threads=args.threads, num_workers=1,
                                 local_files_only=True)
        if self.model.model.device != args.device:
            raise RuntimeError("Unexpected actual device")
        self.actual_device = self.model.model.device
        self.actual_compute = self.model.model.compute_type
        self.model_load_seconds = None
        self.args = args

    def infer(self, audio):
        segments, info = self.model.transcribe(
            str(audio), language=None, beam_size=5, best_of=5,
            vad_filter=False, condition_on_previous_text=True,
            temperature=0.0, word_timestamps=False)
        segments = list(segments)  # generator must be consumed inside timer
        return {"transcript": " ".join(item.text.strip() for item in segments),
                "language": info.language,
                "language_probability": info.language_probability,
                "segments": [{"start": s.start, "end": s.end, "text": s.text}
                             for s in segments]}

    def close(self):
        pass


class Cpp:
    def __init__(self, args, directory):
        import socket
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.url = f"http://127.0.0.1:{port}/inference"
        self.log_path = directory / "cpp-server.log"
        self.log = self.log_path.open("w", encoding="utf-8")
        command = [str(args.cpp_server), "-m", str(args.model_path), "--host",
                   "127.0.0.1", "--port", str(port), "-t", str(args.threads),
                   "-l", "auto", "-bs", "5", "-bo", "5"]
        if args.device == "cpu":
            command.append("--no-gpu")
        self.process = subprocess.Popen(command, stdout=self.log, stderr=self.log,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.sampler = Sampler(self.process.pid)
        self.sampler.__enter__()
        try:
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError("whisper.cpp server exited")
                try:
                    # Static UI may be absent in release binaries; TCP readiness
                    # avoids mistaking its HTTP 404 for model startup failure.
                    with socket.create_connection(("127.0.0.1", port), timeout=1):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise TimeoutError("whisper.cpp startup timeout")
            log = self.log_path.read_text(encoding="utf-8", errors="replace")
            # Require explicit allocation/backend evidence, not only a CUDA-built binary.
            self.actual_device = verify_cpp_device(log, args.device)
            ftype = re.search(r"ftype\s*=\s*(\d+)", log)
            if not ftype or ftype.group(1) != "1":
                raise RuntimeError("Expected verified GGML F16 weights")
            # Weight type is observable; kernel accumulation precision is mixed.
            self.actual_compute = "ggml-f16-weights-mixed-runtime"
            match = re.search(r"load time\s*=\s*([\d.]+) ms", log)
            self.model_load_seconds = float(match.group(1)) / 1000 if match else None
        except BaseException:
            self.close()
            (args.output / f"cpp-startup-{args.model}-{args.device}-{args.session}.log").write_text(
                self.log_path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
            raise

    def infer(self, audio):
        boundary = uuid.uuid4().hex
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"response_format\"\r\n\r\nverbose_json\r\n"
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"temperature\"\r\n\r\n0\r\n"
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"fixture.wav\"\r\n"
                "Content-Type: audio/wav\r\n\r\n").encode() + audio.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        request = urllib.request.Request(self.url, data=body,
                    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(request, timeout=1800) as response:
            result = json.load(response)
        return {"transcript": cpp_transcript(result),
                "language": result.get("language"),
                "segments": result.get("segments", [])}

    def close(self):
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=10)
        self.sampler.__exit__()
        self.log.close()


def run(args):
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="usagi-bench-") as temporary:
        directory = Path(temporary)
        audio = directory / "input.wav"
        duration, conversion = decode(args.audio, audio)
        reference = args.reference.read_text(encoding="utf-8") if args.reference else None
        base = {"schema_version": 1, "engine": args.engine, "model": args.model,
                "requested_device": args.device, "requested_compute": args.compute_type,
                "fixture_id": args.fixture_id, "session": args.session,
                "audio_sha256": hashlib.sha256(args.audio.read_bytes()).hexdigest(),
                "audio_seconds": duration, "conversion_seconds": conversion,
                "threads": args.threads, "beam_size": 5, "vad": False,
                "runtime": "windows_native" if os.name == "nt" else "linux_container",
                "cold_definition": "fresh_process_model_os_cache_uncontrolled",
                "model_load_scope": "engine_and_runtime_initialization_not_disk_only",
                "resource_scope": "cpp_server_process_tree" if args.engine == "whisper.cpp" else "python_process_tree",
                "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "psutil_version": importlib.metadata.version("psutil")}
        if args.engine == "faster-whisper":
            base["faster_whisper_version"] = importlib.metadata.version("faster-whisper")
            base["ctranslate2_version"] = importlib.metadata.version("ctranslate2")
        # Sample model allocation as well as inference.
        with Sampler() as sampler:
            started = time.perf_counter()
            backend = Faster(args) if args.engine == "faster-whisper" else Cpp(args, directory)
            load = time.perf_counter() - started
            base.update(actual_device=backend.actual_device,
                        actual_compute=backend.actual_compute,
                        model_load_seconds=backend.model_load_seconds or load,
                        startup_seconds=load)
            rows = []
            try:
                for repetition in range(args.warm_runs + 1):
                    started = time.perf_counter()
                    result = backend.infer(audio)
                    elapsed = time.perf_counter() - started
                    row = {**base, "phase": "cold" if repetition == 0 else "warm",
                           "repetition": repetition, "status": "completed",
                           "inference_seconds": elapsed,
                           "total_seconds": elapsed + conversion + (load if repetition == 0 else 0),
                           "rtf": elapsed / duration, "speed_x": duration / elapsed,
                           "language": result.get("language"),
                           "segment_count": len(result.get("segments", [])),
                           "wer": None, "cer": None}
                    if args.engine == "whisper.cpp":
                        row["text_reconstruction"] = "native_segments_concat_no_display_newlines"
                    if reference:
                        row.update(quality(reference, result["transcript"]))
                    # No private filename is stored. Transcript lives only in ignored output.
                    stem = f"{args.fixture_id}-{args.engine}-{args.model}-{args.device}-{args.session}-{repetition}"
                    (args.output / (stem + ".hypothesis.json")).write_text(
                        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                    rows.append(row)
            finally:
                backend.close()
                if args.engine == "whisper.cpp":
                    # Backend log used to prove device; remains ignored, not public.
                    (args.output / f"cpp-{args.model}-{args.device}-{args.session}.log").write_text(
                        backend.log_path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        resources = backend.sampler.result() if args.engine == "whisper.cpp" else sampler.result()
        for row in rows:
            row.update(resources)
        stem = f"{args.fixture_id}-{args.engine}-{args.model}-{args.device}-{args.session}"
        (args.output / (stem + ".metrics.json")).write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print(json.dumps({"fixture_id": args.fixture_id, "engine": args.engine,
                          "model": args.model, "device": args.device,
                          "session": args.session, "status": "completed",
                          "cold_seconds": rows[0]["inference_seconds"],
                          "warm_seconds": [r["inference_seconds"] for r in rows[1:]]}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--fixture-id", required=True)
    parser.add_argument("--engine", choices=["faster-whisper", "whisper.cpp"], required=True)
    parser.add_argument("--model", choices=["tiny", "base", "small", "medium", "large-v3"], required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--device", choices=["cpu", "cuda"], required=True)
    parser.add_argument("--compute-type", required=True)
    parser.add_argument("--cpp-server", type=Path)
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--session", type=int, required=True)
    parser.add_argument("--warm-runs", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9-]{1,64}", args.fixture_id):
        parser.error("Use an anonymous lowercase fixture ID, not a filename")
    if args.session < 1 or args.warm_runs < 1 or args.threads < 1:
        parser.error("session, warm-runs and threads must be positive")
    if args.engine == "whisper.cpp" and not args.cpp_server:
        parser.error("--cpp-server required")
    try:
        run(args)
    except Exception as error:
        # No raw provider/file error or transcript ever goes to console.
        failure = {"engine": args.engine, "model": args.model,
                   "requested_device": args.device, "fixture_id": args.fixture_id,
                   "session": args.session, "status": "failed", "error_type": type(error).__name__}
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / f"failure-{args.engine}-{args.model}-{args.device}-{args.session}.json").write_text(
            json.dumps(failure, indent=2), encoding="utf-8")
        print(json.dumps(failure))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
