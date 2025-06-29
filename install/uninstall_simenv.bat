@echo off
setlocal enabledelayedexpansion

echo Uninstalling simulation environment...

:: Check if simenv exists in the current directory
if exist "..\simenv" (
    echo Found simenv in current directory.
    
    :: Ask for confirmation
    set /p CONFIRM="Are you sure you want to remove the simulation environment? (y/n): "
    
    :: Convert to lowercase for comparison
    set "CONFIRM=!CONFIRM:Y=y!"
    
    if "!CONFIRM!"=="y" (
        :: Deactivate environment if active
        where python | findstr /i simenv > nul 2>&1
        if !ERRORLEVEL! EQU 0 (
            echo Deactivating environment before removal...
            call deactivate
        )
        
        :: Remove the environment directory
        echo Removing simenv directory...
        rmdir /s /q ..\simenv
        
        if !ERRORLEVEL! NEQ 0 (
            echo Failed to remove simenv directory. It may be in use.
            echo Please close any applications using it and try again.
            goto :end
        )
        
        echo Simulation environment successfully uninstalled.
    ) else (
        echo Uninstallation cancelled.
    )
) else (
    echo Simulation environment not found in current directory.
    
    :: Ask if user wants to specify a different location
    set /p SEARCH="Do you want to specify a different location? (y/n): "
    
    :: Convert to lowercase for comparison
    set "SEARCH=!SEARCH:Y=y!"
    
    if "!SEARCH!"=="y" (
        set /p CUSTOM_PATH="Enter the path where simenv is installed: "
        
        if exist "!CUSTOM_PATH!\simenv" (
            echo Found simenv at specified location.
            
            :: Ask for confirmation
            set /p CONFIRM="Are you sure you want to remove the simulation environment? (y/n): "
            
            :: Convert to lowercase for comparison
            set "CONFIRM=!CONFIRM:Y=y!"
            
            if "!CONFIRM!"=="y" (
                :: Remove the environment directory
                echo Removing simenv directory...
                rmdir /s /q "!CUSTOM_PATH!\simenv"
                
                if !ERRORLEVEL! NEQ 0 (
                    echo Failed to remove simenv directory. It may be in use.
                    echo Please close any applications using it and try again.
                    goto :end
                )
                
                echo Simulation environment successfully uninstalled.
            ) else (
                echo Uninstallation cancelled.
            )
        ) else (
            echo Simulation environment not found at specified location.
        )
    ) else (
        echo Uninstallation cancelled.
    )
)

:end
echo.
echo Press any key to exit...
pause > nul
endlocal
