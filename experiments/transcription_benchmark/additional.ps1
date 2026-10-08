param([string]$WorkerImage = 'usagidev-worker:latest')
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$artifact = Join-Path $repo '.local-artifacts\cpu-gpu-benchmark'
# Run only after the primary matrix completes. Never run inference matrices in parallel.
& "$PSScriptRoot\matrix.ps1" -WorkerImage $WorkerImage -Engine faster-whisper -Models @('small') -Devices @('cpu','cuda') -Fixture 'fleurs-ptbr-representative-6m' -FixtureId 'fleurs-six-minute'
& "$PSScriptRoot\matrix.ps1" -WorkerImage $WorkerImage -Engine faster-whisper -Models @('medium') -Devices @('cuda') -Fixture 'fleurs-ptbr-representative-6m' -FixtureId 'fleurs-six-minute'
if (Test-Path "$artifact\models\faster-large-v3\model.bin") {
    & "$PSScriptRoot\matrix.ps1" -WorkerImage $WorkerImage -Engine faster-whisper -Models @('large-v3') -Devices @('cuda')
}
& "$PSScriptRoot\matrix.ps1" -WorkerImage $WorkerImage -Engine whisper.cpp -Models @('small','medium') -Devices @('cuda') -Fixture 'fleurs-ptbr-representative-6m' -FixtureId 'fleurs-six-minute'
& "$PSScriptRoot\matrix.ps1" -WorkerImage $WorkerImage -Engine faster-whisper -Models @('small') -Devices @('cpu','cuda') -Fixture 'fleurs-ptbr-two-speaker-1m' -FixtureId 'fleurs-two-speaker'
if (Test-Path "$artifact\local-video-001.wav") {
    foreach ($session in 1..3) {
            docker run --rm --network none --gpus all --entrypoint python --mount "type=bind,source=$PSScriptRoot,target=/benchmark,readonly" --mount "type=bind,source=$artifact\local-video-001.wav,target=/input/audio.wav,readonly" --mount "type=bind,source=$artifact\models\faster-small,target=/models/faster-small,readonly" --mount "type=bind,source=$artifact\results,target=/results" $WorkerImage /benchmark/run.py --audio /input/audio.wav --fixture-id local-video-001 --engine faster-whisper --model small --model-path /models/faster-small --device cuda --compute-type float16 --session $session --output /results
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Private local benchmark failed; no private source published' }
    }
}
# Only authorized, complete cache; inference containers never receive token/.env.
foreach ($fixture in @('ami-clean-2spk','ami-four-speakers')) {
    foreach ($device in @('cpu','cuda')) {
        foreach ($session in 1..3) {
            docker run --rm --network none --gpus all --entrypoint python --mount "type=bind,source=$PSScriptRoot,target=/benchmark,readonly" --mount "type=bind,source=$repo\modules\backend\benchmarks\fixtures\p1c-ami,target=/fixtures,readonly" --mount "type=bind,source=$artifact\models\pyannote,target=/models/pyannote,readonly" --mount "type=bind,source=$artifact\results,target=/results" $WorkerImage /benchmark/diarization.py --audio "/fixtures/$fixture.wav" --reference-rttm "/fixtures/$fixture.reference.rttm" --fixture-id $fixture --device $device --session $session --output /results
            if ($LASTEXITCODE -ne 0) { Write-Warning "Diarization failed: $fixture/$device/$session" }
        }
    }
}
