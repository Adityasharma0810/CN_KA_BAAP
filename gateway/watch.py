"""Compact live view of /clients. Run: python3 gateway/watch.py"""
import json
import time
import urllib.request

while True:
    data = json.load(urllib.request.urlopen("http://localhost:8000/clients"))
    print("\033[2J\033[H", end="")
    print(f"{'ID':<12}{'Intent':<11}{'Down Mbit/s':>12}   Limit")
    for c in data:
        lim = c["limit"]["down_mbps"] if c["limit"] else "-"
        print(f"{c['id']:<12}{c['intent']:<11}{c['down_mbps']:>12}   {lim}")
    time.sleep(1)