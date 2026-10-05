param(
    [Parameter(Mandatory=$true)][string]$PythonExecutable,
    [Parameter(Mandatory=$true)][string]$StateRoot,
    [Parameter(Mandatory=$true)][string]$SessionId,
    [Parameter(Mandatory=$true)][string]$JobId,
    [Parameter(Mandatory=$true)][string]$WorkingDirectory
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'docker_preflight.ps1')
try {
    # MCP hosts can put descendants in a kill-on-close Job Object. A local CIM
    # launch is outside that host's job and still runs as the calling user.
    $workerArguments = @($PythonExecutable, '-m', 'installer.setup_worker',
        '--state-root', $StateRoot, '--session-id', $SessionId, '--job-id', $JobId)
    $commandLine = ConvertTo-WindowsNativeArgumentString -ArgumentList $workerArguments
    $result = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
        CommandLine = $commandLine
        CurrentDirectory = $WorkingDirectory
    }
    if ($result.ReturnValue -ne 0) { throw 'Could not create the independent Setup worker.' }
    @{ pid = [int]$result.ProcessId } | ConvertTo-Json -Compress
} catch {
    [Console]::Error.WriteLine('Could not create the independent Setup worker. Check local Windows Management Instrumentation and retry Setup.')
    exit 1
}
