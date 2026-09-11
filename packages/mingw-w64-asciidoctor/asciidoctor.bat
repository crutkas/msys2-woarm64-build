@echo off
setlocal
set "RUBYOPT="
set "RUBYLIB="
set "GEM_HOME="
set "GEM_PATH="
set "PATH=%~dp0..\..\clangarm64\bin;%SystemRoot%\System32;%SystemRoot%"
"%~dp0..\..\clangarm64\bin\ruby.exe" "%~dp0..\lib\asciidoctor\launcher.rb" %*
exit /b %errorlevel%
