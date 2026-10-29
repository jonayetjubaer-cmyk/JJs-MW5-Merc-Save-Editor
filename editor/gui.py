"""MW5 Mercs Save Editor -- GUI.

A simple Tkinter desktop editor (No Man's Sky-save-editor style):
load a .sav, edit mechs and pilots in tabs, save (with automatic .bak backup).

Run:  python gui.py
"""
from __future__ import annotations

import json
import os
import random
import queue
import shutil
import sys
import threading
import traceback
import urllib.request
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import i18n
from i18n import tr as _
from localized_widgets import LocalizedCombobox, LocalizedDialog

# Resolve the catalog source (built-in vs an external Scarab folder) BEFORE any
# catalog module is imported -- see catalog_source and issue #18.
import catalog_source
catalog_source.activate()
import scarab_integration
import cantina
from file_safety import ensure_backup, atomic_save

from savefile import SaveFile, SKILLS, CAPPED_SKILLS, MAX_SKILL_CAP


def _resource_path(name: str) -> str:
    """Path to a bundled resource, whether running from source, a PyInstaller
    one-file EXE (sys._MEIPASS), or a Nuitka onefile build (data files sit next
    to __file__ / the executable in the unpacked temp dir)."""
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(meipass)
    candidates.append(os.path.dirname(os.path.abspath(__file__)))
    candidates.append(os.path.dirname(os.path.abspath(sys.argv[0])))
    for base in candidates:
        p = os.path.join(base, name)
        if os.path.exists(p):
            return p
    return os.path.join(candidates[-1], name)
from mech_catalog import LABELED, asset_name, display as mech_display, variant_code, chassis_info
from item_catalog import CATALOG, CATEGORY_INVENTORY, WEAPONS, EQUIPMENT, AMMO
from trait_catalog import (PILOT_TRAITS, MECH_TRAITS,
                           dropdown_values as trait_dropdown_values,
                           resolve as resolve_trait)
import pilot_catalog
from savefile import weapon_class, hardpoint_class, ARMOR_PARTS, REAR_PARTS
from stock_templates import max_armor_caps, stock_types

HARDPOINT_LABEL = {"EH": "Energy", "BH": "Ballistic", "MH": "Missile",
                   "AH": "Anti-Missile", "Melee": "Melee"}
BODY_LOADOUT_COMBO_WIDTH = 16
FIRE_GROUP_LABEL_WIDTH = 40

# Body locations in canonical Mech-Lab order, for grouping the loadout editor.
LOCATION_ORDER = ["Head", "CenterTorso", "LeftTorso", "RightTorso",
                  "LeftArm", "RightArm", "LeftHand", "RightHand",
                  "LeftLeg", "RightLeg"]
LOCATION_LABEL = {"Head": "Head", "CenterTorso": "Center Torso",
                  "LeftTorso": "Left Torso", "RightTorso": "Right Torso",
                  "LeftArm": "Left Arm", "RightArm": "Right Arm",
                  "LeftHand": "Left Hand / Melee",
                  "RightHand": "Right Hand / Melee",
                  "LeftLeg": "Left Leg", "RightLeg": "Right Leg"}

# Detailed weapon-mount names shown as conditional sections inside each
# composite arm panel.  Equipment is only serialized at the broad LeftArm /
# RightArm level, so it gets an honest generic section rather than an invented
# upper-arm / forearm assignment.
ARM_PREFIX_SECTION = {
    "Clavicle": "Clavicle",
    "Shoulder": "Shoulder",
    "Upperarm": "Upper Arm",
    "Forearm": "Forearm",
    "Lowerarm": "Lower Arm",
    "Arm": "Arm",
    "Hand": "Hand",
}
ARM_SECTION_ORDER = ("Clavicle", "Shoulder", "Upper Arm", "Forearm",
                     "Lower Arm", "Arm", "Hand")
ARM_PANEL_LOCATIONS = ("LeftArm", "RightArm")
ARM_EQUIPMENT_SECTION = "Equipment"

# Paper-doll positions.  Composite arm panels flank the torso; the compact
# hand / melee panels sit directly below them, alongside the legs.
BODY_LOCATION_POS = {
    "Head": (0, 2),
    "LeftArm": (1, 0), "LeftTorso": (1, 1),
    "CenterTorso": (1, 2), "RightTorso": (1, 3),
    "RightArm": (1, 4),
    "LeftHand": (2, 0), "LeftLeg": (2, 1),
    "RightLeg": (2, 3), "RightHand": (2, 4),
}

# weight-class colours for the mech-bay card icons (mid-tone; read on either theme)
CLASS_ICON = {"Light": "#2f7fd0", "Medium": "#22b083",
              "Heavy": "#d68a2a", "Assault": "#e2683b"}
# per-theme weight-class badge (bg, fg)
CLASS_BADGE_LIGHT = {"Light": ("#e6f1fb", "#0c447c"), "Medium": ("#e1f5ee", "#085041"),
                     "Heavy": ("#faeeda", "#633806"), "Assault": ("#faece7", "#712b13")}
CLASS_BADGE_DARK = {"Light": ("#21384f", "#9cc6f2"), "Medium": ("#1d3b32", "#82d8bb"),
                    "Heavy": ("#3d2f1a", "#e6b870"), "Assault": ("#3d251c", "#f0a184")}

# ---- theming -------------------------------------------------------------
# Two palettes; the live one is THEME (a mutable dict the card/canvas code
# reads). Light keeps the native ttk look; dark restyles via the 'clam' theme.
PALETTES = {
    "light": {
        "window": "#f0f0f0", "surface": "#ffffff", "surface_alt": "#f3f4f8",
        "border": "#cfcfcf", "border_sel": "#2d6cdf",
        "text": "#1a1a1a", "text_muted": "#666666",
        "badge_bg": "#eeeeee", "badge_fg": "#333333",
        "tree_bg": "#ffffff", "tree_sel": "#cfe0fb", "tree_sel_fg": "#10243f",
        "entry_bg": "#ffffff", "button_bg": "#e1e1e1",
        "class_badge": CLASS_BADGE_LIGHT,
    },
    "dark": {
        "window": "#1e1f22", "surface": "#2a2b2e", "surface_alt": "#232427",
        "border": "#3a3b3f", "border_sel": "#4a8cff",
        "text": "#e6e6e6", "text_muted": "#9a9a9a",
        "badge_bg": "#3a3b3f", "badge_fg": "#dddddd",
        "tree_bg": "#232427", "tree_sel": "#2d4a73", "tree_sel_fg": "#eaf1fb",
        "entry_bg": "#33343a", "button_bg": "#3a3b40",
        "class_badge": CLASS_BADGE_DARK,
    },
}
THEME = dict(PALETTES["light"])  # live palette; mutated by EditorApp._apply_theme


def detect_windows_theme() -> str:
    """'dark' or 'light' from the Windows personalization setting; defaults to
    'light' off-Windows or if the registry key is unavailable."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return "light" if val else "dark"
    except Exception:
        return "light"


_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".jjmw5_save_editor.json")


def load_pref(name, default=None):
    try:
        import json as _json
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            return _json.load(f).get(name, default)
    except Exception:
        return default


def save_pref(name, value):
    try:
        import json as _json
        data = {}
        if os.path.exists(_CONFIG_PATH):
            with open(_CONFIG_PATH, encoding="utf-8") as f:
                data = _json.load(f)
        data[name] = value
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            _json.dump(data, f)
    except Exception:
        pass


def weapon_slot_placement(slot_id: str) -> tuple[str, str | None]:
    """Map one raw weapon hardpoint id to (paper-doll panel, detail section).

    Weapon ids use fine-grained mount names (Forearm, Upperarm, Shoulder,
    Clavicle, etc.), while equipment uses broad LeftArm / RightArm parts.  The
    panel key keeps the paper-doll compact; the section preserves the weapon's
    more precise source location for Body, List and fire-group labels.
    """
    t = slot_id.split("_")
    part = t[0] if t else ""
    side = t[1] if len(t) > 1 else ""
    if part == "Head":
        return "Head", None
    if part == "Torso":
        prefix = {"Left": "Left", "Right": "Right", "Center": "Center"}.get(
            side, side)
        return prefix + "Torso", None
    if part == "Leg":
        prefix = {"Left": "Left", "Right": "Right", "Center": "Center"}.get(
            side, side)
        return prefix + "Leg", None
    if part in ARM_PREFIX_SECTION and side in ("Left", "Right"):
        if hardpoint_class(slot_id) == "Melee":
            return side + "Hand", "Melee / Actuator"
        return side + "Arm", ARM_PREFIX_SECTION[part]
    if part == "Arm":
        prefix = {"Left": "Left", "Right": "Right", "Center": "Center"}.get(
            side, side)
        return prefix + "Arm", None
    return part or "Other", None


def weapon_slot_location(slot_id: str) -> str:
    """Paper-doll panel key for a raw weapon hardpoint id."""
    return weapon_slot_placement(slot_id)[0]


def weapon_slot_region(slot_id: str) -> str | None:
    """Detailed source region retained within a composite arm panel."""
    return weapon_slot_placement(slot_id)[1]


def weapon_slot_location_label(slot_id: str) -> str:
    """Readable side + detailed region label for list/fire-group displays."""
    location, region = weapon_slot_placement(slot_id)
    label = LOCATION_LABEL.get(location, location)
    if region and location in ARM_PANEL_LOCATIONS:
        return f"{label} · {region}"
    return label


def localized_slot_label(slot_id: str) -> str:
    location, region = weapon_slot_placement(slot_id)
    label = _(LOCATION_LABEL.get(location, location))
    return f"{label} · {_(region)}" if region and location in ARM_PANEL_LOCATIONS else label


def _fit_combobox_dropdown(combo: ttk.Combobox, max_chars: int = 60):
    """Widen a ttk combobox's popup so long asset names remain readable."""
    try:
        values = combo["values"]
        width = min(max((len(str(v)) for v in values), default=0) + 2, max_chars)
        width = max(width, int(combo.cget("width")))
        popdown = combo.tk.call("ttk::combobox::PopdownWindow", str(combo))
        combo.tk.call(f"{popdown}.f.l", "configure", "-width", width)
    except (tk.TclError, TypeError, ValueError):
        # Some non-Windows Tk themes use a different private popup layout.
        # The wider visible field still improves those platforms.
        pass


def _readable_combobox(parent, *, width: int, **kwargs) -> ttk.Combobox:
    """Combobox with a compact field and a popup sized for its longest value."""
    combo = LocalizedCombobox(parent, width=width,
                             labeler=lambda value: _("(empty)") if value == "(empty)" else value,
                             **kwargs)
    combo.configure(postcommand=lambda c=combo: _fit_combobox_dropdown(c))
    return combo


APP_VERSION = "1.20.0"

# update check (GitHub is the source of truth; Nexus may lag a release behind)
GITHUB_REPO = "jonayetjubaer-cmyk/JJs-MW5-Merc-Save-Editor"
GITHUB_API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"
NEXUS_URL = "https://www.nexusmods.com/mechwarrior5mercenaries/mods/1466"


def _version_tuple(s: str) -> tuple:
    """'v1.15.0' / '1.15.0' -> (1, 15, 0). Non-numeric parts are ignored so a
    malformed tag can't crash the comparison."""
    nums = []
    for part in s.strip().lstrip("vV").split("."):
        digits = "".join(c for c in part if c.isdigit())
        if digits == "":
            break
        nums.append(int(digits))
    return tuple(nums)


def fetch_latest_version(timeout=6):
    """Return the latest release tag (e.g. 'v1.15.0') from GitHub, or None on
    any error (offline, rate-limited, malformed). Never raises."""
    try:
        req = urllib.request.Request(
            GITHUB_API_LATEST,
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": f"JJsMW5SaveEditor/{APP_VERSION}"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("tag_name") or None
    except Exception:
        return None


DEFAULT_SAVE_DIR = os.path.expandvars(
    r"%LOCALAPPDATA%\MW5Mercs\Saved\SaveGames"
)


class EditorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        i18n.set_language(load_pref("language") or i18n.system_language())
        self.title(f"JJ's MW5 Merc Save Editor  v{APP_VERSION}")
        self.geometry("1040x740")
        self.minsize(820, 600)
        self._set_app_icon()
        self.save: SaveFile | None = None
        self.path: str | None = None
        self._background_results = queue.Queue()
        # item catalog (static defaults; merged with save-referenced items on load)
        self.cat = {"weapon": list(WEAPONS), "equipment": list(EQUIPMENT), "ammo": list(AMMO)}
        # trait catalog (names the loaded save references; filled on open)
        self.traitcat = {"pilot": [], "mech": []}

        # theme: 'system' (follow Windows), 'light' or 'dark'
        self.style = ttk.Style(self)
        self._native_theme = self.style.theme_use()
        self._theme_pref = tk.StringVar(value=load_pref("theme", "system"))
        self._apply_theme(self._theme_pref.get())

        self._build_toolbar()
        self._build_update_banner()

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.mech_tab = ttk.Frame(self.nb)
        self.pilot_tab = ttk.Frame(self.nb)
        self.inv_tab = ttk.Frame(self.nb)
        self.faction_tab = ttk.Frame(self.nb)
        self.cantina_tab = ttk.Frame(self.nb)
        self.nb.add(self.mech_tab, text=_('Mechs'))
        self.nb.add(self.pilot_tab, text=_('Pilots'))
        self.nb.add(self.inv_tab, text=_('Inventory'))
        self.nb.add(self.faction_tab, text=_('Factions'))
        self.nb.add(self.cantina_tab, text=_('Cantina (experimental)'))
        self._build_mech_tab()
        self._build_pilot_tab()
        self._build_inventory_tab()
        self._build_faction_tab()
        self._build_cantina_tab()

        self.status = tk.StringVar(value=_("Open a .sav file to begin."))
        ttk.Label(self, textvariable=self.status, relief="sunken",
                  style="Status.TLabel", anchor="w").pack(fill="x", side="bottom")
        # re-apply now that themed widgets (canvas, cards) exist
        self._apply_theme(self._theme_pref.get())

        # quiet update check on startup (background; silent if offline)
        if load_pref("check_updates", True):
            self._startup_check = self.after(800, lambda: self._check_updates_async(manual=False))
        self._background_poll = self.after(100, self._poll_background_results)

    def destroy(self):
        for pending in (getattr(self, "_background_poll", None),
                        getattr(self, "_startup_check", None)):
            if pending:
                try:
                    self.after_cancel(pending)
                except tk.TclError:
                    pass
        super().destroy()

    def _poll_background_results(self):
        try:
            while True:
                callback, args = self._background_results.get_nowait()
                callback(*args)
        except queue.Empty:
            pass
        finally:
            self._background_poll = self.after(100, self._poll_background_results)

    def report_callback_exception(self, exc, value, tb):
        folder = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "MW5SaveEditor")
        path = os.path.join(folder, "errors.log")
        try:
            os.makedirs(folder, exist_ok=True)
            with open(path, "a", encoding="utf-8") as log:
                log.write(f"\nEditor v{APP_VERSION}\n")
                traceback.print_exception(exc, value, tb, file=log)
        except OSError:
            path = _("Error log could not be written.")
        messagebox.showerror(_('Editor error'), f"{exc.__name__}: {value}\n\n{path}", parent=self)

    def _set_app_icon(self):
        """Set the window / taskbar icon from the bundled app_icon.ico."""
        ico = _resource_path("app_icon.ico")
        if not os.path.exists(ico):
            return
        try:
            self.iconbitmap(ico)            # title bar + taskbar on Windows
        except Exception:
            pass
        try:
            self._icon_img = tk.PhotoImage(file=_resource_path("app_icon.png"))
            self.iconphoto(True, self._icon_img)  # fallback / cross-platform
        except Exception:
            pass

    # -- theming -----------------------------------------------------------
    def _on_theme_change(self, _evt=None):
        pref = self._theme_pref.get().lower()
        self._theme_pref.set(pref)
        save_pref("theme", pref)
        self._apply_theme(pref)

    def _apply_theme(self, pref: str):
        """Apply 'system' / 'light' / 'dark'. Mutates the global THEME palette,
        restyles ttk + the raw-tk widgets, and refreshes the mech cards."""
        mode = detect_windows_theme() if pref == "system" else pref
        if mode not in PALETTES:
            mode = "light"
        THEME.clear()
        THEME.update(PALETTES[mode])
        p = THEME
        st = self.style
        # Light keeps the native ttk theme; dark needs 'clam' (fully colourable).
        st.theme_use("clam" if mode == "dark" else self._native_theme)

        if mode == "dark":
            st.configure(".", background=p["window"], foreground=p["text"],
                         fieldbackground=p["entry_bg"], bordercolor=p["border"])
            st.configure("TFrame", background=p["window"])
            st.configure("TLabel", background=p["window"], foreground=p["text"])
            st.configure("TLabelframe", background=p["window"], bordercolor=p["border"])
            st.configure("TLabelframe.Label", background=p["window"], foreground=p["text"])
            st.configure("TButton", background=p["button_bg"], foreground=p["text"])
            st.map("TButton", background=[("active", p["border"])])
            st.configure("TCheckbutton", background=p["window"], foreground=p["text"])
            st.configure("TRadiobutton", background=p["window"], foreground=p["text"])
            st.map("TCheckbutton", background=[("active", p["window"])])
            st.map("TRadiobutton", background=[("active", p["window"])])
            for w in ("TEntry", "TCombobox", "TSpinbox"):
                st.configure(w, fieldbackground=p["entry_bg"], foreground=p["text"],
                             background=p["button_bg"], arrowcolor=p["text"],
                             insertcolor=p["text"])
            st.map("TCombobox", fieldbackground=[("readonly", p["entry_bg"])],
                   foreground=[("readonly", p["text"])])
            st.configure("TNotebook", background=p["window"], bordercolor=p["border"])
            st.configure("TNotebook.Tab", background=p["surface_alt"], foreground=p["text"])
            st.map("TNotebook.Tab", background=[("selected", p["surface"])],
                   foreground=[("selected", p["text"])])
            st.configure("Treeview", background=p["tree_bg"], fieldbackground=p["tree_bg"],
                         foreground=p["text"])
            st.configure("Treeview.Heading", background=p["button_bg"], foreground=p["text"])
            st.map("Treeview", background=[("selected", p["tree_sel"])],
                   foreground=[("selected", p["tree_sel_fg"])])
            st.configure("TScrollbar", background=p["button_bg"], troughcolor=p["surface_alt"],
                         arrowcolor=p["text"], bordercolor=p["border"])

        st.configure("Status.TLabel", background=p["surface_alt"], foreground=p["text_muted"])
        st.configure("Muted.TLabel", foreground=p["text_muted"],
                     background=p["window"])

        self.configure(bg=p["window"])
        # tk Toplevel dialogs and any raw tk.Frame inherit this default bg.
        self.option_add("*background", p["window"])
        self.option_add("*foreground", p["text"])
        if hasattr(self, "mech_canvas"):
            self.mech_canvas.configure(bg=p["window"])
        if getattr(self, "save", None) is not None:
            self._refresh_mechs()

    # -- toolbar -----------------------------------------------------------
    def _build_toolbar(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=8)
        ttk.Button(bar, text=_('Open…'), command=self.on_open).pack(side="left")
        ttk.Button(bar, text=_('Save'), command=self.on_save).pack(side="left", padx=4)
        ttk.Button(bar, text=_('Save As…'), command=self.on_save_as).pack(side="left")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(bar, text=_('Export…'), command=self.on_export).pack(side="left")
        ttk.Button(bar, text=_('Import…'), command=self.on_import).pack(side="left", padx=4)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(bar, text=_('Check for Updates'),
                   command=lambda: self._check_updates_async(manual=True)).pack(side="left")

        options = ttk.Frame(self)
        options.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(options, text=_("Language (restart):")).pack(side="left", padx=(0, 4))
        self.language_var = tk.StringVar(value=i18n.LANGUAGES[i18n.get_language()])
        self.language_combo = ttk.Combobox(options, width=25, state="readonly",
                                          textvariable=self.language_var,
                                          values=tuple(i18n.LANGUAGES.values()))
        self.language_combo.pack(side="left")
        self.language_combo.bind("<<ComboboxSelected>>", self._on_language_change)

        ttk.Button(options, text=_('Catalogs...'), command=self.on_catalog_source).pack(side="right")
        theme_cb = LocalizedCombobox(options, width=12, state="readonly",
                                textvariable=self._theme_pref,
                                values=("System", "Light", "Dark"),
                                labeler=lambda value: _("Light theme") if value == "Light" else _(value))
        theme_cb.set(self._theme_pref.get().capitalize())
        theme_cb.pack(side="right", padx=(0, 8))
        theme_cb.bind("<<ComboboxSelected>>", self._on_theme_change)
        ttk.Label(options, text=_('Theme:')).pack(side="right", padx=(8, 4))

    def _on_language_change(self, _evt=None):
        code = next((key for key, label in i18n.LANGUAGES.items()
                     if label == self.language_var.get()), None)
        if code is not None:
            save_pref("language", code)
            # Do not rebuild forms or close the app: pending edits must survive.
            self.status.set(i18n.translate_for(code,
                "Language saved. Restart the editor to apply it. Save your changes first."))

    # -- catalog source ----------------------------------------------------
    def on_catalog_source(self):
        """Generate or select mod-aware Scarab catalogs. Applied on restart."""
        active = catalog_source.active_dir()
        configured = catalog_source.configured_dir()
        trusted = catalog_source.builtin_dir()

        dlg = tk.Toplevel(self)
        dlg.title(_('Catalogs and Mods'))
        dlg.transient(self)
        dlg.resizable(False, False)
        frm = ttk.Frame(dlg)
        frm.pack(fill="both", expand=True, padx=12, pady=12)
        frm.columnconfigure(1, weight=1)

        scarab_var = tk.StringVar(value=load_pref("scarab_exe", ""))
        mw5_var = tk.StringVar(value=load_pref("mw5_dir", ""))
        output_var = tk.StringVar(value=load_pref("scarab_output", scarab_integration.DEFAULT_OUTPUT))
        report_var = tk.BooleanVar(value=bool(load_pref("scarab_build_report", False)))
        status_var = tk.StringVar(value="")

        src = _("External Scarab folder") if active else _("Built-in catalogs")
        ttk.Label(frm, text=_('In use now: {p0}', p0=src), font=("", 10, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w")
        detail = active or configured or _("No external catalog folder configured.")
        ttk.Label(frm, text=detail, style="Muted.TLabel", wraplength=560).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(2, 8))
        ttk.Label(
            frm,
            text=(_('Scarab support is experimental. Use Scarab {p0} or newer to generate item_catalog.json.gz, mech_catalog.json.gz, trait_catalog.json.gz, and stock_templates.json.gz from your MW5 install and enabled mods.', p0=scarab_integration.MINIMUM_SCARAB)),
            style="Muted.TLabel",
            wraplength=560,
            justify="left",
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(0, 10))

        def add_row(row, label, var, command, button_text="Browse..."):
            ttk.Label(frm, text=_(label)).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Entry(frm, textvariable=var, width=62).grid(
                row=row, column=1, sticky="ew", padx=(8, 6), pady=3)
            ttk.Button(frm, text=_(button_text), command=command).grid(
                row=row, column=2, sticky="ew", pady=3)

        def choose_scarab():
            p = filedialog.askopenfilename(
                title=_('Select scarab.exe'),
                parent=dlg,
                filetypes=[(_('Scarab executable'), "scarab.exe"), (_('Executable'), "*.exe"), (_('All files'), "*.*")],
            )
            if p:
                scarab_var.set(p)

        def choose_mw5():
            d = filedialog.askdirectory(title=_('Select MW5 game folder'), parent=dlg)
            if d:
                mw5_var.set(d)

        add_row(3, "Scarab exe", scarab_var, choose_scarab)
        add_row(4, "MW5 game folder", mw5_var, choose_mw5)
        ttk.Label(frm, text=_('Output folder')).grid(row=5, column=0, sticky="w", pady=3)
        ttk.Entry(frm, textvariable=output_var, width=62).grid(
            row=5, column=1, sticky="ew", padx=(8, 6), pady=3)
        ttk.Label(frm, text=_('relative to scarab.exe'), style="Muted.TLabel").grid(
            row=5, column=2, sticky="w", pady=3)
        ttk.Checkbutton(frm, text=_('Write catalog_build_report.json'), variable=report_var).grid(
            row=6, column=1, sticky="w", padx=(8, 0), pady=(2, 8))

        ttk.Separator(frm).grid(row=7, column=0, columnspan=3, sticky="ew", pady=(4, 10))

        def save_settings():
            save_pref("scarab_exe", scarab_var.get().strip())
            save_pref("mw5_dir", mw5_var.get().strip())
            save_pref("scarab_output", output_var.get().strip() or scarab_integration.DEFAULT_OUTPUT)
            save_pref("scarab_build_report", bool(report_var.get()))

        def choose_existing():
            d = filedialog.askdirectory(title=_('Select a Scarab catalog folder'), parent=dlg)
            if not d:
                return
            if not catalog_source.is_valid(d):
                return messagebox.showwarning(
                    _('Not a catalog folder'),
                    _("That folder doesn't contain a complete catalog set (item_catalog.json.gz, mech_catalog.json.gz, trait_catalog.json.gz, stock_templates.json.gz). Plain .json catalogs are also accepted."),
                    parent=dlg)
            catalog_source.set_dir(d)
            messagebox.showinfo(_('Catalog folder set'),
                                _('Saved. Restart the editor to load these catalogs.'),
                                parent=dlg)
            dlg.destroy()

        def reset():
            catalog_source.set_dir(None)
            messagebox.showinfo(_('Reverted to built-in'),
                                _('Restart the editor to apply.'), parent=dlg)
            dlg.destroy()

        def open_output():
            try:
                p = scarab_integration.output_dir_for(scarab_var.get(), output_var.get())
            except Exception:
                p = ""
            if p and os.path.isdir(p):
                os.startfile(p)
            else:
                messagebox.showinfo(_('Output folder'), _('The output folder does not exist yet.'), parent=dlg)

        def finish_generate(result):
            generate_btn.configure(state="normal")
            close_btn.configure(state="normal")
            status_var.set(result.message)
            self.status.set(result.message)
            if not result.ok:
                return messagebox.showerror(_('Scarab failed'), result.message, parent=dlg)
            catalog_source.set_dir(result.output_dir)
            messagebox.showinfo(
                _('Catalog generated'),
                _('{p0}\n\nSaved for next launch:\n{p1}', p0=result.message, p1=result.output_dir),
                parent=dlg)

        def generate():
            save_settings()
            if not trusted:
                return messagebox.showerror(
                    _('Built-in catalogs missing'),
                    _('The editor could not find its bundled trusted catalog files.'),
                    parent=dlg)
            generate_btn.configure(state="disabled")
            close_btn.configure(state="disabled")
            status_var.set(_('Running Scarab...'))
            self.status.set(_('Running Scarab catalog generation...'))

            def worker():
                result = scarab_integration.run_scarab(
                    scarab_var.get(),
                    mw5_var.get(),
                    output_var.get(),
                    trusted,
                    build_report=report_var.get(),
                )
                self._background_results.put((finish_generate, (result,)))

            threading.Thread(target=worker, daemon=True).start()

        btns = ttk.Frame(frm)
        btns.grid(row=8, column=0, columnspan=3, sticky="ew")
        generate_btn = ttk.Button(btns, text=_('Generate with Scarab'), command=generate)
        generate_btn.pack(side="left")
        ttk.Button(btns, text=_('Choose Existing...'), command=choose_existing).pack(side="left", padx=6)
        ttk.Button(btns, text=_('Open Output'), command=open_output).pack(side="left")
        ttk.Button(btns, text=_('Reset to Built-in'), command=reset).pack(side="left", padx=6)
        close_btn = ttk.Button(btns, text=_('Close'), command=dlg.destroy)
        close_btn.pack(side="right")

        ttk.Label(frm, textvariable=status_var, style="Muted.TLabel", wraplength=560).grid(
            row=9, column=0, columnspan=3, sticky="w", pady=(8, 0))

    # -- update check ------------------------------------------------------
    def _build_update_banner(self):
        """A dismissible 'new version available' bar, hidden until needed."""
        self._update_bar = tk.Frame(self, bg=THEME["border_sel"])
        self._update_msg = tk.Label(self._update_bar, bg=THEME["border_sel"],
                                    fg="#ffffff", anchor="w", padx=10, pady=5,
                                    font=("", 9, "bold"))
        self._update_msg.pack(side="left", fill="x", expand=True)
        tk.Button(self._update_bar, text="GitHub", relief="flat", bd=0,
                  bg="#ffffff", fg=THEME["border_sel"], padx=8,
                  cursor="hand2", command=lambda: webbrowser.open(GITHUB_RELEASES_URL)
                  ).pack(side="left", padx=(0, 4), pady=4)
        tk.Button(self._update_bar, text="Nexus", relief="flat", bd=0,
                  bg="#ffffff", fg=THEME["border_sel"], padx=8,
                  cursor="hand2", command=lambda: webbrowser.open(NEXUS_URL)
                  ).pack(side="left", padx=(0, 8), pady=4)
        tk.Button(self._update_bar, text="✕", relief="flat", bd=0,
                  bg=THEME["border_sel"], fg="#ffffff", padx=8, cursor="hand2",
                  command=self._update_bar.pack_forget).pack(side="right", padx=4)
        # not packed yet -> stays hidden until an update is found

    def _check_updates_async(self, manual=False):
        if getattr(self, "_update_checking", False):
            return
        self._update_checking = True
        if manual:
            self.status.set(_('Checking for updates…'))

        def worker():
            tag = fetch_latest_version()
            self._background_results.put((self._on_update_result, (tag, manual)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_result(self, tag, manual):
        self._update_checking = False
        if not tag:
            if manual:
                messagebox.showwarning(
                    _('Check for Updates'),
                    _("Couldn't reach GitHub to check for updates.\nCheck your connection, or visit the Releases page directly."))
            return
        if _version_tuple(tag) > _version_tuple(APP_VERSION):
            self._update_msg.configure(
                text=_('A new version ({p0}) is available — you have v{p1}.', p0=tag, p1=APP_VERSION))
            self._update_bar.pack(fill="x", before=self.nb)
            self.status.set(_("Update available: {p0}. You're on v{p1}.", p0=tag, p1=APP_VERSION))
        else:
            self.status.set(_("You're up to date (v{p0}).", p0=APP_VERSION))
            if manual:
                messagebox.showinfo(
                    _('Check for Updates'),
                    _("You're running the latest version (v{p0}).", p0=APP_VERSION))

    # -- mech tab ----------------------------------------------------------
    def _build_mech_tab(self):
        mwrap = ttk.Frame(self.mech_tab)
        mwrap.pack(side="left", fill="both", expand=True, padx=(0, 4), pady=4)

        self.mech_count_var = tk.StringVar(value="")
        ttk.Label(mwrap, textvariable=self.mech_count_var).pack(anchor="w", pady=(0, 2))

        # filter: show all mechs, only the active bay, or only cold storage
        flt = ttk.Frame(mwrap)
        flt.pack(anchor="w", pady=(0, 2))
        ttk.Label(flt, text=_('Show:')).pack(side="left")
        self.mech_filter = tk.StringVar(value="all")
        for txt, val in (("All", "all"), ("Active Bay", "active"), ("Cold Storage", "cold")):
            ttk.Radiobutton(flt, text=_(txt), value=val, variable=self.mech_filter,
                            command=self._refresh_mechs).pack(side="left", padx=2)
        ttk.Label(flt, text=_('Sort:')).pack(side="left", padx=(8, 2))
        self.mech_sort_var = tk.StringVar(value="Save order")
        sort = LocalizedCombobox(flt, textvariable=self.mech_sort_var, state="readonly",
                            values=("Save order", "A–Z", "Z–A"), width=20)
        sort.pack(side="left")
        sort.bind("<<ComboboxSelected>>", lambda e: self._refresh_mechs() if self.save else None)

        cwrap = ttk.Frame(mwrap)
        cwrap.pack(fill="both", expand=True)
        self.mech_canvas = tk.Canvas(cwrap, highlightthickness=0, width=320)
        msb = ttk.Scrollbar(cwrap, orient="vertical", command=self.mech_canvas.yview)
        self.mech_canvas.configure(yscrollcommand=msb.set)
        msb.pack(side="right", fill="y")
        self.mech_canvas.pack(side="left", fill="both", expand=True)
        self.mech_cards = ttk.Frame(self.mech_canvas)
        self._mc_win = self.mech_canvas.create_window((0, 0), window=self.mech_cards, anchor="nw")
        self.mech_cards.bind("<Configure>",
                             lambda e: self.mech_canvas.configure(scrollregion=self.mech_canvas.bbox("all")))
        self.mech_canvas.bind("<Configure>",
                              lambda e: self.mech_canvas.itemconfigure(self._mc_win, width=e.width))
        self.mech_canvas.bind("<Enter>", lambda e: self._bind_mech_wheel(True))
        self.mech_canvas.bind("<Leave>", lambda e: self._bind_mech_wheel(False))
        self._mech_objs = []       # Mech per card, in display order
        self._mech_card_frames = []
        self._sel_mech = None      # selected index into _mech_objs

        side = ttk.Frame(self.mech_tab)
        side.pack(side="left", fill="y", pady=4)
        ttk.Button(side, text=_('Add Mech…'), command=self.on_add_mech).pack(fill="x", pady=2)
        ttk.Button(side, text=_('Edit Loadout…'), command=self.on_edit_loadout).pack(fill="x", pady=2)
        ttk.Button(side, text=_('Set Hardpoints…'), command=self.on_set_hardpoints).pack(fill="x", pady=2)
        ttk.Button(side, text=_('Change Chassis…'), command=self.on_change_chassis).pack(fill="x", pady=2)
        ttk.Button(side, text=_('Repair (full armor)'), command=self.on_repair).pack(fill="x", pady=2)
        ttk.Button(side, text=_('Repair ALL Mechs'), command=self.on_repair_all).pack(fill="x", pady=2)
        ttk.Button(side, text=_('Reset to Stock'), command=self.on_reset_to_stock).pack(fill="x", pady=2)
        ttk.Button(side, text=_('Export Loadout…'), command=self.on_export_loadout).pack(fill="x", pady=2)
        ttk.Button(side, text=_('Import Loadout…'), command=self.on_import_loadout).pack(fill="x", pady=2)
        ttk.Button(side, text=_('Remove'), command=self.on_remove_mech).pack(fill="x", pady=2)

    # -- mech-bay cards ----------------------------------------------------
    def _bind_mech_wheel(self, on):
        seqs = ("<MouseWheel>", "<Button-4>", "<Button-5>")
        if on:
            if not getattr(self, "_mech_wheel_bindings", None):
                self._mech_wheel_bindings = {
                    s: self.bind(s, self._mech_wheel, add="+") for s in seqs}
        else:
            for s, binding in getattr(self, "_mech_wheel_bindings", {}).items():
                self.unbind(s, binding)
            self._mech_wheel_bindings = {}

    def _mech_wheel(self, e):
        if not str(e.widget).startswith(str(self.mech_canvas)):
            return
        if e.num == 5 or e.delta < 0:
            self.mech_canvas.yview_scroll(1, "units")
        elif e.num == 4 or e.delta > 0:
            self.mech_canvas.yview_scroll(-1, "units")

    def _draw_mech_glyph(self, c, color):
        """A simple original bipedal-mech silhouette (no game art)."""
        for x0, y0, x1, y1 in ((16, 3, 24, 9), (12, 10, 28, 24), (6, 12, 11, 23),
                               (29, 12, 34, 23), (13, 25, 18, 38), (22, 25, 27, 38)):
            c.create_rectangle(x0, y0, x1, y1, fill=color, outline=color)

    def _make_mech_card(self, idx, m, location):
        tons, cls = chassis_info(m.chassis)
        cold = location == "Cold storage"
        bg = THEME["surface_alt"] if cold else THEME["surface"]
        card = tk.Frame(self.mech_cards, bg=bg, highlightbackground=THEME["border"],
                        highlightcolor=THEME["border"], highlightthickness=1, bd=0)
        card.pack(fill="x", padx=2, pady=3)

        ic = tk.Canvas(card, width=40, height=42, bg=bg, highlightthickness=0)
        ic.pack(side="left", padx=(8, 6), pady=6)
        self._draw_mech_glyph(ic, CLASS_ICON.get(cls, "#888888"))

        badge_bg, badge_fg = THEME["class_badge"].get(
            cls, (THEME["badge_bg"], THEME["badge_fg"]))
        tk.Label(card, text=_(cls or "?").upper(), bg=badge_bg, fg=badge_fg,
                 font=("", 8, "bold"), padx=6, pady=2).pack(side="right", padx=8)

        mid = tk.Frame(card, bg=bg)
        mid.pack(side="left", fill="x", expand=True, pady=6)
        tk.Label(mid, text=mech_display(m.chassis), bg=bg, anchor="w", fg=THEME["text"],
                 justify="left", font=("", 10, "bold")).pack(fill="x")
        tk.Label(mid, text=_('{p0}t · {p1}', p0=tons or '?', p1=_(location)), bg=bg, fg=THEME["text_muted"],
                 anchor="w", font=("", 8)).pack(fill="x")
        # stock structure/armor type, shown only when it's not plain Standard
        # (Endo-Steel / Ferro-Fibrous chassis -- issue #12 data from FiendishDrWu)
        types = stock_types(m.chassis)
        if types is not None:
            armor_t, struct_t = types
            if not (armor_t == "Standard" and struct_t == "Standard"):
                tk.Label(mid, text=f"{struct_t} · {armor_t}", bg=bg,
                         fg=CLASS_ICON.get(cls, THEME["text_muted"]),
                         anchor="w", font=("", 8, "italic")).pack(fill="x")

        for w in (card, ic, mid, *mid.winfo_children()):
            w.bind("<Button-1>", lambda e, i=idx: self._select_mech_card(i))
            w.bind("<Double-Button-1>",
                   lambda e, i=idx: (self._select_mech_card(i), self.on_edit_loadout()))
        self._mech_card_frames.append((idx, card))

    def _select_mech_card(self, idx):
        self._sel_mech = idx
        self._highlight_selected()

    def _highlight_selected(self):
        for idx, card in self._mech_card_frames:
            sel = (idx == self._sel_mech)
            border = THEME["border_sel"] if sel else THEME["border"]
            card.configure(highlightbackground=border, highlightcolor=border,
                           highlightthickness=2 if sel else 1)

    # -- pilot tab ---------------------------------------------------------
    def _build_pilot_tab(self):
        left = ttk.Frame(self.pilot_tab)
        left.pack(side="left", fill="y", padx=(0, 6), pady=4)
        self.pilot_list = tk.Listbox(left, width=22, exportselection=False)
        self.pilot_list.pack(fill="y", expand=True)
        self.pilot_list.bind("<<ListboxSelect>>", self._on_pilot_select)
        pbtns = ttk.Frame(left)
        pbtns.pack(fill="x", pady=4)
        ttk.Label(pbtns, text=_('Saved roster order'), font=("", 9, "bold")).pack(anchor="w")
        for choices in ((("Move Up", -1), ("Move Down", 1)),
                        (("Move to Top", "top"), ("Move to Bottom", "bottom"))):
            row = ttk.Frame(pbtns)
            row.pack(fill="x", pady=1)
            for label, offset in choices:
                ttk.Button(row, text=_(label), command=lambda value=offset: self.on_move_pilot(value)
                           ).pack(side="left", fill="x", expand=True)
        ttk.Label(pbtns, text=_('Player slots stay fixed.\nSave to keep the new order.'),
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Button(pbtns, text=_('Add Pilot…'), command=self.on_add_pilot).pack(fill="x", pady=1)
        ttk.Button(pbtns, text=_('Remove Pilot'), command=self.on_remove_pilot).pack(fill="x", pady=1)

        wrap = ttk.Frame(self.pilot_tab)
        wrap.pack(side="left", fill="both", expand=True, pady=4)
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        self.pilot_canvas = tk.Canvas(wrap, highlightthickness=0)
        self.pilot_canvas.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.pilot_canvas.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb = ttk.Scrollbar(wrap, orient="horizontal", command=self.pilot_canvas.xview)
        hsb.grid(row=1, column=0, sticky="ew")
        self.pilot_canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        form = ttk.Frame(self.pilot_canvas)
        self.pilot_form = form
        window = self.pilot_canvas.create_window((0, 0), window=form, anchor="nw")
        form.bind("<Configure>", lambda e: self.pilot_canvas.configure(
            scrollregion=self.pilot_canvas.bbox("all")))
        self.pilot_canvas.bind("<Configure>", lambda e: self.pilot_canvas.itemconfigure(
            window, width=max(e.width, form.winfo_reqwidth())))

        self.pilot_vars: dict[str, tk.StringVar] = {}

        def row(label, key, r):
            ttk.Label(form, text=_(label)).grid(row=r, column=0, sticky="w", pady=2)
            var = tk.StringVar()
            ttk.Entry(form, textvariable=var, width=24).grid(row=r, column=1, columnspan=2,
                                                             sticky="w", pady=2)
            self.pilot_vars[key] = var

        row(_('Callsign'), "callsign", 0)
        row(_('Full name'), "full_name", 1)
        row(_('Salary (C-Bills)'), "salary", 2)
        ttk.Separator(form, orient="horizontal").grid(row=3, column=0, columnspan=3, sticky="ew", pady=6)
        ttk.Label(form, text=_('Skill'), font=("", 9, "bold")).grid(row=4, column=0, sticky="w")
        ttk.Label(form, text=_('XP'), font=("", 9, "bold")).grid(row=4, column=1, sticky="w")
        ttk.Label(form, text=_('Cap (max 10)'), font=("", 9, "bold")).grid(row=4, column=2, sticky="w")
        for i, sk in enumerate(SKILLS):
            r = 5 + i
            ttk.Label(form, text=_(sk)).grid(row=r, column=0, sticky="w", pady=1)
            xpv = tk.StringVar()
            ttk.Entry(form, textvariable=xpv, width=12).grid(row=r, column=1, sticky="w", pady=1)
            self.pilot_vars[f"skill_{sk}"] = xpv
            capv = tk.StringVar()
            cap_entry = ttk.Entry(form, textvariable=capv, width=6)
            if sk not in CAPPED_SKILLS:   # Gunnery/Piloting don't use the cap system
                cap_entry.configure(state="disabled")
            cap_entry.grid(row=r, column=2, sticky="w", pady=1)
            self.pilot_vars[f"cap_{sk}"] = capv

        br = 5 + len(SKILLS)
        ttk.Button(form, text=_('Apply to Pilot'), command=self.on_apply_pilot).grid(
            row=br, column=0, columnspan=2, sticky="w", pady=8)
        ttk.Button(form, text=_('Max caps (10)'), command=self.on_max_caps).grid(
            row=br, column=2, sticky="w", pady=8)

        # -- traits (apply immediately; no "Apply to Pilot" needed) --
        tr = br + 1
        ttk.Separator(form, orient="horizontal").grid(row=tr, column=0, columnspan=3, sticky="ew", pady=6)
        ttk.Label(form, text=_('Traits'), font=("", 9, "bold")).grid(row=tr + 1, column=0, sticky="w")
        tlf = ttk.Frame(form)
        tlf.grid(row=tr + 2, column=0, columnspan=3, sticky="w")
        self.pilot_trait_list = tk.Listbox(tlf, height=4, width=38, exportselection=False)
        self.pilot_trait_list.pack(side="left", fill="y")
        ptsb = ttk.Scrollbar(tlf, command=self.pilot_trait_list.yview)
        self.pilot_trait_list.configure(yscrollcommand=ptsb.set)
        ptsb.pack(side="left", fill="y")
        taf = ttk.Frame(form)
        taf.grid(row=tr + 3, column=0, columnspan=3, sticky="w", pady=4)
        self.pilot_trait_var = tk.StringVar()
        self.pilot_trait_cb = SearchablePicker(
            taf, textvariable=self.pilot_trait_var, width=44,
            title=_('Choose pilot trait'),
        )
        self.pilot_trait_cb.pack(side="left")
        ttk.Button(taf, text=_('Add'), command=self.on_add_pilot_trait).pack(side="left", padx=4)
        ttk.Button(taf, text=_('Remove'), command=self.on_remove_pilot_trait).pack(side="left")

        # -- appearance (each button applies immediately, like the trait Add button) --
        ar = tr + 4
        ttk.Separator(form, orient="horizontal").grid(row=ar, column=0, columnspan=3, sticky="ew", pady=6)
        ttk.Label(form, text=_('Appearance'), font=("", 9, "bold")).grid(row=ar + 1, column=0, sticky="w")
        sexf = ttk.Frame(form)
        sexf.grid(row=ar + 1, column=1, columnspan=2, sticky="w")
        self.pilot_sex_var = tk.StringVar(value="All")
        sex_cb = LocalizedCombobox(sexf, textvariable=self.pilot_sex_var, width=14, state="readonly",
                              values=pilot_catalog.SEX_FILTERS)
        sex_cb.pack(side="left")
        sex_cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_pilot_looks())
        ttk.Label(sexf, text=_('Filter by sex'),
                  style="Muted.TLabel").pack(side="left", padx=6)

        def look_row(label, row, title, command, button):
            # One compact row (label, picker, button) so it fits like the trait row.
            holder = ttk.Frame(form)
            holder.grid(row=row, column=0, columnspan=3, sticky="w", pady=2)
            ttk.Label(holder, text=_(label), width=14).pack(side="left")
            var = tk.StringVar()
            picker = SearchablePicker(holder, textvariable=var, width=26, title=title)
            picker.pack(side="left")
            ttk.Button(holder, text=_(button), command=command).pack(side="left", padx=4)
            return var, picker

        self.pilot_portrait_var, self.pilot_portrait_cb = look_row(
            _('Portrait'), ar + 2, _('Choose portrait'), self.on_set_pilot_portrait, _('Set'))
        self.pilot_voice_var, self.pilot_voice_cb = look_row(
            _('Voice'), ar + 3, _('Choose dialogue voice'), self.on_set_pilot_voice, _('Set'))
        self.pilot_persona_var, self.pilot_persona_cb = look_row(
            _('Persona'), ar + 4, _('Choose persona'), self.on_apply_persona, _('Apply'))
        self.pilot_bio_caption = tk.StringVar()
        ttk.Label(form, textvariable=self.pilot_bio_caption, style="Muted.TLabel").grid(
            row=ar + 6, column=0, columnspan=3, sticky="w", pady=(6, 0))
        bf = ttk.Frame(form)
        bf.grid(row=ar + 7, column=0, columnspan=3, sticky="w", pady=2)
        ttk.Label(bf, text=_('Bio'), width=14).pack(side="left", anchor="n")
        self.pilot_bio_text = tk.Text(bf, width=34, height=5, wrap="word")
        self.pilot_bio_text.pack(side="left")
        ttk.Button(bf, text=_('Set'), command=self.on_set_pilot_bio).pack(
            side="left", padx=4, anchor="n")
        popts = ttk.Frame(form)
        popts.grid(row=ar + 5, column=0, columnspan=3, sticky="w")
        ttk.Label(popts, text="", width=14).pack(side="left")
        self.pilot_persona_all_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(popts, text=_('Show all personas'), variable=self.pilot_persona_all_var,
                        command=self._refresh_pilot_looks).pack(side="left")
        self.pilot_persona_text_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(popts, text=_('Also set name & bio'),
                        variable=self.pilot_persona_text_var).pack(side="left", padx=8)

    # -- inventory tab -----------------------------------------------------
    def _build_inventory_tab(self):
        top = ttk.Frame(self.inv_tab)
        top.pack(fill="x", padx=4, pady=6)

        # C-Bills
        ttk.Label(top, text=_('C-Bills:')).grid(row=0, column=0, sticky="w")
        self.cbills_var = tk.StringVar(value="0")
        ttk.Entry(top, textvariable=self.cbills_var, width=16).grid(row=0, column=1, sticky="w", padx=4)
        ttk.Button(top, text=_('Set C-Bills'), command=self.on_set_cbills).grid(row=0, column=2, padx=4)
        ttk.Button(top, text=_('Max (2,000,000,000)'),
                   command=lambda: (self.cbills_var.set("2000000000"), self.on_set_cbills())
                   ).grid(row=0, column=3, padx=4)

        ttk.Label(top, text=_('Campaign Date:')).grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.campaign_date_current_var = tk.StringVar(value="N/A")
        ttk.Label(top, textvariable=self.campaign_date_current_var).grid(
            row=1, column=1, sticky="w", padx=4, pady=(6, 0))
        self.campaign_date_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.campaign_date_var, width=12).grid(
            row=1, column=2, sticky="w", padx=4, pady=(6, 0))
        ttk.Button(top, text=_('Set Date'), command=self.on_set_campaign_date).grid(
            row=1, column=3, sticky="w", padx=4, pady=(6, 0))
        ttk.Label(top, text="YYYY.MM.DD", style="Muted.TLabel").grid(
            row=1, column=4, sticky="w", padx=4, pady=(6, 0))

        ttk.Separator(self.inv_tab, orient="horizontal").pack(fill="x", padx=4, pady=2)

        # Add-item row (mirrors the classic editor: Item / Count / Type / Add)
        add = ttk.Frame(self.inv_tab)
        add.pack(fill="x", padx=4, pady=6)
        ttk.Label(add, text=_('Type:')).grid(row=0, column=0, sticky="w")
        self.inv_type_var = tk.StringVar(value="weapon")
        type_cb = LocalizedCombobox(add, textvariable=self.inv_type_var, width=16, state="readonly",
                               values=["weapon", "equipment", "ammo"])
        type_cb.grid(row=0, column=1, padx=4)
        type_cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_item_choices())

        ttk.Label(add, text=_('Item:')).grid(row=0, column=2, sticky="w", padx=(8, 0))
        self.inv_item_var = tk.StringVar()
        self.inv_item_cb = SearchablePicker(add, textvariable=self.inv_item_var,
                                            width=24, title=_('Choose inventory item'))
        self.inv_item_cb.grid(row=0, column=3, padx=4)

        ttk.Label(add, text=_('Count:')).grid(row=0, column=4, sticky="w", padx=(8, 0))
        self.inv_count_var = tk.StringVar(value="1")
        ttk.Spinbox(add, from_=1, to=9999, textvariable=self.inv_count_var, width=6).grid(row=0, column=5, padx=4)

        ttk.Button(add, text=_('Add to Inventory'), command=self.on_add_item).grid(
            row=1, column=2, columnspan=4, sticky="w", padx=8, pady=(4, 0))

        # filter / search row
        filt = ttk.Frame(self.inv_tab)
        filt.pack(fill="x", padx=4, pady=(2, 0))
        ttk.Label(filt, text=_('Filter:')).pack(side="left")
        self.inv_filter_var = tk.StringVar()
        ttk.Entry(filt, textvariable=self.inv_filter_var, width=30).pack(side="left", padx=4)
        self.inv_filter_var.trace_add("write", lambda *a: self._render_inventory())
        ttk.Label(filt, text=_('Sort:')).pack(side="left", padx=(8, 2))
        self.inv_sort_var = tk.StringVar(value="A–Z")
        sort = LocalizedCombobox(filt, textvariable=self.inv_sort_var, state="readonly",
                            values=("A–Z", "Z–A", "Column order"), width=20)
        sort.pack(side="left")
        sort.bind("<<ComboboxSelected>>", self._on_inventory_sort_choice)
        ttk.Label(filt, text=_('(click a column header to sort • shift/ctrl-click rows to multi-select)'),
                  style="Muted.TLabel", wraplength=340).pack(side="left", padx=8)

        # Current inventory list
        iwrap = ttk.Frame(self.inv_tab)
        iwrap.pack(fill="both", expand=True, padx=4, pady=4)
        cols = ("type", "item", "count")
        self.inv_tree = ttk.Treeview(iwrap, columns=cols, show="headings", selectmode="extended")
        for c, txt, w in (("type", "Asset Type", 180), ("item", "Item ID", 300), ("count", "Count", 70)):
            self.inv_tree.heading(c, text=_(txt), command=lambda col=c: self._sort_inventory(col))
            self.inv_tree.column(c, width=w, anchor=("center" if c == "count" else "w"))
        isb = ttk.Scrollbar(iwrap, orient="vertical", command=self.inv_tree.yview)
        self.inv_tree.configure(yscrollcommand=isb.set)
        self.inv_tree.pack(side="left", fill="both", expand=True)
        isb.pack(side="right", fill="y")
        self.inv_tree.bind("<Double-Button-1>", self._on_inv_double_click)
        self._inv_all = []
        self._inv_sort = ("item", False)   # (column, reverse)

        btns = ttk.Frame(self.inv_tab)
        btns.pack(fill="x", padx=4, pady=(0, 6))
        ttk.Button(btns, text=_('Set Count of Selected…'), command=self.on_set_item_count).pack(side="left")
        ttk.Button(btns, text=_('Remove Selected'), command=self.on_remove_item).pack(side="left", padx=4)

        self._refresh_item_choices()

    def _refresh_item_choices(self):
        cat = self.inv_type_var.get()
        names = [n for n, _t in self.cat.get(cat, [])]
        self.inv_item_cb["values"] = names
        if names:
            self.inv_item_var.set(names[0])

    # -- faction tab -------------------------------------------------------
    def _build_faction_tab(self):
        top = ttk.Frame(self.faction_tab)
        top.pack(fill="x", padx=4, pady=6)
        ttk.Label(top, text=_('Company Reputation:')).grid(row=0, column=0, sticky="w")
        self.rep_var = tk.StringVar(value="0")
        ttk.Entry(top, textvariable=self.rep_var, width=12).grid(row=0, column=1, padx=4)
        ttk.Button(top, text=_('Set Reputation'), command=self.on_set_reputation).grid(row=0, column=2, padx=4)

        ttk.Label(self.faction_tab,
                  text=_('Faction standings (typically range -100 hostile … +100 allied). Double-click a row to edit.'),
                  style="Muted.TLabel").pack(anchor="w", padx=6)

        fwrap = ttk.Frame(self.faction_tab)
        fwrap.pack(fill="both", expand=True, padx=6, pady=4)
        cols = ("faction", "standing")
        self.faction_tree = ttk.Treeview(fwrap, columns=cols, show="headings",
                                         selectmode="browse")
        self.faction_tree.heading("faction", text=_('Faction'))
        self.faction_tree.heading("standing", text=_('Standing'))
        self.faction_tree.column("faction", width=240)
        self.faction_tree.column("standing", width=100, anchor="center")
        fsb = ttk.Scrollbar(fwrap, orient="vertical", command=self.faction_tree.yview)
        self.faction_tree.configure(yscrollcommand=fsb.set)
        self.faction_tree.pack(side="left", fill="both", expand=True)
        fsb.pack(side="right", fill="y")
        self.faction_tree.bind("<Double-Button-1>", self._on_faction_double_click)

        btns = ttk.Frame(self.faction_tab)
        btns.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(btns, text=_('Edit Selected…'), command=self.on_edit_standing).pack(side="left")
        ttk.Button(btns, text=_('Set ALL to +100 (allied)'),
                   command=lambda: self.on_set_all_factions(100)).pack(side="left", padx=4)
        ttk.Button(btns, text=_('Set ALL to 0 (neutral)'),
                   command=lambda: self.on_set_all_factions(0)).pack(side="left")

    def _refresh_factions(self):
        self.rep_var.set(str(self.save.reputation))
        self.faction_tree.delete(*self.faction_tree.get_children())
        for i, f in enumerate(self.save.factions()):
            self.faction_tree.insert("", "end", iid=str(i), values=(f.name, f.standing))

    def on_set_reputation(self):
        if not self._guard():
            return
        try:
            self.save.reputation = int(self.rep_var.get())
        except ValueError:
            return messagebox.showerror(_('Invalid'), _('Reputation must be a whole number.'))
        self.status.set(_('Set reputation to {p0}. Remember to Save.', p0=self.save.reputation))

    def _on_faction_double_click(self, event):
        row = self.faction_tree.identify_row(event.y)
        if row:
            self.faction_tree.selection_set(row)
            self.on_edit_standing()
        return "break"

    def on_edit_standing(self):
        if not self._guard():
            return
        sel = self.faction_tree.selection()
        if not sel:
            return self._need_selection()
        idx = int(sel[0])
        f = self.save.factions()[idx]
        new = simpledialog.askinteger(_('Edit standing'), _('Standing for {p0}:', p0=f.name),
                                      initialvalue=f.standing, minvalue=-1000, maxvalue=1000,
                                      parent=self)
        if new is None:
            return
        f.standing = new
        self._refresh_factions()
        self.faction_tree.selection_set(str(idx))
        self.status.set(_('Set {p0} standing to {p1}. Remember to Save.', p0=f.name, p1=new))

    def on_set_all_factions(self, value):
        if not self._guard():
            return
        for f in self.save.factions():
            f.standing = value
        self._refresh_factions()
        self.status.set(_('Set all faction standings to {p0}. Remember to Save.', p0=value))

    def _build_cantina_tab(self):
        self.cantina_info = tk.StringVar(value=_("Open a save to edit Cantina career progress."))
        ttk.Label(self.cantina_tab, textvariable=self.cantina_info, wraplength=650).pack(
            fill="x", padx=8, pady=8)
        ttk.Label(self.cantina_tab, wraplength=650, text=(
            _('Set points/tier also unlocks the corresponding built-in mech upgrades. Missing paths appear at zero and are created only when edited. Lowering points keeps existing upgrades. Jobs, offers and campaign unlocks stay unchanged. Experimental: test with Save As on a copy.'))).pack(fill="x", padx=8)
        ttk.Label(self.cantina_tab, wraplength=650, text=(
            _('Current game assets give Mech Collector tiers 5 and 6 the same 95-point threshold; the effective tier will display as 6. Thresholds and upgrade rewards use the built-in game data; mods changing careers may differ.'))
                  ).pack(fill="x", padx=8)
        self.cantina_tree = ttk.Treeview(self.cantina_tab,
                                        columns=("path", "points", "tier", "record"), show="headings")
        for column, label, width in (("path", "Career path", 260), ("points", "Points", 100),
                                     ("tier", "Tier from points", 130), ("record", "Progress record", 130)):
            self.cantina_tree.heading(column, text=_(label))
            self.cantina_tree.column(column, width=width)
        self.cantina_tree.pack(fill="both", expand=True, padx=8, pady=8)
        actions = ttk.Frame(self.cantina_tab)
        actions.pack(fill="x", padx=8, pady=8)
        self._cantina_buttons = []
        for label, command in (("Set tier…", lambda: self._edit_cantina(True)),
                               ("Set points…", lambda: self._edit_cantina(False)),
                               ("Max all paths…", self._max_cantina),
                               ("Sync upgrade unlocks…", self._sync_cantina_unlocks)):
            button = ttk.Button(actions, text=_(label), command=command, state="disabled")
            button.pack(side="left", padx=(0, 6))
            self._cantina_buttons.append(button)
        self._cantina_paths = []

    def _refresh_cantina(self):
        self.cantina_tree.delete(*self.cantina_tree.get_children())
        try:
            self._cantina_paths = cantina.paths(self.save) if self.save else []
            info = ("Cantina paths. Not-started paths remain unchanged until you edit them."
                    if self._cantina_paths else
                    "This save has no supported Cantina career model.")
        except ValueError as exc:
            self._cantina_paths = []
            info = str(exc)
        self.cantina_info.set(_(info))
        for i, path in enumerate(self._cantina_paths):
            self.cantina_tree.insert("", "end", iid=str(i),
                                     values=(_(path.label), path.points,
                                             path.tier if path.tier is not None else _("Unknown"),
                                             _("Saved") if path.progress is not None else _("Not started")))
        for button in self._cantina_buttons:
            button.configure(state="normal" if self._cantina_paths else "disabled")

    def _edit_cantina(self, by_tier):
        selection = self.cantina_tree.selection()
        if not selection:
            return self._need_selection()
        idx = int(selection[0])
        path = self._cantina_paths[idx]
        if by_tier and path.tier is None:
            return messagebox.showinfo(_('Unknown thresholds'), _('Use Set points for this mod-added path.'), parent=self)
        value = simpledialog.askinteger(_('Cantina progress'),
                                        _("{p0}: {p1}", p0=_(path.label),
                                          p1=_("tier (0–10)") if by_tier else _("points")),
                                        initialvalue=path.tier if by_tier else path.points,
                                        minvalue=0, maxvalue=10 if by_tier else 2147483647, parent=self)
        if value is None:
            return
        try:
            if by_tier:
                path.set_tier(value)
            else:
                path.set_points(value)
        except ValueError as exc:
            return messagebox.showerror(_('Cantina edit not applied'), str(exc), parent=self)
        self._refresh_cantina()
        selected = next(i for i, current in enumerate(self._cantina_paths) if current.asset == path.asset)
        self.cantina_tree.selection_set(str(selected))
        self.status.set(_('{p0}: {p1} points, tier {p2}. Save As a test copy.', p0=path.label, p1=path.points, p2=path.tier))

    def _max_cantina(self):
        if not self._cantina_paths:
            return
        if not messagebox.askyesno(_('Experimental Cantina edit'),
                _('Max all five built-in paths and unlock their mech upgrades?\nMissing path records will be created. Existing upgrades and mod paths are kept.\nJobs and reward-claim records stay unchanged. Test with Save As on a copy.'), parent=self):
            return
        try:
            count = cantina.max_paths(self._cantina_paths)
        except ValueError as exc:
            return messagebox.showerror(_('Cantina edit not applied'), str(exc), parent=self)
        self._refresh_cantina()
        self.status.set(_('Maxed {p0} Cantina paths and synced upgrade unlocks. Save As a test copy.', p0=count))

    def _sync_cantina_unlocks(self):
        if not self._cantina_paths:
            return
        if not messagebox.askyesno(_('Sync Cantina upgrades'),
                _('Add missing built-in mech-upgrade unlocks for the current path points?\nPoints and existing upgrades are kept. Test with Save As on a copy.'), parent=self):
            return
        try:
            count = cantina.sync_unlocks(self.save)
        except ValueError as exc:
            return messagebox.showerror(_('Cantina edit not applied'), str(exc), parent=self)
        self.status.set(_('Added {p0} missing Cantina upgrade unlocks. Save As a test copy.', p0=count))

    def _build_item_catalog(self):
        """Merge the built-in item lists with everything the loaded save
        references, so rare/DLC gear the player has encountered is selectable.
        Save-referenced names win on type (they're the ground truth)."""
        ref = self.save.referenced_items() if self.save else {}
        cat = {}
        for key, static in (("weapon", WEAPONS), ("equipment", EQUIPMENT), ("ammo", AMMO)):
            seen = {}
            for n, t in list(static):
                seen[n] = t
            for n, t in ref.get(key, []):
                seen[n] = t   # save-referenced overrides any guessed type
            cat[key] = sorted(seen.items())
        self.cat = cat
        try:
            self.traitcat = self.save.referenced_traits()
        except Exception:
            self.traitcat = {"pilot": [], "mech": []}

    # -- file ops ----------------------------------------------------------
    def on_open(self):
        initial = DEFAULT_SAVE_DIR if os.path.isdir(DEFAULT_SAVE_DIR) else None
        path = filedialog.askopenfilename(
            title=_('Open MW5 save'), initialdir=initial,
            filetypes=[(_('MW5 save'), "*.sav"), (_('All files'), "*.*")])
        if not path:
            return
        try:
            self.save = SaveFile.load(path)
            self.path = path
            try:
                ensure_backup(path)
                backup_status = "Backup: " + os.path.basename(path) + ".bak"
            except OSError as exc:
                backup_status = f"Backup unavailable: {exc}"
            self._build_item_catalog()
            self._refresh_mechs()
            self._refresh_pilots()
            self._refresh_inventory()
            self._refresh_factions()
            self._refresh_cantina()
            self.status.set(_('Loaded {p0} — {p1} mechs, {p2} pilots, {p3:,} C-Bills. {p4}', p0=os.path.basename(path), p1=len(self.save.mechs()), p2=len(self.save.pilots()), p3=self.save.cbills, p4=backup_status))
        except Exception as e:
            self._error(_('Failed to open save'), e)

    def on_save(self):
        if not self._guard():
            return
        self._write(self.path, backup=True)

    def on_save_as(self):
        if not self._guard():
            return
        path = filedialog.asksaveasfilename(
            title=_('Save As'), defaultextension=".sav",
            initialdir=os.path.dirname(self.path) if self.path else None,
            filetypes=[(_('MW5 save'), "*.sav"), (_('All files'), "*.*")])
        if path:
            self._write(path, backup=True)

    def _write(self, path, backup):
        try:
            if backup and os.path.exists(path):
                ensure_backup(path)
            atomic_save(self.save, path)
            self.path = path
            self.status.set(_('Saved {p0}', p0=os.path.basename(path))
                            + (_('  (backup: .bak)') if os.path.exists(path + ".bak") else ""))
            messagebox.showinfo(_('Saved'), _('Wrote {p0} successfully.', p0=os.path.basename(path)))
        except Exception as e:
            self._error(_('Failed to save'), e)

    # -- export / import ---------------------------------------------------
    def on_export(self):
        if not self._guard():
            return
        cats = CategoryDialog(
            self, _('Export to file'),
            _('Choose what to export to a portable .mw5export file\n(you can import it into another save later):')).result
        if cats is None:
            return
        path = filedialog.asksaveasfilename(
            title=_('Export to…'), defaultextension=".mw5export",
            initialfile="my-mechs.mw5export",
            filetypes=[(_('MW5 export'), "*.mw5export"), (_('All files'), "*.*")])
        if not path:
            return
        try:
            s = self.save.export_to(path, **cats)
            self.status.set(_('Exported {p0} mechs, {p1} pilots, {p2} items.', p0=s['mechs'], p1=s['pilots'], p2=s['weapons'] + s['equipment']))
            messagebox.showinfo(_('Exported'),
                                _('Exported to {p0}:\n\n  {p1} mechs\n  {p2} pilots\n  {p3} inventory items', p0=os.path.basename(path), p1=s['mechs'], p2=s['pilots'], p3=s['weapons'] + s['equipment']))
        except Exception as e:
            self._error(_('Export failed'), e)

    def on_import(self):
        if not self._guard():
            return
        path = filedialog.askopenfilename(
            title=_('Import from…'),
            filetypes=[(_('MW5 export'), "*.mw5export"), (_('All files'), "*.*")])
        if not path:
            return
        cats = CategoryDialog(
            self, _('Import into this save'),
            _("Choose what to ADD from the file into the currently open save.\nMechs and pilots are added with fresh IDs (they don't replace\nwhat's here). Save afterwards to keep the changes.")).result
        if cats is None:
            return
        try:
            s = self.save.import_from(path, **cats)
            self._refresh_mechs()
            self._refresh_pilots()
            self._refresh_inventory()
            self._refresh_factions()
            self.status.set(_('Imported {p0} mechs, {p1} pilots, {p2} items. Remember to Save.', p0=s['mechs'], p1=s['pilots'], p2=s['items']))
            messagebox.showinfo(_('Imported'),
                                _('Added from {p0}:\n\n  {p1} mechs\n  {p2} pilots\n  {p3} inventory items\n\nClick Save to write them into your save file.', p0=os.path.basename(path), p1=s['mechs'], p2=s['pilots'], p3=s['items']))
        except Exception as e:
            self._error(_('Import failed'), e)

    # -- mech actions ------------------------------------------------------
    def _mech_list(self):
        """Active-bay mechs followed by cold-storage mechs, in the same order
        the tree shows them. Operations index into this so a selection maps to
        the right mech regardless of which group it's in."""
        return self.save.mechs() + self.save.cold_storage_mechs()

    def _refresh_mechs(self):
        prev = self._sel_mech
        for w in self.mech_cards.winfo_children():
            w.destroy()
        self._mech_card_frames = []
        active = self.save.mechs()
        cold = self.save.cold_storage_mechs()
        self._mech_objs = list(active) + list(cold)
        flt = getattr(self, "mech_filter", None)
        flt = flt.get() if flt is not None else "all"
        shown = []
        indexed = list(enumerate(self._mech_objs))
        order = self.mech_sort_var.get()
        if order != "Save order":
            indexed.sort(key=lambda entry: mech_display(entry[1].chassis).casefold(),
                         reverse=order == "Z–A")
        for idx, m in indexed:
            location = "Active bay" if idx < len(active) else "Cold storage"
            if flt == "active" and location != "Active bay":
                continue
            if flt == "cold" and location != "Cold storage":
                continue
            self._make_mech_card(idx, m, location)
            shown.append(idx)
        if not shown:
            self._sel_mech = None
        elif prev in shown:
            self._sel_mech = prev
        else:
            self._sel_mech = shown[0]
        self._highlight_selected()
        self.mech_canvas.yview_moveto(0)
        self.mech_count_var.set(
            _('Active bay: {p0}    Cold storage: {p1}    (total {p2})', p0=len(active), p1=len(cold), p2=len(active) + len(cold)))

    def _selected_mech_index(self):
        return self._sel_mech

    def _selected_mech(self):
        if self._sel_mech is None:
            return None
        lst = self._mech_list()
        return lst[self._sel_mech] if 0 <= self._sel_mech < len(lst) else None

    def on_add_mech(self):
        if not self._guard():
            return
        chassis = self._pick_chassis(_('Add Mech'))
        if chassis is None:
            return
        to_cold = messagebox.askyesno(
            _('Add to Cold Storage?'),
            _("Add this mech to Cold Storage?\n\nYes — Cold Storage (recommended): always works, even if your active bay is full. Move it to the bay in-game if there's room.\n\nNo — Active Bay: only appears if you have a free bay slot in-game. If your bay is full it won't show up."))
        location = "cold" if to_cold else "active"
        where = _("Cold Storage") if to_cold else _("Active Bay")
        try:
            _guid, status = self.save.add_mech(chassis, location=location)
            self._refresh_mechs()
            label = mech_display(chassis)
            if status == "stock":
                self.status.set(_('Added {p0} to {p1} — full stock loadout (weapons, armor, equipment). Remember to Save.', p0=label, p1=where))
                messagebox.showinfo(
                    _('Mech added'),
                    _('Added a stock {p0} to {p1} with its real factory loadout: correct armor, weapons, weapon groups and equipment for that chassis. Ready to deploy, or tweak it in Edit Loadout / the in-game Mech Lab.', p0=label, p1=where))
            elif status == "exact":
                self.status.set(_('Added {p0} to {p1} — exact copy of one you own. Remember to Save.', p0=label, p1=where))
            elif status == "real-layout":
                self.status.set(_('Added {p0} to {p1} with its real hardpoints (empty). Fit weapons in Edit Loadout. Remember to Save.', p0=label, p1=where))
                messagebox.showinfo(
                    _('Mech added'),
                    _("Added a {p0} to {p1}. Your save had a real {p2} loadout on record, so it got that chassis's correct (empty) hardpoints.\n\nUse Edit Loadout to fit weapons and set groups — no Mech Lab needed.", p0=label, p1=where, p2=label))
            else:
                self.status.set(_('Added {p0} to {p1} (approximate — set hardpoints / refit in Mech Lab). Remember to Save.', p0=label, p1=where))
                messagebox.showinfo(
                    _('Approximate mech added'),
                    _('Added a {p0} to {p1}. You don\'t own one and your save has no {p2} loadout to copy, so it\'s an approximate clone with its weapons stripped.\n\nEither refit it in the in-game Mech Lab, or use "Set Hardpoints…" to borrow a layout, then Edit Loadout. (A different-chassis mech can\'t be built perfectly from save data alone.)', p0=label, p1=where, p2=label))
        except Exception as e:
            self._error(_('Failed to add mech'), e)

    def on_edit_loadout(self):
        if not self._guard():
            return
        idx = self._selected_mech_index()
        if idx is None:
            return self._need_selection()
        mech = self._selected_mech()
        if not mech.weapon_slots():
            if not self._apply_layout_dialog(mech, idx, empty=True):
                return
            mech = self._selected_mech()   # re-read with the new hardpoints
        LoadoutDialog(self, mech, catalog=self.cat, save=self.save,
                      trait_names=trait_dropdown_values(
                          self.traitcat.get("mech", []), MECH_TRAITS),
                      on_apply=lambda: (self._refresh_mechs(),
                      self.status.set(_('Loadout updated for mech #{p0}. Remember to Save.', p0=idx))))

    def on_set_hardpoints(self):
        if not self._guard():
            return
        idx = self._selected_mech_index()
        if idx is None:
            return self._need_selection()
        mech = self._selected_mech()
        self._apply_layout_dialog(mech, idx, empty=False)

    def _apply_layout_dialog(self, mech, idx, empty) -> bool:
        """Apply a real hardpoint layout (harvested from anywhere in the save)
        to a mech. The same-chassis layout is correct; others are 'borrowed'
        (the hardpoints belong to that chassis). Returns True if applied."""
        layouts = self.save.chassis_layouts()
        if not layouts:
            messagebox.showinfo(_('No layouts'),
                _("Your save doesn't contain any mech loadout to copy hardpoints from."))
            return False
        want = mech.chassis if mech.chassis.endswith("_MDA") else mech.chassis + "_MDA"
        items = sorted(layouts.items(), key=lambda kv: (kv[0] != want, kv[0]))
        labels = []
        for ch, (iw, _wg, _cfg) in items:
            n = len(iw.elements) if iw is not None else 0
            tag = _("this chassis (correct)") if ch == want else _("borrowed layout")
            labels.append(_("{p0} · {p1} hardpoints ({p2})", p0=mech_display(ch), p1=n, p2=tag))
        intro = (_("{p0} has no hardpoints yet.\n", p0=mech_display(mech.chassis))
                 if empty else _("Replace {p0}'s hardpoints.\n", p0=mech_display(mech.chassis)))
        pick = ChoiceDialog(
            self, _('Set hardpoints'),
            intro + _("\nPick a layout to apply, then fit weapons in Edit Loadout.\nSame-chassis layouts are correct; 'borrowed' ones come from another\nchassis and may need an in-game Mech Lab refit to work properly."),
            labels).result
        if pick is None:
            return False
        ch = items[labels.index(pick)][0]
        mech.apply_layout(*layouts[ch])
        mech.flush()
        self._refresh_mechs()
        note = _("correct layout") if ch == want else _("borrowed {p0} layout", p0=mech_display(ch))
        self.status.set(_('Set hardpoints on mech #{p0} ({p1}). Open Edit Loadout to fit weapons. Save when done.', p0=idx, p1=note))
        return True

    def on_change_chassis(self):
        idx = self._selected_mech_index()
        if idx is None:
            return self._need_selection()
        chassis = self._pick_chassis(_('Change Chassis'))
        if chassis is None:
            return
        m = self._selected_mech()
        m.chassis = chassis
        m.flush()
        self._refresh_mechs()
        self.status.set(_('Mech #{p0} chassis -> {p1}. Remember to Save.', p0=idx, p1=chassis))

    def on_repair(self):
        idx = self._selected_mech_index()
        if idx is None:
            return self._need_selection()
        m = self._selected_mech()
        m.repair()
        m.flush()
        self.status.set(_('Mech #{p0} repaired to full armor. Remember to Save.', p0=idx))

    def on_repair_all(self):
        if not self._guard():
            return
        n = 0
        for m in self._mech_list():   # active bay + cold storage
            m.repair()
            m.flush()
            n += 1
        self.status.set(_('Repaired all {p0} mechs (armor restored to installed). Remember to Save.', p0=n))
        messagebox.showinfo(_('Repair All'), _('Restored armor on {p0} mechs.', p0=n))

    def on_reset_to_stock(self):
        if not self._guard():
            return
        idx = self._selected_mech_index()
        if idx is None:
            return self._need_selection()
        m = self._selected_mech()
        label = mech_display(m.chassis)
        if not messagebox.askyesno(
                _('Reset to stock'),
                _("Reset {p0} to its factory-stock loadout?\n\nThis replaces its armor, weapons, weapon groups and equipment with the chassis's stock configuration. Any custom loadout is overwritten.", p0=label)):
            return
        try:
            if self.save.reset_mech_to_stock(m):
                self._refresh_mechs()
                self.status.set(_('Reset {p0} to stock loadout. Remember to Save.', p0=label))
            else:
                messagebox.showinfo(
                    _('No stock data'),
                    _("There's no stock template for {p0} (it may be a modded or non-standard chassis), so it can't be reset to stock.", p0=label))
        except Exception as e:
            self._error(_('Failed to reset to stock'), e)

    def on_export_loadout(self):
        if not self._guard():
            return
        if self._selected_mech_index() is None:
            return self._need_selection()
        m = self._selected_mech()
        path = filedialog.asksaveasfilename(
            title=_('Export loadout'), defaultextension=".mw5loadout",
            initialfile=f"{variant_code(m.chassis)}.mw5loadout",
            filetypes=[(_('MW5 loadout'), "*.mw5loadout"), (_('All files'), "*.*")])
        if not path:
            return
        try:
            self.save.export_mech_loadout(m, path)
            self.status.set(_('Exported {p0} loadout to {p1}.', p0=mech_display(m.chassis), p1=os.path.basename(path)))
        except Exception as e:
            self._error(_('Failed to export loadout'), e)

    def on_import_loadout(self):
        if not self._guard():
            return
        if self._selected_mech_index() is None:
            return self._need_selection()
        m = self._selected_mech()
        path = filedialog.askopenfilename(
            title=_('Import loadout'),
            filetypes=[(_('MW5 loadout'), "*.mw5loadout"), (_('All files'), "*.*")])
        if not path:
            return
        if not messagebox.askyesno(
                _('Import loadout'),
                _('Apply this loadout to {p0}?\n\nThis overwrites its current weapons, equipment and armor. Loadouts are meant for the same chassis.', p0=mech_display(m.chassis))):
            return
        try:
            src = self.save.import_mech_loadout(m, path)
            self._refresh_mechs()
            if src and variant_code(src) != variant_code(m.chassis):
                messagebox.showwarning(
                    _('Different chassis'),
                    _('That loadout was exported from {p0}, but you applied it to {p1}. The hardpoints may not match — check it in Edit Loadout or the in-game Mech Lab.', p0=mech_display(src), p1=mech_display(m.chassis)))
            self.status.set(_('Imported loadout onto {p0}. Remember to Save.', p0=mech_display(m.chassis)))
        except Exception as e:
            self._error(_('Failed to import loadout'), e)

    def on_remove_mech(self):
        idx = self._selected_mech_index()
        if idx is None:
            return self._need_selection()
        m = self._selected_mech()
        if not messagebox.askyesno(_('Remove mech'),
                                   _('Remove mech #{p0} ({p1})?', p0=idx, p1=m.chassis)):
            return
        self.save.remove_mech(m.guid)
        self._refresh_mechs()
        self.status.set(_('Removed mech #{p0}. Remember to Save.', p0=idx))

    def _pick_chassis(self, title):
        variant = ChassisDialog(self, title).result
        return asset_name(variant) if variant else None

    # -- pilot actions -----------------------------------------------------
    def _refresh_pilots(self, selected=None, reload_form=True):
        previous = self._selected_pilot_index() if selected is None else selected
        self.pilot_list.delete(0, "end")
        pilots = self.save.pilots()
        for p in pilots:
            self.pilot_list.insert("end", p.callsign or p.full_name or "(pilot)")
        if pilots:
            idx = min(previous if previous is not None else 0, len(pilots) - 1)
            self.pilot_list.selection_set(idx)
            self.pilot_list.activate(idx)
            self.pilot_list.see(idx)
            if reload_form:
                self._load_pilot_form()

    def _on_pilot_select(self, event=None):
        idx = self._selected_pilot_index()
        if self.save is None or idx is None:
            return
        # A reorder can generate a selection event for the same pilot at a
        # different index. Preserve its pending fields instead of reloading.
        pilot = self.save.pilots()[idx]
        if pilot.element is not getattr(self, "_loaded_pilot_element", None):
            self._load_pilot_form()

    def on_move_pilot(self, offset):
        if not self._guard():
            return
        idx = self._selected_pilot_index()
        if idx is None:
            return self._need_selection()
        pilots = self.save.pilots()
        if pilots[idx].is_commander:
            self.status.set(_('Player/commander pilots keep their existing roster slots.'))
            return
        if offset == "top":
            offset = -len(pilots)
        elif offset == "bottom":
            offset = len(pilots)
        new_index = self.save.move_pilot(idx, offset)
        if new_index == idx:
            self.status.set(_('Pilot is already at that end of the movable roster.'))
            return
        self._refresh_pilots(selected=new_index, reload_form=False)
        self.status.set(_('Moved pilot to roster position {p0}. Remember to Save.', p0=new_index + 1))

    def _selected_pilot_index(self):
        sel = self.pilot_list.curselection()
        return sel[0] if sel else None

    def _load_pilot_form(self):
        idx = self._selected_pilot_index()
        if idx is None:
            return
        p = self.save.pilots()[idx]
        self._load_pilot_stats(p)
        self._load_pilot_look(p)
        self._load_pilot_bio(p)
        self._refresh_pilot_looks()
        self._refresh_pilot_traits(p)
        self._loaded_pilot_element = p.element

    # The sections below reload only their own widgets, so a button that
    # changes one group of fields never discards pending edits in the others.
    def _load_pilot_stats(self, p):
        """Name, salary, skill XP and caps -- the 'Apply to Pilot' group."""
        self.pilot_vars["callsign"].set(p.callsign)
        self.pilot_vars["full_name"].set(p.full_name)
        self.pilot_vars["salary"].set(str(p.salary))
        for sk in SKILLS:
            self.pilot_vars[f"skill_{sk}"].set(str(p.skill(sk)))
            self.pilot_vars[f"cap_{sk}"].set(str(p.skill_cap(sk)))

    def _load_pilot_names(self, p):
        """Just the callsign and full-name fields."""
        self.pilot_vars["callsign"].set(p.callsign)
        self.pilot_vars["full_name"].set(p.full_name)

    def _load_pilot_look(self, p):
        self.pilot_portrait_var.set(pilot_catalog.portrait_display(p.portrait))
        self.pilot_voice_var.set(pilot_catalog.voice_display(p.voice))

    def _load_pilot_bio(self, p):
        self.pilot_bio_text.delete("1.0", "end")
        self.pilot_bio_text.insert("1.0", p.bio)
        self.pilot_bio_caption.set(
            _('Current bio. Edit it, then click Set.') if p.bio
            else _('This pilot has no bio. Type one, then click Set.'))

    def _update_pilot_list_label(self, idx, p):
        """Refresh one roster entry's text without touching the form."""
        self.pilot_list.delete(idx)
        self.pilot_list.insert(idx, p.callsign or p.full_name or "(pilot)")
        self.pilot_list.selection_set(idx)

    def _refresh_pilot_looks(self):
        """Portrait / voice / persona choices: the catalog plus whatever the
        loaded save already uses (so modded or unknown assets stay selectable)."""
        pilots = self.save.pilots() if self.save else []
        sex = self.pilot_sex_var.get()
        self.pilot_portrait_cb["values"] = [
            pilot_catalog.portrait_display(name) for name in pilot_catalog.asset_choices(
                [p.portrait for p in pilots], pilot_catalog.PORTRAITS,
                pilot_catalog.portrait_sex, sex)]
        self.pilot_voice_cb["values"] = [
            pilot_catalog.voice_display(name) for name in pilot_catalog.asset_choices(
                [p.voice for p in pilots], pilot_catalog.VOICES,
                pilot_catalog.voice_sex, sex)]
        self.pilot_persona_cb["values"] = pilot_catalog.persona_choices(
            hireable_only=not self.pilot_persona_all_var.get())

    def _set_pilot_look(self, field, var, label):
        """Write one appearance field to the selected pilot right away."""
        if not self._guard():
            return
        idx = self._selected_pilot_index()
        if idx is None:
            return self._need_selection()
        value = pilot_catalog.resolve_asset(var.get())
        if not value:
            return messagebox.showinfo(_('Pick {p0}', p0=label), _('Choose or type a {p0} asset name.', p0=label))
        p = self.save.pilots()[idx]
        try:
            setattr(p, field, value)
        except ValueError as exc:
            return messagebox.showerror(_('Invalid input'), str(exc))
        show = pilot_catalog.portrait_display if field == "portrait" else pilot_catalog.voice_display
        var.set(show(getattr(p, field)))
        self.status.set(_("Set {p0}'s {p1} to {p2}. Remember to Save.", p0=p.callsign, p1=label, p2=value))

    def on_set_pilot_portrait(self):
        self._set_pilot_look("portrait", self.pilot_portrait_var, _("Portrait"))

    def on_set_pilot_voice(self):
        self._set_pilot_look("voice", self.pilot_voice_var, _("Voice"))

    def on_set_pilot_bio(self):
        """Write the bio box to the selected pilot (as one text; Bio1/Bio2 cleared)."""
        if not self._guard():
            return
        idx = self._selected_pilot_index()
        if idx is None:
            return self._need_selection()
        p = self.save.pilots()[idx]
        text = self.pilot_bio_text.get("1.0", "end").strip()
        if text != p.bio:
            p.bio = text
        self.status.set(_("Set {p0}'s bio. Remember to Save.", p0=p.callsign))

    def on_apply_persona(self):
        if not self._guard():
            return
        idx = self._selected_pilot_index()
        if idx is None:
            return self._need_selection()
        persona = pilot_catalog.find_persona(self.pilot_persona_var.get())
        if persona is None:
            return messagebox.showinfo(_('Pick persona'), _('Choose a persona from the list.'))
        p = self.save.pilots()[idx]
        try:
            if persona.get("portrait"):
                p.portrait = persona["portrait"]
            if persona.get("voice"):
                p.voice = persona["voice"]
            note = ""
            text_changed = bio_changed = False
            if self.pilot_persona_text_var.get():
                # Generic template personas have no name or bio of their own;
                # keep the pilot's own rather than writing an asset name.
                if pilot_catalog.has_name(persona):
                    p.full_name = pilot_catalog.persona_name(persona)
                    p.callsign = pilot_catalog.persona_callsign(persona)
                    text_changed = True
                else:
                    note = _(" (no name in persona; name kept)")
                parts = pilot_catalog.persona_bio_parts(persona)
                if parts is not None:
                    p.set_bio_parts(*parts)
                    bio_changed = True
                else:
                    note += _(" (no bio in persona; bio kept)")
        except ValueError as exc:
            return messagebox.showerror(_("Can't apply persona"), str(exc))
        # Reload only what the persona wrote; other pending edits stay put.
        self._load_pilot_look(p)
        self._refresh_pilot_looks()
        if text_changed:
            self._load_pilot_names(p)
            self._update_pilot_list_label(idx, p)
        if bio_changed:
            self._load_pilot_bio(p)
        self.status.set(_("Applied persona '{p0}' to pilot #{p1}{p2}. Remember to Save.", p0=persona['asset_name'], p1=idx, p2=note))

    def _refresh_pilot_traits(self, pilot=None):
        if pilot is None:
            idx = self._selected_pilot_index()
            pilot = self.save.pilots()[idx] if (self.save and idx is not None) else None
        self.pilot_trait_list.delete(0, "end")
        if pilot:
            for t in pilot.traits():
                self.pilot_trait_list.insert("end", t)
        self.pilot_trait_cb["values"] = trait_dropdown_values(
            self.traitcat.get("pilot", []), PILOT_TRAITS)

    def on_add_pilot_trait(self):
        if not self._guard():
            return
        idx = self._selected_pilot_index()
        if idx is None:
            return self._need_selection()
        name = resolve_trait(self.pilot_trait_var.get())
        if not name:
            return messagebox.showinfo(_('Pick trait'), _('Choose or type a pilot trait asset name.'))
        p = self.save.pilots()[idx]
        try:
            if self.save.add_pilot_trait(p, name):
                self._refresh_pilot_traits(p)
                self.status.set(_("Added trait '{p0}' to {p1}. Remember to Save.", p0=name, p1=p.callsign))
            else:
                self.status.set(_("{p0} already has '{p1}'.", p0=p.callsign, p1=name))
        except Exception as e:
            self._error(_('Failed to add trait'), e)

    def on_remove_pilot_trait(self):
        if not self._guard():
            return
        idx = self._selected_pilot_index()
        if idx is None:
            return self._need_selection()
        sel = self.pilot_trait_list.curselection()
        if not sel:
            return self._need_selection()
        name = self.pilot_trait_list.get(sel[0])
        p = self.save.pilots()[idx]
        if self.save.remove_pilot_trait(p, name):
            self._refresh_pilot_traits(p)
            self.status.set(_("Removed trait '{p0}' from {p1}. Remember to Save.", p0=name, p1=p.callsign))

    def on_apply_pilot(self):
        if not self._guard():
            return
        idx = self._selected_pilot_index()
        if idx is None:
            return self._need_selection()
        p = self.save.pilots()[idx]
        try:
            salary = int(self.pilot_vars["salary"].get())
            xp = {sk: int(self.pilot_vars[f"skill_{sk}"].get()) for sk in SKILLS}
            caps = {sk: int(self.pilot_vars[f"cap_{sk}"].get()) for sk in CAPPED_SKILLS}
            if not 0 <= salary <= 2147483647 or any(
                    not 0 <= value <= 2147483647 for value in xp.values()):
                raise ValueError("Salary and XP must be between 0 and 2,147,483,647.")
            if any(not 0 <= value <= MAX_SKILL_CAP for value in caps.values()):
                raise ValueError("Skill caps must be between 0 and 10.")
            p.callsign = self.pilot_vars["callsign"].get()
            p.full_name = self.pilot_vars["full_name"].get()
            p.salary = salary
            for sk in SKILLS:
                p.set_skill(sk, xp[sk])
                if sk in CAPPED_SKILLS:
                    p.set_skill_cap(sk, caps[sk])
            # Reload only this group; a pending portrait/voice/bio edit survives.
            self._load_pilot_stats(p)
            self._update_pilot_list_label(idx, p)
            self.status.set(_('Applied changes to pilot #{p0}. Remember to Save.', p0=idx))
        except ValueError as exc:
            messagebox.showerror(_('Invalid input'), _('Salary, skill XP and caps must be whole numbers.\n{p0}', p0=exc))

    def on_max_caps(self):
        """Fill the cap fields for the selected pilot with the max (10)."""
        if self._selected_pilot_index() is None:
            return self._need_selection()
        for sk in CAPPED_SKILLS:
            self.pilot_vars[f"cap_{sk}"].set(str(MAX_SKILL_CAP))
        self.status.set(_("Caps set to 10 — click 'Apply to Pilot' to save the change."))

    def on_add_pilot(self):
        if not self._guard():
            return
        callsign = simpledialog.askstring(_('Add Pilot'), _('Callsign for the new pilot:'))
        if not callsign:
            return
        randomize = messagebox.askyesno(
            _('Skills'),
            _("Randomize this pilot's skills?\n\nYes = random skill XP (a freshly generated merc)\nNo  = start all skills at 0 (green rookie)"))
        if randomize:
            skills = {sk: random.randint(300, 3500) for sk in SKILLS}
        else:
            skills = {sk: 0 for sk in SKILLS}
        try:
            self.save.add_pilot(callsign, full_name=callsign, skills=skills,
                                salary=10000, hiring_cost=0)
            self._refresh_pilots()
            self.pilot_list.selection_clear(0, "end")
            self.pilot_list.selection_set("end")
            self.pilot_list.see("end")
            self._load_pilot_form()
            self.status.set(_("Added pilot '{p0}'. Tweak skills below if you like, then Save.", p0=callsign))
        except Exception as e:
            self._error(_('Failed to add pilot'), e)

    def on_remove_pilot(self):
        if not self._guard():
            return
        idx = self._selected_pilot_index()
        if idx is None:
            return self._need_selection()
        pilots = self.save.pilots()
        p = pilots[idx]
        # Protect the actual commander (real player slot), not just whoever is
        # first in the roster -- so regular pilots that happen to be listed
        # first can still be removed (issue #17).
        if p.is_commander:
            return messagebox.showwarning(
                _("Can't remove"),
                _("Won't remove your commander ({p0}). The commander is tied to your campaign, and deleting it can corrupt the save. (Back up first and restore the .bak if anything goes wrong.)", p0=p.callsign or 'Player 1'))
        if not messagebox.askyesno(_('Remove pilot'), _("Remove pilot '{p0}'?", p0=p.callsign)):
            return
        self.save.remove_pilot(p.persona_id)
        self._refresh_pilots()
        self.status.set(_("Removed pilot '{p0}'. Remember to Save.", p0=p.callsign))

    # -- inventory actions -------------------------------------------------
    def _refresh_inventory(self):
        self.cbills_var.set(str(self.save.cbills))
        self.campaign_date_current_var.set(self.save.campaign_date_text)
        self.campaign_date_var.set(self.save.campaign_date_text)
        rows = [(it.asset_type, it.asset_name, it.count, "weapon")
                for it in self.save.weapon_inventory()]
        rows += [(it.asset_type, it.asset_name, it.count, "equipment")
                 for it in self.save.equipment_inventory()]
        self._inv_all = rows
        self._render_inventory()

    def _render_inventory(self):
        """Apply the current filter + sort to the master list and repaint."""
        q = self.inv_filter_var.get().strip().lower()
        rows = [r for r in self._inv_all if not q or q in r[0].lower() or q in r[1].lower()]
        col, rev = self._inv_sort
        idx = {"type": 0, "item": 1, "count": 2}[col]
        rows.sort(key=lambda r: r[2] if col == "count" else r[idx].lower(), reverse=rev)
        self.inv_tree.delete(*self.inv_tree.get_children())
        for t, name, count, inv in rows:
            self.inv_tree.insert("", "end", values=(t, name, count), tags=(inv,))

    def _sort_inventory(self, col):
        cur_col, cur_rev = self._inv_sort
        self._inv_sort = (col, (not cur_rev) if col == cur_col else False)
        self.inv_sort_var.set(("Z–A" if self._inv_sort[1] else "A–Z")
                              if col == "item" else "Column order")
        self._render_inventory()

    def _on_inventory_sort_choice(self, event=None):
        order = self.inv_sort_var.get()
        if order != "Column order":
            self._inv_sort = ("item", order == "Z–A")
        self._render_inventory()

    def _on_inv_double_click(self, event):
        if self.inv_tree.identify_row(event.y):
            self.on_set_item_count()

    def on_set_cbills(self):
        if not self._guard():
            return
        try:
            self.save.cbills = int(self.cbills_var.get())
        except ValueError:
            return messagebox.showerror(_('Invalid'), _('C-Bills must be a whole number.'))
        self.status.set(_('Set C-Bills to {p0:,}. Remember to Save.', p0=self.save.cbills))

    def on_set_campaign_date(self):
        if not self._guard():
            return
        try:
            self.save.set_campaign_date_text(self.campaign_date_var.get())
        except ValueError as e:
            return messagebox.showerror(_('Invalid'), str(e))
        self.campaign_date_current_var.set(self.save.campaign_date_text)
        self.campaign_date_var.set(self.save.campaign_date_text)
        self.status.set(_('Set campaign date to {p0}. Remember to Save.', p0=self.save.campaign_date_text))

    def on_add_item(self):
        if not self._guard():
            return
        cat = self.inv_type_var.get()
        name = self.inv_item_var.get().strip()
        if not name:
            return messagebox.showinfo(_('Pick item'), _('Choose or type an item asset name.'))
        try:
            count = int(self.inv_count_var.get())
        except ValueError:
            return messagebox.showerror(_('Invalid'), _('Count must be a whole number.'))
        # resolve asset_type from catalog; fall back by category
        asset_type = None
        for n, t in self.cat.get(cat, []):
            if n == name:
                asset_type = t
                break
        if asset_type is None:
            asset_type = {"weapon": "MWProjectileWeaponDataAsset",
                          "equipment": "MWHeatSinkDataAsset",
                          "ammo": "MWAmmoDataAsset"}[cat]
        inv = CATEGORY_INVENTORY[cat]
        try:
            self.save.add_item(inv, asset_type, name, count)
            self._refresh_inventory()
            self.status.set(_('Added {p0}x {p1}. Remember to Save.', p0=count, p1=name))
        except Exception as e:
            self._error(_('Failed to add item'), e)

    def _selected_inv_rows(self):
        rows = []
        for iid in self.inv_tree.selection():
            vals = self.inv_tree.item(iid, "values")
            tags = self.inv_tree.item(iid, "tags")
            rows.append({"type": vals[0], "name": vals[1], "count": vals[2],
                         "inv": tags[0] if tags else "weapon"})
        return rows

    def on_set_item_count(self):
        if not self._guard():
            return
        rows = self._selected_inv_rows()
        if not rows:
            return self._need_selection()
        title = (_("New count for {p0}:", p0=rows[0]['name']) if len(rows) == 1
                 else _("New count for the {p0} selected items:", p0=len(rows)))
        new = simpledialog.askinteger(_('Set count'), title,
                                      initialvalue=int(rows[0]["count"]), minvalue=0, parent=self)
        if new is None:
            return
        # group target names per inventory so we only scan each list once
        want = {"weapon": set(), "equipment": set()}
        for r in rows:
            want[r["inv"]].add(r["name"])
        for inv, names in want.items():
            if not names:
                continue
            items = self.save.weapon_inventory() if inv == "weapon" else self.save.equipment_inventory()
            for it in items:
                if it.asset_name in names:
                    it.count = new
        self._refresh_inventory()
        self.status.set(_('Set count to {p0} for {p1} item(s). Remember to Save.', p0=new, p1=len(rows)))

    def on_remove_item(self):
        if not self._guard():
            return
        rows = self._selected_inv_rows()
        if not rows:
            return self._need_selection()
        if not messagebox.askyesno(_('Remove items'),
                                   _('Remove {p0} selected item(s) from inventory?', p0=len(rows))):
            return
        for r in rows:
            self.save.remove_item(r["inv"], r["name"])
        self._refresh_inventory()
        self.status.set(_('Removed {p0} item(s). Remember to Save.', p0=len(rows)))

    # -- helpers -----------------------------------------------------------
    def _guard(self):
        if self.save is None:
            messagebox.showwarning(_('No save'), _('Open a .sav file first.'))
            return False
        return True

    def _need_selection(self):
        messagebox.showinfo(_('Select first'), _('Select an item in the list first.'))

    def _error(self, title, exc):
        traceback.print_exc()
        messagebox.showerror(title, f"{type(exc).__name__}: {exc}")
        self.status.set(f"{title}: {exc}")


class LoadoutDialog(tk.Toplevel):
    """Full per-mech loadout editor: weapons (per hardpoint, class-filtered),
    fire groups, and armor."""

    def __init__(self, parent, mech, on_apply=None, catalog=None,
                 save=None, trait_names=None):
        super().__init__(parent)
        self.mech = mech
        self.on_apply = on_apply
        self.save = save
        self.trait_names = trait_names or []
        self.title(_('Edit Loadout — {p0}', p0=mech_display(mech.chassis)))
        self.geometry("1000x660")
        self.transient(parent)

        # item catalog: use the save-merged one if given, else the static lists
        cat = catalog or {"weapon": list(WEAPONS), "equipment": list(EQUIPMENT), "ammo": list(AMMO)}
        weapons = cat.get("weapon", WEAPONS)
        equipment = cat.get("equipment", EQUIPMENT)
        ammo = cat.get("ammo", AMMO)

        # weapon options per hardpoint class (name list), from the catalog
        self._by_class = {"EH": [], "BH": [], "MH": [], "AH": [], "Melee": []}
        for name, atype in weapons:
            cls = weapon_class(name, atype)
            if cls in self._by_class:
                self._by_class[cls].append((name, atype))
        for cls in self._by_class:
            self._by_class[cls].sort()

        # equipment options by slot type
        # Every equipment slot can list every equipment type. Filtering options by
        # slot type used to hide valid gear -- notably jump jets, which on modded
        # (e.g. YAML) mechs sit in general/omni crit slots, not "JumpJet" slots, so
        # they never appeared. The slot label still shows its kind; the game
        # enforces what actually fits.
        self._all_equip = sorted(set(tuple(x) for x in equipment) | set(tuple(x) for x in ammo))

        self.slots = mech.weapon_slots()
        self.eq_slots = mech.equipment_slots()
        # Vars persist for the dialog's lifetime so switching Body/List view keeps
        # in-progress edits (both views bind widgets to these same vars).
        self.slot_widgets = []   # (slot, weapon_var, [group_vars])
        for slot in self.slots:
            wv = tk.StringVar(value="(empty)" if slot.is_empty else slot.weapon_name)
            gv = [tk.BooleanVar(value=(g in slot.groups())) for g in range(1, 7)]
            self.slot_widgets.append((slot, wv, gv))
        self.eq_widgets = []     # (equip_slot, equip_var)
        for slot in self.eq_slots:
            ev = tk.StringVar(value="(empty)" if slot.is_empty else slot.equip_name)
            self.eq_widgets.append((slot, ev))
        self.armor_vars = {}     # location -> StringVar
        self.max_armor = max_armor_caps(mech.chassis) or {}
        self._chain_vars = [tk.BooleanVar(value=v) for v in mech.chain_fire_groups()]
        self.view_mode = tk.StringVar(value=getattr(LoadoutDialog, "_last_mode", "body"))

        self._build()

    def _equip_options(self, slot_type):
        return self._all_equip

    def _weapon_options(self, slot):
        cls = slot.hardpoint_class or "?"
        opts = ["(empty)"] + [n for n, _t in self._by_class.get(cls, [])]
        cur = slot.weapon_name
        if cur not in ("None", "") and cur not in opts:
            opts.insert(1, cur)
        return opts

    def _equip_names(self, slot):
        names = ["(empty)"] + [n for n, _t in self._equip_options(slot.slot_type)]
        cur = slot.equip_name
        if cur not in ("None", "") and cur not in names:
            names.insert(1, cur)
        return names

    # -- UI ---------------------------------------------------------------
    def _build(self):
        # Apply/Cancel pinned to the bottom first, so they stay reachable no
        # matter how tall the loadout content gets.
        btns = ttk.Frame(self)
        btns.pack(side="bottom", fill="x", padx=10, pady=10)
        ttk.Button(btns, text=_('Apply'), command=self._apply).pack(side="right")
        ttk.Button(btns, text=_('Cancel'), command=self.destroy).pack(side="right", padx=6)

        # Everything else lives in ONE vertically scrollable area (scrollbar +
        # mouse wheel), so weapons, equipment, armor and traits are all reachable
        # even on tall mechs / small screens.
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        content = ttk.Frame(canvas)
        cwin = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(cwin, width=e.width))

        # Scope wheel input to this dialog; closing it must not remove the
        # editor's bindings or affect other windows/popups.
        def _wheel(e):
            if e.num == 5 or e.delta < 0:
                canvas.yview_scroll(1, "units")
            elif e.num == 4 or e.delta > 0:
                canvas.yview_scroll(-1, "units")
        self.bind("<MouseWheel>", _wheel)
        self.bind("<Button-4>", _wheel)
        self.bind("<Button-5>", _wheel)

        # view toggle: Body (paper-doll) or List (dense, all hardpoints)
        vt = ttk.Frame(content)
        vt.pack(anchor="w", padx=10, pady=(10, 0))
        ttk.Label(vt, text=_('Loadout view:')).pack(side="left")
        ttk.Radiobutton(vt, text=_('Body'), value="body", variable=self.view_mode,
                        command=self._switch_view).pack(side="left", padx=4)
        ttk.Radiobutton(vt, text=_('List (all hardpoints)'), value="list",
                        variable=self.view_mode, command=self._switch_view).pack(side="left")

        # container rebuilt when the view is switched (vars persist, so do edits)
        self.loadout_frame = ttk.Frame(content)
        self.loadout_frame.pack(fill="x")
        self._render_loadout()

        # armor
        ttk.Separator(content, orient="horizontal").pack(fill="x", padx=10, pady=8)
        ttk.Label(content, text=_('Armor (current / installed / chassis max)'),
                  font=("", 10, "bold")).pack(anchor="w", padx=10)
        ttk.Label(content,
                  text=_('MDA chassis max is a physical location cap; torso max is shared between front and rear armor.'),
                  style="Muted.TLabel").pack(anchor="w", padx=10)
        af = ttk.Frame(content)
        af.pack(fill="x", padx=10, pady=4)
        locs = ARMOR_PARTS + REAR_PARTS
        for i, loc in enumerate(locs):
            row, col = divmod(i, 2)
            cell = ttk.Frame(af)
            cell.grid(row=row, column=col, sticky="w", padx=4, pady=2)
            ttk.Label(cell, text=_(loc), width=17).pack(side="left")
            v = tk.StringVar(value=str(int(self.mech.armor_value(loc))))
            ttk.Entry(cell, textvariable=v, width=6).pack(side="left")
            self.armor_vars[loc] = v

            installed = int(self.mech.armor_value(loc, installed=True))
            cap_key = loc[:-4] if loc in REAR_PARTS else loc
            cap = self.max_armor.get(cap_key)
            detail = _("installed {p0}", p0=installed)
            if cap is not None:
                detail += _(" · max {p0}", p0=int(float(cap)))
                if cap_key in ("CenterTorso", "LeftTorso", "RightTorso"):
                    detail += _(" total F+R")
            ttk.Label(cell, text=detail, width=31, style="Muted.TLabel").pack(
                side="left", padx=(4, 0))

        ttk.Button(content, text=_('Repair armor (= installed)'),
                   command=self._repair_armor).pack(anchor="w", padx=10, pady=2)

        # traits (Cantina-style mech quirks) -- experimental
        if self.save is not None:
            ttk.Separator(content, orient="horizontal").pack(fill="x", padx=10, pady=8)
            ttk.Label(content, text=_('Mech Traits (experimental)'),
                      font=("", 10, "bold")).pack(anchor="w", padx=10)
            ttk.Label(content, text=_('Cantina-style quirks (e.g. Faster Cooling). Untested in-game — back up your save before relying on these.'),
                      foreground="#a00", wraplength=720, justify="left").pack(anchor="w", padx=10)
            tfrm = ttk.Frame(content)
            tfrm.pack(fill="x", padx=10, pady=4)
            self.mtrait_list = tk.Listbox(tfrm, height=3, width=40, exportselection=False)
            self.mtrait_list.pack(side="left", fill="y")
            mtsb = ttk.Scrollbar(tfrm, command=self.mtrait_list.yview)
            self.mtrait_list.configure(yscrollcommand=mtsb.set)
            mtsb.pack(side="left", fill="y")
            actf = ttk.Frame(tfrm)
            actf.pack(side="left", fill="x", padx=8)
            self.mtrait_var = tk.StringVar()
            _readable_combobox(
                actf, textvariable=self.mtrait_var, values=self.trait_names,
                width=44,
            ).pack(anchor="w")
            bf = ttk.Frame(actf)
            bf.pack(anchor="w", pady=4)
            ttk.Button(bf, text=_('Add'), command=self._add_trait).pack(side="left")
            ttk.Button(bf, text=_('Remove'), command=self._remove_trait).pack(side="left", padx=4)
            self._refresh_traits()

    # -- loadout views -----------------------------------------------------
    def _switch_view(self):
        LoadoutDialog._last_mode = self.view_mode.get()
        self._render_loadout()

    def _render_loadout(self):
        for w in self.loadout_frame.winfo_children():
            w.destroy()
        if self.view_mode.get() == "list":
            self._render_list_view()
        else:
            self._render_body_view()

    def _group_by_location(self):
        wloc, eloc = {}, {}
        for sw in self.slot_widgets:
            wloc.setdefault(weapon_slot_location(sw[0].slot_id), []).append(sw)
        for ew in self.eq_widgets:
            eloc.setdefault(ew[0].part_label, []).append(ew)
        return wloc, eloc

    def _weapon_sections(self, sws):
        grouped = {}
        for sw in sws:
            section = weapon_slot_region(sw[0].slot_id) or "Weapons"
            grouped.setdefault(section, []).append(sw)
        order = [section for section in ARM_SECTION_ORDER if section in grouped]
        order += [section for section in grouped if section not in order]
        return [(section, grouped[section]) for section in order]

    def _fill_weapon_rows(self, parent, sws):
        for slot, var, _gvars in sws:
            cls = slot.hardpoint_class or "?"
            row = ttk.Frame(parent)
            row.pack(fill="x", padx=3, pady=1)
            ttk.Label(row, text=_(HARDPOINT_LABEL.get(cls, cls)), width=14, font=("", 8)).pack(side="left")
            _readable_combobox(
                row, textvariable=var, values=self._weapon_options(slot),
                width=BODY_LOADOUT_COMBO_WIDTH, state="readonly",
            ).pack(side="left")

    def _fill_equipment_rows(self, parent, ews):
        for slot, var in ews:
            kind = "Jump Jet" if "JumpJet" in slot.slot_type else "Gear"
            row = ttk.Frame(parent)
            row.pack(fill="x", padx=3, pady=1)
            ttk.Label(row, text=_(kind), width=9, font=("", 8)).pack(side="left")
            _readable_combobox(
                row, textvariable=var, values=self._equip_names(slot),
                width=BODY_LOADOUT_COMBO_WIDTH, state="readonly",
            ).pack(side="left")

    def _fill_panel(self, parent, sws, ews, *, sectioned=False):
        if sectioned:
            for section, section_sws in self._weapon_sections(sws):
                ttk.Label(parent, text=_(section), style="Muted.TLabel",
                          font=("", 8, "bold")).pack(
                              anchor="w", padx=3, pady=(3, 0))
                self._fill_weapon_rows(parent, section_sws)
            if ews:
                ttk.Label(parent, text=_(ARM_EQUIPMENT_SECTION),
                          style="Muted.TLabel", font=("", 8, "bold")).pack(
                              anchor="w", padx=3, pady=(3, 0))
                self._fill_equipment_rows(parent, ews)
        else:
            self._fill_weapon_rows(parent, sws)
            self._fill_equipment_rows(parent, ews)
        if not sws and not ews:
            ttk.Label(parent, text=_('(none)'), style="Muted.TLabel", font=("", 8)).pack(padx=3, pady=2)

    def _render_body_view(self):
        f = self.loadout_frame
        ttk.Label(f, text=_('Loadout — by body location  (pick a weapon/equipment per slot)'),
                  font=("", 10, "bold")).pack(anchor="w", padx=10, pady=(8, 2))
        wloc, eloc = self._group_by_location()
        pd = ttk.Frame(f)
        pd.pack(padx=10, pady=2)
        for loc, (rr, cc) in BODY_LOCATION_POS.items():
            panel = ttk.LabelFrame(pd, text=_(LOCATION_LABEL.get(loc, loc)))
            panel.grid(row=rr, column=cc, padx=3, pady=3, sticky="nsew")
            self._fill_panel(
                panel, wloc.get(loc, []), eloc.get(loc, []),
                sectioned=loc in ARM_PANEL_LOCATIONS,
            )
        # any hardpoints/equipment outside the paper-doll locations (modded mechs)
        others = [l for l in (list(wloc) + list(eloc)) if l not in BODY_LOCATION_POS]
        others = list(dict.fromkeys(others))
        if others:
            op = ttk.LabelFrame(f, text=_('Other hardpoints'))
            op.pack(fill="x", padx=10, pady=(8, 2))
            for loc in others:
                ttk.Label(op, text=_(LOCATION_LABEL.get(loc, loc)),
                          font=("", 9, "bold")).pack(anchor="w", padx=4, pady=(4, 0))
                self._fill_panel(op, wloc.get(loc, []), eloc.get(loc, []))
        self._render_fire_groups(f)

    def _render_fire_groups(self, parent):
        if not self.slot_widgets:
            return
        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=10, pady=8)
        ttk.Label(parent, text=_('Fire groups'), font=("", 10, "bold")).pack(anchor="w", padx=10)
        fgf = ttk.Frame(parent)
        fgf.pack(fill="x", padx=10, pady=2)
        ttk.Label(fgf, text=_('Weapon hardpoint'), width=FIRE_GROUP_LABEL_WIDTH).grid(
            row=0, column=0, sticky="w")
        for g in range(1, 7):
            ttk.Label(fgf, text=str(g), width=3).grid(row=0, column=g)
        for i, (slot, _var, gvars) in enumerate(self.slot_widgets, start=1):
            cls = slot.hardpoint_class or "?"
            ttk.Label(fgf, width=FIRE_GROUP_LABEL_WIDTH, anchor="w",
                      text=f"{localized_slot_label(slot.slot_id)} · "
                           f"{_(HARDPOINT_LABEL.get(cls, cls))}"
                      ).grid(row=i, column=0, sticky="w", pady=1)
            for gi, gv in enumerate(gvars, start=1):
                ttk.Checkbutton(fgf, variable=gv).grid(row=i, column=gi)
        self._render_chain_fire_row(fgf, len(self.slot_widgets) + 1, 0)

    def _render_chain_fire_row(self, grid, row, group_col0):
        """A 'chain fire' toggle per group (1-6): on = weapons in that group fire
        one after another; off = salvo (all at once). group_col0 is the grid
        column just before group 1's column."""
        ttk.Label(grid, text=_('Chain fire (off = salvo)'),
                  width=FIRE_GROUP_LABEL_WIDTH, anchor="w",
                  style="Muted.TLabel").grid(row=row, column=0, sticky="w", pady=(6, 1))
        for gi in range(1, 7):
            ttk.Checkbutton(grid, variable=self._chain_vars[gi - 1]).grid(
                row=row, column=group_col0 + gi)

    def _render_list_view(self):
        """Dense, one-row-per-hardpoint view with inline fire groups. Renders
        every slot (good for heavily-modded mechs with many hardpoints)."""
        f = self.loadout_frame
        ttk.Label(f, text=_('Loadout — all hardpoints'),
                  font=("", 10, "bold")).pack(anchor="w", padx=10, pady=(8, 2))
        grid = ttk.Frame(f)
        grid.pack(fill="x", padx=10)
        ttk.Label(grid, text=_('Hardpoint / Equipment'), width=34).grid(row=0, column=0, sticky="w")
        ttk.Label(grid, text=_('Fitted'), width=24).grid(row=0, column=1, sticky="w")
        for g in range(1, 7):
            ttk.Label(grid, text=str(g), width=3).grid(row=0, column=1 + g)
        wloc, eloc = self._group_by_location()
        ordered = [l for l in LOCATION_ORDER if l in wloc or l in eloc]
        ordered += [l for l in (list(wloc) + list(eloc))
                    if l not in LOCATION_ORDER and l not in ordered]
        ordered = list(dict.fromkeys(ordered))
        r = 1
        for loc in ordered:
            ttk.Label(grid, text=_(LOCATION_LABEL.get(loc, loc)), font=("", 9, "bold")).grid(
                row=r, column=0, columnspan=8, sticky="w", pady=(8, 1))
            r += 1
            sectioned = loc in ARM_PANEL_LOCATIONS
            sws = wloc.get(loc, [])
            weapon_sections = self._weapon_sections(sws) if sectioned else [(None, sws)]
            for section, section_sws in weapon_sections:
                if section is not None:
                    ttk.Label(grid, text=f"    {_(section)}", width=34,
                              style="Muted.TLabel", font=("", 8, "bold")).grid(
                                  row=r, column=0, sticky="w", pady=(3, 1))
                    r += 1
                indent = "        " if sectioned else "    "
                for slot, var, gvars in section_sws:
                    cls = slot.hardpoint_class or "?"
                    ttk.Label(
                        grid, text=f"{indent}{_(HARDPOINT_LABEL.get(cls, cls))}",
                        width=34,
                    ).grid(row=r, column=0, sticky="w", pady=1)
                    _readable_combobox(
                        grid, textvariable=var, values=self._weapon_options(slot),
                        width=36, state="readonly",
                    ).grid(row=r, column=1, sticky="w", padx=2)
                    for gi, gv in enumerate(gvars, start=1):
                        ttk.Checkbutton(grid, variable=gv).grid(row=r, column=1 + gi)
                    r += 1
            ews = eloc.get(loc, [])
            if sectioned and ews:
                ttk.Label(grid, text=f"    {_(ARM_EQUIPMENT_SECTION)}", width=34,
                          style="Muted.TLabel", font=("", 8, "bold")).grid(
                              row=r, column=0, sticky="w", pady=(3, 1))
                r += 1
            for slot, var in eloc.get(loc, []):
                kind = "Jump Jet" if "JumpJet" in slot.slot_type else "Gear"
                indent = "        " if sectioned else "    "
                ttk.Label(grid, text=f"{indent}[{_(kind)}]", width=34).grid(
                    row=r, column=0, sticky="w", pady=1)
                _readable_combobox(
                    grid, textvariable=var, values=self._equip_names(slot),
                    width=36, state="readonly",
                ).grid(row=r, column=1, columnspan=6, sticky="w", padx=2)
                r += 1
        if self.slot_widgets:
            self._render_chain_fire_row(grid, r + 1, 1)   # group cols are 1+gi here

    def _refresh_traits(self):
        self.mtrait_list.delete(0, "end")
        for t in self.mech.traits():
            self.mtrait_list.insert("end", t)

    def _add_trait(self):
        name = resolve_trait(self.mtrait_var.get())
        if not name:
            return messagebox.showinfo(_('Pick trait'), _('Choose or type a mech trait asset name.'))
        try:
            if self.save.add_mech_trait(self.mech, name, flush=False):
                self._refresh_traits()
            else:
                messagebox.showinfo(_('Already installed'), _("This mech already has '{p0}'.", p0=name))
        except Exception as e:
            messagebox.showerror(_('Failed to add trait'), f"{type(e).__name__}: {e}")

    def _remove_trait(self):
        sel = self.mtrait_list.curselection()
        if not sel:
            return messagebox.showinfo(_('Select first'), _('Select a trait to remove.'))
        name = self.mtrait_list.get(sel[0])
        if self.save.remove_mech_trait(self.mech, name, flush=False):
            self._refresh_traits()

    def _repair_armor(self):
        for loc in ARMOR_PARTS + REAR_PARTS:
            self.armor_vars[loc].set(str(int(self.mech.armor_value(loc, installed=True))))

    def _apply(self):
        # weapons + groups
        wname_to_type = {n: t for vlist in self._by_class.values() for n, t in vlist}
        for slot, var, gvars in self.slot_widgets:
            choice = var.get()
            if choice == "(empty)":
                slot.clear()
            elif not slot.is_empty or choice != slot.weapon_name:
                atype = wname_to_type.get(choice)
                if atype is None:
                    atype = slot.weapon_type  # unrecognized current weapon kept as-is
                if atype and atype != "None":
                    slot.set_weapon(atype, choice)
            for g in range(1, 7):
                slot.set_group(g, gvars[g - 1].get())
        # equipment
        ename_to_type = {n: t for n, t in self._all_equip}
        for slot, var in self.eq_widgets:
            choice = var.get()
            if choice == "(empty)":
                slot.clear()
            elif slot.is_empty or choice != slot.equip_name:
                atype = ename_to_type.get(choice, slot.equip_type)
                if atype and atype != "None":
                    slot.set_equipment(atype, choice)
        # armor: current health cannot exceed the installed allocation
        try:
            armor_values = {loc: float(int(v.get())) for loc, v in self.armor_vars.items()}
        except ValueError:
            messagebox.showerror(_('Invalid'), _('Armor values must be whole numbers.'))
            return
        for loc, value in armor_values.items():
            installed = self.mech.armor_value(loc, installed=True)
            if value < 0 or value > installed:
                messagebox.showerror(
                    _('Invalid armor'),
                    _('{p0} current armor must be between 0 and its installed armor ({p1}).', p0=loc, p1=int(installed)))
                return
        for loc, value in armor_values.items():
            self.mech.set_armor(loc, value)
        # chain-fire (per group 1-6)
        for gi, v in enumerate(self._chain_vars, start=1):
            self.mech.set_chain_fire_group(gi, v.get())
        self.mech.flush()
        if self.on_apply:
            self.on_apply()
        self.destroy()


class CategoryDialog(LocalizedDialog):
    """Checkboxes for what to export/import. result = dict of kwargs or None."""
    CATS = [("mechs", "Mechs"), ("pilots", "Pilots"), ("inventory", "Inventory (weapons / equipment / ammo)"),
            ("cbills", "C-Bills"), ("factions", "Factions + reputation")]

    def __init__(self, parent, title, prompt):
        self.prompt = prompt
        self.result = None
        super().__init__(parent, title)

    def body(self, master):
        ttk.Label(master, text=self.prompt, justify="left").pack(padx=10, pady=8, anchor="w")
        self.vars = {}
        for key, label in self.CATS:
            v = tk.BooleanVar(value=True)
            ttk.Checkbutton(master, text=_(label), variable=v).pack(padx=16, pady=1, anchor="w")
            self.vars[key] = v
        return None

    def apply(self):
        self.result = {k: v.get() for k, v in self.vars.items()}


class ChoiceDialog(LocalizedDialog):
    """Simple modal: a prompt + a dropdown of choices. result = chosen string or None."""
    def __init__(self, parent, title, prompt, choices):
        self.prompt = prompt
        self.choices = choices
        self.result = None
        super().__init__(parent, title)

    def body(self, master):
        ttk.Label(master, text=self.prompt, justify="left").pack(padx=10, pady=8, anchor="w")
        self.var = tk.StringVar(value=self.choices[0])
        cb = ttk.Combobox(master, textvariable=self.var, values=self.choices,
                          width=40, state="readonly")
        cb.pack(padx=10, pady=4)
        return cb

    def apply(self):
        self.result = self.var.get()


class ChassisDialog(LocalizedDialog):
    """Searchable mech picker: type to filter the 540+ chassis/variant list,
    double-click or OK to choose. Also accepts a hand-typed variant code."""
    def __init__(self, parent, title):
        self.result = None
        self.labels = [lbl for lbl, _ in LABELED]
        self._lbl_to_variant = dict(LABELED)
        super().__init__(parent, title)

    def body(self, master):
        ttk.Label(master, text=_('Search a mech (name or code), then pick one:')
                  ).pack(padx=8, pady=(8, 2), anchor="w")
        self.search_var = tk.StringVar()
        ent = ttk.Entry(master, textvariable=self.search_var, width=40)
        ent.pack(padx=8, pady=2, fill="x")
        self.search_var.trace_add("write", lambda *a: self._filter())

        frame = ttk.Frame(master)
        frame.pack(padx=8, pady=4, fill="both", expand=True)
        self.lb = tk.Listbox(frame, width=44, height=16, exportselection=False)
        sb = ttk.Scrollbar(frame, command=self.lb.yview)
        self.lb.configure(yscrollcommand=sb.set)
        self.lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.lb.bind("<Double-Button-1>", lambda e: self.ok())

        ttk.Label(master, text=_('(or type an exact variant code above and press OK)'),
                  style="Muted.TLabel").pack(padx=8, pady=(0, 6), anchor="w")
        self._filter()
        return ent

    def _filter(self):
        q = self.search_var.get().strip().lower()
        self.lb.delete(0, "end")
        for lbl in self.labels:
            if q in lbl.lower():
                self.lb.insert("end", lbl)
        if self.lb.size():
            self.lb.selection_set(0)

    def apply(self):
        sel = self.lb.curselection()
        if sel:
            lbl = self.lb.get(sel[0])
            self.result = self._lbl_to_variant.get(lbl, lbl.split()[-1])
        else:
            typed = self.search_var.get().strip()
            self.result = typed or None


class SearchablePicker(ttk.Frame):
    """Editable asset field with an owned, searchable selection window."""
    def __init__(self, parent, *, textvariable, width, title):
        super().__init__(parent)
        self.variable = textvariable
        self.values = ()
        self.title = title
        ttk.Entry(self, textvariable=textvariable, width=width).pack(side="left", fill="x", expand=True)
        ttk.Button(self, text=_('Browse…'), command=self._browse).pack(side="left", padx=(4, 0))

    def __getitem__(self, key):
        return self.values if key == "values" else super().__getitem__(key)

    def __setitem__(self, key, value):
        if key == "values":
            self.values = tuple(value)
        else:
            super().__setitem__(key, value)

    def _browse(self):
        dialog = SearchChoiceDialog(self.winfo_toplevel(), self.title, self.values)
        if dialog.result is not None:
            self.variable.set(dialog.result)


class SearchChoiceDialog(LocalizedDialog):
    def __init__(self, parent, title, values):
        self.values = tuple(values)
        super().__init__(parent, title)

    def body(self, master):
        ttk.Label(master, text=_('Search, select a result, then press OK:')).pack(anchor="w")
        self.query = tk.StringVar()
        entry = ttk.Entry(master, textvariable=self.query, width=48)
        entry.pack(fill="x", pady=4)
        frame = ttk.Frame(master)
        frame.pack(fill="both", expand=True)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.results = tk.Listbox(frame, width=48, height=12, exportselection=False)
        self.results.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(frame, command=self.results.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=self.results.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.results.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.results.bind("<Double-Button-1>", lambda e: self.ok())
        self.query.trace_add("write", lambda *args: self._filter())
        self._filter()
        return entry

    def _filter(self):
        text = self.query.get().strip().casefold()
        self.results.delete(0, "end")
        for value in self.values:
            if text in value.casefold():
                self.results.insert("end", value)
        if self.results.size():
            self.results.selection_set(0)

    def validate(self):
        return bool(self.results.curselection())

    def apply(self):
        self.result = self.results.get(self.results.curselection()[0])


if __name__ == "__main__":
    EditorApp().mainloop()
