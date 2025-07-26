#!/bin/bash
sleep 10
chmod 666 /dev/gpiomem
sleep 1
python3 /home/han/photo/wifi_sender.py
