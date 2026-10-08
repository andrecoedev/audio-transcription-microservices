param(
    [string]$WorkerImage = 'usagidev-worker:latest',
    [ValidateSet('faster-whisper','whisper.cpp')][string]$Engine = 'faster-whisper',
    [string[]]$Models = @('tiny','base','small','medium'),
    [string[]]$Devices = @('cpu','cuda'),
    [int]$Sessions = 3,
    [ValidatePattern('^[a-z0-9][a-z0-9-]{0,63}$')][string]$Fixture = 'fleurs-ptbr-quality-1m',
    [ValidatePattern('^[a-z0-9][a-z0-9-]{0,63}$')][string]$FixtureId = 'fleurs-quality',
    [switch]$Resume
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$artifact = Join-Path $repo '.local-artifacts\cpu-gpu-benchmark'
$python = "$artifact\venv\Scripts\python.exe"
$fixtureDir = "$repo\modules\backend\benchmarks\fixtures"
$server = Get-ChildItem "$artifact\bin\whisper" -Recurse -Filter 'whisper-server.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($Sessions -lt 3) { throw 'At least three fresh sessions are required' }
foreach ($model in $Models) {
    if ($model -notin @('tiny','base','small','medium','large-v3')) { throw 'Unsupported model' }
    foreach ($device in $Devices) {
        if ($device -notin @('cpu','cuda')) { throw 'Unsupported device' }
        foreach ($session in 1..$Sessions) {
            $metrics = "$artifact\results\$FixtureId-$Engine-$model-$device-$session.metrics.json"
            if (Test-Path -LiteralPath $metrics) {
                if (-not $Resume) { throw 'Evidence already exists. Use a new cohort/directory or explicitly -Resume after verifying the same artifacts/configuration.' }
                Write-Output "Explicitly resumed: $FixtureId/$Engine/$model/$device/$session"; continue
            }
            if ($Engine -eq 'faster-whisper') {
                $compute = if ($device -eq 'cpu') { 'int8' } else { 'float16' }
                # Mount only this experiment, media and models, never the repository/.env.
                docker run --rm --network none --gpus all --entrypoint python --mount "type=bind,source=$PSScriptRoot,target=/benchmark,readonly" --mount "type=bind,source=$fixtureDir,target=/fixtures,readonly" --mount "type=bind,source=$artifact\models,target=/models,readonly" --mount "type=bind,source=$artifact\results,target=/results" $WorkerImage /benchmark/run.py --audio "/fixtures/$Fixture.wav" --reference "/fixtures/$Fixture.reference.txt" --fixture-id $FixtureId --engine $Engine --model $model --model-path "/models/faster-$model" --device $device --compute-type $compute --session $session --output /results
            } else {
                if (-not $server) { throw 'whisper-server.exe missing' }
                & $python "$PSScriptRoot\run.py" --audio "$fixtureDir\$Fixture.wav" --reference "$fixtureDir\$Fixture.reference.txt" --fixture-id $FixtureId --engine $Engine --model $model --model-path "$artifact\models\ggml-$model.bin" --device $device --compute-type ggml-f16 --cpp-server $server.FullName --session $session --output "$artifact\results"
            }
            if ($LASTEXITCODE -ne 0) { Write-Warning "Failed: $FixtureId/$Engine/$model/$device/$session; see ignored local failure evidence" }
        }
    }
}
