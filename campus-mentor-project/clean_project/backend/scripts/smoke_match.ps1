# Usage:
#   cd campus-mentor-project/backend
#   .\scripts\smoke_match.ps1
# Server must already be running on http://127.0.0.1:8000

$ErrorActionPreference = "Stop"
$base = "http://127.0.0.1:8000"

Write-Host "GET $base/health"
Invoke-RestMethod "$base/health" | ConvertTo-Json -Compress

$bodyPath = Join-Path $PSScriptRoot "..\examples\match.request.json"
$body = Get-Content -Raw -Encoding UTF8 $bodyPath
Write-Host "POST $base/api/match"
Invoke-RestMethod -Method Post -Uri "$base/api/match" -ContentType "application/json; charset=utf-8" -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) | ConvertTo-Json -Depth 6
