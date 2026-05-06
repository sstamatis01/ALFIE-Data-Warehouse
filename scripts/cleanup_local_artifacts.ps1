param(
  [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

function Remove-IfExists {
  param(
    [Parameter(Mandatory=$true)][string]$Path,
    [switch]$Recurse
  )
  if (Test-Path -LiteralPath $Path) {
    if ($WhatIf) {
      Write-Host "[WhatIf] Would remove: $Path"
      return
    }
    if ($Recurse) {
      Remove-Item -LiteralPath $Path -Recurse -Force
    } else {
      Remove-Item -LiteralPath $Path -Force
    }
    Write-Host "Removed: $Path"
  }
}

Write-Host "Cleaning local artifacts (safe, targeted)..."
Write-Host "Tip: run with -WhatIf first to preview."

# Folders
Remove-IfExists -Path "Garbage_Dataset_Classification_subset" -Recurse
Remove-IfExists -Path "v2" -Recurse
Remove-IfExists -Path "model" -Recurse
Remove-IfExists -Path "autogluon_models" -Recurse
Remove-IfExists -Path "concept_drift_upload_debug" -Recurse
Remove-IfExists -Path "__pycache__" -Recurse

# Files
Remove-IfExists -Path "model.zip"
Remove-IfExists -Path "model.pkl"
Remove-IfExists -Path "compact_report.html"
Remove-IfExists -Path "drift_log.csv"
Remove-IfExists -Path "metrics_summary.csv"
Remove-IfExists -Path "train.csv"

# Globs (synthetic/exports)
Get-ChildItem -File -ErrorAction SilentlyContinue -Filter "compliance_alerts_synthetic_*.csv" | ForEach-Object {
  Remove-IfExists -Path $_.FullName
}
Get-ChildItem -File -ErrorAction SilentlyContinue -Filter "tabular_data*.csv" | ForEach-Object {
  Remove-IfExists -Path $_.FullName
}

Write-Host "Done."

