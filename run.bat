@echo off
chcp 65001 >nul
title VK SelfBot - Селф-бот ВКонтакте

echo ==============================================================
echo             Запуск VK Селф-бота (Userbot)
echo ==============================================================

if not exist .env (
    echo [!] Файл конфигурации .env не найден.
    echo [*] Создаю .env из шаблона .env.example...
    copy .env.example .env >nul
    echo.
    echo [!] Пожалуйста, откройте файл .env и вставьте ваш VK_TOKEN!
    echo.
    notepad .env
    pause
)

where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set PY_CMD=py -3
    goto run
)

where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set PY_CMD=python
    goto run
)

if exist "C:\Users\vanap\AppData\Local\Programs\Python\Python311\python.exe" (
    set PY_CMD="C:\Users\vanap\AppData\Local\Programs\Python\Python311\python.exe"
    goto run
)

echo [X] Python не найден! Установите Python 3.9+ и добавьте его в PATH.
pause
exit /b 1

:run
echo [*] Запуск бота через %PY_CMD%...
%PY_CMD% main.py
if %ERRORLEVEL% neq 0 (
    echo.
    echo [X] Произошла ошибка при работе бота.
)
pause
