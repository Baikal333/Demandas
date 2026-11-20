@echo off
chcp 65001 >nul
cd /d "%~dp0"
if "%~1"=="" (
  echo Arrastre una factura PDF del proveedor y sueltela encima de este archivo.
  pause
  exit /b
)
python facturas_contasimple.py nuevo-proveedor "%~1"
pause
