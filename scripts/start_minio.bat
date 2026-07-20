@echo off
echo Starting MinIO Server...
echo.
echo   API:     http://localhost:9000
echo   Console: http://localhost:9001
echo   User:    minioadmin
echo   Pass:    minioadmin123
echo.
set MINIO_ROOT_USER=minioadmin
set MINIO_ROOT_PASSWORD=minioadmin123
C:\minio\minio.exe server C:\minio\data --console-address ":9001"
