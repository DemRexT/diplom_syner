@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Установка ServiceDesk PM ===
python -m venv venv || (echo Не найден Python. Установите Python 3.11+ с python.org и отметьте "Add to PATH". & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist .env copy .env.example .env
python manage.py migrate
python manage.py seed_demo
echo.
echo Готово! Запустите run_site.bat и откройте http://127.0.0.1:8000
pause
