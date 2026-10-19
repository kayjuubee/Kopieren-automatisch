import json
import os
import sys
import time
import math
from pathlib import Path
import queue
import errno
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
import threading
import tkinter as tk
from tkinter import ttk, filedialog
from copier import events, copy_new, DiskFull, CopyCancelled
from devices import volumes, volume_id, eject
from overview import summarize
from transfer_progress import format_remaining
from recovery import retry_copy, RepeatedCopyError
from journal import Journal
from appearance import configure, brand
from startup import acquire_instance, autostart_enabled, set_autostart, start_watcher, watch
from background import lower_process_priority, background_copy_thread, suppress_system_error_dialogs, copy_priority

CONFIG = Path(os.getenv('LOCALAPPDATA', str(Path.home()))) / 'HotfolderUSB' / 'settings.json'


class App(tk.Tk):
    def __init__(self, start_hidden=False):
        super().__init__()
        if start_hidden:
            self.withdraw()
        self.title('kayjuubee | Hotfolder → USB')
        self.geometry('1040x900')
        self.minsize(900, 650)
        configure(self)
        try:
            settings = json.loads(CONFIG.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            settings = {}
        if not isinstance(settings, dict):
            settings = {}
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        self.log = logging.getLogger('hotfolder')
        self.log.setLevel(logging.INFO)
        handler = RotatingFileHandler(CONFIG.parent / 'transfer.log', maxBytes=2_000_000, backupCount=3, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        self.log.addHandler(handler)
        self.log.info('Programm gestartet; Veranstaltung muss manuell gewählt werden')
        sys.excepthook = self.unhandled_error
        threading.excepthook = lambda args: self.unhandled_error(args.exc_type, args.exc_value, args.exc_traceback)
        self.autostart = tk.BooleanVar(value=autostart_enabled())
        self.full_speed = tk.BooleanVar(value=False)
        self.performance_hint = tk.StringVar()
        self.remaining_text = tk.StringVar(value='Restmenge wird beim Kopierstart ermittelt.')
        self.recovery_spec = None
        self.saved_recovery = settings.get('recovery') if isinstance(settings.get('recovery'), dict) else None
        self.restart_all = False
        self.verify = tk.BooleanVar(value=settings.get('verify', False))
        self.countdown = tk.StringVar(value='Nächste Prüfung: –')
        self.next_check = None
        self.pending_eject = None
        self.overview_busy = False
        self.overview_window = None
        self.worker_thread = None
        self.overview_thread = None
        self.tray_icon = None
        self.stop_worker = threading.Event()
        self.exiting = False
        self.storage_wait = False
        self.wait_message = ''
        self.selected_volume = settings.get('volume')
        self.drive_choices = {}
        self.rate = tk.StringVar(value=str(settings.get('rate', 16)))
        self.last_run = tk.StringVar(value='Noch kein Durchlauf')
        self.progress_text = tk.StringVar(value='Bereit')
        self.parent = tk.StringVar(value=settings.get('parent', r'C:\dslrBooth'))
        self.source, self.target = tk.StringVar(), tk.StringVar()
        self.thumbs = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value='Automatik aktiv')
        self.busy, self.running = False, True
        self.timer = None
        self.interval = tk.StringVar(value=str(settings.get('interval', 5)))
        self.messages = queue.Queue()
        self.options = {}
        container = ttk.Frame(self)
        container.pack(fill='both', expand=True)
        canvas = tk.Canvas(container, background='#111417', highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient='vertical', command=canvas.yview)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        body = ttk.Frame(canvas, padding=28)
        body_id = canvas.create_window((0, 0), window=body, anchor='nw')
        body.bind('<Configure>', lambda _: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(body_id, width=event.width))
        self.bind_all('<MouseWheel>', lambda event: canvas.yview_scroll(int(-event.delta / 120), 'units'))
        brand(body)
        ttk.Label(body, text='Hotfolder → USB', style='Title.TLabel').pack(anchor='w')
        ttk.Label(body, text='Veranstaltung auswählen · neue Dateien automatisch kopieren', style='Muted.TLabel').pack(anchor='w', pady=8)
        row = ttk.Frame(body)
        row.pack(fill='x')
        ttk.Entry(row, textvariable=self.parent).pack(side='left', fill='x', expand=True)
        ttk.Button(row, text='Überordner …', command=self.browse).pack(side='left')
        ttk.Button(row, text='Aktualisieren', command=self.refresh).pack(side='left')
        ttk.Label(body, text='01  VERANSTALTUNG / QUELLE').pack(anchor='w', pady=(12, 0))
        self.sources = ttk.Combobox(body, textvariable=self.source, state='readonly')
        self.sources.pack(fill='x')
        self.sources.bind('<<ComboboxSelected>>', lambda _: self.select_source())
        ttk.Button(body, text='Neueste Veranstaltung auswählen', command=self.choose_latest).pack(anchor='w', pady=4)
        ttk.Label(body, text='02  USB-STICK / ZIEL').pack(anchor='w', pady=(12, 0))
        self.targets = ttk.Combobox(body, textvariable=self.target, state='readonly')
        self.targets.pack(fill='x')
        self.targets.bind('<<ComboboxSelected>>', self.select_target)
        usb_actions = ttk.Frame(body)
        usb_actions.pack(fill='x', pady=4)
        ttk.Button(usb_actions, text='Mit diesem Stick fortsetzen', command=self.resume_storage).pack(side='left')
        ttk.Button(usb_actions, text='Stick sicher entfernen', command=self.request_eject).pack(side='left', padx=8)
        interval_row = ttk.Frame(body)
        interval_row.pack(fill='x', pady=(12, 0))
        ttk.Label(interval_row, text='Prüfintervall (Minuten):').pack(side='left')
        ttk.Spinbox(interval_row, from_=1, to=1440, width=6, textvariable=self.interval).pack(side='left', padx=8)
        ttk.Button(interval_row, text='Intervall übernehmen', command=self.schedule).pack(side='left')
        speed_row = ttk.Frame(body)
        speed_row.pack(fill='x', pady=(10, 0))
        ttk.Label(speed_row, text='Max. Kopiertempo (MiB/s):').pack(side='left')
        self.rate_entry = ttk.Spinbox(speed_row, from_=1, to=64, width=6, textvariable=self.rate)
        self.rate_entry.pack(side='left', padx=8)
        self.performance_toggle = ttk.Checkbutton(speed_row, text='Volle Kopierleistung', variable=self.full_speed, command=self.performance_changed)
        self.performance_toggle.pack(side='left')
        ttk.Label(body, textvariable=self.performance_hint, style='Muted.TLabel', wraplength=900).pack(anchor='w', pady=4)
        ttk.Checkbutton(body, text='Mit dslrBooth / lumaBooth starten (Windows)', variable=self.autostart, command=self.change_autostart).pack(anchor='w', pady=(10, 0))
        self.folders = ttk.LabelFrame(body, text='03  ORDNERAUSWAHL', padding=10)
        self.folders.pack(fill='x', pady=14)
        ttk.Checkbutton(body, text='Auch Prints/thumbs kopieren', variable=self.thumbs).pack(anchor='w')
        ttk.Checkbutton(body, text='Dateiinhalt nach dem Kopieren prüfen (SHA-256, zusätzliche Lesezeit)', variable=self.verify).pack(anchor='w')
        row = ttk.Frame(body)
        row.pack(fill='x', pady=16)
        ttk.Button(row, text='▶  Jetzt alle kopieren', style='Primary.TButton', command=self.copy).pack(side='left')
        self.pause = ttk.Button(row, text='Pausieren', command=self.toggle)
        self.pause.pack(side='left', padx=8)
        ttk.Button(row, text='Im Hintergrund minimieren', command=self.hide).pack(side='left')
        self.progressbar = ttk.Progressbar(body, maximum=100)
        self.progressbar.pack(fill='x', pady=(0, 6))
        ttk.Label(body, textvariable=self.progress_text, wraplength=900).pack(anchor='w')
        ttk.Label(body, textvariable=self.remaining_text, wraplength=900).pack(anchor='w', pady=4)
        ttk.Label(body, textvariable=self.countdown, style='Muted.TLabel').pack(anchor='w', pady=4)
        ttk.Label(body, textvariable=self.last_run, style='Muted.TLabel').pack(anchor='w', pady=6)
        details = ttk.Frame(body)
        details.pack(fill='x', pady=6)
        ttk.Button(details, text='Protokoll anzeigen', command=self.show_log).pack(side='left')
        ttk.Button(details, text='Veranstaltungsübersicht', command=self.show_overview).pack(side='left', padx=8)
        ttk.Label(body, textvariable=self.status, style='Status.TLabel', wraplength=900).pack(fill='x')
        ttk.Label(body, text='Schonender Modus ist Standard · Fehler bleiben im Hintergrund' , style='Muted.TLabel').pack(anchor='w', pady=12)
        ttk.Button(body, text='Programm beenden', command=self.close).pack(anchor='w')
        self.protocol('WM_DELETE_WINDOW', self.hide)
        self.refresh()
        self.after(300, self.poll)
        self.schedule()
        self.init_tray()
        self.after(3000, self.monitor_usb)
        self.update_countdown()
        self.performance_changed()

    def performance_changed(self):
        full = self.full_speed.get()
        self.rate_entry.configure(state='disabled' if full else 'normal')
        self.performance_hint.set('Volle Leistung: ungedrosselt, normale Windows-Priorität. Kann dslrBooth beeinträchtigen. Gilt ab dem nächsten Kopierstart.' if full else 'Schonend: begrenztes Tempo, niedrige CPU- und Datenträgerpriorität. dslrBooth hat Vorrang.')

    def change_autostart(self):
        try:
            set_autostart(self.autostart.get())
            if self.autostart.get():
                start_watcher()
            self.status.set('Booth-Autostart aktiviert.' if self.autostart.get() else 'Booth-Autostart deaktiviert.')
            self.log.info('Booth-Autostart: %s', self.autostart.get())
        except OSError:
            self.autostart.set(autostart_enabled())
            self.log.exception('Booth-Autostart konnte nicht geändert werden')
            self.status.set('Autostart konnte nicht geändert werden. Details im Protokoll.')

    def browse(self):
        path = filedialog.askdirectory(title='Übergeordneten Veranstaltungsordner wählen')
        if path:
            self.parent.set(path)
            self.refresh()

    def refresh(self):
        if self.busy or self.recovery_spec:
            return
        try:
            choices = [str(p) for p in events(self.parent.get())]
            self.sources['values'] = choices
            previous_source = self.source.get()
            self.source.set(previous_source if previous_source in choices else '')
            self.scan_usb()
            self.load_folders()
            self.status.set(self.wait_message if self.storage_wait else 'Bitte Veranstaltung auswählen.' if not self.source.get() else 'Auswahl aktualisiert.')
        except OSError as error:
            self.status.set(str(error))

    def choose_latest(self):
        if self.busy or self.recovery_spec:
            return
        self.refresh()
        choices = self.sources['values']
        if choices:
            self.source.set(choices[0])
            self.load_folders()
            self.restore_recovery()
            self.status.set(self.wait_message if self.storage_wait else 'Neueste Veranstaltung ausgewählt. Sofort kopieren oder Intervall abwarten.')

    def select_source(self):
        self.load_folders()
        self.restore_recovery()

    def load_folders(self):
        for child in self.folders.winfo_children():
            child.destroy()
        previous = {name: value.get() for name, value in self.options.items()} if getattr(self, 'folder_source', '') == self.source.get() else {}
        self.folder_source = self.source.get()
        self.options = {}
        if not self.source.get():
            return
        try:
            paths = sorted(p for p in Path(self.source.get()).iterdir() if p.is_dir() and not p.is_symlink())
            for i, path in enumerate(paths):
                value = tk.BooleanVar(value=previous.get(path.name, path.name.lower() in {'originals', 'prints'}))
                self.options[path.name] = value
                ttk.Checkbutton(self.folders, text=path.name, variable=value).grid(row=i//3, column=i%3, sticky='w', padx=12)
        except OSError as error:
            self.status.set(str(error))

    def restore_recovery(self):
        if self.saved_recovery and self.source.get() == self.saved_recovery.get('source'):
            self.recovery_spec = self.saved_recovery
            self.storage_wait = True
            self.wait_message = self.saved_recovery.get('message', 'Bitte anderen Stick anschließen. Ganze Veranstaltung erneut kopieren.')
            self.sources.configure(state='disabled')
            self.status.set(self.wait_message)

    def toggle(self):
        self.running = not self.running
        self.pause.configure(text='Pausieren' if self.running else 'Fortsetzen')
        self.status.set(self.wait_message if self.storage_wait else 'Automatik aktiv' if self.running else 'Pausiert; laufender Kopiervorgang wird fertiggestellt.')

    def schedule(self):
        try:
            minutes = int(self.interval.get())
            if not 1 <= minutes <= 1440:
                raise ValueError
        except ValueError:
            self.status.set('Bitte ein Intervall von 1 bis 1440 Minuten eingeben.')
            return
        self.active_minutes = minutes
        if self.timer is not None:
            self.after_cancel(self.timer)
        self.next_check = time.monotonic() + minutes * 60
        self.timer = self.after(minutes * 60000, self.tick)
        self.status.set(self.wait_message if self.storage_wait else f'Prüfintervall: {minutes} Minuten.')

    def tick(self):
        if self.running and self.source.get():
            self.copy()
        self.next_check = time.monotonic() + self.active_minutes * 60
        self.timer = self.after(self.active_minutes * 60000, self.tick)

    def update_countdown(self):
        if self.pending_eject:
            text = 'Kopiervorgang wird für sicheres Entfernen angehalten'
        elif self.storage_wait:
            text = 'Wartet auf Ersatz-Stick'
        elif self.busy:
            text = 'Vorgang läuft'
        elif not self.running:
            text = 'Automatik pausiert'
        elif not self.source.get():
            text = 'Veranstaltung auswählen'
        else:
            remaining = max(0, math.ceil((self.next_check or time.monotonic()) - time.monotonic()))
            text = f'Nächste Prüfung in {remaining // 60:02d}:{remaining % 60:02d}'
        self.countdown.set(text)
        self.after(1000, self.update_countdown)

    def request_eject(self):
        if self.exiting or self.pending_eject:
            return
        choice = self.drive_choices.get(self.target.get())
        if not choice or volume_id(choice[0]) != choice[1]:
            self.status.set('Bitte den angeschlossenen USB-Stick auswählen.')
            return
        self.running = False
        self.pause.configure(text='Fortsetzen')
        self.pending_eject = choice
        self.status.set('Kopieren wird angehalten; anschließend Stick sicher entfernen …')
        if self.busy:
            self.stop_worker.set()
        else:
            self.begin_eject()

    def begin_eject(self):
        target, identity = self.pending_eject
        self.busy = True
        self.targets.configure(state='disabled')
        self.sources.configure(state='disabled')
        def worker():
            try:
                background_copy_thread()
                eject(target, identity)
                self.log.info('Stick sicher entfernt: %s (%s)', target, identity)
                self.messages.put(('ejected', 'Stick wurde ausgeworfen und kann entfernt werden. Automatik bleibt pausiert.'))
            except Exception:
                self.log.exception('Sicheres Entfernen fehlgeschlagen')
                self.messages.put(('eject_error', 'Windows konnte den Stick nicht auswerfen. Möglicherweise wird er noch verwendet. Details im Protokoll; Automatik bleibt pausiert.'))
        self.worker_thread = threading.Thread(target=worker, daemon=True)
        self.worker_thread.start()

    def scan_usb(self):
        drives = volumes()
        previous = self.target.get()
        self.drive_choices = {f"{root}  {info['label']}  [{info['id'].strip(chr(92))[-9:]}]": (root, info['id']) for root, info in drives.items()}
        self.targets['values'] = list(self.drive_choices)
        matching = next((label for label, (_, identity) in self.drive_choices.items() if identity == self.selected_volume), None)
        if matching:
            self.target.set(matching)
        elif previous in self.drive_choices:
            self.target.set(previous)
        elif self.selected_volume is None and self.drive_choices:
            self.target.set(next(iter(self.drive_choices)))
            self.select_target()
        elif self.storage_wait and self.drive_choices:
            self.target.set(next(iter(self.drive_choices)))
        else:
            self.target.set('')

    def select_target(self, _=None):
        choice = self.drive_choices.get(self.target.get())
        if choice and not self.busy:
            self.selected_volume = choice[1]

    def monitor_usb(self):
        try:
            if not self.busy:
                self.scan_usb()
        except Exception:
            self.log.exception('USB-Erkennung fehlgeschlagen; erneuter Versuch in 3 Sekunden')
            if not self.storage_wait:
                self.status.set('USB-Erkennung fehlgeschlagen. Details im Protokoll.')
        finally:
            self.after(3000, self.monitor_usb)

    def resume_storage(self):
        if self.busy:
            return
        self.select_target()
        choice = self.drive_choices.get(self.target.get())
        if not choice or volume_id(choice[0]) != choice[1]:
            self.status.set('Bitte angeschlossenen Ersatz-Stick im Dropdown auswählen.')
            return
        if self.recovery_spec:
            if choice[1] == self.recovery_spec['volume']:
                self.status.set('Bitte einen anderen Stick auswählen. Der fehlerhafte Stick wird nicht erneut verwendet.')
                return
            self.source.set(self.recovery_spec['source'])
            self.restart_all = True
        self.storage_wait = False
        self.wait_message = ''
        self.running = True
        self.pause.configure(text='Pausieren')
        self.log.info('Fortsetzen mit Volume %s; ganze Veranstaltung: %s', choice[1], self.restart_all)
        self.copy()

    def copy(self):
        if self.busy or self.exiting:
            return
        if self.storage_wait:
            self.status.set(self.wait_message)
            return
        choice = self.drive_choices.get(self.target.get())
        source = self.source.get()
        folders = self.recovery_spec['folders'] if self.recovery_spec else [name for name, value in self.options.items() if value.get()]
        if not source or not choice or not folders or volume_id(choice[0]) != choice[1]:
            self.status.set('Quelle, angeschlossenen USB-Stick und Ordner auswählen.')
            return
        full_speed = self.full_speed.get()
        try:
            rate = 16 if full_speed else int(self.rate.get())
            if not 1 <= rate <= 64:
                raise ValueError
        except ValueError:
            self.status.set('Bitte Kopiertempo von 1 bis 64 MiB/s eingeben.')
            return
        target, identity = choice
        thumbs = self.recovery_spec['thumbs'] if self.recovery_spec else self.thumbs.get()
        verify = self.verify.get()
        volume_label = self.target.get()
        ignore_history = self.restart_all
        copy_spec = {'volume': identity, 'source': source, 'folders': list(folders), 'thumbs': thumbs}
        self.selected_volume = identity
        self.busy = True
        self.stop_worker.clear()
        self.sources.configure(state='disabled')
        self.targets.configure(state='disabled')
        self.performance_toggle.configure(state='disabled')
        self.remaining_text.set('Restmenge wird ermittelt …')
        self.status.set('Kopieren läuft …')
        self.log.info('Start: %s → %s, Volume %s, Ordner %s, max. %s MiB/s', source, target, identity, folders, 'ungedrosselt' if full_speed else rate)
        reported_count = 0
        completed_total = 0
        session_delivered = set()
        def report(name, done, total, count):
            nonlocal reported_count, completed_total
            if count > reported_count:
                completed_total += count - reported_count
                self.log.info('Kopiert: %s (%s Bytes)', name, total)
                reported_count = count
            self.messages.put(('progress', (name, done, total, completed_total)))
        def worker():
            journal = None
            result = None
            try:
                journal = Journal(CONFIG.parent / 'delivered.sqlite3')
                journal.remember_volume(identity, volume_label)
                def attempt():
                    nonlocal reported_count
                    reported_count = 0
                    return copy_new(source, target, folders, thumbs, journal=journal, volume=identity,
                                    session_delivered=session_delivered, rate=rate, progress=report, valid_target=lambda: volume_id(target) == identity,
                                    stop=self.stop_worker, verify=verify, full_speed=full_speed, ignore_history=ignore_history,
                                    overall=lambda value: self.messages.put(('remaining', value)),
                                    phase=lambda text: self.messages.put(('phase', text)))
                def notify(error, count):
                    self.log.warning('Kopierfehler (%s/5 gleicher Fehler): %s', count, error)
                    self.messages.put(('phase', f'Kopierfehler ({count}/5): {error}. Neuer Versuch in 3 Sekunden.'))
                with copy_priority(full_speed):
                    count = retry_copy(attempt, self.stop_worker, notify)
                self.log.info('Durchlauf abgeschlossen: %s neue Dateien insgesamt', completed_total)
                result = ('done', f'{completed_total} neue Dateien kopiert.')
            except CopyCancelled:
                self.log.info('Kopiervorgang angehalten; fertige Dateien bleiben erhalten')
                result = ('cancelled', 'Kopiervorgang angehalten.')
            except RepeatedCopyError as error:
                self.log.error('%s; Ersatz-Stick und vollständige Neukopie erforderlich', error)
                result = ('replace', {**copy_spec, 'message': f'{error}. Bitte anderen Stick anschließen und „Mit diesem Stick fortsetzen“ drücken. Die ganze Veranstaltung wird erneut kopiert.'})
            except Exception as error:
                self.log.exception('Kopiervorgang fehlgeschlagen')
                result = ('error', str(error))
            finally:
                if journal:
                    journal.close()
            if result:
                self.messages.put(result)
        self.worker_thread = threading.Thread(target=worker, daemon=True)
        self.worker_thread.start()

    def poll(self):
        for _ in range(100):
            try:
                kind, value = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind == 'show':
                self.show()
            elif kind == 'exit':
                self.close()
                if not self.busy:
                    return
            elif kind == 'overview':
                self.overview_busy = False
                self.render_overview(value)
            elif kind == 'overview_error':
                self.overview_busy = False
                self.status.set(value)
            elif kind == 'remaining':
                self.remaining_text.set(format_remaining(value))
            elif kind == 'phase':
                self.status.set(value)
            elif kind == 'notice':
                if not self.storage_wait:
                    self.status.set(value)
            elif kind == 'progress':
                name, done, total, count = value
                self.progressbar['value'] = 100 * done / total if total else 100
                self.progress_text.set(f'{count} Dateien kopiert · {name} · {done / 1048576:.1f} / {total / 1048576:.1f} MiB')
            else:
                if self.worker_thread is not None:
                    self.worker_thread.join(timeout=0.2)
                completed_eject = kind in {'ejected', 'eject_error'}
                if completed_eject:
                    self.pending_eject = None
                self.busy = False
                self.performance_toggle.configure(state='normal')
                if kind == 'replace':
                    self.recovery_spec = value
                    self.saved_recovery = value
                    self.restart_all = False
                    self.storage_wait = True
                    self.wait_message = value['message']
                    value = self.wait_message
                self.sources.configure(state='disabled' if self.recovery_spec else 'readonly')
                self.targets.configure(state='readonly')
                if kind == 'full':
                    self.storage_wait = True
                    self.wait_message = value
                self.status.set(value)
                self.last_run.set(f'Letzter Versuch: {datetime.now():%d.%m.%Y %H:%M:%S} · {value}')
                if kind == 'done':
                    self.progress_text.set(value)
                    self.recovery_spec = None
                    self.saved_recovery = None
                    self.restart_all = False
                    self.sources.configure(state='readonly')
                else:
                    self.remaining_text.set('Angehalten · ' + self.remaining_text.get().removeprefix('Angehalten · '))
                self.save_settings()
                if self.exiting:
                    self.finish_exit()
                    return
                if self.pending_eject and not completed_eject:
                    self.begin_eject()
        self.after(300, self.poll)

    def unhandled_error(self, exc_type, error, traceback):
        # This can run on a worker thread: do not access Tk here.
        self.log.error('Unerwarteter Fehler', exc_info=(exc_type, error, traceback))
        self.messages.put(('notice', 'Unerwarteter Fehler. Details im Protokoll.'))

    def report_callback_exception(self, exc_type, error, traceback):
        self.unhandled_error(exc_type, error, traceback)

    def init_tray(self):
        try:
            from tray import start_tray
            self.tray_icon = start_tray(self.messages)
        except Exception as error:
            self.log.warning('Tray nicht verfügbar, Fenster bleibt minimierbar: %s', error)
        self.bind('<Unmap>', self.on_minimize)
        if not self.tray_icon and self.state() == 'withdrawn':
            self.iconify()

    def on_minimize(self, event):
        if event.widget == self and self.tray_icon and self.state() == 'iconic':
            self.withdraw()

    def hide(self):
        self.save_settings()
        if self.tray_icon:
            self.withdraw()
        else:
            self.iconify()

    def show(self):
        self.deiconify()
        self.lift()
        if self.storage_wait:
            self.status.set(self.wait_message)

    def show_overview(self):
        if self.overview_busy:
            return
        source = self.source.get()
        folders = [name for name, value in self.options.items() if value.get()]
        if not source or not folders:
            self.status.set('Bitte Veranstaltung und Ordner für die Übersicht auswählen.')
            return
        thumbs = self.thumbs.get()
        self.overview_busy = True
        self.status.set('Veranstaltungsübersicht wird ermittelt …')
        def worker():
            journal = None
            try:
                background_copy_thread()
                journal = Journal(CONFIG.parent / 'delivered.sqlite3')
                result = summarize(source, folders, thumbs, journal)
                result['source'] = source
                self.messages.put(('overview', result))
            except Exception:
                self.log.exception('Veranstaltungsübersicht fehlgeschlagen')
                self.messages.put(('overview_error', 'Übersicht konnte nicht erstellt werden. Details im Protokoll.'))
            finally:
                if journal:
                    journal.close()
        self.overview_thread = threading.Thread(target=worker, daemon=True)
        self.overview_thread.start()

    def render_overview(self, result):
        # Only a user-requested overview may create a window. Do not raise it
        # when the main app was hidden while its background scan was running.
        if self.state() in {'withdrawn', 'iconic'}:
            self.status.set('Übersicht ermittelt. Zum Anzeigen erneut Veranstaltungsübersicht wählen.')
            return
        if self.overview_window and self.overview_window.winfo_exists():
            self.overview_window.destroy()
        window = tk.Toplevel(self)
        self.overview_window = window
        window.title('Veranstaltungsübersicht')
        window.geometry('1000x650')
        ttk.Label(window, text=result['source'], wraplength=960).pack(anchor='w', padx=16, pady=10)
        ttk.Label(window, text=f"{result['total']} Quelldateien · {result['delivered']} protokolliert übertragen · {result['pending']} ohne Übertragungsnachweis ({result['recent']} noch neu)").pack(anchor='w', padx=16)
        table = ttk.Treeview(window, columns=('stick', 'files', 'mib', 'verified'), show='headings', height=6)
        for key, label, width in [('stick', 'Stick / Kennung', 540), ('files', 'Dateien', 100), ('mib', 'MiB', 100), ('verified', 'Inhalt geprüft', 110)]:
            table.heading(key, text=label)
            table.column(key, width=width)
        table.pack(fill='x', padx=16, pady=12)
        for identity, entry in result['volumes'].items():
            table.insert('', 'end', values=(entry['label'], entry['files'], f"{entry['bytes'] / 1048576:.1f}", entry['verified']))
        ttk.Label(window, text='Ohne Übertragungsnachweis (max. 500 angezeigt; bereits vorhandene Zieldateien werden nicht überschrieben):', wraplength=960).pack(anchor='w', padx=16)
        frame = ttk.Frame(window)
        frame.pack(fill='both', expand=True, padx=16, pady=8)
        missing = tk.Text(frame, background='#1c2227', foreground='#f3f6f7', wrap='word')
        scroll = ttk.Scrollbar(frame, command=missing.yview)
        missing.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        missing.pack(fill='both', expand=True)
        missing.insert('end', '\n'.join(result['pending_files'][:500]) or 'Alle ausgewählten Quelldateien sind protokolliert übertragen.')
        missing.configure(state='disabled')
        ttk.Label(window, text='Lokale Historie der aktuell ausgewählten Quelldateien; keine erneute Prüfung bereits entfernter Sticks.', wraplength=960).pack(anchor='w', padx=16, pady=8)
        ttk.Button(window, text='Aktualisieren', command=self.show_overview).pack(pady=8)

    def show_log(self):
        window = tk.Toplevel(self)
        window.title('Kopierprotokoll')
        window.geometry('950x500')
        frame = ttk.Frame(window)
        frame.pack(fill='both', expand=True)
        text = tk.Text(frame, background='#1c2227', foreground='#f3f6f7', wrap='word')
        scroll = ttk.Scrollbar(frame, command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        text.pack(fill='both', expand=True)
        def refresh_log():
            try:
                contents = (CONFIG.parent / 'transfer.log').read_text(encoding='utf-8')
            except OSError as error:
                contents = str(error)
            text.configure(state='normal')
            text.delete('1.0', 'end')
            text.insert('end', contents)
            text.see('end')
            text.configure(state='disabled')
        ttk.Button(window, text='Aktualisieren', command=refresh_log).pack(pady=8)
        refresh_log()

    def save_settings(self):
        try:
            rate = int(self.rate.get())
            if not 1 <= rate <= 64:
                rate = 16
        except ValueError:
            rate = 16
        try:
            temporary = CONFIG.with_suffix('.tmp')
            temporary.write_text(json.dumps({'parent': self.parent.get(), 'interval': getattr(self, 'active_minutes', 5),
                                             'rate': rate, 'volume': self.selected_volume, 'verify': self.verify.get(), 'recovery': self.saved_recovery}), encoding='utf-8')
            temporary.replace(CONFIG)
        except OSError:
            self.log.exception('Einstellungen konnten nicht gespeichert werden')

    def close(self):
        self.exiting = True
        self.save_settings()
        if self.busy:
            self.stop_worker.set()
            self.status.set('Kopiervorgang wird sicher beendet …')
        else:
            self.finish_exit()

    def finish_exit(self):
        if self.tray_icon:
            self.tray_icon.stop()
        self.log.info('Programm beendet')
        self.destroy()


if __name__ == '__main__':
    suppress_system_error_dialogs()
    try:
        lower_process_priority()
        if '--self-test' in sys.argv:
            from selfcheck import run
            run(Path.cwd() / 'self-test-report.json')
        elif '--watch' in sys.argv:
            watch()
        elif acquire_instance():
            App(start_hidden='--background' in sys.argv).mainloop()
    except Exception:
        # Also keep startup failures silent when launched as a windowed EXE.
        try:
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            import traceback
            with (CONFIG.parent / 'startup-error.log').open('a', encoding='utf-8') as output:
                output.write(f'\n{datetime.now().isoformat()}\n')
                traceback.print_exc(file=output)
        except OSError:
            pass
        sys.exit(1)
