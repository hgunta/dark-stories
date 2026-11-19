@echo off
rem Windows: double-click to regenerate and open the private review desk.
cd /d "%~dp0"
py -3 tools\review_mysteries.py
if errorlevel 1 (
  echo Could not create the review desk. Check the error above.
  pause
)
