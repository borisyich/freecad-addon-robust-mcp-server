$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $rng.GetBytes($bytes)
}
finally {
    $rng.Dispose()
}

$token = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
$env:FREECAD_ACCESS_TOKEN = $token
[Environment]::SetEnvironmentVariable('FREECAD_ACCESS_TOKEN', $token, 'User')

Write-Host 'FREECAD_ACCESS_TOKEN was generated and saved for the current Windows user.'
Write-Host 'Copy it now to the SaaS agent secret storage:'
Write-Host $token
