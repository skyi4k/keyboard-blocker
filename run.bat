@echo off
:: Запуск Cat Keyboard Blocker от имени администратора
:: (Для блокировки клавиатуры нужны права администратора)

cd /d "%~dp0"

:: Проверяем, установлены ли зависимости
pip show pystray >nul 2>&1
if errorlevel 1 (
    echo Устанавливаю зависимости...
    pip install -r requirements.txt
)

echo.
echo ========================================
echo   Cat Keyboard Blocker
echo   Блокировщик клавиатуры от кошки
echo ========================================
echo.

python cat_blocker.py
pause
