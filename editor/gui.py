"""MW5 Mercs Save Editor -- GUI.

A simple Tkinter desktop editor (No Man's Sky-save-editor style):
load a .sav, edit mechs and pilots in tabs, save (with automatic .bak backup).

Run:  python gui.py
"""
from __future__ import annotations

import os
import random
import shutil
import sys
import traceback
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
from mech_catalog import LABELED, asset_name, display as mech_display, variant_code
from item_catalog import CATALOG, CATEGORY_INVENTORY, WEAPONS, EQUIPMENT, AMMO
from savefile import weapon_class, ARMOR_PARTS, REAR_PARTS

HARDPOINT_LABEL = {"EH": "Energy", "BH": "Ballistic", "MH": "Missile", "Melee": "Melee"}


APP_VERSION = "1.8.0"

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

        self._build_toolbar()

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
                  anchor="w").pack(fill="x", side="bottom")

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

    # -- toolbar -----------------------------------------------------------
    def _build_toolbar(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=8)
        ttk.Button(bar, text="Open…", command=self.on_open).pack(side="left")
        ttk.Button(bar, text="Save", command=self.on_save).pack(side="left", padx=4)
        ttk.Button(bar, text="Save As…", command=self.on_save_as).pack(side="left")

    # -- mech tab ----------------------------------------------------------
    def _build_mech_tab(self):
        mwrap = ttk.Frame(self.mech_tab)
        mwrap.pack(side="left", fill="both", expand=True, padx=(0, 4), pady=4)
        cols = ("idx", "name", "code", "guid")
        self.mech_tree = ttk.Treeview(mwrap, columns=cols, show="headings",
                                      selectmode="browse")
        self.mech_tree.heading("idx", text="#")
        self.mech_tree.heading("name", text="Mech")
        self.mech_tree.heading("code", text="Asset ID")
        self.mech_tree.heading("guid", text="Instance GUID")
        self.mech_tree.column("idx", width=36, anchor="center")
        self.mech_tree.column("name", width=210)
        self.mech_tree.column("code", width=120)
        self.mech_tree.column("guid", width=290)
        msb = ttk.Scrollbar(mwrap, orient="vertical", command=self.mech_tree.yview)
        self.mech_tree.configure(yscrollcommand=msb.set)
        self.mech_tree.pack(side="left", fill="both", expand=True)
        msb.pack(side="right", fill="y")

        side = ttk.Frame(self.mech_tab)
        side.pack(side="left", fill="y", pady=4)
        ttk.Button(side, text="Add Mech…", command=self.on_add_mech).pack(fill="x", pady=2)
        ttk.Button(side, text="Edit Loadout…", command=self.on_edit_loadout).pack(fill="x", pady=2)
        ttk.Button(side, text="Set Hardpoints…", command=self.on_set_hardpoints).pack(fill="x", pady=2)
        ttk.Button(side, text="Change Chassis…", command=self.on_change_chassis).pack(fill="x", pady=2)
        ttk.Button(side, text="Repair (full armor)", command=self.on_repair).pack(fill="x", pady=2)
        ttk.Button(side, text="Repair ALL Mechs", command=self.on_repair_all).pack(fill="x", pady=2)
        ttk.Button(side, text="Remove", command=self.on_remove_mech).pack(fill="x", pady=2)

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

        # Current inventory list
        iwrap = ttk.Frame(self.inv_tab)
        iwrap.pack(fill="both", expand=True, padx=4, pady=4)
        cols = ("type", "item", "count")
        self.inv_tree = ttk.Treeview(iwrap, columns=cols, show="headings")
        self.inv_tree.heading("type", text="Asset Type")
        self.inv_tree.heading("item", text="Item ID")
        self.inv_tree.heading("count", text="Count")
        self.inv_tree.column("type", width=180)
        self.inv_tree.column("item", width=300)
        self.inv_tree.column("count", width=70, anchor="center")
        isb = ttk.Scrollbar(iwrap, orient="vertical", command=self.inv_tree.yview)
        self.inv_tree.configure(yscrollcommand=isb.set)
        self.inv_tree.pack(side="left", fill="both", expand=True)
        isb.pack(side="right", fill="y")

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
                  foreground="#666").pack(anchor="w", padx=6)

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

    # -- mech actions ------------------------------------------------------
    def _refresh_mechs(self):
        self.mech_tree.delete(*self.mech_tree.get_children())
        for i, m in enumerate(self.save.mechs()):
            self.mech_tree.insert("", "end", iid=str(i),
                                  values=(i, mech_display(m.chassis),
                                          variant_code(m.chassis), m.guid.hex()))

    def _selected_mech_index(self):
        sel = self.mech_tree.selection()
        return int(sel[0]) if sel else None

    def on_add_mech(self):
        if not self._guard():
            return
        chassis = self._pick_chassis("Add Mech")
        if chassis is None:
            return
        try:
            _guid, status = self.save.add_mech(chassis)
            self._refresh_mechs()
            label = mech_display(chassis)
            if status == "exact":
                self.status.set(f"Added {label} — exact copy of one you own. Remember to Save.")
            elif status == "real-layout":
                self.status.set(f"Added {label} with its real hardpoints (empty). "
                                "Fit weapons in Edit Loadout. Remember to Save.")
                messagebox.showinfo(
                    "Mech added",
                    f"Added a {label}. Your save had a real {label} loadout on record, "
                    "so it got that chassis's correct (empty) hardpoints.\n\n"
                    "Use Edit Loadout to fit weapons and set groups — no Mech Lab needed.")
            else:
                self.status.set(f"Added {label} (approximate — set hardpoints / refit in Mech Lab). Remember to Save.")
                messagebox.showinfo(
                    "Approximate mech added",
                    f"You don't own a {label} and your save has no {label} loadout to "
                    "copy, so it was added as an approximate clone with its weapons "
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
        mech = self.save.mechs()[idx]
        if not mech.weapon_slots():
            if not self._apply_layout_dialog(mech, idx, empty=True):
                return
            mech = self.save.mechs()[idx]   # re-read with the new hardpoints
        LoadoutDialog(self, mech, catalog=self.cat, on_apply=lambda: (self._refresh_mechs(),
                      self.status.set(f"Loadout updated for mech #{idx}. Remember to Save.")))

    def on_set_hardpoints(self):
        if not self._guard():
            return
        idx = self._selected_mech_index()
        if idx is None:
            return self._need_selection()
        mech = self.save.mechs()[idx]
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
        m = self.save.mechs()[idx]
        m.chassis = chassis
        m.flush()
        self._refresh_mechs()
        self.status.set(f"Mech #{idx} chassis -> {chassis}. Remember to Save.")

    def on_repair(self):
        idx = self._selected_mech_index()
        if idx is None:
            return self._need_selection()
        m = self.save.mechs()[idx]
        m.repair()
        m.flush()
        self.status.set(f"Mech #{idx} repaired to full armor. Remember to Save.")

    def on_repair_all(self):
        if not self._guard():
            return
        n = 0
        for m in self.save.mechs():
            m.repair()
            m.flush()
            n += 1
        self.status.set(f"Repaired all {n} mechs (armor restored to installed). Remember to Save.")
        messagebox.showinfo("Repair All", f"Restored armor on {n} mechs.")

    def on_remove_mech(self):
        idx = self._selected_mech_index()
        if idx is None:
            return self._need_selection()
        m = self.save.mechs()[idx]
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
        self.inv_tree.delete(*self.inv_tree.get_children())
        for it in self.save.weapon_inventory():
            self.inv_tree.insert("", "end", values=(it.asset_type, it.asset_name, it.count),
                                 tags=("weapon",))
        for it in self.save.equipment_inventory():
            self.inv_tree.insert("", "end", values=(it.asset_type, it.asset_name, it.count),
                                 tags=("equipment",))

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

    def _selected_inv_row(self):
        sel = self.inv_tree.selection()
        if not sel:
            return None
        vals = self.inv_tree.item(sel[0], "values")
        tags = self.inv_tree.item(sel[0], "tags")
        return {"type": vals[0], "name": vals[1], "count": vals[2],
                "inv": tags[0] if tags else "weapon"}

    def on_set_item_count(self):
        if not self._guard():
            return
        row = self._selected_inv_row()
        if row is None:
            return self._need_selection()
        new = simpledialog.askinteger("Set count", f"New count for {row['name']}:",
                                      initialvalue=int(row["count"]), minvalue=0)
        if new is None:
            return
        for it in (self.save.weapon_inventory() if row["inv"] == "weapon"
                   else self.save.equipment_inventory()):
            if it.asset_name == row["name"]:
                it.count = new
                break
        self._refresh_inventory()
        self.status.set(f"Set {row['name']} count to {new}. Remember to Save.")

    def on_remove_item(self):
        if not self._guard():
            return
        row = self._selected_inv_row()
        if row is None:
            return self._need_selection()
        self.save.remove_item(row["inv"], row["name"])
        self._refresh_inventory()
        self.status.set(f"Removed {row['name']}. Remember to Save.")

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

    def __init__(self, parent, mech, on_apply=None, catalog=None):
        super().__init__(parent)
        self.mech = mech
        self.on_apply = on_apply
        self.title(f"Edit Loadout — {mech_display(mech.chassis)}")
        self.geometry("760x620")
        self.transient(parent)

        # item catalog: use the save-merged one if given, else the static lists
        cat = catalog or {"weapon": list(WEAPONS), "equipment": list(EQUIPMENT), "ammo": list(AMMO)}
        weapons = cat.get("weapon", WEAPONS)
        equipment = cat.get("equipment", EQUIPMENT)
        ammo = cat.get("ammo", AMMO)

        # weapon options per hardpoint class (name list), from the catalog
        self._by_class = {"EH": [], "BH": [], "MH": [], "Melee": []}
        for name, atype in weapons:
            cls = weapon_class(name, atype)
            if cls in self._by_class:
                self._by_class[cls].append((name, atype))
        for cls in self._by_class:
            self._by_class[cls].sort()

        # equipment options by slot type
        self._jumpjets = sorted((n, t) for n, t in equipment if t == "MWJumpJetDataAsset")
        self._general_equip = sorted([(n, t) for n, t in equipment
                                      if t != "MWJumpJetDataAsset"] + list(ammo))

        self.slots = mech.weapon_slots()
        self.eq_slots = mech.equipment_slots()
        self.slot_widgets = []   # (slot, weapon_var, [group_vars])
        self.eq_widgets = []     # (equip_slot, equip_var)
        self.armor_vars = {}     # location -> StringVar

        self._build()

    def _equip_options(self, slot_type):
        return self._jumpjets if "JumpJet" in slot_type else self._general_equip

    # -- UI ---------------------------------------------------------------
    def _build(self):
        ttk.Label(self, text="Weapons  (pick a weapon per hardpoint; ✓ the fire groups)",
                  font=("", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 2))

        # scrollable weapon area
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True, padx=10)
        canvas = tk.Canvas(outer, highlightthickness=0, height=300)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        frame = ttk.Frame(canvas)
        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # header row
        ttk.Label(frame, text="Hardpoint", width=30).grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text="Weapon", width=26).grid(row=0, column=1, sticky="w")
        for g in range(1, 7):
            ttk.Label(frame, text=str(g), width=3).grid(row=0, column=1 + g)

        for r, slot in enumerate(self.slots, start=1):
            cls = slot.hardpoint_class or "?"
            loc = slot.slot_id.rsplit("_", 1)[0] if "_" in slot.slot_id else slot.slot_id
            ttk.Label(frame, text=f"{HARDPOINT_LABEL.get(cls, cls)}: {loc}",
                      width=30).grid(row=r, column=0, sticky="w", pady=1)

            options = ["(empty)"] + [n for n, _t in self._by_class.get(cls, [])]
            cur = slot.weapon_name
            if cur not in ("None", "") and cur not in options:
                options.insert(1, cur)   # keep an unrecognized current weapon
            var = tk.StringVar(value="(empty)" if slot.is_empty else cur)
            cb = ttk.Combobox(frame, textvariable=var, values=options, width=24, state="readonly")
            cb.grid(row=r, column=1, sticky="w", padx=2)

            gvars = []
            for g in range(1, 7):
                gv = tk.BooleanVar(value=(g in slot.groups()))
                ttk.Checkbutton(frame, variable=gv).grid(row=r, column=1 + g)
                gvars.append(gv)
            self.slot_widgets.append((slot, var, gvars))

        # equipment rows (in the same scroll frame, below the weapons)
        er = len(self.slots) + 2
        if self.eq_slots:
            ttk.Label(frame, text="Equipment  (heat sinks, ammo, jump jets…)",
                      font=("", 9, "bold")).grid(row=er, column=0, columnspan=3,
                                                 sticky="w", pady=(10, 2))
            er += 1
            for slot in self.eq_slots:
                opts = self._equip_options(slot.slot_type)
                names = ["(empty)"] + [n for n, _t in opts]
                cur = slot.equip_name
                if cur not in ("None", "") and cur not in names:
                    names.insert(1, cur)
                kind = "JumpJet" if "JumpJet" in slot.slot_type else "General"
                ttk.Label(frame, text=f"{slot.part_label}  [{kind}]",
                          width=30).grid(row=er, column=0, sticky="w", pady=1)
                var = tk.StringVar(value="(empty)" if slot.is_empty else cur)
                ttk.Combobox(frame, textvariable=var, values=names, width=24,
                             state="readonly").grid(row=er, column=1, columnspan=6, sticky="w", padx=2)
                self.eq_widgets.append((slot, var))
                er += 1

        # armor
        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=10, pady=8)
        ttk.Label(self, text="Armor (current)", font=("", 10, "bold")).pack(anchor="w", padx=10)
        af = ttk.Frame(self)
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
        ttk.Button(self, text="Max armor (= installed)", command=self._max_armor).pack(anchor="w", padx=10, pady=2)

        # buttons
        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=10, pady=10)
        ttk.Button(btns, text="Apply", command=self._apply).pack(side="right")
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=6)

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
        ename_to_type = {n: t for n, t in (self._jumpjets + self._general_equip)}
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
        self.mech.flush()
        if self.on_apply:
            self.on_apply()
        self.destroy()


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
                  foreground="#666").pack(padx=8, pady=(0, 6), anchor="w")
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
