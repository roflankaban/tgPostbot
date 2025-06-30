#!/bin/bash
# Launcher for tgPostbot, using venv python directly to bypass pyenv activation issues

# --- Configuration ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR_NAME="venv" 
PYTHON_SCRIPT="main.py" 
# --- End Configuration ---

echo "--- tgPostbot Launcher ---"
echo "Script directory: ${SCRIPT_DIR}"
cd "${SCRIPT_DIR}" || exit 1 # Change to script's dir, exit if cd fails

VENV_PATH="${SCRIPT_DIR}/${VENV_DIR_NAME}"
PYTHON_EXEC_IN_VENV="${VENV_PATH}/bin/python3" # Expect python3
MAIN_PY_PATH="${SCRIPT_DIR}/${PYTHON_SCRIPT}"

# Check if venv python executable exists. If not, create venv.
if [ ! -f "${PYTHON_EXEC_IN_VENV}" ]; then
    echo "Virtual environment python not found at ${PYTHON_EXEC_IN_VENV}."
    # Check if system python3 exists before trying to create
    if ! command -v python3 &> /dev/null; then
         echo "ERROR: system 'python3' command not found. Cannot create virtual environment."
         exit 1
    fi
    echo "Creating/Recreating venv..."
    rm -rf "${VENV_PATH}" # Remove potentially incomplete venv
    python3 -m venv "${VENV_DIR_NAME}" # Use system python3
    if [ "$?" -ne 0 ] || [ ! -f "${PYTHON_EXEC_IN_VENV}" ]; then
        echo "ERROR: Failed to create virtual environment using 'python3 -m venv'."
        exit 1
    fi
    echo "Virtual environment created. You may need to install dependencies manually:"
    echo "cd \"${SCRIPT_DIR}\" && source \"${VENV_PATH}/bin/activate\" && pip install -r requirements.txt # (or pip install aiogram Pillow etc.)"
    # Decide whether to exit or try running anyway. Let's exit for now.
    echo "Please install dependencies before first run."
    exit 1 
    # Alternatively, could try to run pip install here, but let's keep it simple first.
fi

# Check if the main python script exists
if [ ! -f "${MAIN_PY_PATH}" ]; then
    echo "ERROR: Python script '${PYTHON_SCRIPT}' not found at ${MAIN_PY_PATH}"
    exit 1
fi

echo "Starting Python script '${PYTHON_SCRIPT}' using interpreter from venv..."
# Execute the python script using the python from the venv directly
# Pass along any arguments given to this shell script ($@)
"${PYTHON_EXEC_IN_VENV}" "${MAIN_PY_PATH}" "$@"

echo "Python script finished."
exit 0
