param([ValidateSet('protect','unprotect')][string]$Operation)
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Security
$credentialInput = [Console]::In.ReadToEnd()
if ($Operation -eq 'protect') {
    $credentialBytes = [System.Text.Encoding]::UTF8.GetBytes($credentialInput)
    $protectedBytes = [System.Security.Cryptography.ProtectedData]::Protect($credentialBytes, $null, [System.Security.Cryptography.DataProtectionScope]::CurrentUser)
    [Console]::Out.Write([Convert]::ToBase64String($protectedBytes))
} else {
    $credentialBytes = [Convert]::FromBase64String($credentialInput.Trim())
    $protectedBytes = [System.Security.Cryptography.ProtectedData]::Unprotect($credentialBytes, $null, [System.Security.Cryptography.DataProtectionScope]::CurrentUser)
    [Console]::Out.Write([System.Text.Encoding]::UTF8.GetString($protectedBytes))
}
