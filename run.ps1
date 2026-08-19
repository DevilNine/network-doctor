<#
.SYNOPSIS
    Launcher universal do Network Doctor para Windows (PowerShell).

.DESCRIPTION
    Executa o diagnostico de rede Network Doctor diretamente pelo PowerShell,
    seja localmente ou remotamente via:
    irm https://raw.githubusercontent.com/DevilNine/network-doctor/main/run.ps1 | iex

.EXAMPLE
    irm https://raw.githubusercontent.com/DevilNine/network-doctor/main/run.ps1 | iex
    .\run.ps1 -rapido
    .\run.ps1 -contratada 300 -salvar
#>

function Invoke-NetworkDoctorLauncher {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Argumentos
    )

    $ErrorActionPreference = 'Stop'
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8

    $RepoZipUrl = 'https://github.com/DevilNine/network-doctor/archive/refs/heads/main.zip'
    $TempBase   = Join-Path $env:TEMP 'network-doctor'
    $AppDir     = Join-Path $TempBase 'app'
    $PythonDir  = Join-Path $TempBase 'python'

    function Test-PythonCandidate {
        param([string]$CandidatePath)
        if ([string]::IsNullOrWhiteSpace($CandidatePath)) { return $false }
        if (-not (Test-Path -LiteralPath $CandidatePath)) { return $false }

        # Rejeita stubs de 0 bytes do WindowsApps (Microsoft Store redirect)
        if ($CandidatePath -like '*\Microsoft\WindowsApps\*') {
            try {
                $item = Get-Item -LiteralPath $CandidatePath -ErrorAction Stop
                if ($item.Length -eq 0) {
                    return $false
                }
            } catch {
                return $false
            }
        }

        try {
            $pInfo = New-Object System.Diagnostics.ProcessStartInfo
            $pInfo.FileName = $CandidatePath
            $pInfo.Arguments = '-c "import sys; sys.exit(0 if sys.version_info[0] >= 3 else 1)"'
            $pInfo.UseShellExecute = $false
            $pInfo.CreateNoWindow = $true
            $pInfo.RedirectStandardOutput = $true
            $pInfo.RedirectStandardError = $true

            $proc = [System.Diagnostics.Process]::Start($pInfo)
            $proc.WaitForExit(3000)
            if ($proc.HasExited -and $proc.ExitCode -eq 0) {
                return $true
            } else {
                if (-not $proc.HasExited) { $proc.Kill() }
                return $false
            }
        } catch {
            return $false
        }
    }

    function Find-PythonExecutable {
        # 1. Tenta python isolado no TEMP se ja existir
        $localPy = Join-Path $PythonDir 'python.exe'
        if (Test-PythonCandidate $localPy) { return $localPy }

        # 2. Tenta py launcher oficial
        $pyLaunchers = Get-Command 'py.exe' -All -ErrorAction SilentlyContinue
        foreach ($cmd in $pyLaunchers) {
            if (Test-PythonCandidate $cmd.Source) { return $cmd.Source }
        }

        # 3. Tenta python.exe no PATH (filtrando stubs do WindowsApps)
        $pyCmds = Get-Command 'python.exe' -All -ErrorAction SilentlyContinue
        foreach ($cmd in $pyCmds) {
            if (Test-PythonCandidate $cmd.Source) { return $cmd.Source }
        }

        # 4. Tenta python3.exe no PATH
        $py3Cmds = Get-Command 'python3.exe' -All -ErrorAction SilentlyContinue
        foreach ($cmd in $py3Cmds) {
            if (Test-PythonCandidate $cmd.Source) { return $cmd.Source }
        }

        # 5. Tenta caminhos padrao de instalacao no Windows
        $commonPaths = @(
            "$env:LocalAppData\Programs\Python\Python3*\python.exe",
            "$env:ProgramFiles\Python3*\python.exe",
            "$env:ProgramFiles(x86)\Python3*\python.exe",
            "C:\Python3*\python.exe"
        )
        foreach ($pattern in $commonPaths) {
            $found = Get-Item -Path $pattern -ErrorAction SilentlyContinue
            foreach ($f in $found) {
                if (Test-PythonCandidate $f.FullName) { return $f.FullName }
            }
        }

        return $null
    }

    function Install-PortablePython {
        Write-Host "  [*] Python nao encontrado no sistema. Baixando ambiente portatil..." -ForegroundColor Yellow
        if (-not (Test-Path $PythonDir)) {
            New-Item -ItemType Directory -Path $PythonDir -Force | Out-Null
        }

        $is64 = [Environment]::Is64BitOperatingSystem
        $arch = if ($is64) { 'amd64' } else { 'win32' }
        $zipFile = Join-Path $TempBase "python-embed-$arch.zip"
        $pyUrl = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-$arch.zip"

        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13
            Invoke-WebRequest -Uri $pyUrl -OutFile $zipFile -UseBasicParsing
            Expand-Archive -Path $zipFile -DestinationPath $PythonDir -Force
            Remove-Item $zipFile -Force -ErrorAction SilentlyContinue

            # Habilita suporte a site-packages/import no embeddable
            $pthFile = Get-ChildItem -Path $PythonDir -Filter '*._pth' | Select-Object -First 1
            if ($pthFile) {
                $pthContent = Get-Content $pthFile.FullName
                $pthContent = $pthContent -replace '^#import site', 'import site'
                if ($pthContent -notmatch '\.\.\\app') {
                    $pthContent += "`n..\app`n."
                }
                Set-Content -Path $pthFile.FullName -Value $pthContent
            }

            $downloadedPy = Join-Path $PythonDir 'python.exe'
            if (Test-PythonCandidate $downloadedPy) {
                Write-Host "  [+] Ambiente Python portatil preparado com sucesso!" -ForegroundColor Green
                return $downloadedPy
            } else {
                throw "Executavel do Python baixado nao passou na validacao."
            }
        }
        catch {
            Write-Host "  [-] Nao foi possivel preparar o Python portatil: $($_.Exception.Message)" -ForegroundColor Red
            Write-Host "  [!] Instale o Python em https://www.python.org/downloads/ ou via: winget install Python.Python.3.12" -ForegroundColor Yellow
            return $null
        }
    }

    function Sync-NetworkDoctorCode {
        param([string]$LocalScriptDir)

        # Se estiver rodando de dentro do repositorio local
        if ($LocalScriptDir -and (Test-Path (Join-Path $LocalScriptDir 'main.py'))) {
            return $LocalScriptDir
        }

        # Se estiver rodando via irm | iex (remoto)
        Write-Host "  [*] Baixando a versao mais recente do Network Doctor..." -ForegroundColor Cyan
        if (-not (Test-Path $TempBase)) {
            New-Item -ItemType Directory -Path $TempBase -Force | Out-Null
        }

        $zipPath = Join-Path $TempBase 'network-doctor-latest.zip'
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13

        Invoke-WebRequest -Uri $RepoZipUrl -OutFile $zipPath -UseBasicParsing

        if (Test-Path $AppDir) {
            Remove-Item -Path $AppDir -Recurse -Force -ErrorAction SilentlyContinue
        }
        Expand-Archive -Path $zipPath -DestinationPath $TempBase -Force
        Remove-Item -Path $zipPath -Force -ErrorAction SilentlyContinue

        $extracted = Join-Path $TempBase 'network-doctor-main'
        if (Test-Path $extracted) {
            if (Test-Path $AppDir) { Remove-Item $AppDir -Recurse -Force }
            Rename-Item -Path $extracted -NewName 'app'
        }

        return $AppDir
    }

    # --- Execucao Principal ---
    $scriptDir = $PSScriptRoot
    if (-not $scriptDir -and $MyInvocation.MyCommand.Path) {
        $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    }

    $workingDir = Sync-NetworkDoctorCode -LocalScriptDir $scriptDir
    if (-not $workingDir -or -not (Test-Path (Join-Path $workingDir 'main.py'))) {
        Write-Host "  [-] Erro: Nao foi possivel localizar o ponto de entrada main.py do Network Doctor." -ForegroundColor Red
        exit 1
    }

    $pythonExe = Find-PythonExecutable
    if (-not $pythonExe) {
        $pythonExe = Install-PortablePython
        if (-not $pythonExe) {
            exit 1
        }
    }

    # Define PYTHONPATH apontando para a pasta raiz do app
    $env:PYTHONPATH = $workingDir

    # Monta os argumentos
    $mainPy = Join-Path $workingDir 'main.py'
    $passArgs = @($mainPy)
    if ($Argumentos) {
        foreach ($arg in $Argumentos) {
            if ($arg -match '^-[a-zA-Z]{2,}') {
                $passArgs += "-$arg"
            } else {
                $passArgs += $arg
            }
        }
    }

    # Executa o Network Doctor a partir da pasta do app
    Push-Location $workingDir
    try {
        & $pythonExe $passArgs
    }
    finally {
        Pop-Location
    }
}

Invoke-NetworkDoctorLauncher @args
