@echo off
takeown /f build /r /d y >nul 2>&1
icacls build /grant Everyone:F /t >nul 2>&1
powershell -Command "Remove-Item -Path 'build' -Recurse -Force -ErrorAction SilentlyContinue" >nul 2>&1
if exist SimTimeInd.spec del /q SimTimeInd.spec >nul 2>&1

pyinstaller --noconfirm --clean --onefile --windowed --name SimTimeInd main.py

if exist dist\SimTimeInd.exe (echo OK: dist\SimTimeInd.exe) else (echo ERROR)
pause
