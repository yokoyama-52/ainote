#!/bin/zsh
set -e
cd "${0:A:h}"
if ! command -v python3.12 >/dev/null 2>&1; then
  echo 'この構成はPython 3.12で検証しています。python3.12をインストールして再実行してください。'
  read
  exit 1
fi
python3.12 -m venv .venv-audio
.venv-audio/bin/python -m pip install 'numpy==1.26.4' 'setuptools==80.10.2' wheel
.venv-audio/bin/python -m pip install --no-build-isolation -r requirements.lock.txt
.venv-audio/bin/python scripts/fetch_models.py
echo '準備できました。run.commandで起動してください。'
