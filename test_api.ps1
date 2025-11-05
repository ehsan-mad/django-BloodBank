# Test API endpoints
$baseUrl = "https://django-bloodbank-qmsn.onrender.com/api/v1"

Write-Host "Testing Login..." -ForegroundColor Green
$loginBody = @{
    username = "admin1"
    password = "12345"
} | ConvertTo-Json

try {
    $loginResponse = Invoke-RestMethod -Uri "$baseUrl/auth/login/" -Method Post -Body $loginBody -ContentType 'application/json'
    $token = $loginResponse.access
    Write-Host "Login successful! Token received." -ForegroundColor Green
} catch {
    Write-Host "Login failed: $_" -ForegroundColor Red
    exit
}

Write-Host "`nTesting Dashboard Metrics..." -ForegroundColor Green
try {
    $metricsResponse = Invoke-RestMethod -Uri "$baseUrl/analytics/dashboard/metrics/" -Method Get -Headers @{
        "Authorization" = "Bearer $token"
    }
    Write-Host "Dashboard Metrics Response:" -ForegroundColor Yellow
    $metricsResponse | ConvertTo-Json
} catch {
    Write-Host "Metrics request failed: $_" -ForegroundColor Red
}

Write-Host "`nTesting Blood Type Distribution..." -ForegroundColor Green
try {
    $chartResponse = Invoke-RestMethod -Uri "$baseUrl/analytics/charts/data/?type=blood_type_distribution" -Method Get -Headers @{
        "Authorization" = "Bearer $token"
    }
    Write-Host "Chart Response:" -ForegroundColor Yellow
    $chartResponse | ConvertTo-Json
} catch {
    Write-Host "Chart request failed: $_" -ForegroundColor Red
}

Write-Host "`nTesting Donation Trend..." -ForegroundColor Green
try {
    $trendResponse = Invoke-RestMethod -Uri "$baseUrl/analytics/charts/data/?type=donation_trend&start_date=2025-01-01&end_date=2025-10-31" -Method Get -Headers @{
        "Authorization" = "Bearer $token"
    }
    Write-Host "Trend Response:" -ForegroundColor Yellow
    $trendResponse | ConvertTo-Json
} catch {
    Write-Host "Trend request failed: $_" -ForegroundColor Red
}

Write-Host "`nTesting Report Generation..." -ForegroundColor Green
$reportBody = @{
    report_type = "donation_summary"
    start_date = "2025-01-01"
    end_date = "2025-10-31"
    format = "json"
    group_by = "week"
} | ConvertTo-Json

try {
    $reportResponse = Invoke-RestMethod -Uri "$baseUrl/analytics/reports/generate/" -Method Post -Body $reportBody -ContentType 'application/json' -Headers @{
        "Authorization" = "Bearer $token"
    }
    Write-Host "Report Response:" -ForegroundColor Yellow
    $reportResponse | ConvertTo-Json
} catch {
    Write-Host "Report generation failed: $_" -ForegroundColor Red
}