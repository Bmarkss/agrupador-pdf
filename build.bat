@echo off
chcp 65001 > nul
echo.
echo =====================================================
echo    AgrupadorPDF v1.6.3  -  Build Script
echo =====================================================
echo.

if not exist "AgrupadorPDF.py" (
    echo [ERRO] Abra o CMD dentro da pasta do projeto
    echo        onde esta o AgrupadorPDF.py
    echo.
    pause
    exit /b 1
)

if not exist "AgrupadorPDF.ico" (
    echo [ERRO] AgrupadorPDF.ico nao encontrado
    echo.
    pause
    exit /b 1
)

echo [1/5] Verificando Python...
python --version > nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado. Instale em python.org e marque "Add to PATH"
    echo.
    pause
    exit /b 1
)
python --version
echo.

echo [2/5] Instalando dependencias...
python -m pip install --upgrade pip --quiet
python -m pip install pyinstaller pypdf pdfplumber scikit-learn rapidfuzz networkx tkinterdnd2 --quiet
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias
    pause
    exit /b 1
)
echo OK - PyInstaller + pypdf + pdfplumber + scikit-learn + rapidfuzz + networkx
echo.

echo [3/5] Limpando builds anteriores...
if exist "dist"  rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
echo OK
echo.

echo [4/5] Gerando AgrupadorPDF.exe (aguarde 1-2 minutos)...
echo.
python -m PyInstaller AgrupadorPDF.spec --noconfirm
if errorlevel 1 (
    echo.
    echo [ERRO] PyInstaller falhou. Veja o log acima.
    pause
    exit /b 1
)

if not exist "dist\AgrupadorPDF.exe" (
    echo [ERRO] dist\AgrupadorPDF.exe nao foi gerado
    pause
    exit /b 1
)
echo.
echo OK - dist\AgrupadorPDF.exe gerado com sucesso
echo.

if exist "AgrupadorPDF_Documentacao.docx" (
    copy /y "AgrupadorPDF_Documentacao.docx" "dist\AgrupadorPDF_Documentacao.docx" > nul
)

echo [5/5] Gerando instalador com Inno Setup...
echo.

:: Salva ProgramFiles(x86) numa variavel simples (os parenteses quebram o IF)
set "PF86=%ProgramFiles(x86)%"
set "PF64=%ProgramFiles%"
set "PFLOC=%LocalAppData%\Programs"

set ISCC=
if exist "%PF86%\Inno Setup 6\ISCC.exe"  set "ISCC=%PF86%\Inno Setup 6\ISCC.exe"
if exist "%PF64%\Inno Setup 6\ISCC.exe"  set "ISCC=%PF64%\Inno Setup 6\ISCC.exe"
if exist "%PFLOC%\Inno Setup 6\ISCC.exe" set "ISCC=%PFLOC%\Inno Setup 6\ISCC.exe"
if exist "C:\InnoSetup6\ISCC.exe"         set "ISCC=C:\InnoSetup6\ISCC.exe"

if "%ISCC%"=="" (
    for /f "delims=" %%i in ('where ISCC.exe 2^>nul') do set "ISCC=%%i"
)

if "%ISCC%"=="" (
    echo [AVISO] Inno Setup nao encontrado.
    echo         Baixe e instale em: https://jrsoftware.org/isdl.php
    echo         Depois rode este build.bat novamente.
    echo.
    echo O arquivo dist\AgrupadorPDF.exe ja funciona como executavel standalone.
    echo.
    pause
    exit /b 0
)

echo Usando: %ISCC%
echo.
"%ISCC%" "AgrupadorPDF_Installer.iss"
if errorlevel 1 (
    echo.
    echo [ERRO] Inno Setup falhou. Veja o log acima.
    pause
    exit /b 1
)

echo.
echo =====================================================
echo    BUILD CONCLUIDO COM SUCESSO!
echo =====================================================
echo.
echo Instalador: dist_installer\AgrupadorPDF_v1.6.3_Installer.exe
echo.
echo Distribua apenas o arquivo Installer.exe.
echo.
pause
