"""USBシリアルでArduinoへテスト打撃を1回送る。"""
from contextlib import contextmanager
import os
import queue
import threading
from pathlib import Path
import select
import termios
import time
import tty


def usb_ports():
    """macOSでよく使われるUSBシリアルポートを探す。"""
    return sorted(str(path) for path in Path('/dev').glob('cu.*')
                  if path.name.startswith(('cu.usb', 'cu.SLAB_USB', 'cu.wchusb')))


@contextmanager
def serial_connection(port):
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        tty.setraw(fd)
        settings = termios.tcgetattr(fd)
        settings[2] |= termios.CLOCAL | termios.CREAD
        settings[4] = settings[5] = termios.B115200
        termios.tcsetattr(fd, termios.TCSANOW, settings)
        yield fd
    except termios.error as exc:
        raise OSError(f'USBポートを設定できませんでした。{exc}') from exc
    finally:
        os.close(fd)


def send_hit(fd, stopped):
    termios.tcflush(fd, termios.TCIFLUSH)
    if os.write(fd, b'HIT\n') != 4:
        raise OSError('打撃の指示を送信できませんでした。')

    deadline = time.monotonic() + 2
    pending = b''
    while not stopped.is_set():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('ArduinoからOKが返りませんでした。スケッチとポートを確認してください。')
        ready, _, _ = select.select([fd], [], [], min(remaining, .05))
        if not ready:
            continue
        chunk = os.read(fd, 1024)
        if not chunk:
            raise OSError('Arduinoとの接続が切れました。')
        *lines, pending = (pending + chunk).split(b'\n')
        if any(line.strip() == b'OK' for line in lines):
            return


def test_hit(port):
    with serial_connection(port) as fd:
        # USBシリアルを開くと再起動する機種があるので、起動を待つ。
        time.sleep(2)
        send_hit(fd, threading.Event())


class ArduinoPlayback:
    """音声処理から打撃時刻を受け取り、別スレッドでUSBへ送る。"""
    def __init__(self, port):
        self.port = port
        self.status = 'Arduinoの起動を待っています…'
        self.ready = False
        self.stopped = threading.Event()
        self.pending = queue.Queue(maxsize=1)
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

    def schedule(self, delay):
        if not self.ready:
            return
        try:
            self.pending.put_nowait(time.monotonic() + max(0, delay))
        except queue.Full:
            pass

    def stop(self):
        self.stopped.set()
        self.worker.join()

    def _run(self):
        try:
            with serial_connection(self.port) as fd:
                if self.stopped.wait(2):
                    return
                self.ready = True
                self.status = 'Arduino接続中 · 拍に合わせて打撃'
                while not self.stopped.is_set():
                    try:
                        due = self.pending.get(timeout=.05)
                    except queue.Empty:
                        continue
                    # サーボの往復中に過ぎた拍を、後からまとめて叩かない。
                    delay = due - time.monotonic()
                    if delay < -.035 or self.stopped.wait(max(0, delay)):
                        continue
                    send_hit(fd, self.stopped)
        except OSError as exc:
            self.status = f'Arduino出力を停止しました。{exc}'
        finally:
            self.ready = False
