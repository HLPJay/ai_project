@echo off
:: 关闭变量延迟扩展，防止路径中的感叹号导致崩溃
setlocal DisableDelayedExpansion

:: 设置控制台为 UTF-8 模式显示
chcp 65001 >nul

title KB-Viewer-Starter

:: --- 配置区 ---
set "NOTES_DIR=C:\Users\yun68\Desktop\日常文件整理"
set "PORT=3000"
set "SERVER_JS=server.js"
set "CUR_DIR=%~dp0"

:: --- 参数解析 ---
:PARSE_ARGS
if "%~1"=="" goto ARGS_DONE
if /i "%~1"=="-d" (
    if "%~2"=="" (
        echo [ERROR] -d 参数需要指定目录路径
        pause
        exit /b 1
    )
    set "NOTES_DIR=%~2"
    shift
    shift
    goto PARSE_ARGS
)
if /i "%~1"=="--dir" (
    if "%~2"=="" (
        echo [ERROR] --dir 参数需要指定目录路径
        pause
        exit /b 1
    )
    set "NOTES_DIR=%~2"
    shift
    shift
    goto PARSE_ARGS
)
if /i "%~1"=="-p" (
    if "%~2"=="" (
        echo [ERROR] -p 参数需要指定端口号
        pause
        exit /b 1
    )
    set "PORT=%~2"
    shift
    shift
    goto PARSE_ARGS
)
if /i "%~1"=="--port" (
    if "%~2"=="" (
        echo [ERROR] --port 参数需要指定端口号
        pause
        exit /b 1
    )
    set "PORT=%~2"
    shift
    shift
    goto PARSE_ARGS
)
if /i "%~1"=="-h" goto SHOW_HELP
if /i "%~1"=="--help" goto SHOW_HELP

:: 如果没有使用参数标识，第一个参数视为目录路径（向后兼容）
if not defined ARGS_PARSED (
    set "NOTES_DIR=%~1"
    shift
)
set "ARGS_PARSED=1"
goto PARSE_ARGS

:SHOW_HELP
echo 知识库本地查看器启动脚本
echo.
echo 用法: start.bat [选项] [目录路径]
echo.
echo 选项:
echo   -d, --dir DIR    指定知识库目录 (默认: C:\Users\yun68\Desktop\日常文件整理)
echo   -p, --port PORT  指定端口 (默认: 3000)
echo   -h, --help       显示此帮助信息
echo.
echo 示例:
echo   start.bat -d D:\我的笔记 -p 8080
echo   start.bat C:\Users\用户名\Documents\Notes
echo   start.bat --dir "D:\工作笔记" --port 3001
pause
exit /b 0

:ARGS_DONE

echo [START] Running Knowledge Base Viewer...
echo ----------------------------------------
echo [DEBUG] Script Path: "%CUR_DIR%"
echo [DEBUG] Target Path: "%NOTES_DIR%"

:: 1. 环境检查
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Node.js not found!
    pause & exit /b 1
)

:: 2. 检查 server.js
if not exist "%CUR_DIR%%SERVER_JS%" (
    echo [ERROR] Cannot find %SERVER_JS% in "%CUR_DIR%"
    pause & exit /b 1
)

:: 3. 端口检测 (简化逻辑以增强稳定性)
echo [DEBUG] Checking Port %PORT%...
netstat -ano | findstr /r /c:":%PORT% *LISTENING" >nul
if %errorlevel% equ 0 (
    echo [WARN] Port %PORT% is busy.
    set /a PORT=%PORT%+1
)

:: 4. 构造指令
set "EXEC_CMD=node "%CUR_DIR%%SERVER_JS%" "%NOTES_DIR%" %PORT%"

echo ----------------------------------------
echo [EXECUTE] %EXEC_CMD%
echo ----------------------------------------

:: 5. 启动服务器 (使用简单的组合键，避免复杂的转义)
:: 注意：start 后面的第一个引号对是窗口标题
start "Knowledge-Base-Server" cmd /c "cd /d "%CUR_DIR%" && %EXEC_CMD% || pause"

:: 6. 启动浏览器
echo [INFO] Waiting for server...
timeout /t 3 /nobreak >nul
echo [INFO] Opening Browser...
start "" "http://localhost:%PORT%"

echo.
echo ========================================
echo SUCCESS: Server command sent.
echo If the page fails to load, check the NEW black window for errors.
echo ========================================
pause