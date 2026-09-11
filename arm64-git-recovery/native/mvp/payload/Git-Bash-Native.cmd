@echo off
setlocal
set "MSYSTEM=MINGWARM64"
set "PATH=%~dp0mingwarm64\bin;%~dp0usr\bin;%SystemRoot%\System32"
"%~dp0usr\bin\bash.exe" --login -i %*
exit /b %ERRORLEVEL%
