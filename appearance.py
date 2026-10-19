"""Booth-inspired dark interface and optional original brand artwork."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk

BACKGROUND = '#111417'
PANEL = '#1c2227'
TEXT = '#f3f6f7'
MUTED = '#9faeb7'
ACCENT = '#53e4d0'


def configure(window):
    window.configure(background=BACKGROUND)
    window.option_add('*Font', ('Segoe UI', 11))
    window.option_add('*TCombobox*Listbox.background', PANEL)
    window.option_add('*TCombobox*Listbox.foreground', TEXT)
    window.option_add('*TCombobox*Listbox.selectBackground', '#237c74')
    style = ttk.Style(window)
    style.theme_use('clam')
    style.configure('.', background=BACKGROUND, foreground=TEXT, font=('Segoe UI', 11))
    style.configure('TFrame', background=BACKGROUND)
    style.configure('Panel.TFrame', background=PANEL)
    style.configure('TLabel', background=BACKGROUND, foreground=TEXT)
    style.configure('Muted.TLabel', foreground=MUTED)
    style.configure('Title.TLabel', font=('Segoe UI', 24, 'bold'))
    style.configure('Brand.TLabel', foreground=ACCENT, font=('Segoe UI', 20, 'bold'))
    style.configure('TButton', background='#2b353d', foreground=TEXT, borderwidth=0, padding=(16, 12))
    style.map('TButton', background=[('pressed', '#35464f'), ('active', '#3c4e58')])
    style.configure('Primary.TButton', background=ACCENT, foreground='#082b27', font=('Segoe UI', 12, 'bold'), padding=(22, 14))
    style.map('Primary.TButton', background=[('pressed', '#26b8a6'), ('active', '#83f5e4')])
    for name in ('TEntry', 'TCombobox', 'TSpinbox'):
        style.configure(name, fieldbackground=PANEL, background='#303c44', foreground=TEXT,
                        insertcolor=TEXT, arrowcolor=ACCENT, padding=9, bordercolor='#38454e')
        style.map(name, fieldbackground=[('readonly', PANEL)], foreground=[('readonly', TEXT)])
    style.configure('TLabelframe', background=BACKGROUND, bordercolor='#38454e', borderwidth=1)
    style.configure('TLabelframe.Label', background=BACKGROUND, foreground=MUTED, font=('Segoe UI', 10, 'bold'))
    style.configure('TCheckbutton', background=BACKGROUND, foreground=TEXT, padding=(8, 9))
    style.map('TCheckbutton', background=[('active', '#25343a')], indicatorbackground=[('selected', ACCENT), ('!selected', '#36434b')])
    style.configure('Status.TLabel', background=PANEL, foreground=ACCENT, padding=14)


def brand(parent):
    """Load the supplied original as PNG without altering the artwork."""
    path = Path(__file__).parent / 'assets' / 'kayjuubee.png'
    if path.is_file():
        try:
            original = tk.PhotoImage(file=path)
            factor = max(1, (original.width() + 239) // 240, (original.height() + 139) // 140)
            logo = original.subsample(factor)
            label = ttk.Label(parent, image=logo)
            label.image = logo
            label.pack(anchor='w', pady=(0, 16))
            return
        except tk.TclError:
            pass
    ttk.Label(parent, text='kayjuubee', style='Brand.TLabel').pack(anchor='w')
    ttk.Label(parent, text='EVENTMODULE · USB TRANSFER', style='Muted.TLabel').pack(anchor='w', pady=(2, 20))
