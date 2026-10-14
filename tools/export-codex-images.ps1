param(
    [string]$SessionsDirectory = (Join-Path $env:USERPROFILE '.codex\sessions'),
    [string]$OutputDirectory = (Join-Path (Get-Location) 'output\generated-images'),
    [switch]$LatestSessionOnly
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $SessionsDirectory)) {
    throw "Codex sessions directory not found: $SessionsDirectory"
}

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

$sessionFiles = Get-ChildItem -LiteralPath $SessionsDirectory -Recurse -File -Filter '*.jsonl' |
    Sort-Object LastWriteTime -Descending

if ($LatestSessionOnly) {
    $sessionFiles = $sessionFiles | Select-Object -First 1
}

$exported = [System.Collections.Generic.List[object]]::new()

foreach ($sessionFile in $sessionFiles) {
    $stream = [System.IO.FileStream]::new(
        $sessionFile.FullName,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::ReadWrite
    )
    $reader = [System.IO.StreamReader]::new($stream)

    try {
        while (-not $reader.EndOfStream) {
            $line = $reader.ReadLine()

            try {
                $entry = $line | ConvertFrom-Json
            }
            catch {
                continue
            }

            $payload = $entry.payload
            if ($payload.type -ne 'image_generation_call' -or
                $payload.status -ne 'completed' -or
                [string]::IsNullOrWhiteSpace([string]$payload.result)) {
                continue
            }

            try {
                $bytes = [Convert]::FromBase64String([string]$payload.result)
            }
            catch {
                Write-Warning "Skipping invalid Base64 image in $($sessionFile.Name), ordinal $($entry.ordinal)."
                continue
            }

            $extension = '.bin'
            if ($bytes.Length -ge 8 -and
                $bytes[0] -eq 0x89 -and $bytes[1] -eq 0x50 -and
                $bytes[2] -eq 0x4E -and $bytes[3] -eq 0x47) {
                $extension = '.png'
            }
            elseif ($bytes.Length -ge 3 -and
                $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xD8 -and $bytes[2] -eq 0xFF) {
                $extension = '.jpg'
            }
            elseif ($bytes.Length -ge 12 -and
                [Text.Encoding]::ASCII.GetString($bytes, 0, 4) -eq 'RIFF' -and
                [Text.Encoding]::ASCII.GetString($bytes, 8, 4) -eq 'WEBP') {
                $extension = '.webp'
            }

            $timestamp = ([datetime]$entry.timestamp).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
            $imageId = if ($payload.id) { [string]$payload.id } else { "ordinal-$($entry.ordinal)" }
            $safeId = $imageId -replace '[^A-Za-z0-9._-]', '_'
            $outputPath = Join-Path $OutputDirectory "$timestamp-$safeId$extension"

            if (-not (Test-Path -LiteralPath $outputPath)) {
                [System.IO.File]::WriteAllBytes($outputPath, $bytes)
            }

            $metadataPath = [System.IO.Path]::ChangeExtension($outputPath, '.json')
            if (-not (Test-Path -LiteralPath $metadataPath)) {
                [ordered]@{
                    id = $payload.id
                    timestamp = $entry.timestamp
                    prompt = $payload.revised_prompt
                    source_session = $sessionFile.FullName
                    source_ordinal = $entry.ordinal
                    image_path = $outputPath
                } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $metadataPath -Encoding utf8
            }

            $exported.Add([pscustomobject]@{
                Path = $outputPath
                Bytes = $bytes.Length
                Prompt = $payload.revised_prompt
            })
        }
    }
    finally {
        $reader.Dispose()
        $stream.Dispose()
    }
}

$uniqueExported = $exported | Sort-Object Path -Unique
$uniqueExported | Format-Table Path, Bytes, Prompt -AutoSize

Write-Host "Exported $($uniqueExported.Count) image(s) to $OutputDirectory"
