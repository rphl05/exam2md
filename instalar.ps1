# Instalador do exam2md para Windows.
# Uso (PowerShell):  irm https://raw.githubusercontent.com/rphl05/exam2md/main/instalar.ps1 | iex
# Rodar de novo atualiza para a versao mais recente (mantem o que ja foi instalado).
#
# O que faz: baixa o exam2md para %USERPROFILE%\exam2md, instala o Python se faltar
# (via winget, so para o seu usuario), prepara as dependencias e cria atalhos na
# area de trabalho e no menu Iniciar.

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest fica muito lento com a barra
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$Repo    = 'rphl05/exam2md'
# EXAM2MD_DESTINO: instalar em outra pasta
$Destino = if ($env:EXAM2MD_DESTINO) { $env:EXAM2MD_DESTINO } else { Join-Path $env:USERPROFILE 'exam2md' }
# EXAM2MD_ZIP permite instalar de outro endereco ou de um .zip local (testes)
$Zip     = if ($env:EXAM2MD_ZIP) { $env:EXAM2MD_ZIP } else { "https://github.com/$Repo/archive/refs/heads/main.zip" }

function Passo($msg) { Write-Host "`n>> $msg" -ForegroundColor Cyan }
function Falha($msg) { Write-Host "`n[ERRO] $msg`n" -ForegroundColor Red; throw $msg }

function Achar-Python {
    $teste = 'import sys; sys.exit(sys.version_info < (3, 10))'
    $candidatos = @(@('py', '-3'), @('python'))
    foreach ($v in '313', '312', '311', '310') {
        $candidatos += , @("$env:LOCALAPPDATA\Programs\Python\Python$v\python.exe")
    }
    foreach ($c in $candidatos) {
        try {
            $args_ = @($c | Select-Object -Skip 1) + @('-c', $teste)
            & $c[0] @args_ 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { return , $c }
        } catch { }
    }
    return $null
}

Write-Host '=============================================='
Write-Host '  exam2md - instalacao'
Write-Host '=============================================='

# 1. Python
Passo 'Procurando o Python 3.10+...'
$py = Achar-Python
if (-not $py) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Passo 'Python nao encontrado. Instalando o Python 3.12 (so para o seu usuario)...'
        winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
        $py = Achar-Python
    }
    if (-not $py) {
        Start-Process 'https://www.python.org/downloads/'
        Falha ('Instale o Python em https://www.python.org/downloads/ ' +
               '(marque "Add python.exe to PATH") e rode este comando de novo.')
    }
}
Write-Host "   OK: $($py -join ' ')"

# 2. Arquivos do exam2md (preserva o ambiente .venv de uma instalacao anterior)
Passo "Baixando o exam2md para $Destino ..."
$tmp = Join-Path ([IO.Path]::GetTempPath()) ("exam2md_" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
    $arquivo = Join-Path $tmp 'exam2md.zip'
    if (Test-Path -LiteralPath $Zip) { Copy-Item -LiteralPath $Zip $arquivo }
    else { Invoke-WebRequest -Uri $Zip -OutFile $arquivo -UseBasicParsing }
    Expand-Archive -LiteralPath $arquivo -DestinationPath (Join-Path $tmp 'x') -Force
    $raiz = Get-ChildItem (Join-Path $tmp 'x') -Directory | Select-Object -First 1
    New-Item -ItemType Directory -Force -Path $Destino | Out-Null
    Copy-Item -Path (Join-Path $raiz.FullName '*') -Destination $Destino -Recurse -Force
} finally {
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
}

# 3. Dependencias
$args_ = @($py | Select-Object -Skip 1) + @((Join-Path $Destino 'exam2md_launcher.py'), '--preparar')
& $py[0] @args_
if ($LASTEXITCODE -ne 0) { Falha 'Nao foi possivel preparar o exam2md (veja a mensagem acima).' }

# 4. Atalhos
Passo 'Criando atalhos...'
$shell = New-Object -ComObject WScript.Shell
$icone = "$env:SystemRoot\System32\shell32.dll,70"
function Criar-Atalho($pasta, $nome, $alvo, $descricao) {
    $lnk = $shell.CreateShortcut((Join-Path $pasta "$nome.lnk"))
    $lnk.TargetPath = $alvo
    $lnk.WorkingDirectory = $Destino
    $lnk.IconLocation = $icone
    $lnk.Description = $descricao
    $lnk.Save()
}
$areaDeTrabalho = [Environment]::GetFolderPath('Desktop')
$menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'exam2md'
if ($env:EXAM2MD_ATALHOS) { $areaDeTrabalho = $menu = $env:EXAM2MD_ATALHOS }   # testes
New-Item -ItemType Directory -Force -Path $menu | Out-Null
foreach ($pasta in $areaDeTrabalho, $menu) {
    Criar-Atalho $pasta 'exam2md' (Join-Path $Destino 'Iniciar.bat') 'Converter provas em PDF para Markdown'
    Criar-Atalho $pasta 'exam2md - arraste PDFs aqui' (Join-Path $Destino 'Arraste PDFs aqui.bat') 'Arraste PDFs sobre este icone para converter'
}

Write-Host ''
Write-Host '==============================================' -ForegroundColor Green
Write-Host '  Pronto! O exam2md foi instalado.' -ForegroundColor Green
Write-Host '==============================================' -ForegroundColor Green
Write-Host '  Na area de trabalho:'
Write-Host '   - "exam2md": abre o conversor no navegador'
Write-Host '   - "exam2md - arraste PDFs aqui": solte PDFs sobre ele'
Write-Host "  Arquivos em: $Destino"
Write-Host ''

if (-not $env:EXAM2MD_NAO_ABRIR) {
    Start-Process -FilePath (Join-Path $Destino 'Iniciar.bat') -WorkingDirectory $Destino
}
