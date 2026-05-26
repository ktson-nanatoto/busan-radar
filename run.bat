@echo off
chcp 65001 > nul
title 부산 청약 레이더

echo ==========================================
echo   부산 청약 레이더 시작
echo ==========================================

python -c "import flask, selenium" 2>nul
if errorlevel 1 (
    echo 패키지 설치 중...
    pip install flask selenium
)

if not exist data.json (
    echo data.json 없음 - 크롤링 실행 중 (약 30초)...
    python crawler.py --no-detail
)

echo.
echo 브라우저에서 http://localhost:5000 접속하세요
echo 종료하려면 이 창을 닫으세요
echo.
start "" http://localhost:5000
python server.py
pause