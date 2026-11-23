import sys
import time
from dataclasses import replace
from pathlib import Path
import numpy as np
import soundfile as sf
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QSettings
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QDoubleSpinBox, QFileDialog, QMessageBox, QProgressBar, QGroupBox, QComboBox, QCheckBox, QScrollArea, QToolButton, QSizePolicy)
from .ui.character_widget import CharacterWidget
from .ui.beat_bridge import BeatBridge
from .ui.styles import STYLE
from .arduino import test_hit, usb_ports
from .engine import Engine
from .devices import discover
from .live import LiveEngine
import sounddevice as sd
from .music import estimate, demo, beat_indicator

# ファイル読み込みを別スレッドに任せ、読み込み中も画面を操作できるようにする。
class Loader(QThread):
    loaded = Signal(object, int, str)
    failed = Signal(str)
    def __init__(self, path):
        super().__init__()
        self.path = path
    def run(self):
        try:
            info = sf.info(self.path)
            if info.duration > 900:
                raise ValueError('この試作品では15分以内の音源を選択してください。')
            audio, rate = sf.read(self.path, dtype='float32', always_2d=True)
            if not len(audio) or not np.isfinite(audio).all():
                raise ValueError('空または破損した音源です。')
            if audio.shape[1] == 1:
                audio = np.repeat(audio, 2, axis=1)
            else:
                audio = audio[:, :2].copy()
            self.loaded.emit(audio, rate, Path(self.path).name)
        except Exception as exc:
            self.failed.emit(str(exc))

# ファイルのBPMと拍位置の推定も、画面の処理とは別に行う。
class Analyzer(QThread):
    result = Signal(object)
    failed = Signal(str)
    def __init__(self, audio, rate):
        super().__init__()
        self.audio, self.rate = audio, rate
    def run(self):
        try:
            self.result.emit(estimate(self.audio, self.rate))
        except Exception as exc:
            self.failed.emit(str(exc))

class ArduinoTest(QThread):
    message = Signal(str)

    def __init__(self, port, parent):
        super().__init__(parent)
        self.port = port

    def run(self):
        try:
            test_hit(self.port)
        except (OSError, ValueError) as exc:
            self.message.emit(f'テスト打撃を確認できませんでした。{exc}')
        else:
            self.message.emit('ArduinoからOKを受信しました。')


class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('AINOTE — 歌のとなりに、タンバリン。')
        self.resize(740, 720)
        self.file_engine = Engine()
        self.live_engine = LiveEngine()
        self.engine = self.file_engine
        self.audio, self.rate = demo()
        self.busy = False
        self.taps = []
        self.settings = QSettings('Ainote', 'KaraokePrototype')
        self.live_timing_ms = float(self.settings.value('live_timing_ms', 0))
        self.file_timing_ms = 0.0
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(6)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        self.scroll.setWidget(body)
        outer.addWidget(self.scroll, 1)
        root = QVBoxLayout(body)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(8)
        title = QLabel('AINOTE  /  KARAOKE PARTNER')
        title.setObjectName('title')
        root.addWidget(title)

        self.source = QLabel('練習用デモ · 120 BPM · 32秒')
        self.source.setWordWrap(True)
        self.source.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        root.addWidget(self.source)
        row = QHBoxLayout()
        self.file_button = QPushButton('音源ファイルを開く')
        self.file_button.clicked.connect(self.open_file)
        row.addWidget(self.file_button)
        self.demo_button = QPushButton('デモに戻す')
        self.demo_button.clicked.connect(self.load_demo)
        row.addWidget(self.demo_button)
        self.analyze_button = QPushButton('BPM・拍位置を推定')
        self.analyze_button.clicked.connect(self.analyze)
        row.addWidget(self.analyze_button)
        root.addLayout(row)
        live_row = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(['ファイル再生', 'リアルタイム入力'])
        self.mode.currentIndexChanged.connect(self.change_mode)
        live_row.addWidget(self.mode)
        self.input_device = QComboBox()
        self.output_device = QComboBox()
        live_row.addWidget(self.input_device)
        live_row.addWidget(self.output_device)
        refresh_devices = QPushButton('機器更新')
        refresh_devices.clicked.connect(lambda: self.refresh_devices(reinitialize=True))
        live_row.addWidget(refresh_devices)
        root.addLayout(live_row)
        self.advanced = QWidget()
        advanced_layout = QVBoxLayout(self.advanced)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        advanced_layout.setSpacing(6)
        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel('拍の認識方式'))
        self.tracker_choice = QComboBox()
        self.tracker_choice.addItem('AI 2モデル相互確認（推奨）', 'ensemble')
        self.tracker_choice.addItem('AI small1（比較用）', 'small1')
        self.tracker_choice.addItem('AI small0（比較用）', 'small0')
        self.tracker_choice.addItem('従来方式（aubio）', 'aubio')
        self.tracker_choice.currentIndexChanged.connect(self.apply_mode)
        scale_row.addWidget(self.tracker_choice)
        scale_row.addWidget(QLabel('拍間隔補正'))
        self.tempo_scale = QComboBox()
        self.tempo_scale.addItem('半分のテンポ', .5)
        self.tempo_scale.addItem('推定どおり', 1.0)
        self.tempo_scale.addItem('倍のテンポ', 2.0)
        self.tempo_scale.setCurrentIndex(1)
        self.tempo_scale.currentIndexChanged.connect(self.set_tempo_scale)
        scale_row.addWidget(self.tempo_scale)
        self.rescan = QPushButton('テンポを取り直す')
        self.rescan.clicked.connect(self.rescan_tempo)
        scale_row.addWidget(self.rescan)
        advanced_layout.addLayout(scale_row)
        self.bass_support = QCheckBox('低音域の補助解析（30–150 Hz・5秒窓）')
        self.bass_support.setChecked(False)
        advanced_layout.addWidget(self.bass_support)
        self.refresh_devices()
        self.pulse = QLabel('●  ●  ●  ●')
        self.pulse.setObjectName('pulse')
        self.pulse.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.pulse)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        root.addWidget(self.progress)
        self.status = QLabel('準備完了 — デモはそのまま再生できます')
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        timing = QGroupBox('リズムを合わせる')
        layout = QHBoxLayout(timing)
        self.bpm_label = QLabel('BPM')
        layout.addWidget(self.bpm_label)
        self.bpm = QDoubleSpinBox()
        self.bpm.setRange(40, 240)
        self.bpm.setValue(float(self.settings.value('bpm', 120)))
        self.bpm.setDecimals(1)
        self.bpm.valueChanged.connect(self.update_controls)
        layout.addWidget(self.bpm)
        self.tap_button = QPushButton('タップ')
        self.tap_button.clicked.connect(self.tap)
        layout.addWidget(self.tap_button)
        layout.addWidget(QLabel('タイミング補正 (ms)'))
        self.offset = QDoubleSpinBox()
        self.offset.setRange(-2000, 2000)
        self.offset.setSingleStep(10)
        self.offset.setToolTip('マイナスで早く、プラスで遅く鳴らします。BPMは変わりません。')
        self.offset.valueChanged.connect(self.update_controls)
        layout.addWidget(self.offset)
        root.addWidget(timing)
        nudge_row = QHBoxLayout()
        self.nudge_label = QLabel('発音位置')
        nudge_row.addWidget(self.nudge_label)
        self.earlier = QPushButton('10 ms早める')
        self.earlier.clicked.connect(lambda: self.offset.setValue(self.offset.value()-10))
        nudge_row.addWidget(self.earlier)
        self.later = QPushButton('10 ms遅らせる')
        self.later.clicked.connect(lambda: self.offset.setValue(self.offset.value()+10))
        nudge_row.addWidget(self.later)
        self.reset_timing = QPushButton('補正を0に戻す')
        self.reset_timing.clicked.connect(lambda: self.offset.setValue(0))
        nudge_row.addWidget(self.reset_timing)
        root.addLayout(nudge_row)
        self.energy_label = QLabel()
        root.addWidget(self.energy_label)
        self.energy = QSlider(Qt.Orientation.Horizontal)
        self.energy.setRange(0, 100)
        self.energy.setValue(int(self.settings.value('energy', 50)))
        self.energy.valueChanged.connect(self.update_controls)
        root.addWidget(self.energy)
        self.interlude = QPushButton('間奏モード OFF')
        self.interlude.setCheckable(True)
        self.interlude.toggled.connect(self.update_controls)
        root.addWidget(self.interlude)
        row = QHBoxLayout()
        row.addWidget(QLabel('伴奏の音量'))
        self.music_volume = QSlider(Qt.Orientation.Horizontal)
        self.music_volume.setRange(0, 100)
        self.music_volume.setValue(70)
        self.music_volume.valueChanged.connect(self.update_controls)
        row.addWidget(self.music_volume)
        row.addWidget(QLabel('タンバリン音量'))
        self.hit_volume = QSlider(Qt.Orientation.Horizontal)
        self.hit_volume.setRange(0, 100)
        self.hit_volume.setValue(50)
        self.hit_volume.valueChanged.connect(self.update_controls)
        row.addWidget(self.hit_volume)
        root.addLayout(row)
        row = QHBoxLayout()
        self.play = QPushButton('▶ 演奏開始')
        self.play.setObjectName('play')
        self.play.clicked.connect(self.start)
        row.addWidget(self.play)
        stop = QPushButton('■ 停止 / Space')
        stop.clicked.connect(self.stop)
        row.addWidget(stop)
        outer.addLayout(row)
        self.stop_button = stop
        self.details_button = QToolButton()
        self.details_button.setText('詳細設定（認識方式・拍間隔・低音補助）')
        self.details_button.setCheckable(True)
        self.details_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.details_button.setArrowType(Qt.ArrowType.RightArrow)
        self.details_button.toggled.connect(self.toggle_details)
        root.addWidget(self.details_button)
        root.addWidget(self.advanced)
        self.advanced.hide()
        arduino = QGroupBox('Arduino（USB）')
        arduino_layout = QVBoxLayout(arduino)
        row = QHBoxLayout()
        self.arduino_port = QComboBox()
        self.arduino_port.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        row.addWidget(self.arduino_port, 1)
        self.arduino_scan = QPushButton('再検索')
        self.arduino_scan.clicked.connect(self.refresh_arduino_ports)
        row.addWidget(self.arduino_scan)
        self.arduino_hit = QPushButton('テスト打撃')
        self.arduino_hit.clicked.connect(self.start_arduino_test)
        row.addWidget(self.arduino_hit)
        arduino_layout.addLayout(row)
        self.arduino_playback = QCheckBox('演奏中はArduinoでタンバリンを叩く')
        arduino_layout.addWidget(self.arduino_playback)
        self.arduino_status = QLabel('Arduino IDEのシリアルモニタを閉じてから試してください。')
        self.arduino_status.setWordWrap(True)
        arduino_layout.addWidget(self.arduino_status)
        root.addWidget(arduino)
        self.arduino_worker = None
        self.refresh_arduino_ports()
        root.addStretch(1)
        note = QLabel('入力への回り込みを防ぐため、ヘッドホンを推奨。')
        note.setWordWrap(True)
        root.addWidget(note)
        self.shortcut = QShortcut(QKeySequence('Space'), self)
        self.shortcut.activated.connect(self.stop)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        # Poll frequently enough to give scheduled hardware hits visible lead time.
        self.timer.start(16)
        self.update_controls()
        self.apply_mode()
        # Keep every existing control; settings scroll independently of the face.
        root.removeWidget(title)
        title.setText('ainote')
        header = QHBoxLayout()
        header.addWidget(title)
        header.addStretch()
        self.connection = QLabel('Arduino · 未接続')
        self.connection.setObjectName('connection')
        header.addWidget(self.connection)
        outer.insertLayout(0, header)
        self.character = CharacterWidget()
        outer.insertWidget(1, self.character, 1)
        self.caption = QLabel('おんがくをまっているよ')
        self.caption.setObjectName('caption')
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.insertWidget(2, self.caption)
        self.tempo_display = QLabel('— BPM')
        self.tempo_display.setObjectName('tempo')
        self.tempo_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.insertWidget(3, self.tempo_display)
        for index, widget in enumerate((self.pulse, self.progress), 4):
            root.removeWidget(widget)
            outer.insertWidget(index, widget)
        self.settings_toggle = QToolButton()
        self.settings_toggle.setText('音源・接続・詳細設定')
        self.settings_toggle.setCheckable(True)
        self.settings_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.settings_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.settings_toggle.toggled.connect(self.show_settings)
        outer.insertWidget(6, self.settings_toggle)
        self.scroll.hide()
        self.scroll.setMinimumHeight(90)
        self.play.setText('START / 演奏開始')
        self.stop_button.setText('STOP / Space')
        self.bridge = BeatBridge(self)
        self.bridge.scheduled.connect(self.character.schedule_beat)
        self.setStyleSheet(STYLE)

        for combo in (self.mode, self.input_device, self.output_device, self.tracker_choice, self.tempo_scale):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(6)
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            combo.setMinimumWidth(70)
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.resize(min(740, available.width()-24), min(720, available.height()-64))

    def show_settings(self, visible):
        self.scroll.setVisible(visible)
        self.settings_toggle.setArrowType(Qt.ArrowType.DownArrow if visible else Qt.ArrowType.RightArrow)

    def refresh_arduino_ports(self):
        previous = self.arduino_port.currentData()
        self.arduino_port.clear()
        for port in usb_ports():
            self.arduino_port.addItem(Path(port).name, port)
        if not self.arduino_port.count():
            self.arduino_port.addItem('USBポートが見つかりません')
        index = self.arduino_port.findData(previous)
        if index >= 0:
            self.arduino_port.setCurrentIndex(index)
        self.arduino_hit.setEnabled(self.arduino_port.currentData() is not None)

    def start_arduino_test(self):
        port = self.arduino_port.currentData()
        if port is None or self.arduino_worker is not None:
            return
        self.arduino_status.setText('打撃を1回テスト中…')
        self.arduino_hit.setEnabled(False)
        self.arduino_scan.setEnabled(False)
        self.arduino_port.setEnabled(False)
        worker = ArduinoTest(port, self)
        self.arduino_worker = worker
        worker.message.connect(self.arduino_status.setText)
        worker.finished.connect(self.finish_arduino_test)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def finish_arduino_test(self):
        self.arduino_worker = None
        self.update_arduino_controls()

    def update_arduino_controls(self):
        idle = not self.engine.active and self.arduino_worker is None
        self.arduino_hit.setEnabled(idle and self.arduino_port.currentData() is not None)
        for widget in (self.arduino_scan, self.arduino_port, self.arduino_playback):
            widget.setEnabled(idle)

    def toggle_details(self, visible):
        self.advanced.setVisible(visible)
        self.details_button.setArrowType(Qt.ArrowType.DownArrow if visible else Qt.ArrowType.RightArrow)

    # 画面で選んだ設定を演奏側へ渡す。
    def update_controls(self, *_):
        if not hasattr(self, 'energy') or not hasattr(self, 'hit_volume'):
            return
        energy = self.energy.value()
        mode = '休止' if energy == 0 else '控えめ' if energy <= 33 else '標準' if energy <= 66 else 'にぎやか'
        self.energy_label.setText(f'盛り上げ度  {energy} / 100 — {mode}')
        if self.engine is self.live_engine:
            self.live_timing_ms = self.offset.value()
            self.settings.setValue('live_timing_ms', self.live_timing_ms)
        self.interlude.setText('間奏モード ON' if self.interlude.isChecked() else '間奏モード OFF')
        self.engine.controls = replace(self.engine.controls, bpm=self.bpm.value(),
            offset=self.offset.value()/1000, excitement=energy, interlude=self.interlude.isChecked(),
            music_volume=self.music_volume.value()/100, percussion_volume=self.hit_volume.value()/100)

    def set_busy(self, busy):
        self.busy = busy
        for button in (self.file_button, self.demo_button, self.analyze_button, self.play, self.mode):
            button.setEnabled(not busy)
        if not busy:
            self.apply_mode()

    def rescan_tempo(self):
        if self.mode.currentIndex() and not self.busy:
            self.stop()
            self.start()

    def set_tempo_scale(self):
        self.live_engine.tempo_scale = self.tempo_scale.currentData()

    def refresh_devices(self, reinitialize=False):
        if self.file_engine.active or self.live_engine.active:
            if hasattr(self, 'status'):
                self.status.setText('機器更新は演奏を停止してから行ってください。')
            return
        previous_input = self.input_device.currentText()
        previous_output = self.output_device.currentText()
        if reinitialize:
            self.file_engine.stop()
            self.live_engine.stop()
        try:
            inputs, outputs = discover(reinitialize)
        except Exception as exc:
            inputs, outputs = [], []
            notice = f'音声機器を取得できません: {exc}。接続後に機器更新かアプリ再起動を試してください。'
        else:
            notice = (f'音声機器を更新しました：入力{len(inputs)}件・出力{len(outputs)}件。'
                      '表示されない場合はOSのサウンド設定で接続先を確認してください。')
        self.input_device.clear()
        self.output_device.clear()
        self.input_device.addItem('標準の音声入力', None)
        self.output_device.addItem('標準の音声出力', None)
        for combo, devices, previous in ((self.input_device, inputs, previous_input),
                                          (self.output_device, outputs, previous_output)):
            for index, name in devices:
                combo.addItem(name, index)
                combo.setItemData(combo.count()-1, name, Qt.ItemDataRole.ToolTipRole)
            restored = combo.findText(previous)
            if restored >= 0:combo.setCurrentIndex(restored)
        if reinitialize and hasattr(self, 'status'):
            self.status.setText(notice)

    def apply_mode(self):
        live = self.mode.currentIndex() == 1
        self.update_arduino_controls()
        for control in (self.file_button, self.demo_button, self.analyze_button):
            control.setEnabled(not live and not self.busy)
        self.input_device.setEnabled(live and not self.engine.active)
        self.output_device.setEnabled(not self.engine.active)
        self.source.setVisible(not live)
        for control in (self.file_button, self.demo_button, self.analyze_button, self.bpm_label, self.bpm, self.tap_button):
            control.setVisible(not live)
        for control in (self.nudge_label, self.earlier, self.later, self.reset_timing):
            control.setVisible(live)
        self.bpm.setEnabled(not live)
        for control in (self.earlier, self.later, self.reset_timing):
            control.setEnabled(live)
        self.tempo_scale.setEnabled(live)
        self.rescan.setEnabled(live and not self.busy)
        self.bass_support.setEnabled(live and not self.engine.active and self.tracker_choice.currentData() != 'aubio')
        self.tracker_choice.setEnabled(live and not self.engine.active)
        self.music_volume.setEnabled(not live)

    def change_mode(self):
        if self.engine is self.live_engine:
            self.live_timing_ms = self.offset.value()
        else:
            self.file_timing_ms = self.offset.value()
        self.stop()
        self.engine = self.live_engine if self.mode.currentIndex() else self.file_engine
        self.offset.setValue(self.live_timing_ms if self.mode.currentIndex() else self.file_timing_ms)
        self.update_controls()
        self.apply_mode()
        self.status.setText('リアルタイム入力を選んで開始してください' if self.mode.currentIndex() else 'ファイル再生モード')

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'カラオケ伴奏を選択', '', '音声 (*.wav *.flac *.mp3 *.ogg *.aiff);;すべて (*)')
        if not path:
            return
        self.stop()
        self.set_busy(True)
        self.status.setText('音源を読み込み中…')
        self.loader = Loader(path)
        self.loader.loaded.connect(self.loaded)
        self.loader.failed.connect(self.failure)
        self.loader.finished.connect(lambda: self.set_busy(False))
        self.loader.start()

    def loaded(self, audio, rate, name):
        self.audio, self.rate = audio, rate
        self.offset.setValue(0)
        self.source.setText(f'{name} · {len(audio)/rate:.1f}秒')
        self.status.setText('読み込み完了。BPMを指定するか、推定ボタンを押してください。')

    def load_demo(self):
        self.stop()
        self.audio, self.rate = demo()
        self.bpm.setValue(120)
        self.offset.setValue(0)
        self.source.setText('練習用デモ · 120 BPM · 32秒')

    def analyze(self):
        self.stop()
        self.set_busy(True)
        self.status.setText('音源の先頭90秒から一定テンポと拍位置を推定中…')
        self.worker = Analyzer(self.audio, self.rate)
        self.worker.result.connect(self.analysis_done)
        self.worker.failed.connect(self.failure)
        self.worker.finished.connect(lambda: self.set_busy(False))
        self.worker.start()

    def analysis_done(self, result):
        self.bpm.setValue(result.bpm)
        self.offset.setValue(result.offset*1000)
        self.status.setText(f'推定 {result.bpm:.1f} BPM / 周期性の目安 {result.confidence:.0%}。耳で確認し、必要ならBPM・拍位置を調整してください。')

    def failure(self, message):
        self.status.setText('処理できませんでした')
        QMessageBox.warning(self, '確認してください', message)

    def tap(self):
        if self.mode.currentIndex():
            return
        now = time.monotonic()
        self.taps = [t for t in self.taps if now-t < 5][-7:] + [now]
        if len(self.taps) >= 3:
            self.bpm.setValue(float(np.clip(60/np.median(np.diff(self.taps)), 40, 240)))

    # 選択中のモードに応じて、マイク入力かファイル再生を始める。
    def start(self):
        if self.busy or self.arduino_worker is not None or self.engine.active:
            return
        port = self.arduino_port.currentData() if self.arduino_playback.isChecked() else None
        if self.arduino_playback.isChecked() and port is None:
            self.arduino_status.setText('ArduinoをUSB接続して、ポートを選んでください。')
            return
        self.update_controls()
        try:
            if self.mode.currentIndex():
                self.live_engine.backend = self.tracker_choice.currentData()
                self.live_engine.bass_support = self.bass_support.isChecked()
                self.live_engine.start_live(self.input_device.currentData(), self.output_device.currentData(), arduino_port=port)
            else:
                self.engine.start(self.audio, self.rate, output_device=self.output_device.currentData(), arduino_port=port)
            self.apply_mode()
            self.status.setText('拍を確認中…' if self.mode.currentIndex() else '演奏中 — 最初から再生 / Spaceで停止')
        except Exception as exc:
            self.failure(f'音声出力を開始できません。出力デバイスを確認してください。\n{exc}')

    def stop(self):
        self.engine.stop()
        if self.arduino_playback.isChecked() and self.arduino_worker is None:
            self.arduino_status.setText('Arduinoへの打撃指示を停止しました。')
        self.status.setText('停止中 — 演奏開始で最初から再生')
        self.pulse.setText('●  ●  ●  ●')
        if hasattr(self, 'character'):
            self.character.set_playing(False)
        if hasattr(self, 'mode'):
            self.apply_mode()

    # 演奏側の状態を読み、入力メーターや拍の表示を更新する。
    def refresh(self):
        e = self.engine
        self.character.set_playing(e.active)
        self.bridge.poll(e)
        if e.arduino is not None:
            self.connection.setText('Arduino · 接続中' if e.arduino.ready else e.arduino.status)
            self.connection.setToolTip(e.arduino.status)
            arduino_error = not e.arduino.ready and '停止' in e.arduino.status
        else:
            arduino_error = self.arduino_playback.isChecked() and self.arduino_port.currentData() is None
            self.connection.setText('Arduino · 未接続' if self.arduino_port.currentData() is None else 'Arduino · ポート選択済み')
        self.caption.setText('つながっていないみたい' if arduino_error else
                             'リズムをきいているよ' if e.active else 'おんがくをまっているよ')
        bpm = e.state.bpm*e.tempo_scale if e is self.live_engine and e.active and e.state.locked else self.bpm.value() if e is self.file_engine else None
        self.tempo_display.setText(f'{bpm:.1f} BPM' if bpm is not None else '— BPM')
        if e.arduino is not None:
            self.arduino_status.setText(e.arduino.status)
        if e.finished:
            self.stop()
            e.finished = False
            self.status.setText('演奏終了')
        if e.active and e.stream is not None and not e.stream.active:
            self.stop()
            self.status.setText('音声出力が停止しました。出力デバイスを確認してください。')
        if e is self.live_engine:
            if e.active:
                state = e.state
                age = e.position/e.rate-state.updated
                locked = state.locked and 0 <= age < .8
                if e.shutdown.is_set():
                    description = '解析が停止しています。停止して再開してください'
                elif age >= .8:
                    description = '解析が遅れています。ほかの重い処理を停止してください'
                elif e.position/e.rate < 1:
                    description = '音声入力を確認中'
                elif e.input_level < .0003:
                    description = '入力音が小さいか無音です。入力機器・マイク権限を確認してください'
                else:
                    description = state.reason
                db = 20*np.log10(max(e.input_level, 1e-8))
                self.status.setText(f"{('仮追従' if state.provisional else '演奏中') if locked else '拍を確認中'} · {state.bpm*e.tempo_scale:.1f} BPM · 追従目安 {state.confidence:.0%} · 入力 {db:.0f} dBFS\n{description} · 検出拍 {state.beat_count} · 入力欠落 {e.dropped}")
                if locked:
                    beat = beat_indicator(e.position/e.rate, state.bpm, state.phase, state.beat_index, e.tempo_scale, e.controls.offset)
                    self.pulse.setText('  '.join('◉' if i == beat else '○' for i in range(4)))
                else:
                    self.pulse.setText('○  ○  ○  ○')
            self.progress.setValue(min(1000, int(e.input_level*4000)))
            if e.error:
                self.status.setText('入力の通知: '+e.error)
                e.error = ''
            return
        position = e.position/getattr(e, 'rate', self.rate)
        self.progress.setValue(min(1000, int(position/(len(self.audio)/self.rate)*1000)))
        if e.active:
            beat = max(0, int((position-e.controls.offset)*e.controls.bpm/60)) % 4
            self.pulse.setText('  '.join('◉' if i == beat else '○' for i in range(4)))
        if e.error:
            self.status.setText('音声処理の通知: ' + e.error)
            e.error = ''

    def closeEvent(self, event):
        if self.arduino_worker is not None:
            self.arduino_status.setText('テスト打撃の完了後に閉じてください。')
            event.ignore()
            return
        if self.busy:
            QMessageBox.information(self, '処理中', '読み込み・解析の完了後に閉じてください。')
            event.ignore()
            return
        self.engine.stop()
        self.settings.setValue('bpm', self.bpm.value())
        self.settings.setValue('energy', self.energy.value())
        event.accept()

def main():
    app = QApplication(sys.argv)
    window = Window()
    window.show()
    sys.exit(app.exec())
