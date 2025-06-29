@echo off
echo ===================================
echo Simulation Environment
echo ===================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is not installed or not in PATH.
    echo Please install Python and try again.
    goto :end
)

REM Check if virtual environment exists
if not exist .\simenv\Scripts\activate (
    echo Virtual environment 'simenv' not found.
    echo Creating new virtual environment...
    python -m venv simenv
    if %errorlevel% neq 0 (
        echo Failed to create virtual environment.
        goto :end
    )
)

REM Activate the virtual environment
echo Activating Python virtual environment 'simenv'...
call .\simenv\Scripts\activate
if %errorlevel% neq 0 (
    echo Failed to activate virtual environment 'simenv'.
    echo Make sure the environment exists and is properly set up.
    goto :end
)

REM Check if required packages are installed
echo Checking required packages...
python -c "import pandas, numpy, sklearn, joblib" >nul 2>&1
if %errorlevel% neq 0 (
    echo Some required packages are missing.
    echo Installing required packages...
    python -m pip install pandas numpy scikit-learn joblib
    if %errorlevel% neq 0 (
        echo Failed to install required packages.
        goto :end
    )
)

echo All required packages are installed.
echo.
echo Starting Simulation Environment...
echo.

REM Start the app in a separate process
start /B python app.py

REM Wait a moment for the server to start
echo Waiting for server to start...
timeout /t 3 /nobreak >nul

REM Open the browser with the base URL
echo Opening browser...
start http://localhost:5000/

echo.
echo Simulation Environment is running.
echo Press Ctrl+C in the command window to stop the server.

:end
if %errorlevel% neq 0 (
    echo.
    echo Simulation Environment ended with errors.
    echo Press any key to exit...
    pause >nul
)
