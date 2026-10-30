@echo off
rem Build GitNow single-file exe with PyInstaller
cd /d %~dp0
C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe -m PyInstaller --noconfirm --clean --onefile --name GitNow --collect-all textual --collect-all gitnow --paths . gitnow_exe.py
echo.
echo Done. Output: dist\GitNow.exe
pause
