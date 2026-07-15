param(
    [string]$BaseUrl = "http://127.0.0.1:8100",
    [string]$ApiKey = "autorisk-dev-key"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$headers = @{ "X-API-Key" = $ApiKey }
$runId = Get-Date -Format "yyyyMMdd-HHmmss"

Write-Host "Checking AutoRisk at $BaseUrl ..." -ForegroundColor Cyan
$health = Invoke-RestMethod -Uri "$BaseUrl/health"
$health | Format-List status, service, workflow_mode, ai_provider, rules_config

$cases = @(
    @{
        Name = "GREEN"
        Indicators = @{
            leverage_ratio = 1.00
            single_stock_concentration = 0.05
            var_95_1d = 0.010
            liquidity_ratio = 0.30
        }
    },
    @{
        Name = "YELLOW"
        Indicators = @{
            leverage_ratio = 1.20
            single_stock_concentration = 0.09
            var_95_1d = 0.021
            liquidity_ratio = 0.14
        }
    },
    @{
        Name = "RED"
        Indicators = @{
            leverage_ratio = 1.35
            single_stock_concentration = 0.12
            var_95_1d = 0.030
            liquidity_ratio = 0.08
        }
    }
)

$reports = foreach ($case in $cases) {
    $body = @{
        request_id = "DEMO-$($case.Name)-$runId"
        trigger_source = "PRE_TRADE"
        fund_code = "DEMO001.HK"
        fund_name = "AutoRisk Demo Fund"
        indicators = $case.Indicators
        proposed_trade = @{
            symbol = "700.HK"
            side = "BUY"
            notional_hkd = 10000000
        }
        market_snapshot = @{
            snapshot_time = (Get-Date).ToUniversalTime().ToString("o")
        }
    } | ConvertTo-Json -Depth 8

    $report = Invoke-RestMethod `
        -Method Post `
        -Uri "$BaseUrl/api/v1/risk-evals/assess" `
        -Headers $headers `
        -ContentType "application/json; charset=utf-8" `
        -Body $body

    [pscustomobject]@{
        Case = $case.Name
        ReportId = $report.report_id
        Severity = $report.severity
        Status = $report.status
        Decision = $report.execution_decision
        FirstReviewer = $report.ai_reviews[0].reviewer_id
        FirstProvider = $report.ai_reviews[0].provider
        FirstResult = $report.ai_reviews[0].recommendation
        SecondReviewer = $report.ai_reviews[1].reviewer_id
        SecondProvider = $report.ai_reviews[1].provider
        SecondResult = $report.ai_reviews[1].recommendation
        FirstSigned = $null -ne $report.first_sign
        SecondSigned = $null -ne $report.second_sign
    }
}

Write-Host "`nAI review results" -ForegroundColor Cyan
$reports | Format-Table Case, Severity, Status, Decision, FirstResult, SecondResult, FirstSigned, SecondSigned -AutoSize

Write-Host "`nGenerated reports" -ForegroundColor Cyan
$reports | Format-Table Case, ReportId -AutoSize

Write-Host "`nReviewer details" -ForegroundColor Cyan
$reports | Format-Table Case, FirstReviewer, FirstProvider, SecondReviewer, SecondProvider -AutoSize

Write-Host "`nIntegrity checks" -ForegroundColor Cyan
$checks = foreach ($report in $reports) {
    $verification = Invoke-RestMethod `
        -Uri "$BaseUrl/api/v1/risk-evals/reports/$($report.ReportId)/verify" `
        -Headers $headers
    $artifactsValid = -not ($verification.artifacts | Where-Object { -not $_.valid })
    [pscustomobject]@{
        Case = $report.Case
        ContentHash = $verification.content_hash_valid
        FirstSignature = $verification.signatures.first_sign
        SecondSignature = $verification.signatures.second_sign
        Artifacts = $artifactsValid
        AuditChain = $verification.audit_chain.valid
    }
}
$checks | Format-Table -AutoSize

Write-Host "`nExpected decisions: GREEN=ALLOW, YELLOW=ALLOW_WITH_WARNING, RED=BLOCK" -ForegroundColor Green
