@echo off
REM ============================================================================
REM audioPrime  --  pull latest from GitHub and build the Windows app.
REM
REM Invoke over SSH from the Mac (same host/credentials as the transcribe box):
REM     ssh <build-user>@<host> F:\audioPrime\pull_and_build.bat
REM
REM This box is treated as a BUILD SLAVE: it always resets its working tree to
REM origin/main, discarding any local drift, so every build is reproducible.
REM Auth for the private repo comes from the repo-local credential store file
REM .git\build-credentials (git credential.helper = store --file=...), NOT from
REM Git Credential Manager -- a headless service account has no access to the
REM interactive user's GCM vault.
REM credential.interactive is forced off so a headless run never hangs.
REM
REM safe.directory is passed on the command line rather than relied on from
REM ~/.gitconfig: the repo lives on an exFAT volume, which reports every file's
REM owner as "Everyone", so git's ownership check fails for every account. A
REM non-interactive SSH session may not resolve HOME/USERPROFILE, in which case
REM ~/.gitconfig is never read and git aborts with "dubious ownership".
REM
REM vcvars64.bat is sourced because Nuitka shells out to MSVC cl.exe, which is
REM only on PATH inside a Visual Studio developer environment -- an interactive
REM desktop login gets that from the VS shortcuts, a headless SSH shell does not.
REM ============================================================================

setlocal
set "REPO=F:\audioPrime"
set "PY=%REPO%\.venv\Scripts\python.exe"
set "GIT=C:\Program Files\Git\cmd\git.exe"
set "GITOPTS=-c safe.directory=F:/audioPrime -c credential.interactive=false"
set "VCVARS=C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"

cd /d "%REPO%" || (echo FATAL: cannot cd to %REPO% & exit /b 1)

echo(
echo === [1/4] Fetching origin (non-interactive) ===
set GIT_TERMINAL_PROMPT=0
"%GIT%" %GITOPTS% fetch --prune origin
if errorlevel 1 (echo FATAL: git fetch failed ^(check GitHub credentials^) & exit /b 1)

echo(
echo === [2/4] Resetting working tree to origin/main ===
"%GIT%" %GITOPTS% reset --hard origin/main
if errorlevel 1 (echo FATAL: git reset failed & exit /b 1)
REM The whole command needs an extra surrounding quote pair: inside for /f, cmd
REM strips the quotes around %GIT% and then mis-parses the args that follow.
for /f "delims=" %%h in ('""%GIT%" %GITOPTS% rev-parse --short HEAD"') do echo Now at commit %%h

echo(
echo === [3/4] Loading MSVC build environment ===
where cl.exe >nul 2>&1
if errorlevel 1 (
    if not exist "%VCVARS%" (echo FATAL: vcvars64.bat not found at %VCVARS% & exit /b 1)
    call "%VCVARS%" >nul
    where cl.exe >nul 2>&1
    if errorlevel 1 (echo FATAL: cl.exe still not on PATH after vcvars64 & exit /b 1)
    echo MSVC environment loaded.
) else (
    echo cl.exe already on PATH.
)

echo(
echo === [4/4] Building Windows app (Nuitka) ===
"%PY%" scripts\build_win.py
set "BUILD_RC=%ERRORLEVEL%"
if not "%BUILD_RC%"=="0" (echo. & echo BUILD FAILED ^(rc=%BUILD_RC%^) & exit /b %BUILD_RC%)

echo(
echo === DONE: build succeeded -- output in %REPO%\dist\audioPrime.dist ===
exit /b 0
