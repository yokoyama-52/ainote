#!/bin/zsh
cd "${0:A:h}"
if [[ ! -x .venv-audio/bin/python ]]; then
  echo '先にREADMEのセットアップを実行してください。'
  read
  exit 1
fi
.venv-audio/bin/python -m ainote
if [[ $? -ne 0 ]]; then
  echo '起動できませんでした。上のメッセージを確認してください。'
  read
fi
