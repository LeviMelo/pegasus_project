#!/bin/bash
# waits for the XI fit, then tests the negative control (J20-J22 test runs separately); gives up only if the fit process is gone
cd /c/Users/Galaxy/LEVI/projects/pegasus_project
until grep -q -E "BLOCK XI|^FAIL|Traceback|fit failed" data/logs/brumadinho_fit.log; do sleep 30; done
grep -q "BLOCK XI" data/logs/brumadinho_fit.log && PYTHONUTF8=1 C:/Users/Galaxy/miniconda3/envs/pegasus/python.exe scripts/heavy.py --label "brumadinho test XI" -- C:/Users/Galaxy/miniconda3/envs/pegasus/python.exe data/brumadinho_test.py XI > data/logs/brumadinho_test_XI.log 2>&1
