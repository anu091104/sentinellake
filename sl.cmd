@echo off
rem Run a SentinelLake task with the projects own Python, no activation needed.
rem Usage:  .\sl doctor  |  .\sl test  |  .\sl demo  |  .\sl   (lists all tasks)
"%~dp0.venv\Scripts\python.exe" "%~dp0tasks.py" %*
