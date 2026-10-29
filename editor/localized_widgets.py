"""Presentation widgets whose labels are separate from canonical model values."""
import tkinter as tk
from tkinter import ttk, simpledialog

from i18n import tr as _


class LocalizedCombobox(ttk.Combobox):
    """A readonly choice keeps English/internal values in its public StringVar.

    Translate only known UI enums. Asset pickers must use the ordinary widgets.
    """
    def __init__(self, parent, *, textvariable, values, labeler=_, **kwargs):
        self.canonical = textvariable
        self.keys = tuple(values)
        self.labels = tuple(labeler(value) for value in self.keys)
        self.display = tk.StringVar(master=parent)
        super().__init__(parent, textvariable=self.display, values=self.labels, **kwargs)
        self._syncing = False
        self._trace = self.canonical.trace_add('write', self._show_canonical)
        # A caller may bind its own selection handler. A variable trace runs
        # before that event and cannot be replaced by the caller's bind().
        self._display_trace = self.display.trace_add('write', self._choose)
        self._show_canonical()

    def _show_canonical(self, *_args):
        value = self.canonical.get()
        index = next((i for i, key in enumerate(self.keys)
                      if key.casefold() == value.casefold()), None)
        self._syncing = True
        try:
            self.display.set(self.labels[index] if index is not None else value)
        finally:
            self._syncing = False

    def _choose(self, *_args):
        if self._syncing:
            return
        index = self.current()
        if index >= 0:
            self.canonical.set(self.keys[index])

    def set(self, value):
        self.canonical.set(value)

    def destroy(self):
        self.canonical.trace_remove('write', self._trace)
        self.display.trace_remove('write', self._display_trace)
        super().destroy()


class LocalizedDialog(simpledialog.Dialog):
    def buttonbox(self):
        box = ttk.Frame(self)
        ttk.Button(box, text=_('OK'), command=self.ok).pack(side='left', padx=5, pady=5)
        ttk.Button(box, text=_('Cancel'), command=self.cancel).pack(side='left', padx=5, pady=5)
        self.bind('<Return>', self.ok)
        self.bind('<Escape>', self.cancel)
        box.pack()
