param(
    [ValidateSet('Disable', 'Restore')][string]$Mode = 'Disable',
    [string]$GameRoot = $PSScriptRoot
)
$ErrorActionPreference = 'Stop'

function Get-AudioHash([string]$Path) {
    $audioStream = [System.IO.File]::OpenRead($Path)
    $audioHasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        return [System.BitConverter]::ToString($audioHasher.ComputeHash($audioStream)).Replace('-', '')
    } finally {
        $audioHasher.Dispose()
        $audioStream.Dispose()
    }
}

try {
    $audioRoot = (Resolve-Path -LiteralPath $GameRoot).Path
    $audioClient = Join-Path $audioRoot 'Client'
    if (-not (Test-Path -LiteralPath (Join-Path $audioClient 'PsoBB.exe') -PathType Leaf)) {
        throw 'Place this tool in the game root folder, beside the launcher and Client folder.'
    }
    if (Get-Process -Name 'PsoBB' -ErrorAction SilentlyContinue) {
        throw 'Please exit the game normally before changing its audio DLL.'
    }
    $audioActive = Join-Path $audioClient 'dsound.dll'
    $audioDisabledDir = Join-Path $audioClient 'audio-compat/disabled'
    $audioDisabled = Join-Path $audioDisabledDir 'dsound.dll'
    $audioExpectedHash = 'C304C7C822E885D35D016EF2667ED98BD3C3F688D16C35CE5E412D61749542CF'
    if ($Mode -eq 'Disable') {
        $audioFrom = $audioActive
        $audioTo = $audioDisabled
    } else {
        $audioFrom = $audioDisabled
        $audioTo = $audioActive
    }
    if (-not (Test-Path -LiteralPath $audioFrom -PathType Leaf)) {
        if ($Mode -eq 'Disable' -and -not (Test-Path -LiteralPath $audioActive)) {
            Write-Output 'Already using the Windows DirectSound path. No files changed.'
            exit 0
        }
        throw 'The audio DLL to restore was not found. No files changed.'
    }
    if (Test-Path -LiteralPath $audioTo) {
        throw 'Destination already exists. Refusing to overwrite either DLL.'
    }
    $audioHash = Get-AudioHash $audioFrom
    if ($audioHash -ne $audioExpectedHash) {
        throw 'This is not the bundled v3 DSOAL DLL. Refusing to change an unknown audio component.'
    }
    if ($Mode -eq 'Disable' -and -not (Test-Path -LiteralPath $audioDisabledDir)) {
        New-Item -ItemType Directory -Path $audioDisabledDir | Out-Null
    }
    Move-Item -LiteralPath $audioFrom -Destination $audioTo
    if ((Get-AudioHash $audioTo) -ne $audioHash) {
        throw 'Post-move hash check failed.'
    }
    Write-Output ('Audio compatibility layer: ' + $Mode + ' completed. DLL preserved and verified.')
    Write-Output 'No game executable, save, display setting or Windows system file was changed.'
    exit 0
} catch {
    Write-Error -ErrorAction Continue $_
    exit 1
}
