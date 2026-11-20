@echo off
chcp 65001 >nul
cd /d "%~dp0"
python --version >nul 2>&1 || (echo Python no esta instalado. Instalelo desde https://www.python.org/downloads/ marcando "Add python.exe to PATH". & pause & exit /b 1)
python -m pip install -r requirements.txt
if not exist config.json copy config.ejemplo.json config.json
if not exist proveedores.json copy proveedores.ejemplo.json proveedores.json
echo.
echo Instalacion terminada. Edite config.json y proveedores.json y ejecute probar.bat
pause
