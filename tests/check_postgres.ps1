# Check if PostgreSQL service is running
$service = Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue
if ($service) {
    Write-Host "PostgreSQL service is installed and running"
    Write-Host "Service name: $($service.Name)"
    Write-Host "Status: $($service.Status)"
} else {
    Write-Host "PostgreSQL service is not installed"
}

# Check if psql is in PATH
$psqlPath = "C:\Program Files\PostgreSQL\17\bin\psql.exe"
if (Test-Path $psqlPath) {
    Write-Host "PostgreSQL client (psql) is installed at: $psqlPath"
    & $psqlPath --version
} else {
    Write-Host "PostgreSQL client (psql) is not found"
}

# Try to connect to PostgreSQL
try {
    $env:PGPASSWORD = "1979007"
    & $psqlPath -h localhost -U postgres -c "\conninfo" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Successfully connected to PostgreSQL"
    } else {
        Write-Host "Failed to connect to PostgreSQL"
    }
} catch {
    Write-Host "Error connecting to PostgreSQL: $_"
} 