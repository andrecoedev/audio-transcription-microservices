$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$fixtureRoot = Join-Path $PSScriptRoot 'fixtures/p3b1'
New-Item -ItemType Directory -Force $fixtureRoot | Out-Null
$fixtures = Get-Content (Join-Path $PSScriptRoot 'p3b1_fixtures.json') -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($entry in $fixtures.PSObject.Properties) {
    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
    try {
        $synth.SetOutputToWaveFile((Join-Path $fixtureRoot ($entry.Name + '.wav')))
        $index = 0
        foreach ($turn in $entry.Value.turns) {
            $voice = if ($index % 2 -eq 0) { 'Microsoft Zira Desktop' } else { 'Microsoft Maria Desktop' }
            $synth.SelectVoice($voice)
            $synth.Rate = -1
            $synth.Speak($turn)
            $index++
        }
    } finally { $synth.Dispose() }
    Write-Output ('synthetic_fixture_created=' + $entry.Name)
}
