#!/bin/sh
# macOS: double-click to regenerate and open the private review desk.
cd "$(dirname "$0")" || exit 1
python3 tools/review_mysteries.py
status=$?
if [ "$status" -ne 0 ]; then
  echo "Could not create the review desk. Check the error above."
  printf "Press Enter to close... "
  read answer
fi
exit "$status"
