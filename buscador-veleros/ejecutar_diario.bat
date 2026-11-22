@echo off
REM Búsqueda diaria de veleros (Windows). Prográmelo con el Programador de tareas (ver README).
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
if not exist registros mkdir registros
python -m veleros ejecutar %* >> registros\ultimo.log 2>&1
