@echo off
chcp 65001 >nul
title YouTube Ultimate Downloader - 8K/4K/FHD
cd /d "%~dp0"

echo ========================================================
echo       YOUTUBE ULTIMATE DOWNLOADER - PRO EDITION
echo   Tải Video YouTube Đầy Đủ Độ Phân Giải (8K / 4K / 1080p / MP3)
echo ========================================================
echo.
echo [1/2] Đang kiểm tra môi trường...
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [LỖI] Không tìm thấy Python trên hệ thống! Vui lòng cài đặt Python 3.9 trở lên.
    pause
    exit /b
)

echo [2/2] Đang khởi động Server...
echo Mở trình duyệt web tại http://127.0.0.1:8000
echo Nhấn Ctrl + C để dừng chương trình.
echo.

python app.py

if %errorlevel% neq 0 (
    echo.
    echo Đã xảy ra lỗi khi khởi chạy ứng dụng.
    pause
)
