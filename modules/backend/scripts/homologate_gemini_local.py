"""Explicit synthetic-only real-provider drill. No credentials or bodies in logs."""
import json
import argparse
import os
import time
from pathlib import Path

import requests
from redis import Redis
from rq.job import Job


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixtures', nargs='+', choices=['A', 'B', 'C'], default=['A', 'B', 'C'])
    args = parser.parse_args()
    output = Path('/tmp/p3b1-results')
    output.mkdir(exist_ok=True)
    session = requests.Session()
    base = 'http://api:2020'

    def call(method, path, **kwargs):
        response = session.request(method, base + path, timeout=30, **kwargs)
        if not response.ok:
            raise RuntimeError(f'HTTP {response.status_code}')
        return response.json()

    token = call('POST', '/auth/login', json={'username': 'admin', 'password': os.environ['USAGI_SMOKE_PASSWORD']})['access_token']
    session.headers['Authorization'] = 'Bearer ' + token
    connection = Redis.from_url(os.environ['REDIS_URL'])

    def wait(path, field, limit=600):
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            state = call('GET', path)
            value = field(state)
            if value == 'completed':
                return state
            if value == 'failed':
                raise RuntimeError('Job failed')
            time.sleep(2)
        raise TimeoutError('Polling deadline')

    def remove_ephemeral(generation_id):
        deadline = time.monotonic() + 30
        job = Job.fetch(f'meeting_intelligence_{generation_id}', connection=connection)
        while time.monotonic() < deadline:
            if job.get_status(refresh=True) == 'finished':
                job.delete()
                return
            time.sleep(0.5)
        raise TimeoutError('RQ completion deadline')

    for fixture in args.fixtures:
        mid = None
        report = {'fixture': fixture, 'attempted_real_calls': 0, 'retries': 0}
        try:
            audio = Path(f'/tmp/p3b1-audio/{fixture}.wav')
            with audio.open('rb') as stream:
                job = call('POST', '/transcriptions/jobs', files={'file': (audio.name, stream, 'audio/wav')},
                           data={'transcription_model': 'whisper', 'use_diarization': 'true'})
            mid = job['transcription_id']
            report['meeting_id'] = mid
            print(f'fixture={fixture} transcription_started=true', flush=True)
            wait(f'/transcriptions/jobs/{mid}/status', lambda state: state['job_status'])
            transcript = call('GET', f'/transcriptions/{mid}')
            report['segments'] = transcript['segments']
            report['duration_seconds'] = transcript['duration_seconds']
            report['transcript_characters'] = sum(len(segment['text']) for segment in transcript['segments'])
            report['meeting'] = call('GET', f'/meetings/{mid}')
            prefix = f'/meetings/{mid}/intelligence'
            assert call('GET', prefix + '/status')['configured']
            started = time.monotonic()
            generation = call('POST', prefix)
            report['attempted_real_calls'] += 1
            assert call('POST', prefix)['id'] == generation['id']
            wait(prefix + '/status', lambda state: state['generation']['status'])
            result = call('GET', prefix + '/result')
            report['polling_latency_seconds'] = time.monotonic() - started
            remove_ephemeral(generation['id'])
            assert call('GET', prefix + '/result') == result
            report['result'] = result
            report['survived_rq_deletion'] = True
            if fixture == 'B':
                started = time.monotonic()
                newer = call('POST', prefix + '/regenerate')
                report['attempted_real_calls'] += 1
                assert newer['revision'] == result['revision'] + 1
                assert call('POST', prefix + '/regenerate')['id'] == newer['id']
                assert call('GET', prefix + '/result')['revision'] == result['revision']
                active = call('GET', prefix + '/status')
                assert sum(row['status'] in ['pending', 'processing'] for row in active['revisions']) == 1
                wait(prefix + '/status', lambda state: state['generation']['status'])
                report['regenerated'] = call('GET', prefix + '/result')
                report['regeneration_polling_latency_seconds'] = time.monotonic() - started
                assert call('GET', prefix + f'/result?revision={result["revision"]}') == result
                remove_ephemeral(newer['id'])
                assert call('GET', prefix + '/result') == report['regenerated']
            report['execution_status'] = 'completed'
            print(f'fixture={fixture} completed=true calls={report["attempted_real_calls"]}', flush=True)
        except Exception as exc:
            report['execution_status'] = 'failed'
            report['error_type'] = type(exc).__name__
            print(f'fixture={fixture} failed_type={type(exc).__name__}', flush=True)
            raise
        finally:
            (output / f'{fixture}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            if mid is not None:
                deleted = session.delete(base + f'/transcriptions/{mid}', timeout=30)
                print(f'fixture={fixture} cleanup_http={deleted.status_code}', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'homologation_stopped={type(exc).__name__}', flush=True)
        raise SystemExit(1) from None
