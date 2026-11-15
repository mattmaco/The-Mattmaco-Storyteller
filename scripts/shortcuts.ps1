# Creates (or with -Remove, deletes) the Storyteller shortcuts on the desktop and in the Start menu.
# The shortcut runs run.bat in a minimised window; closing that window stops Storyteller.
param([switch]$Remove)
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$places = @(
    [Environment]::GetFolderPath('Desktop'),   # follows OneDrive desktop redirection
    [Environment]::GetFolderPath('Programs')   # Start menu
)

foreach ($dir in $places) {
    $lnk = Join-Path $dir 'Storyteller.lnk'
    if ($Remove) {
        if (Test-Path $lnk) { Remove-Item $lnk -Force }
        continue
    }
    $shell = New-Object -ComObject WScript.Shell
    $s = $shell.CreateShortcut($lnk)
    $s.TargetPath = Join-Path $env:SystemRoot 'System32\cmd.exe'
    $s.Arguments = '/c "' + (Join-Path $root 'run.bat') + '"'
    $s.WorkingDirectory = $root
    $s.IconLocation = (Join-Path $root 'storyteller\web\icon.ico') + ',0'
    $s.Description = 'Read study PDFs aloud with highlighting'
    $s.WindowStyle = 7  # minimised
    $s.Save()
}
