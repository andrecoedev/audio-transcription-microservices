param(
    [string]$WorkerImage = 'usagidev-worker:latest',
    [string[]]$Models = @('tiny', 'base', 'small', 'medium'),
    [string]$Release = 'b5454'
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$artifact = Join-Path $repo '.local-artifacts\cpu-gpu-benchmark'
New-Item -ItemType Directory -Force -Path "$artifact\bin", "$artifact\models", "$artifact\results" | Out-Null
foreach ($model in $Models) {
    if ($model -notin @('tiny','base','small','medium','large-v3')) { throw 'Unsupported model' }
}
python -m venv "$artifact\venv"
& "$artifact\venv\Scripts\python.exe" -m pip install psutil==7.2.2
if ($LASTEXITCODE -ne 0) { throw 'Cannot install benchmark sampler' }
$releaseInfo = Invoke-RestMethod "https://api.github.com/repos/ggml-org/whisper.cpp/releases/tags/$Release"
$asset = $releaseInfo.assets | Where-Object name -eq 'whisper-bin-win-cuda-12.4.0-x64.zip'
if (-not $asset) { throw 'CUDA x64 release artifact unavailable' }
$zip = "$artifact\bin\whisper.zip"
if (-not (Test-Path "$artifact\bin\whisper")) {
    curl.exe --fail --location --retry 2 --output $zip $asset.browser_download_url
    if ($LASTEXITCODE -ne 0) { throw 'Binary download failed' }
    Expand-Archive -LiteralPath $zip -DestinationPath "$artifact\bin\whisper"
}
foreach ($model in $Models) {
    $destination = "$artifact\models\ggml-$model.bin"
    if (-not (Test-Path -LiteralPath $destination)) {
        curl.exe --fail --location --retry 2 --output $destination "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-$model.bin"
        if ($LASTEXITCODE -ne 0) { throw 'Model download failed; remove incomplete artifact before retry' }
    }
}
# No application .env/credentials. Only public model downloads use network.
$modelList = ($Models | ForEach-Object { "'$_'" }) -join ','
$downloadCode = "from huggingface_hub import snapshot_download; [snapshot_download('Systran/faster-whisper-'+m,local_dir='/models/faster-'+m,allow_patterns=['model.bin','config.json','tokenizer.json','vocabulary.*','preprocessor_config.json']) for m in [$modelList]]"
docker run --rm --entrypoint python --mount "type=bind,source=$artifact\models,target=/models" $WorkerImage -c $downloadCode
if ($LASTEXITCODE -ne 0) { throw 'Faster-Whisper model download failed' }
# Preserve immutable evidence of downloaded model/build identities, never credentials.
Get-ChildItem "$artifact\models" -Recurse -File | Where-Object { $_.Name -eq 'model.bin' -or $_.Name -like 'ggml-*.bin' } |
    Get-FileHash -Algorithm SHA256 | Select-Object Hash,@{N='Artifact';E={Split-Path $_.Path -Leaf}} |
    ConvertTo-Json | Set-Content "$artifact\results\model-hashes.local.json" -Encoding UTF8
