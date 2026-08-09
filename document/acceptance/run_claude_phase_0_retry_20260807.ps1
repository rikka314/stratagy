Set-Location -LiteralPath 'D:\Learn\20_Projects\2026_SPRING\AIE1902\课堂内容\stratagy'

$phasePrompt = Get-Content -LiteralPath 'document\acceptance\claude_phase_0_prompt_20260807.md' -Raw -Encoding UTF8
$phaseLog = 'document\acceptance\claude_phase_0_retry_20260807.log'

"=== Phase 0 retry started $(Get-Date -Format o) ===" | Tee-Object -FilePath $phaseLog -Encoding utf8
& claude -p --dangerously-skip-permissions --permission-mode bypassPermissions --effort max --output-format stream-json --include-partial-messages $phasePrompt *>&1 |
    Tee-Object -FilePath $phaseLog -Append -Encoding utf8
$phaseExitCode = $LASTEXITCODE
"=== Phase 0 retry finished $(Get-Date -Format o); exit=$phaseExitCode ===" |
    Tee-Object -FilePath $phaseLog -Append -Encoding utf8
