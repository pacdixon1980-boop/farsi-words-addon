#!/bin/sh
# Start the persistent Python translation server in the background, then
# run the main Node server in the foreground (which is what Docker watches).
python3 /app/tools/translate_server.py &
exec node /app/server.js
