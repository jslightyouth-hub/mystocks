$ErrorActionPreference = "Stop"

$root = "E:\stock1"
$backendDir = Join-Path $root "fastapi1"
$frontendDir = Join-Path $root "react1\vite-project"
$pythonExe = Join-Path $backendDir ".venv\Scripts\python.exe"
$backendLog = Join-Path $backendDir "uvicorn.out.log"
$backendErr = Join-Path $backendDir "uvicorn.err.log"
$frontendLog = Join-Path $frontendDir "vite.out.log"
$frontendErr = Join-Path $frontendDir "vite.err.log"
$url = "http://127.0.0.1:5173/000001.SZ"

function Test-PortListening {
    param([int]$Port)

    $line = netstat -ano -p tcp | Select-String "127.0.0.1:$Port\s" | Select-Object -First 1
    return $null -ne $line
}

function Start-Backend {
    if (Test-PortListening -Port 8000) {
        Write-Host "Backend is already running on http://127.0.0.1:8000"
        return
    }

    if (-not (Test-Path -LiteralPath $pythonExe)) {
        throw "Python venv not found: $pythonExe"
    }

    Start-Process -FilePath $pythonExe `
        -ArgumentList @("-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000") `
        -WorkingDirectory $backendDir `
        -RedirectStandardOutput $backendLog `
        -RedirectStandardError $backendErr `
        -WindowStyle Hidden

    Write-Host "Started backend on http://127.0.0.1:8000"
}

function Start-Frontend {
    if (Test-PortListening -Port 5173) {
        Write-Host "Frontend is already running on http://127.0.0.1:5173"
        return
    }

    $npm = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
    if ($null -eq $npm) {
        throw "npm.cmd was not found in PATH"
    }

    Start-Process -FilePath $npm.Source `
        -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", "5173") `
        -WorkingDirectory $frontendDir `
        -RedirectStandardOutput $frontendLog `
        -RedirectStandardError $frontendErr `
        -WindowStyle Hidden

    Write-Host "Started frontend on http://127.0.0.1:5173"
}

Start-Backend
Start-Sleep -Seconds 2
Start-Frontend
Start-Sleep -Seconds 3

Start-Process $url
Write-Host "Opened $url"
