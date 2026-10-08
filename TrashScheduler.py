#!/usr/bin/env python3
import subprocess, time, datetime, sys, os

os.chdir("/home/edp/Desktop/Waterstation")
last_run = None

while True:
    now = datetime.datetime.now()
    if now.hour == 5 and now.minute == 30  and last_run != now.date():
        last_run = now.date()
        subprocess.Popen([sys.executable, "TrashDay.py"])
    time.sleep(20)
