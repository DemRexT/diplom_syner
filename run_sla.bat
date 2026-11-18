@echo off
chcp 65001 >nul
cd /d "%~dp0"
call venv\Scripts\activate.bat
echo Проверка SLA каждые 60 секунд. Закройте окно, чтобы остановить.
python manage.py check_sla --loop 60
