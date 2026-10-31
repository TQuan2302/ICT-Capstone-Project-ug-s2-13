#!/bin/bash
# This file is used to start the RoadSight website.
# The first click installs the Python packages from the requirements.txt file.
# Later clicks only start the website.

# Go to the directory of this file.
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || exit 1

# Check if the Python version is 3.10 or newer.
python_ok() {
  "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1
}

# Find the Python version that is 3.10 or newer.
PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && python_ok "$candidate"; then
    PY="$candidate"
    break
  fi
done

# If no Python version that is 3.10 or newer is found, inform the user and exit.
if [ -z "$PY" ]; then
  echo "Error: Python 3.10 or newer is not installed. Install it and try again."
  exit 1
fi

# Check if Tesseract is installed, if not install it.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if ! command -v tesseract >/dev/null 2>&1; then
  echo "Webapp needs Tesseract to read numbers on speed-signs."
  echo "Installing Tesseract..."
  echo
  if ! command -v brew >/dev/null 2>&1; then
    NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || {
      echo
      echo "Error: Homebrew could not be installed, so Tesseract was not installed."
      echo "The webapp will still show the detected features but not the numbers on the speed-signs."
      echo
    }
    if [ -x /opt/homebrew/bin/brew ]; then
      eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [ -x /usr/local/bin/brew ]; then
      eval "$(/usr/local/bin/brew shellenv)"
    fi
  fi
  if command -v brew >/dev/null 2>&1; then
    brew install tesseract || {
      echo
      echo "Error: Tesseract could not be installed."
      echo "The webapp will still show the detected features but not the numbers on the speed-signs."
      echo
    }
  fi
fi

# Check if ExifTool is installed, if not install it.
if ! command -v exiftool >/dev/null 2>&1; then
  echo "Webapp needs ExifTool to read latitude and longitude from a .MOV."
  echo "Installing ExifTool..."
  echo
  if ! command -v brew >/dev/null 2>&1; then
    NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || {
      echo
      echo "Error: Homebrew could not be installed, so ExifTool was not installed."
      echo "The webapp will still detect features, but latitude and longitude will notbe shown."
      echo
    }
    if [ -x /opt/homebrew/bin/brew ]; then
      eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [ -x /usr/local/bin/brew ]; then
      eval "$(/usr/local/bin/brew shellenv)"
    fi
  fi
  if command -v brew >/dev/null 2>&1; then
    brew install exiftool || {
      echo
      echo "Error: ExifTool could not be installed."
      echo "The webapp will still detect features, but latitude and longitude will not be shown."
      echo
    }
  fi
fi

# First launch, checks if the Python environment is already created. If not, creates it.
# If the environment is already created, activates it.
if [ ! -d .venv ]; then
  echo "Installing python packages from requirements.txt..."
  echo
  "$PY" -m venv .venv || {
    echo "Error: Could not create the Python environment."
    read -r -p "Press Return to close."
    exit 1
  }
  source .venv/bin/activate
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt || {
    echo
    echo "Error: Installation failed."
    read -r -p "Press Return to close."
    exit 1
  }
  echo
  echo "Success: Installation finished."
else
  source .venv/bin/activate
fi

# Start the webapp
(
  for _ in $(seq 1 90); do
    if curl -sf -o /dev/null "http://127.0.0.1:8000/"; then
      open "http://127.0.0.1:8000/"
      exit 0
    fi
    sleep 1
  done
) &

cd src || exit 1
echo "Starting RoadSight at http://127.0.0.1:8000"
echo "To close the RoadSight webapp, close this window."
echo
exec fastapi dev webapp.py