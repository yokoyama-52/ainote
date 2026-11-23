# UI renewal

## Applied changes

- Replaced the previous dark, settings-first window with a compact light UI that puts the hand-drawn character, status, BPM, beat indicator, and transport controls first. The existing source-selection, audio-device, rhythm-analysis, live-input, timing, and Arduino controls remain available under **音源・接続・詳細設定**.
- Added `ainote/ui/character_widget.py`, `beat_bridge.py`, and `styles.py`. The character uses the supplied original PNG raster without retracing it; only its original facial regions are transformed while painting.
- Added `Engine.visual_hits`, a bounded queue populated by `Engine.schedule_hit()`. Both PC sound/Arduino scheduling and character animation now originate from that same hit calculation. The GUI drains that queue through `BeatBridge`; it does not perform separate beat detection.
- The character receives the same scheduled deadline as the Arduino command. It eases down during the preceding 100 ms, reaches its lowest point at that deadline, then makes a damped upward rebound that blends into the next scheduled dip.
- Added `ainote/assets/character.png` and `character_source.png` (identical source artwork) and `tests/test_character_ui.py`.

## Starting on this Mac

From the project directory:

```zsh
./run.command
```

Or run the existing audio environment directly:

```zsh
.venv-audio/bin/python -m ainote
```

The existing `run.command`, `setup.command`, virtual environments, models, dependencies, and audio/Arduino implementation were intentionally left unchanged.

## Verification

Run all tests with:

```zsh
.venv-audio/bin/python -m unittest discover -s tests
```

The UI-specific tests also run headlessly with `QT_QPA_PLATFORM=offscreen` and cover resize safety, shared event timing, stale event handling, queue bounds, and stopped-state behavior.

## Backup and remaining checks

The pre-renewal versions of the changed destination files are saved in `.ui-renewal-backup.teUptp/` at the project root.

Arduino hardware was not connected for this change, so physical servo synchronization is still unverified. The visual event and Arduino command are derived from the same engine scheduling event; verify with a connected Arduino using the existing **テスト打撃** button and a live/file playback session.

The restored Arduino sketch is `sketch/sketch.ino`. It accepts the desktop app's `HIT` command at 115200 bps and replies `OK`. Its current larger servo stroke is 35° (rest) to 125° (strike); confirm mechanical clearance and use an external servo supply with common GND before uploading.
