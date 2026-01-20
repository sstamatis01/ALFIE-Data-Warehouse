# PowerShell script to resolve merge conflicts by keeping HEAD version
# Removes everything from ======= to >>>>>>> markers

$files = Get-ChildItem -Recurse -Filter *.py | Where-Object {
    $content = Get-Content $_.FullName -Raw -ErrorAction SilentlyContinue
    $content -match '======='
}

$resolved = 0

foreach ($file in $files) {
    $content = Get-Content $file.FullName -Raw
    $original = $content
    
    # Remove <<<<<<< HEAD lines
    $content = $content -replace '<<<<<<< HEAD\s*\r?\n', ''
    
    # Remove everything from ======= to >>>>>>>
    $content = $content -replace '=======.*?>>>>>>> [^\r\n]+\r?\n', '' -replace '=======.*?>>>>>>> [^\r\n]+', ''
    
    # Also handle cases where ======= and >>>>>>> are on separate lines
    $lines = $content -split '\r?\n'
    $newLines = @()
    $skip = $false
    
    foreach ($line in $lines) {
        if ($line.Trim() -eq '=======') {
            $skip = $true
            continue
        }
        if ($line.Trim() -match '^>>>>>>>') {
            $skip = $false
            continue
        }
        if (-not $skip) {
            $newLines += $line
        }
    }
    
    $content = $newLines -join "`n"
    
    if ($content -ne $original) {
        Set-Content -Path $file.FullName -Value $content -NoNewline
        Write-Host "Resolved: $($file.FullName)"
        $resolved++
    }
}

Write-Host "`nTotal files resolved: $resolved"
