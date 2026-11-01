"""Windows 11 / NVIDIA GPU temperature guard. No activation at startup."""
import csv
import ctypes
import json
import logging
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk
from profiles import PROFILES

LIMIT = 85
CREATE_NO_WINDOW = 0x08000000
CONFIG = Path(os.environ.get('LOCALAPPDATA', '.')) / 'GPUShield' / 'settings.json'


def validate_limit(value):
    if isinstance(value, bool):
        raise ValueError('Укажите целое число от 60 до 95 °C.')
    number = int(str(value))
    if not 60 <= number <= 95:
        raise ValueError('Укажите целое число от 60 до 95 °C.')
    return number


def load_limit():
    try:
        return validate_limit(json.loads(CONFIG.read_text(encoding='utf-8'))['limit'])
    except (OSError, ValueError, KeyError, TypeError):
        return LIMIT


def save_limit(value):
    value = validate_limit(value)
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG.with_suffix('.tmp')
    temporary.write_text(json.dumps({'limit': value}), encoding='utf-8')
    temporary.replace(CONFIG)


def read_temperatures():
    executable = shutil.which('nvidia-smi')
    if not executable:
        candidate = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'System32' / 'nvidia-smi.exe'
        if not candidate.exists():
            raise RuntimeError('Не найден nvidia-smi. Установите драйвер NVIDIA.')
        executable = str(candidate)
    result = subprocess.run(
        [executable, '--query-gpu=name,temperature.gpu', '--format=csv,noheader,nounits'],
        capture_output=True, text=True, timeout=5, creationflags=CREATE_NO_WINDOW,
    )
    if result.returncode:
        raise RuntimeError('Не удалось прочитать датчик NVIDIA.')
    readings = []
    for row in csv.reader(result.stdout.splitlines()):
        if len(row) != 2:
            raise RuntimeError('Некорректный ответ датчика NVIDIA.')
        value = float(row[1].strip())
        if not 0 <= value <= 150:
            raise RuntimeError('Некорректная температура GPU.')
        readings.append((row[0].strip(), value))
    if not readings:
        raise RuntimeError('Датчики NVIDIA не обнаружены.')
    return readings


def too_hot(readings, limit=LIMIT):
    return any(value >= limit for _, value in readings)


def shutdown_pc():
    executable = str(Path(os.environ.get('WINDIR', r'C:\Windows')) / 'System32' / 'shutdown.exe')
    result = subprocess.run([executable, '/s', '/f', '/t', '0'],
                            capture_output=True, text=True, timeout=8,
                            creationflags=CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError('Windows отклонила выключение: ' + result.stderr.strip())


class App:
    def __init__(self):
        import pystray
        from PIL import Image, ImageDraw
        self.events = queue.Queue()
        self.stopping = threading.Event()
        self.active = False
        self.error = None
        self.limit = load_limit()
        self.root = tk.Tk()
        self.root.title(f'GPU Shield • {self.limit} °C')
        self.root.geometry('620x520')
        self.root.resizable(False, False)
        self.root.configure(bg='#111827')
        tk.Label(self.root, text='GPU SHIELD', font=('Segoe UI', 23, 'bold'),
                 fg='#67e8f9', bg='#111827').pack(pady=(23, 10))
        self.status = tk.StringVar(value='Защита выключена')
        tk.Label(self.root, textvariable=self.status, wraplength=450, font=('Segoe UI', 11),
                 fg='white', bg='#111827').pack(pady=8)
        tk.Label(self.root, text='При достижении порога компьютер выключится.\n'
                 'Принудительное закрытие программ: сохраните данные.\n'
                 'После включения окно скроется в трей.',
                 font=('Segoe UI', 10), fg='#cbd5e1', bg='#111827').pack(pady=10)
        settings = tk.Frame(self.root, bg='#111827')
        settings.pack(pady=6)
        tk.Label(settings, text='Порог выключения (60–95 °C):', fg='white', bg='#111827').pack(side='left')
        self.limit_var = tk.StringVar(value=str(self.limit))
        self.limit_entry = tk.Spinbox(settings, from_=60, to=95, textvariable=self.limit_var, width=5)
        self.limit_entry.pack(side='left', padx=8)
        self.save_button = tk.Button(settings, text='Сохранить', command=self.apply_limit)
        self.save_button.pack(side='left')
        self.profile_box = ttk.Combobox(self.root, state='readonly', width=65,
            values=[f'{p[0]} — {p[2]} °C' if p[2] else f'{p[0]} — не поддерживается' for p in PROFILES])
        self.profile_box.set('Рекомендации: топ-20 Steam, сентябрь 2026')
        self.profile_box.pack(pady=8)
        self.profile_box.bind('<<ComboboxSelected>>', self.select_profile)
        self.profile_note = tk.StringVar(value='Выберите карту: порог появится в поле. Нажмите «Сохранить».')
        tk.Label(self.root, textvariable=self.profile_note, wraplength=580, fg='#cbd5e1',
                 bg='#111827', font=('Segoe UI', 9)).pack(pady=4)
        self.button = tk.Button(self.root, text='Включить', command=self.toggle,
                                font=('Segoe UI', 12, 'bold'), width=24)
        self.button.pack(pady=8)
        tk.Button(self.root, text='Выход', command=self.close, width=14).pack(pady=4)
        self.root.protocol('WM_DELETE_WINDOW', self.hide_or_close)
        im = Image.new('RGBA', (64, 64), '#111827')
        draw = ImageDraw.Draw(im)
        draw.rounded_rectangle((10, 7, 54, 57), radius=12, fill='#06b6d4')
        draw.text((17, 23), '85', fill='black', font_size=22)
        self.icon = pystray.Icon('GPUShield', im, 'GPU Shield — выключен', pystray.Menu(
            pystray.MenuItem('Открыть', lambda *_: self.events.put(('show', None)), default=True),
            pystray.MenuItem('Выключить защиту', lambda *_: self.events.put(('disable', None))),
            pystray.MenuItem('Выход', lambda *_: self.events.put(('quit', None)))))
        self.icon.run_detached()
        threading.Thread(target=self.monitor, daemon=True).start()
        self.root.after(150, self.pump)

    def select_profile(self, _event=None):
        name, share, recommendation, maximum = PROFILES[self.profile_box.current()]
        if recommendation is None:
            self.profile_note.set('Intel Iris Xe — семейство встроенной графики. NVIDIA-датчик его не поддерживает; единого порога нет.')
            return
        self.limit_var.set(str(recommendation))
        detail = f'Предел NVIDIA: {maximum} °C.' if maximum else 'Уточните предел у производителя конкретной модели устройства.'
        self.profile_note.set(f'{detail} Порог — рекомендация автора, не гарантия защиты. Сохраните перед включением.')

    def apply_limit(self):
        if self.active:
            return False
        try:
            candidate = validate_limit(self.limit_var.get())
            save_limit(candidate)
        except (ValueError, OSError) as exc:
            messagebox.showerror('Настройки', str(exc), parent=self.root)
            return False
        self.limit = candidate
        self.root.title(f'GPU Shield • {self.limit} °C')
        return True

    def toggle(self):
        if self.active:
            self.disable()
        else:
            if not self.apply_limit():
                return
            self.active = True
            self.limit_entry.configure(state='disabled')
            self.save_button.configure(state='disabled')
            self.profile_box.configure(state='disabled')
            self.button.configure(text='Выключить защиту')
            self.status.set('Защита включена. Чтение датчика…')
            self.icon.title = 'GPU Shield — защита включена'
            self.root.withdraw()

    def disable(self):
        self.active = False
        self.limit_entry.configure(state='normal')
        self.save_button.configure(state='normal')
        self.profile_box.configure(state='readonly')
        self.status.set('Защита выключена')
        self.button.configure(text='Включить')
        self.icon.title = 'GPU Shield — выключен'

    def show(self):
        self.root.deiconify()
        self.root.lift()

    def hide_or_close(self):
        if self.active:
            self.root.withdraw()
        else:
            self.close()

    def monitor(self):
        while not self.stopping.is_set():
            if self.active:
                try:
                    readings = read_temperatures()
                    if self.active and not self.stopping.is_set():
                        self.events.put(('temperature', readings))
                except Exception as exc:
                    self.events.put(('error', str(exc)))
            self.stopping.wait(1)

    def pump(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'quit':
                    self.close()
                    return
                if kind == 'show':
                    self.show()
                elif kind == 'disable':
                    self.disable()
                    self.show()
                elif kind == 'error' and self.active:
                    self.status.set('Датчик недоступен. Повторяем проверку…\n' + value)
                    self.icon.title = 'GPU Shield — ошибка датчика!'
                    if self.error != value:
                        logging.error(value)
                        self.show()
                    self.error = value
                elif kind == 'temperature' and self.active:
                    self.error = None
                    label = '; '.join(f'{name}: {temp:g} °C' for name, temp in value)
                    self.status.set('Защита включена\n' + label)
                    self.icon.title = ('GPU Shield — ' + label)[:127]
                    if too_hot(value, self.limit):
                        logging.warning('Threshold reached: %s', value)
                        try:
                            shutdown_pc()
                        except Exception as exc:
                            logging.exception('Shutdown failed')
                            self.status.set(str(exc))
                            self.show()
                        else:
                            self.disable()
                            self.status.set('Команда выключения отправлена Windows.')
        except queue.Empty:
            pass
        self.root.after(150, self.pump)

    def close(self):
        self.active = False
        self.stopping.set()
        self.icon.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    mutex = kernel.CreateMutexW(None, False, 'Local\\GPUShield85')
    if not mutex or ctypes.get_last_error() == 183:
        messagebox.showinfo('GPU Shield', 'Приложение уже запущено. Найдите значок в трее.')
        return
    log_dir = Path(os.environ.get('LOCALAPPDATA', '.')) / 'GPUShield'
    log_dir.mkdir(parents=True, exist_ok=True)
    from logging.handlers import RotatingFileHandler
    logging.basicConfig(handlers=[RotatingFileHandler(log_dir / 'events.log',
                        maxBytes=300000, backupCount=2, encoding='utf-8')],
                        level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        App().run()
    except Exception as exc:
        logging.exception('Application failed')
        messagebox.showerror('GPU Shield', str(exc))
    finally:
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
