@echo off
REM Windows `zip` shim -- see scripts/zip_shim.py for why this exists.
REM agentcore refuses direct_code_deploy without a zip on PATH, then never
REM executes one. Put this directory on PATH before running agentcore.
python "%~dp0zip_shim.py" %*
