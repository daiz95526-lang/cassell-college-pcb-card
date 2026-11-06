$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$archive = Join-Path $repoRoot "eda/project/EasyEDA_Editable_Source.zip"
Expand-Archive -LiteralPath $archive -DestinationPath $repoRoot -Force
Write-Output "EasyEDA Pro source restored under eda/project and eda/."
