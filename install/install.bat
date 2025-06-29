@echo off
echo Starting installation process...

:: Check if Python is installed
python --version > nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Python is not installed or not in PATH.
    echo Please install Python and try again.
    goto :error
)

:: Create virtual environment
echo Creating Python virtual environment 'simenv'...
python -m venv ..\simenv

:: Check if venv creation was successful
if %ERRORLEVEL% NEQ 0 (
    echo Failed to create virtual environment.
    goto :error
)

:: Activate the virtual environment
echo Activating virtual environment...
call ..\simenv\Scripts\activate

:: Check if activation was successful
if %ERRORLEVEL% NEQ 0 (
    echo Failed to activate virtual environment.
    goto :error
)

:: Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip

:: Install requirements
echo Installing required packages...
pip install -r requirements.txt

:: Check if installation was successful
if %ERRORLEVEL% NEQ 0 (
    echo Error occurred while installing packages.
    goto :error
)

echo Installation completed successfully!
echo.
echo To activate the environment, run: .\simenv\Scripts\activate
echo To run the simulation, use: run_simulation.bat
goto :end

:error
echo An error occurred during installation.

:end
:: Pause to keep the window open
pause
