$env:APP_ENV = "development"
Write-Host "=========================================" -ForegroundColor Green
Write-Host " Starting SONIC-REDA Backend (Port 12000)" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green

while ($true) {
    .\sonic-core\.venv\Scripts\python.exe -m uvicorn sonic.api.main:app --port 12000
    Write-Host "[SONIC] Server stopped. Restarting in 2s... (Ctrl+C to quit)" -ForegroundColor Yellow
    Start-Sleep -Seconds 2
}
