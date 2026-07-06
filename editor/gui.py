"""MW5 Mercs Save Editor -- GUI.

A simple Tkinter desktop editor (No Man's Sky-save-editor style):
load a .sav, edit mechs and pilots in tabs, save (with automatic .bak backup).

Run:  python gui.py
"""
from __future__ import annotations

import json
import os
import random
import shutil
import sys
import threading
import traceback
import urllib.request
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

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
from savefile import weapon_class, ARMOR_PARTS, REAR_PARTS
from stock_templates import stock_types

HARDPOINT_LABEL = {"EH": "Energy", "BH": "Ballistic", "MH": "Missile",
                   "AH": "Anti-Missile", "Melee": "Melee"}

# Body locations in canonical Mech-Lab order, for grouping the loadout editor.
LOCATION_ORDER = ["Head", "CenterTorso", "LeftTorso", "RightTorso",
                  "LeftArm", "RightArm", "LeftLeg", "RightLeg"]
LOCATION_LABEL = {"Head": "Head", "CenterTorso": "Center Torso",
                  "LeftTorso": "Left Torso", "RightTorso": "Right Torso",
                  "LeftArm": "Left Arm", "RightArm": "Right Arm",
                  "LeftLeg": "Left Leg", "RightLeg": "Right Leg"}

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


def weapon_slot_location(slot_id: str) -> str:
    """Map a weapon hardpoint slot id (e.g. 'Torso_Left_EH1_...', 'Head_MH1_...',
    'Arm_Right_...') to a canonical body location matching the equipment
    part labels (LeftTorso, Head, RightArm, ...)."""
    t = slot_id.split("_")
    part = t[0] if t else ""
    side = t[1] if len(t) > 1 else ""
    if part == "Head":
        return "Head"
    if part in ("Torso", "Arm", "Leg"):
        base = "Torso" if part == "Torso" else part
        return {"Left": "Left", "Right": "Right", "Center": "Center"}.get(side, side) + base
    return part or "Other"


APP_VERSION = "1.16.1"

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
        self.title(f"JJ's MW5 Merc Save Editor  v{APP_VERSION}")
        self.geometry("860x680")
        self.minsize(720, 520)
        self._set_app_icon()
        self.save: SaveFile | None = None
        self.path: str | None = None
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
        self.nb.add(self.mech_tab, text="Mechs")
        self.nb.add(self.pilot_tab, text="Pilots")
        self.nb.add(self.inv_tab, text="Inventory")
        self.nb.add(self.faction_tab, text="Factions")
        self._build_mech_tab()
        self._build_pilot_tab()
        self._build_inventory_tab()
        self._build_faction_tab()

        self.status = tk.StringVar(value="Open a .sav file to begin.")
        ttk.Label(self, textvariable=self.status, relief="sunken",
                  style="Status.TLabel", anchor="w").pack(fill="x", side="bottom")
        # re-apply now that themed widgets (canvas, cards) exist
        self._apply_theme(self._theme_pref.get())

        # quiet update check on startup (background; silent if offline)
        if load_pref("check_updates", True):
            self.after(800, lambda: self._check_updates_async(manual=False))

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
        ttk.Button(bar, text="Open…", command=self.on_open).pack(side="left")
        ttk.Button(bar, text="Save", command=self.on_save).pack(side="left", padx=4)
        ttk.Button(bar, text="Save As…", command=self.on_save_as).pack(side="left")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(bar, text="Export…", command=self.on_export).pack(side="left")
        ttk.Button(bar, text="Import…", command=self.on_import).pack(side="left", padx=4)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(bar, text="Check for Updates",
                   command=lambda: self._check_updates_async(manual=True)).pack(side="left")

        # theme selector (right side): System follows the Windows app theme
        ttk.Label(bar, text="Theme:").pack(side="right", padx=(0, 4))
        theme_cb = ttk.Combobox(bar, width=8, state="readonly",
                                textvariable=self._theme_pref,
                                values=("System", "Light", "Dark"))
        theme_cb.set(self._theme_pref.get().capitalize())
        theme_cb.pack(side="right")
        theme_cb.bind("<<ComboboxSelected>>", self._on_theme_change)

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
            self.status.set("Checking for updates…")

        def worker():
            tag = fetch_latest_version()
            self.after(0, lambda: self._on_update_result(tag, manual))

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_result(self, tag, manual):
        self._update_checking = False
        if not tag:
            if manual:
                messagebox.showwarning(
                    "Check for Updates",
                    "Couldn't reach GitHub to check for updates.\n"
                    "Check your connection, or visit the Releases page directly.")
            return
        if _version_tuple(tag) > _version_tuple(APP_VERSION):
            self._update_msg.configure(
                text=f"A new version ({tag}) is available — you have v{APP_VERSION}.")
            self._update_bar.pack(fill="x", before=self.nb)
            self.status.set(f"Update available: {tag}. You're on v{APP_VERSION}.")
        else:
            self.status.set(f"You're up to date (v{APP_VERSION}).")
            if manual:
                messagebox.showinfo(
                    "Check for Updates",
                    f"You're running the latest version (v{APP_VERSION}).")

    # -- mech tab ----------------------------------------------------------
    def _build_mech_tab(self):
        mwrap = ttk.Frame(self.mech_tab)
        mwrap.pack(side="left", fill="both", expand=True, padx=(0, 4), pady=4)

        self.mech_count_var = tk.StringVar(value="")
        ttk.Label(mwrap, textvariable=self.mech_count_var).pack(anchor="w", pady=(0, 2))

        # filter: show all mechs, only the active bay, or only cold storage
        flt = ttk.Frame(mwrap)
        flt.pack(anchor="w", pady=(0, 2))
        ttk.Label(flt, text="Show:").pack(side="left")
        self.mech_filter = tk.StringVar(value="all")
        for txt, val in (("All", "all"), ("Active Bay", "active"), ("Cold Storage", "cold")):
            ttk.Radiobutton(flt, text=txt, value=val, variable=self.mech_filter,
                            command=self._refresh_mechs).pack(side="left", padx=2)

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
        ttk.Button(side, text="Add Mech…", command=self.on_add_mech).pack(fill="x", pady=2)
        ttk.Button(side, text="Edit Loadout…", command=self.on_edit_loadout).pack(fill="x", pady=2)
        ttk.Button(side, text="Set Hardpoints…", command=self.on_set_hardpoints).pack(fill="x", pady=2)
        ttk.Button(side, text="Change Chassis…", command=self.on_change_chassis).pack(fill="x", pady=2)
        ttk.Button(side, text="Repair (full armor)", command=self.on_repair).pack(fill="x", pady=2)
        ttk.Button(side, text="Repair ALL Mechs", command=self.on_repair_all).pack(fill="x", pady=2)
        ttk.Button(side, text="Reset to Stock", command=self.on_reset_to_stock).pack(fill="x", pady=2)
        ttk.Button(side, text="Export Loadout…", command=self.on_export_loadout).pack(fill="x", pady=2)
        ttk.Button(side, text="Import Loadout…", command=self.on_import_loadout).pack(fill="x", pady=2)
        ttk.Button(side, text="Remove", command=self.on_remove_mech).pack(fill="x", pady=2)

    # -- mech-bay cards ----------------------------------------------------
    def _bind_mech_wheel(self, on):
        seqs = ("<MouseWheel>", "<Button-4>", "<Button-5>")
        if on:
            for s in seqs:
                self.mech_canvas.bind_all(s, self._mech_wheel)
        else:
            for s in seqs:
                self.mech_canvas.unbind_all(s)

    def _mech_wheel(self, e):
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
        tk.Label(card, text=(cls or "?").upper(), bg=badge_bg, fg=badge_fg,
                 font=("", 8, "bold"), padx=6, pady=2).pack(side="right", padx=8)

        mid = tk.Frame(card, bg=bg)
        mid.pack(side="left", fill="x", expand=True, pady=6)
        tk.Label(mid, text=mech_display(m.chassis), bg=bg, anchor="w", fg=THEME["text"],
                 justify="left", font=("", 10, "bold")).pack(fill="x")
        tk.Label(mid, text=f"{tons or '?'}t · {location}", bg=bg, fg=THEME["text_muted"],
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
        self.pilot_list.bind("<<ListboxSelect>>", lambda e: self._load_pilot_form())
        pbtns = ttk.Frame(left)
        pbtns.pack(fill="x", pady=4)
        ttk.Button(pbtns, text="Add Pilot…", command=self.on_add_pilot).pack(fill="x", pady=1)
        ttk.Button(pbtns, text="Remove Pilot", command=self.on_remove_pilot).pack(fill="x", pady=1)

        form = ttk.Frame(self.pilot_tab)
        form.pack(side="left", fill="both", expand=True, pady=4)

        self.pilot_vars: dict[str, tk.StringVar] = {}

        def row(label, key, r):
            ttk.Label(form, text=label).grid(row=r, column=0, sticky="w", pady=2)
            var = tk.StringVar()
            ttk.Entry(form, textvariable=var, width=24).grid(row=r, column=1, columnspan=2,
                                                             sticky="w", pady=2)
            self.pilot_vars[key] = var

        row("Callsign", "callsign", 0)
        row("Full name", "full_name", 1)
        row("Salary (C-Bills)", "salary", 2)
        ttk.Separator(form, orient="horizontal").grid(row=3, column=0, columnspan=3, sticky="ew", pady=6)
        ttk.Label(form, text="Skill", font=("", 9, "bold")).grid(row=4, column=0, sticky="w")
        ttk.Label(form, text="XP", font=("", 9, "bold")).grid(row=4, column=1, sticky="w")
        ttk.Label(form, text="Cap (max 10)", font=("", 9, "bold")).grid(row=4, column=2, sticky="w")
        for i, sk in enumerate(SKILLS):
            r = 5 + i
            ttk.Label(form, text=sk).grid(row=r, column=0, sticky="w", pady=1)
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
        ttk.Button(form, text="Apply to Pilot", command=self.on_apply_pilot).grid(
            row=br, column=0, columnspan=2, sticky="w", pady=8)
        ttk.Button(form, text="Max caps (10)", command=self.on_max_caps).grid(
            row=br, column=2, sticky="w", pady=8)

        # -- traits (apply immediately; no "Apply to Pilot" needed) --
        tr = br + 1
        ttk.Separator(form, orient="horizontal").grid(row=tr, column=0, columnspan=3, sticky="ew", pady=6)
        ttk.Label(form, text="Traits", font=("", 9, "bold")).grid(row=tr + 1, column=0, sticky="w")
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
        self.pilot_trait_cb = ttk.Combobox(taf, textvariable=self.pilot_trait_var, width=32)
        self.pilot_trait_cb.pack(side="left")
        ttk.Button(taf, text="Add", command=self.on_add_pilot_trait).pack(side="left", padx=4)
        ttk.Button(taf, text="Remove", command=self.on_remove_pilot_trait).pack(side="left")

    # -- inventory tab -----------------------------------------------------
    def _build_inventory_tab(self):
        top = ttk.Frame(self.inv_tab)
        top.pack(fill="x", padx=4, pady=6)

        # C-Bills
        ttk.Label(top, text="C-Bills:").grid(row=0, column=0, sticky="w")
        self.cbills_var = tk.StringVar(value="0")
        ttk.Entry(top, textvariable=self.cbills_var, width=16).grid(row=0, column=1, sticky="w", padx=4)
        ttk.Button(top, text="Set C-Bills", command=self.on_set_cbills).grid(row=0, column=2, padx=4)
        ttk.Button(top, text="Max (2,000,000,000)",
                   command=lambda: (self.cbills_var.set("2000000000"), self.on_set_cbills())
                   ).grid(row=0, column=3, padx=4)

        ttk.Separator(self.inv_tab, orient="horizontal").pack(fill="x", padx=4, pady=2)

        # Add-item row (mirrors the classic editor: Item / Count / Type / Add)
        add = ttk.Frame(self.inv_tab)
        add.pack(fill="x", padx=4, pady=6)
        ttk.Label(add, text="Type:").grid(row=0, column=0, sticky="w")
        self.inv_type_var = tk.StringVar(value="weapon")
        type_cb = ttk.Combobox(add, textvariable=self.inv_type_var, width=12, state="readonly",
                               values=["weapon", "equipment", "ammo"])
        type_cb.grid(row=0, column=1, padx=4)
        type_cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_item_choices())

        ttk.Label(add, text="Item:").grid(row=0, column=2, sticky="w", padx=(8, 0))
        self.inv_item_var = tk.StringVar()
        self.inv_item_cb = ttk.Combobox(add, textvariable=self.inv_item_var, width=36)
        self.inv_item_cb.grid(row=0, column=3, padx=4)

        ttk.Label(add, text="Count:").grid(row=0, column=4, sticky="w", padx=(8, 0))
        self.inv_count_var = tk.StringVar(value="1")
        ttk.Spinbox(add, from_=1, to=9999, textvariable=self.inv_count_var, width=6).grid(row=0, column=5, padx=4)

        ttk.Button(add, text="Add to Inventory", command=self.on_add_item).grid(row=0, column=6, padx=8)

        # filter / search row
        filt = ttk.Frame(self.inv_tab)
        filt.pack(fill="x", padx=4, pady=(2, 0))
        ttk.Label(filt, text="Filter:").pack(side="left")
        self.inv_filter_var = tk.StringVar()
        ttk.Entry(filt, textvariable=self.inv_filter_var, width=30).pack(side="left", padx=4)
        self.inv_filter_var.trace_add("write", lambda *a: self._render_inventory())
        ttk.Label(filt, text="(click a column header to sort • shift/ctrl-click rows to multi-select)",
                  style="Muted.TLabel").pack(side="left", padx=8)

        # Current inventory list
        iwrap = ttk.Frame(self.inv_tab)
        iwrap.pack(fill="both", expand=True, padx=4, pady=4)
        cols = ("type", "item", "count")
        self.inv_tree = ttk.Treeview(iwrap, columns=cols, show="headings", selectmode="extended")
        for c, txt, w in (("type", "Asset Type", 180), ("item", "Item ID", 300), ("count", "Count", 70)):
            self.inv_tree.heading(c, text=txt, command=lambda col=c: self._sort_inventory(col))
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
        ttk.Button(btns, text="Set Count of Selected…", command=self.on_set_item_count).pack(side="left")
        ttk.Button(btns, text="Remove Selected", command=self.on_remove_item).pack(side="left", padx=4)

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
        ttk.Label(top, text="Company Reputation:").grid(row=0, column=0, sticky="w")
        self.rep_var = tk.StringVar(value="0")
        ttk.Entry(top, textvariable=self.rep_var, width=12).grid(row=0, column=1, padx=4)
        ttk.Button(top, text="Set Reputation", command=self.on_set_reputation).grid(row=0, column=2, padx=4)

        ttk.Label(self.faction_tab,
                  text="Faction standings (typically range -100 hostile … +100 allied). "
                       "Double-click a row to edit.",
                  style="Muted.TLabel").pack(anchor="w", padx=6)

        fwrap = ttk.Frame(self.faction_tab)
        fwrap.pack(fill="both", expand=True, padx=6, pady=4)
        cols = ("faction", "standing")
        self.faction_tree = ttk.Treeview(fwrap, columns=cols, show="headings",
                                         selectmode="browse")
        self.faction_tree.heading("faction", text="Faction")
        self.faction_tree.heading("standing", text="Standing")
        self.faction_tree.column("faction", width=240)
        self.faction_tree.column("standing", width=100, anchor="center")
        fsb = ttk.Scrollbar(fwrap, orient="vertical", command=self.faction_tree.yview)
        self.faction_tree.configure(yscrollcommand=fsb.set)
        self.faction_tree.pack(side="left", fill="both", expand=True)
        fsb.pack(side="right", fill="y")
        self.faction_tree.bind("<Double-Button-1>", lambda e: self.on_edit_standing())

        btns = ttk.Frame(self.faction_tab)
        btns.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(btns, text="Edit Selected…", command=self.on_edit_standing).pack(side="left")
        ttk.Button(btns, text="Set ALL to +100 (allied)",
                   command=lambda: self.on_set_all_factions(100)).pack(side="left", padx=4)
        ttk.Button(btns, text="Set ALL to 0 (neutral)",
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
            return messagebox.showerror("Invalid", "Reputation must be a whole number.")
        self.status.set(f"Set reputation to {self.save.reputation}. Remember to Save.")

    def on_edit_standing(self):
        if not self._guard():
            return
        sel = self.faction_tree.selection()
        if not sel:
            return self._need_selection()
        idx = int(sel[0])
        f = self.save.factions()[idx]
        new = simpledialog.askinteger("Edit standing", f"Standing for {f.name}:",
                                      initialvalue=f.standing, minvalue=-1000, maxvalue=1000)
        if new is None:
            return
        f.standing = new
        self._refresh_factions()
        self.faction_tree.selection_set(str(idx))
        self.status.set(f"Set {f.name} standing to {new}. Remember to Save.")

    def on_set_all_factions(self, value):
        if not self._guard():
            return
        for f in self.save.factions():
            f.standing = value
        self._refresh_factions()
        self.status.set(f"Set all faction standings to {value}. Remember to Save.")

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
            title="Open MW5 save", initialdir=initial,
            filetypes=[("MW5 save", "*.sav"), ("All files", "*.*")])
        if not path:
            return
        try:
            self.save = SaveFile.load(path)
            self.path = path
            self._build_item_catalog()
            self._refresh_mechs()
            self._refresh_pilots()
            self._refresh_inventory()
            self._refresh_factions()
            self.status.set(f"Loaded {os.path.basename(path)} — "
                            f"{len(self.save.mechs())} mechs, {len(self.save.pilots())} pilots, "
                            f"{self.save.cbills:,} C-Bills")
        except Exception as e:
            self._error("Failed to open save", e)

    def on_save(self):
        if not self._guard():
            return
        self._write(self.path, backup=True)

    def on_save_as(self):
        if not self._guard():
            return
        path = filedialog.asksaveasfilename(
            title="Save As", defaultextension=".sav",
            initialdir=os.path.dirname(self.path) if self.path else None,
            filetypes=[("MW5 save", "*.sav"), ("All files", "*.*")])
        if path:
            self._write(path, backup=False)

    def _write(self, path, backup):
        try:
            if backup and os.path.exists(path):
                bak = path + ".bak"
                if not os.path.exists(bak):
                    shutil.copy2(path, bak)
            self.save.save(path)
            self.path = path
            self.status.set(f"Saved {os.path.basename(path)}"
                            + ("  (backup: .bak)" if backup else ""))
            messagebox.showinfo("Saved", f"Wrote {os.path.basename(path)} successfully.")
        except Exception as e:
            self._error("Failed to save", e)

    # -- export / import ---------------------------------------------------
    def on_export(self):
        if not self._guard():
            return
        cats = CategoryDialog(
            self, "Export to file",
            "Choose what to export to a portable .mw5export file\n"
            "(you can import it into another save later):").result
        if cats is None:
            return
        path = filedialog.asksaveasfilename(
            title="Export to…", defaultextension=".mw5export",
            initialfile="my-mechs.mw5export",
            filetypes=[("MW5 export", "*.mw5export"), ("All files", "*.*")])
        if not path:
            return
        try:
            s = self.save.export_to(path, **cats)
            self.status.set(f"Exported {s['mechs']} mechs, {s['pilots']} pilots, "
                            f"{s['weapons'] + s['equipment']} items.")
            messagebox.showinfo("Exported",
                                f"Exported to {os.path.basename(path)}:\n\n"
                                f"  {s['mechs']} mechs\n  {s['pilots']} pilots\n"
                                f"  {s['weapons'] + s['equipment']} inventory items")
        except Exception as e:
            self._error("Export failed", e)

    def on_import(self):
        if not self._guard():
            return
        path = filedialog.askopenfilename(
            title="Import from…",
            filetypes=[("MW5 export", "*.mw5export"), ("All files", "*.*")])
        if not path:
            return
        cats = CategoryDialog(
            self, "Import into this save",
            "Choose what to ADD from the file into the currently open save.\n"
            "Mechs and pilots are added with fresh IDs (they don't replace\n"
            "what's here). Save afterwards to keep the changes.").result
        if cats is None:
            return
        try:
            s = self.save.import_from(path, **cats)
            self._refresh_mechs()
            self._refresh_pilots()
            self._refresh_inventory()
            self._refresh_factions()
            self.status.set(f"Imported {s['mechs']} mechs, {s['pilots']} pilots, "
                            f"{s['items']} items. Remember to Save.")
            messagebox.showinfo("Imported",
                                f"Added from {os.path.basename(path)}:\n\n"
                                f"  {s['mechs']} mechs\n  {s['pilots']} pilots\n"
                                f"  {s['items']} inventory items\n\n"
                                "Click Save to write them into your save file.")
        except Exception as e:
            self._error("Import failed", e)

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
        for idx, m in enumerate(self._mech_objs):
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
            f"Active bay: {len(active)}    Cold storage: {len(cold)}    (total {len(active) + len(cold)})")

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
        chassis = self._pick_chassis("Add Mech")
        if chassis is None:
            return
        to_cold = messagebox.askyesno(
            "Add to Cold Storage?",
            "Add this mech to Cold Storage?\n\n"
            "Yes — Cold Storage (recommended): always works, even if your active "
            "bay is full. Move it to the bay in-game if there's room.\n\n"
            "No — Active Bay: only appears if you have a free bay slot in-game. "
            "If your bay is full it won't show up.")
        location = "cold" if to_cold else "active"
        where = "Cold Storage" if to_cold else "the Active Bay"
        try:
            _guid, status = self.save.add_mech(chassis, location=location)
            self._refresh_mechs()
            label = mech_display(chassis)
            if status == "stock":
                self.status.set(f"Added {label} to {where} — full stock loadout "
                                "(weapons, armor, equipment). Remember to Save.")
                messagebox.showinfo(
                    "Mech added",
                    f"Added a stock {label} to {where} with its real factory loadout: "
                    "correct armor, weapons, weapon groups and equipment for that chassis. "
                    "Ready to deploy, or tweak it in Edit Loadout / the in-game Mech Lab.")
            elif status == "exact":
                self.status.set(f"Added {label} to {where} — exact copy of one you own. Remember to Save.")
            elif status == "real-layout":
                self.status.set(f"Added {label} to {where} with its real hardpoints (empty). "
                                "Fit weapons in Edit Loadout. Remember to Save.")
                messagebox.showinfo(
                    "Mech added",
                    f"Added a {label} to {where}. Your save had a real {label} loadout on "
                    "record, so it got that chassis's correct (empty) hardpoints.\n\n"
                    "Use Edit Loadout to fit weapons and set groups — no Mech Lab needed.")
            else:
                self.status.set(f"Added {label} to {where} (approximate — set hardpoints / refit in Mech Lab). Remember to Save.")
                messagebox.showinfo(
                    "Approximate mech added",
                    f"Added a {label} to {where}. You don't own one and your save has no "
                    f"{label} loadout to copy, so it's an approximate clone with its weapons "
                    "stripped.\n\nEither refit it in the in-game Mech Lab, or use "
                    "\"Set Hardpoints…\" to borrow a layout, then Edit Loadout. "
                    "(A different-chassis mech can't be built perfectly from save "
                    "data alone.)")
        except Exception as e:
            self._error("Failed to add mech", e)

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
                      self.status.set(f"Loadout updated for mech #{idx}. Remember to Save.")))

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
            messagebox.showinfo("No layouts",
                "Your save doesn't contain any mech loadout to copy hardpoints from.")
            return False
        want = mech.chassis if mech.chassis.endswith("_MDA") else mech.chassis + "_MDA"
        items = sorted(layouts.items(), key=lambda kv: (kv[0] != want, kv[0]))
        labels = []
        for ch, (iw, _wg, _cfg) in items:
            n = len(iw.elements) if iw is not None else 0
            tag = "  ← this chassis (correct)" if ch == want else "  (borrowed layout)"
            labels.append(f"{mech_display(ch)}  · {n} hardpoints{tag}")
        intro = (f"{mech_display(mech.chassis)} has no hardpoints yet.\n"
                 if empty else f"Replace {mech_display(mech.chassis)}'s hardpoints.\n")
        pick = ChoiceDialog(
            self, "Set hardpoints",
            intro + "\nPick a layout to apply, then fit weapons in Edit Loadout.\n"
            "Same-chassis layouts are correct; 'borrowed' ones come from another\n"
            "chassis and may need an in-game Mech Lab refit to work properly.",
            labels).result
        if pick is None:
            return False
        ch = items[labels.index(pick)][0]
        mech.apply_layout(*layouts[ch])
        mech.flush()
        self._refresh_mechs()
        note = "correct layout" if ch == want else f"borrowed {mech_display(ch)} layout"
        self.status.set(f"Set hardpoints on mech #{idx} ({note}). Open Edit Loadout to fit weapons. Save when done.")
        return True

    def on_change_chassis(self):
        idx = self._selected_mech_index()
        if idx is None:
            return self._need_selection()
        chassis = self._pick_chassis("Change Chassis")
        if chassis is None:
            return
        m = self._selected_mech()
        m.chassis = chassis
        m.flush()
        self._refresh_mechs()
        self.status.set(f"Mech #{idx} chassis -> {chassis}. Remember to Save.")

    def on_repair(self):
        idx = self._selected_mech_index()
        if idx is None:
            return self._need_selection()
        m = self._selected_mech()
        m.repair()
        m.flush()
        self.status.set(f"Mech #{idx} repaired to full armor. Remember to Save.")

    def on_repair_all(self):
        if not self._guard():
            return
        n = 0
        for m in self._mech_list():   # active bay + cold storage
            m.repair()
            m.flush()
            n += 1
        self.status.set(f"Repaired all {n} mechs (armor restored to installed). Remember to Save.")
        messagebox.showinfo("Repair All", f"Restored armor on {n} mechs.")

    def on_reset_to_stock(self):
        if not self._guard():
            return
        idx = self._selected_mech_index()
        if idx is None:
            return self._need_selection()
        m = self._selected_mech()
        label = mech_display(m.chassis)
        if not messagebox.askyesno(
                "Reset to stock",
                f"Reset {label} to its factory-stock loadout?\n\n"
                "This replaces its armor, weapons, weapon groups and equipment with "
                "the chassis's stock configuration. Any custom loadout is overwritten."):
            return
        try:
            if self.save.reset_mech_to_stock(m):
                self._refresh_mechs()
                self.status.set(f"Reset {label} to stock loadout. Remember to Save.")
            else:
                messagebox.showinfo(
                    "No stock data",
                    f"There's no stock template for {label} (it may be a modded or "
                    "non-standard chassis), so it can't be reset to stock.")
        except Exception as e:
            self._error("Failed to reset to stock", e)

    def on_export_loadout(self):
        if not self._guard():
            return
        if self._selected_mech_index() is None:
            return self._need_selection()
        m = self._selected_mech()
        path = filedialog.asksaveasfilename(
            title="Export loadout", defaultextension=".mw5loadout",
            initialfile=f"{variant_code(m.chassis)}.mw5loadout",
            filetypes=[("MW5 loadout", "*.mw5loadout"), ("All files", "*.*")])
        if not path:
            return
        try:
            self.save.export_mech_loadout(m, path)
            self.status.set(f"Exported {mech_display(m.chassis)} loadout to {os.path.basename(path)}.")
        except Exception as e:
            self._error("Failed to export loadout", e)

    def on_import_loadout(self):
        if not self._guard():
            return
        if self._selected_mech_index() is None:
            return self._need_selection()
        m = self._selected_mech()
        path = filedialog.askopenfilename(
            title="Import loadout",
            filetypes=[("MW5 loadout", "*.mw5loadout"), ("All files", "*.*")])
        if not path:
            return
        if not messagebox.askyesno(
                "Import loadout",
                f"Apply this loadout to {mech_display(m.chassis)}?\n\nThis overwrites its "
                "current weapons, equipment and armor. Loadouts are meant for the same chassis."):
            return
        try:
            src = self.save.import_mech_loadout(m, path)
            self._refresh_mechs()
            if src and variant_code(src) != variant_code(m.chassis):
                messagebox.showwarning(
                    "Different chassis",
                    f"That loadout was exported from {mech_display(src)}, but you applied it to "
                    f"{mech_display(m.chassis)}. The hardpoints may not match — check it in Edit "
                    "Loadout or the in-game Mech Lab.")
            self.status.set(f"Imported loadout onto {mech_display(m.chassis)}. Remember to Save.")
        except Exception as e:
            self._error("Failed to import loadout", e)

    def on_remove_mech(self):
        idx = self._selected_mech_index()
        if idx is None:
            return self._need_selection()
        m = self._selected_mech()
        if not messagebox.askyesno("Remove mech",
                                   f"Remove mech #{idx} ({m.chassis})?"):
            return
        self.save.remove_mech(m.guid)
        self._refresh_mechs()
        self.status.set(f"Removed mech #{idx}. Remember to Save.")

    def _pick_chassis(self, title):
        variant = ChassisDialog(self, title).result
        return asset_name(variant) if variant else None

    # -- pilot actions -----------------------------------------------------
    def _refresh_pilots(self):
        self.pilot_list.delete(0, "end")
        for p in self.save.pilots():
            self.pilot_list.insert("end", p.callsign or p.full_name or "(pilot)")
        if self.save.pilots():
            self.pilot_list.selection_set(0)
            self._load_pilot_form()

    def _selected_pilot_index(self):
        sel = self.pilot_list.curselection()
        return sel[0] if sel else None

    def _load_pilot_form(self):
        idx = self._selected_pilot_index()
        if idx is None:
            return
        p = self.save.pilots()[idx]
        self.pilot_vars["callsign"].set(p.callsign)
        self.pilot_vars["full_name"].set(p.full_name)
        self.pilot_vars["salary"].set(str(p.salary))
        for sk in SKILLS:
            self.pilot_vars[f"skill_{sk}"].set(str(p.skill(sk)))
            self.pilot_vars[f"cap_{sk}"].set(str(p.skill_cap(sk)))
        self._refresh_pilot_traits(p)

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
            return messagebox.showinfo("Pick trait", "Choose or type a pilot trait asset name.")
        p = self.save.pilots()[idx]
        try:
            if self.save.add_pilot_trait(p, name):
                self._refresh_pilot_traits(p)
                self.status.set(f"Added trait '{name}' to {p.callsign}. Remember to Save.")
            else:
                self.status.set(f"{p.callsign} already has '{name}'.")
        except Exception as e:
            self._error("Failed to add trait", e)

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
            self.status.set(f"Removed trait '{name}' from {p.callsign}. Remember to Save.")

    def on_apply_pilot(self):
        if not self._guard():
            return
        idx = self._selected_pilot_index()
        if idx is None:
            return self._need_selection()
        p = self.save.pilots()[idx]
        try:
            p.callsign = self.pilot_vars["callsign"].get()
            p.full_name = self.pilot_vars["full_name"].get()
            p.salary = int(self.pilot_vars["salary"].get())
            for sk in SKILLS:
                p.set_skill(sk, int(self.pilot_vars[f"skill_{sk}"].get()))
                if sk in CAPPED_SKILLS:
                    p.set_skill_cap(sk, int(self.pilot_vars[f"cap_{sk}"].get()))
            self._refresh_pilots()
            self.pilot_list.selection_set(idx)
            self.status.set(f"Applied changes to pilot #{idx}. Remember to Save.")
        except ValueError:
            messagebox.showerror("Invalid input", "Salary, skill XP and caps must be whole numbers.")

    def on_max_caps(self):
        """Fill the cap fields for the selected pilot with the max (10)."""
        if self._selected_pilot_index() is None:
            return self._need_selection()
        for sk in CAPPED_SKILLS:
            self.pilot_vars[f"cap_{sk}"].set(str(MAX_SKILL_CAP))
        self.status.set("Caps set to 10 — click 'Apply to Pilot' to save the change.")

    def on_add_pilot(self):
        if not self._guard():
            return
        callsign = simpledialog.askstring("Add Pilot", "Callsign for the new pilot:")
        if not callsign:
            return
        randomize = messagebox.askyesno(
            "Skills",
            "Randomize this pilot's skills?\n\n"
            "Yes = random skill XP (a freshly generated merc)\n"
            "No  = start all skills at 0 (green rookie)")
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
            self.status.set(f"Added pilot '{callsign}'. Tweak skills below if you like, then Save.")
        except Exception as e:
            self._error("Failed to add pilot", e)

    def on_remove_pilot(self):
        if not self._guard():
            return
        idx = self._selected_pilot_index()
        if idx is None:
            return self._need_selection()
        pilots = self.save.pilots()
        p = pilots[idx]
        if idx == 0:
            return messagebox.showwarning(
                "Can't remove", "Won't remove the first pilot (your commander).")
        if not messagebox.askyesno("Remove pilot", f"Remove pilot '{p.callsign}'?"):
            return
        self.save.remove_pilot(p.persona_id)
        self._refresh_pilots()
        self.status.set(f"Removed pilot '{p.callsign}'. Remember to Save.")

    # -- inventory actions -------------------------------------------------
    def _refresh_inventory(self):
        self.cbills_var.set(str(self.save.cbills))
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
            return messagebox.showerror("Invalid", "C-Bills must be a whole number.")
        self.status.set(f"Set C-Bills to {self.save.cbills:,}. Remember to Save.")

    def on_add_item(self):
        if not self._guard():
            return
        cat = self.inv_type_var.get()
        name = self.inv_item_var.get().strip()
        if not name:
            return messagebox.showinfo("Pick item", "Choose or type an item asset name.")
        try:
            count = int(self.inv_count_var.get())
        except ValueError:
            return messagebox.showerror("Invalid", "Count must be a whole number.")
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
            self.status.set(f"Added {count}x {name}. Remember to Save.")
        except Exception as e:
            self._error("Failed to add item", e)

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
        title = (f"New count for {rows[0]['name']}:" if len(rows) == 1
                 else f"New count for the {len(rows)} selected items:")
        new = simpledialog.askinteger("Set count", title,
                                      initialvalue=int(rows[0]["count"]), minvalue=0)
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
        self.status.set(f"Set count to {new} for {len(rows)} item(s). Remember to Save.")

    def on_remove_item(self):
        if not self._guard():
            return
        rows = self._selected_inv_rows()
        if not rows:
            return self._need_selection()
        if not messagebox.askyesno("Remove items",
                                   f"Remove {len(rows)} selected item(s) from inventory?"):
            return
        for r in rows:
            self.save.remove_item(r["inv"], r["name"])
        self._refresh_inventory()
        self.status.set(f"Removed {len(rows)} item(s). Remember to Save.")

    # -- helpers -----------------------------------------------------------
    def _guard(self):
        if self.save is None:
            messagebox.showwarning("No save", "Open a .sav file first.")
            return False
        return True

    def _need_selection(self):
        messagebox.showinfo("Select first", "Select an item in the list first.")

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
        self.title(f"Edit Loadout — {mech_display(mech.chassis)}")
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
        ttk.Button(btns, text="Apply", command=self._apply).pack(side="right")
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=6)

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

        # Mouse-wheel scrolling while the dialog is open. bind_all catches the
        # wheel wherever the cursor is (over comboboxes etc.); unbound on close.
        def _wheel(e):
            if e.num == 5 or e.delta < 0:
                canvas.yview_scroll(1, "units")
            elif e.num == 4 or e.delta > 0:
                canvas.yview_scroll(-1, "units")
        canvas.bind_all("<MouseWheel>", _wheel)
        canvas.bind_all("<Button-4>", _wheel)
        canvas.bind_all("<Button-5>", _wheel)
        self.bind("<Destroy>", lambda e: self._unbind_wheel(canvas) if e.widget is self else None)

        # view toggle: Body (paper-doll) or List (dense, all hardpoints)
        vt = ttk.Frame(content)
        vt.pack(anchor="w", padx=10, pady=(10, 0))
        ttk.Label(vt, text="Loadout view:").pack(side="left")
        ttk.Radiobutton(vt, text="Body", value="body", variable=self.view_mode,
                        command=self._switch_view).pack(side="left", padx=4)
        ttk.Radiobutton(vt, text="List (all hardpoints)", value="list",
                        variable=self.view_mode, command=self._switch_view).pack(side="left")

        # container rebuilt when the view is switched (vars persist, so do edits)
        self.loadout_frame = ttk.Frame(content)
        self.loadout_frame.pack(fill="x")
        self._render_loadout()

        # armor
        ttk.Separator(content, orient="horizontal").pack(fill="x", padx=10, pady=8)
        ttk.Label(content, text="Armor (current)", font=("", 10, "bold")).pack(anchor="w", padx=10)
        af = ttk.Frame(content)
        af.pack(fill="x", padx=10, pady=4)
        locs = ARMOR_PARTS + REAR_PARTS
        for i, loc in enumerate(locs):
            row, col = divmod(i, 4)
            cell = ttk.Frame(af)
            cell.grid(row=row, column=col, sticky="w", padx=4, pady=2)
            ttk.Label(cell, text=loc, width=15).pack(side="left")
            v = tk.StringVar(value=str(int(self.mech.armor_value(loc))))
            ttk.Entry(cell, textvariable=v, width=6).pack(side="left")
            self.armor_vars[loc] = v
        ttk.Button(content, text="Max armor (= installed)", command=self._max_armor).pack(anchor="w", padx=10, pady=2)

        # traits (Cantina-style mech quirks) -- experimental
        if self.save is not None:
            ttk.Separator(content, orient="horizontal").pack(fill="x", padx=10, pady=8)
            ttk.Label(content, text="Mech Traits (experimental)",
                      font=("", 10, "bold")).pack(anchor="w", padx=10)
            ttk.Label(content, text="Cantina-style quirks (e.g. Faster Cooling). Untested in-game — "
                      "back up your save before relying on these.",
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
            ttk.Combobox(actf, textvariable=self.mtrait_var, values=self.trait_names,
                         width=34).pack(anchor="w")
            bf = ttk.Frame(actf)
            bf.pack(anchor="w", pady=4)
            ttk.Button(bf, text="Add", command=self._add_trait).pack(side="left")
            ttk.Button(bf, text="Remove", command=self._remove_trait).pack(side="left", padx=4)
            self._refresh_traits()

    def _unbind_wheel(self, canvas):
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            try:
                canvas.unbind_all(seq)
            except tk.TclError:
                pass

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

    def _fill_panel(self, parent, sws, ews):
        for slot, var, _gvars in sws:
            cls = slot.hardpoint_class or "?"
            row = ttk.Frame(parent)
            row.pack(fill="x", padx=3, pady=1)
            ttk.Label(row, text=HARDPOINT_LABEL.get(cls, cls), width=9, font=("", 8)).pack(side="left")
            ttk.Combobox(row, textvariable=var, values=self._weapon_options(slot),
                         width=15, state="readonly").pack(side="left")
        for slot, var in ews:
            kind = "Jump Jet" if "JumpJet" in slot.slot_type else "Gear"
            row = ttk.Frame(parent)
            row.pack(fill="x", padx=3, pady=1)
            ttk.Label(row, text=kind, width=9, font=("", 8)).pack(side="left")
            ttk.Combobox(row, textvariable=var, values=self._equip_names(slot),
                         width=15, state="readonly").pack(side="left")
        if not sws and not ews:
            ttk.Label(parent, text="(none)", style="Muted.TLabel", font=("", 8)).pack(padx=3, pady=2)

    def _render_body_view(self):
        f = self.loadout_frame
        ttk.Label(f, text="Loadout — by body location  (pick a weapon/equipment per slot)",
                  font=("", 10, "bold")).pack(anchor="w", padx=10, pady=(8, 2))
        wloc, eloc = self._group_by_location()
        pd = ttk.Frame(f)
        pd.pack(padx=10, pady=2)
        POS = {"Head": (0, 2), "LeftArm": (1, 0), "LeftTorso": (1, 1),
               "CenterTorso": (1, 2), "RightTorso": (1, 3), "RightArm": (1, 4),
               "LeftLeg": (2, 1), "RightLeg": (2, 3)}
        for loc, (rr, cc) in POS.items():
            panel = ttk.LabelFrame(pd, text=LOCATION_LABEL.get(loc, loc))
            panel.grid(row=rr, column=cc, padx=3, pady=3, sticky="nsew")
            self._fill_panel(panel, wloc.get(loc, []), eloc.get(loc, []))
        # any hardpoints/equipment outside the standard 8 locations (modded mechs)
        others = [l for l in (list(wloc) + list(eloc)) if l not in POS]
        others = list(dict.fromkeys(others))
        if others:
            op = ttk.LabelFrame(f, text="Other hardpoints")
            op.pack(fill="x", padx=10, pady=(8, 2))
            for loc in others:
                ttk.Label(op, text=LOCATION_LABEL.get(loc, loc),
                          font=("", 9, "bold")).pack(anchor="w", padx=4, pady=(4, 0))
                self._fill_panel(op, wloc.get(loc, []), eloc.get(loc, []))
        self._render_fire_groups(f)

    def _render_fire_groups(self, parent):
        if not self.slot_widgets:
            return
        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=10, pady=8)
        ttk.Label(parent, text="Fire groups", font=("", 10, "bold")).pack(anchor="w", padx=10)
        fgf = ttk.Frame(parent)
        fgf.pack(fill="x", padx=10, pady=2)
        ttk.Label(fgf, text="Weapon hardpoint", width=34).grid(row=0, column=0, sticky="w")
        for g in range(1, 7):
            ttk.Label(fgf, text=str(g), width=3).grid(row=0, column=g)
        for i, (slot, _var, gvars) in enumerate(self.slot_widgets, start=1):
            loc = weapon_slot_location(slot.slot_id)
            cls = slot.hardpoint_class or "?"
            ttk.Label(fgf, width=34, anchor="w",
                      text=f"{LOCATION_LABEL.get(loc, loc)} · {HARDPOINT_LABEL.get(cls, cls)}"
                      ).grid(row=i, column=0, sticky="w", pady=1)
            for gi, gv in enumerate(gvars, start=1):
                ttk.Checkbutton(fgf, variable=gv).grid(row=i, column=gi)
        self._render_chain_fire_row(fgf, len(self.slot_widgets) + 1, 0)

    def _render_chain_fire_row(self, grid, row, group_col0):
        """A 'chain fire' toggle per group (1-6): on = weapons in that group fire
        one after another; off = salvo (all at once). group_col0 is the grid
        column just before group 1's column."""
        ttk.Label(grid, text="Chain fire (off = salvo)", width=34, anchor="w",
                  style="Muted.TLabel").grid(row=row, column=0, sticky="w", pady=(6, 1))
        for gi in range(1, 7):
            ttk.Checkbutton(grid, variable=self._chain_vars[gi - 1]).grid(
                row=row, column=group_col0 + gi)

    def _render_list_view(self):
        """Dense, one-row-per-hardpoint view with inline fire groups. Renders
        every slot (good for heavily-modded mechs with many hardpoints)."""
        f = self.loadout_frame
        ttk.Label(f, text="Loadout — all hardpoints",
                  font=("", 10, "bold")).pack(anchor="w", padx=10, pady=(8, 2))
        grid = ttk.Frame(f)
        grid.pack(fill="x", padx=10)
        ttk.Label(grid, text="Hardpoint / Equipment", width=34).grid(row=0, column=0, sticky="w")
        ttk.Label(grid, text="Fitted", width=24).grid(row=0, column=1, sticky="w")
        for g in range(1, 7):
            ttk.Label(grid, text=str(g), width=3).grid(row=0, column=1 + g)
        wloc, eloc = self._group_by_location()
        ordered = [l for l in LOCATION_ORDER if l in wloc or l in eloc]
        ordered += [l for l in (list(wloc) + list(eloc))
                    if l not in LOCATION_ORDER and l not in ordered]
        ordered = list(dict.fromkeys(ordered))
        r = 1
        for loc in ordered:
            ttk.Label(grid, text=LOCATION_LABEL.get(loc, loc), font=("", 9, "bold")).grid(
                row=r, column=0, columnspan=8, sticky="w", pady=(8, 1))
            r += 1
            for slot, var, gvars in wloc.get(loc, []):
                cls = slot.hardpoint_class or "?"
                ttk.Label(grid, text=f"    {HARDPOINT_LABEL.get(cls, cls)}", width=34).grid(
                    row=r, column=0, sticky="w", pady=1)
                ttk.Combobox(grid, textvariable=var, values=self._weapon_options(slot),
                             width=22, state="readonly").grid(row=r, column=1, sticky="w", padx=2)
                for gi, gv in enumerate(gvars, start=1):
                    ttk.Checkbutton(grid, variable=gv).grid(row=r, column=1 + gi)
                r += 1
            for slot, var in eloc.get(loc, []):
                kind = "Jump Jet" if "JumpJet" in slot.slot_type else "Gear"
                ttk.Label(grid, text=f"    [{kind}]", width=34).grid(
                    row=r, column=0, sticky="w", pady=1)
                ttk.Combobox(grid, textvariable=var, values=self._equip_names(slot),
                             width=22, state="readonly").grid(row=r, column=1, columnspan=6,
                                                              sticky="w", padx=2)
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
            return messagebox.showinfo("Pick trait", "Choose or type a mech trait asset name.")
        try:
            if self.save.add_mech_trait(self.mech, name, flush=False):
                self._refresh_traits()
            else:
                messagebox.showinfo("Already installed", f"This mech already has '{name}'.")
        except Exception as e:
            messagebox.showerror("Failed to add trait", f"{type(e).__name__}: {e}")

    def _remove_trait(self):
        sel = self.mtrait_list.curselection()
        if not sel:
            return messagebox.showinfo("Select first", "Select a trait to remove.")
        name = self.mtrait_list.get(sel[0])
        if self.save.remove_mech_trait(self.mech, name, flush=False):
            self._refresh_traits()

    def _max_armor(self):
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
        # armor
        try:
            for loc, v in self.armor_vars.items():
                self.mech.set_armor(loc, float(int(v.get())))
        except ValueError:
            messagebox.showerror("Invalid", "Armor values must be whole numbers.")
            return
        # chain-fire (per group 1-6)
        for gi, v in enumerate(self._chain_vars, start=1):
            self.mech.set_chain_fire_group(gi, v.get())
        self.mech.flush()
        if self.on_apply:
            self.on_apply()
        self.destroy()


class CategoryDialog(simpledialog.Dialog):
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
            ttk.Checkbutton(master, text=label, variable=v).pack(padx=16, pady=1, anchor="w")
            self.vars[key] = v
        return None

    def apply(self):
        self.result = {k: v.get() for k, v in self.vars.items()}


class ChoiceDialog(simpledialog.Dialog):
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


class ChassisDialog(simpledialog.Dialog):
    """Searchable mech picker: type to filter the 540+ chassis/variant list,
    double-click or OK to choose. Also accepts a hand-typed variant code."""
    def __init__(self, parent, title):
        self.result = None
        self.labels = [lbl for lbl, _ in LABELED]
        self._lbl_to_variant = dict(LABELED)
        super().__init__(parent, title)

    def body(self, master):
        ttk.Label(master, text="Search a mech (name or code), then pick one:"
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

        ttk.Label(master, text="(or type an exact variant code above and press OK)",
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


if __name__ == "__main__":
    EditorApp().mainloop()
