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

    function Find-PythonExecutable {
        # 1. Tenta python no PATH
        $pyCmd = Get-Command 'python.exe' -ErrorAction SilentlyContinue
        if ($pyCmd) { return $pyCmd.Source }

        # 2. Tenta py launcher
        $pyLauncher = Get-Command 'py.exe' -ErrorAction SilentlyContinue
        if ($pyLauncher) { return $pyLauncher.Source }

        # 3. Tenta python isolado no TEMP
        $localPy = Join-Path $PythonDir 'python.exe'
        if (Test-Path $localPy) { return $localPy }

        return $null
    }

    function Install-PortablePython {
        Write-Host "  ⏳ Python nao encontrado no sistema. Baixando ambiente portatil..." -ForegroundColor Yellow
        if (-not (Test-Path $PythonDir)) {
            New-Item -ItemType Directory -Path $PythonDir -Force | Out-Null
        }

        $zipFile = Join-Path $TempBase 'python-embed.zip'
        $pyUrl = 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip'

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
                Set-Content -Path $pthFile.FullName -Value $pthContent
            }
            Write-Host "  ✓ Ambiente Python portatil preparado com sucesso!" -ForegroundColor Green
            return (Join-Path $PythonDir 'python.exe')
        }
        catch {
            Write-Host "  ❌ Nao foi possivel preparar o Python portatil: $($_.Exception.Message)" -ForegroundColor Red
            Write-Host "  👉 Instale o Python em https://www.python.org/downloads/ ou via: winget install Python.Python.3.12" -ForegroundColor Yellow
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
        Write-Host "  ⏳ Baixando a versao mais recente do Network Doctor..." -ForegroundColor Cyan
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
        Write-Host "  ❌ Erro: Nao foi possivel localizar o ponto de entrada main.py do Network Doctor." -ForegroundColor Red
        exit 1
    }

    $pythonExe = Find-PythonExecutable
    if (-not $pythonExe) {
        $pythonExe = Install-PortablePython
        if (-not $pythonExe) {
            exit 1
        }
    }

    # Monta os argumentos
    $mainPy = Join-Path $workingDir 'main.py'
    $passArgs = @($mainPy)
    if ($Argumentos) {
        $passArgs += $Argumentos
    }

    # Executa o Network Doctor
    & $pythonExe $passArgs
}

Invoke-NetworkDoctorLauncher @args
