param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$NotebookLmArgs
)

function Normalize-PathValue {
  param(
    [string]$Value
  )

  if ([string]::IsNullOrWhiteSpace($Value)) {
    $trimmed = ""
  } else {
    $trimmed = $Value.Trim()
  }
  if (-not $trimmed) {
    return ""
  }

  $normalized = $trimmed.Trim("'`"")
  return $normalized
}

$pythonCommand = if ($env:NOTEBOOKLM_PYTHON_COMMAND) { $env:NOTEBOOKLM_PYTHON_COMMAND } elseif ($env:PYTHON) { $env:PYTHON } else { "python" }

$resolvedCertPath = Normalize-PathValue $env:SSL_CERT_FILE
if (-not $resolvedCertPath -or -not (Test-Path -LiteralPath $resolvedCertPath)) {
  try {
    $certPath = & $pythonCommand -c "import certifi; print(certifi.where())"
    if ($LASTEXITCODE -eq 0 -and $certPath) {
      $resolvedCertPath = Normalize-PathValue $certPath
    }
  } catch {
    # Leave SSL_CERT_FILE unset if certifi lookup fails.
  }
}

if ($resolvedCertPath -and (Test-Path -LiteralPath $resolvedCertPath)) {
  $env:SSL_CERT_FILE = $resolvedCertPath
  $env:REQUESTS_CA_BUNDLE = $resolvedCertPath
  $env:CURL_CA_BUNDLE = $resolvedCertPath
}

$env:PYTHONHTTPSVERIFY = "1"
$env:RAGENIUS_NOTEBOOKLM_COMPAT_SCRIPT = Join-Path $PSScriptRoot "notebooklm_compat.py"

$pythonBootstrap = @"
import os
import runpy
import sys

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

compat_script = os.environ['RAGENIUS_NOTEBOOKLM_COMPAT_SCRIPT']
sys.argv = [compat_script, *sys.argv[1:]]
runpy.run_path(compat_script, run_name='__main__')
"@

& $pythonCommand -c $pythonBootstrap @NotebookLmArgs
exit $LASTEXITCODE
