param(
    [string]$EnginePath = ''
)
$ErrorActionPreference = 'Stop'
if (-not $EnginePath) {
    $runtimeFolder = if ($PSVersionTable.PSEdition -eq 'Core') { 'netcore' } else { 'netfx' }
    $EnginePath = Join-Path $env:APPDATA "pyRevit-Master\bin\$runtimeFolder\engines\IPY2712PR"
}
foreach ($assemblyName in @('pyRevitLabs.Microsoft.Scripting.dll', 'pyRevitLabs.Microsoft.Dynamic.dll', 'pyRevitLabs.IronPython.dll', 'pyRevitLabs.IronPython.Modules.dll')) {
    [Reflection.Assembly]::LoadFrom((Join-Path $EnginePath $assemblyName)) | Out-Null
}
$layoutEngine = [IronPython.Hosting.Python]::CreateEngine()
$layoutScope = $layoutEngine.CreateScope()
$layoutScope.SetVariable('workspace', (Split-Path -Parent $PSScriptRoot))
$layoutEngine.ExecuteFile((Join-Path $PSScriptRoot 'probe_ui_layout.py'), $layoutScope) | Out-Null
