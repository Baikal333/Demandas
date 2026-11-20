@echo off
chcp 65001 >nul
cd /d "%~dp0"
python facturas_contasimple.py procesar
pause
