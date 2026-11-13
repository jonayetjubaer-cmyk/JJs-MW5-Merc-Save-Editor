"""Exercise owned pickers and explicit modal parenting without a game save."""
from types import SimpleNamespace
import datetime
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

from gui import EditorApp, SearchChoiceDialog, SearchablePicker


class DialogRoutingTests(unittest.TestCase):
    def test_faction_double_click_selects_the_clicked_row(self):
        app = SimpleNamespace(faction_tree=Mock(), on_edit_standing=Mock())
        app.faction_tree.identify_row.return_value = "3"
        self.assertEqual(EditorApp._on_faction_double_click(app, SimpleNamespace(y=42)), "break")
        app.faction_tree.selection_set.assert_called_once_with("3")
        app.on_edit_standing.assert_called_once()

    def test_faction_dialog_is_owned_by_editor(self):
        faction = SimpleNamespace(name="Test Faction", standing=10)
        app = SimpleNamespace(_guard=lambda: True, faction_tree=Mock(),
                              save=SimpleNamespace(factions=lambda: [faction]))
        app.faction_tree.selection.return_value = ("0",)
        with patch("gui.simpledialog.askinteger", return_value=None) as ask:
            EditorApp.on_edit_standing(app)
        self.assertIs(ask.call_args.kwargs["parent"], app)

class PickerUiTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.geometry("500x400")
        self.root.update()

    def tearDown(self):
        if hasattr(self, "root"):
            self.root.update_idletasks()
            self.root.destroy()

    def test_work_order_dialog_shows_current_date_and_accepts_one_day(self):
        with patch("gui.load_pref", side_effect=lambda key, default=None:
                   False if key == "check_updates" else default):
            app = EditorApp()
        self.addCleanup(app.destroy)
        order = SimpleNamespace(
            mech_asset="GHR-5J_MDA",
            execution_date_text="3059-08-29",
            execution_date=datetime.date(3059, 8, 29),
            event_index=3,
        )

        def set_date(value, *, current_date):
            self.assertEqual(current_date, datetime.date(3059, 8, 27))
            order.execution_date_text = value

        order.set_execution_date_text = set_date

        def set_work_order_execution_date(selected_order, value, *, current_date):
            selected_order.set_execution_date_text(value, current_date=current_date)

        app.save = SimpleNamespace(
            campaign_date=datetime.date(3059, 8, 27),
            set_work_order_execution_date=set_work_order_execution_date,
            mission_launch_events=lambda: [],
        )
        app._work_orders_by_index = {3: order}
        app.work_order_tree.insert("", "end", iid="3", values=(
            "GHR-5J", order.execution_date_text, 180))
        app.work_order_tree.selection_set("3")
        app._refresh_work_orders = Mock()
        placement = []
        def choose_one_day_and_apply():
            dialog = next(
                child for child in app.winfo_children()
                if isinstance(child, tk.Toplevel))
            dialog.update_idletasks()
            placement.append((
                dialog.winfo_rootx(), dialog.winfo_rooty(),
                dialog.winfo_width(), dialog.winfo_height(),
                dialog.winfo_screenwidth(), dialog.winfo_screenheight(),
            ))
            widgets = []

            def walk(parent):
                for child in parent.winfo_children():
                    widgets.append(child)
                    walk(child)

            walk(dialog)
            entries = [widget for widget in widgets if isinstance(widget, ttk.Entry)]
            self.assertEqual(len(entries), 1)
            completion_entry = entries[0]
            self.assertFalse(completion_entry.instate(("readonly",)))
            self.assertFalse(any(
                isinstance(widget, ttk.Label)
                and widget.cget("text") == "Current in-game date:"
                for widget in widgets))
            completion_entry.delete(0, "end")
            completion_entry.insert(0, "1")
            self.assertFalse(any(
                isinstance(widget, ttk.Button) and widget.cget("text") == "Tomorrow"
                for widget in widgets))
            next(button for button in widgets
                 if isinstance(button, ttk.Button)
                 and button.cget("text") == "Apply").invoke()

        app.after(100, choose_one_day_and_apply)
        EditorApp.on_edit_work_order_date(app)

        x, y, width, height, screen_width, screen_height = placement[0]
        self.assertLess(abs(x + width / 2 - screen_width / 2), 25)
        self.assertLess(abs(y + height / 2 - screen_height / 2), 25)
        self.assertEqual(order.execution_date_text, "3059-08-28")
        app._refresh_work_orders.assert_called_once_with()
        self.assertEqual(app.work_order_tree.selection(), ("3",))

    def test_work_order_dialog_applies_one_date_to_all_selected_orders(self):
        with patch("gui.load_pref", side_effect=lambda key, default=None:
                   False if key == "check_updates" else default):
            app = EditorApp()
        self.addCleanup(app.destroy)
        self.assertEqual(str(app.work_order_tree.cget("selectmode")), "extended")
        orders = {
            index: SimpleNamespace(
                mech_asset=f"MECH-{index}_MDA",
                execution_date_text=f"3059-08-{27 + index}",
                execution_date=datetime.date(3059, 8, 27 + index),
                event_index=index,
            )
            for index in (3, 4)
        }

        def set_work_order_execution_date(order, value, *, current_date):
            self.assertEqual(current_date, datetime.date(3059, 8, 27))
            order.execution_date_text = value

        app.save = SimpleNamespace(
            campaign_date=datetime.date(3059, 8, 27),
            set_work_order_execution_date=set_work_order_execution_date,
            mission_launch_events=lambda: [],
        )
        app._work_orders_by_index = orders
        for index, order in orders.items():
            app.work_order_tree.insert(
                "", "end", iid=str(index),
                values=(order.mech_asset, order.execution_date_text, index))
        app.work_order_tree.selection_set("3", "4")
        app._refresh_work_orders = Mock()

        def choose_date_and_apply():
            dialog = next(
                child for child in app.winfo_children()
                if isinstance(child, tk.Toplevel))
            widgets = []

            def walk(parent):
                for child in parent.winfo_children():
                    widgets.append(child)
                    walk(child)

            walk(dialog)
            entries = [widget for widget in widgets if isinstance(widget, ttk.Entry)]
            completion_entry = next(
                entry for entry in entries if not entry.instate(("readonly",)))
            labels = [widget.cget("text") for widget in widgets
                      if isinstance(widget, ttk.Label)]
            self.assertTrue(any("2" in label for label in labels))
            completion_entry.delete(0, "end")
            completion_entry.insert(0, "5")
            next(button for button in widgets
                 if isinstance(button, ttk.Button)
                 and button.cget("text") == "Apply").invoke()

        app.after(100, choose_date_and_apply)
        EditorApp.on_edit_work_order_date(app)

        self.assertEqual([order.execution_date_text for order in orders.values()],
                         ["3059-09-01", "3059-09-01"])
        app._refresh_work_orders.assert_called_once_with()
        self.assertEqual(app.work_order_tree.selection(), ("3", "4"))

    def test_work_order_table_displays_days_remaining(self):
        with patch("gui.load_pref", side_effect=lambda key, default=None:
                   False if key == "check_updates" else default):
            app = EditorApp()
        self.addCleanup(app.destroy)
        order = SimpleNamespace(
            mech_asset="GHR-5J_MDA",
            event_index=3,
            event_id=180,
            execution_date=datetime.date(3059, 1, 21),
            execution_date_text="3059-01-21",
        )
        app.save = SimpleNamespace(
            campaign_date=datetime.date(3059, 1, 1),
            work_orders=lambda: [order],
            mission_launch_events=lambda: [],
        )

        EditorApp._refresh_work_orders(app)

        self.assertEqual(app.work_order_tree.item("3", "values"),
                         ("GHR-5J", "20 days"))
        self.assertEqual(order.execution_date_text, "3059-01-21")

    def test_mission_launch_row_is_visible_but_cannot_be_selected_or_edited(self):
        with patch("gui.load_pref", side_effect=lambda key, default=None:
                   False if key == "check_updates" else default):
            app = EditorApp()
        self.addCleanup(app.destroy)
        order = SimpleNamespace(
            mech_asset="GHR-5J_MDA",
            event_index=3,
            event_id=180,
            execution_date=datetime.date(3059, 8, 29),
            execution_date_text="3059-08-29",
        )
        marker = SimpleNamespace(
            event_index=8,
            event_id=189,
            execution_date=datetime.date(3059, 8, 27),
            is_current=True,
        )
        app.save = SimpleNamespace(
            campaign_date=datetime.date(3059, 8, 27),
            work_orders=lambda: [order],
            mission_launch_events=lambda: [marker],
        )
        EditorApp._refresh_work_orders(app)
        app.nb.select(app.work_order_tab)
        app.update()
        marker_iid = "timeline-8"
        self.assertEqual(app.work_order_tree.item(marker_iid, "values"),
                         ("Mission launch (current)", "0 days"))
        self.assertEqual(str(app.work_order_tree.tag_configure(
            "timeline_marker", "foreground")), "#d32f2f")
        self.assertEqual(str(app.work_order_tree.tag_configure(
            "timeline_marker", "background")), "#e5e5e5")

        bounds = app.work_order_tree.bbox(marker_iid)
        self.assertTrue(bounds)
        x, y, width, height = bounds
        app.work_order_tree.event_generate(
            "<Button-1>", x=x + width // 2, y=y + height // 2)
        app.update()
        self.assertEqual(app.work_order_tree.selection(), ())

        app.work_order_tree.selection_set(marker_iid)
        app._on_work_order_selection()
        self.assertEqual(app.work_order_tree.selection(), ())
        app.work_order_tree.selection_set(marker_iid)
        app.on_edit_work_order_date = Mock()
        app._on_work_order_double_click(SimpleNamespace(y=y + height // 2))
        app.on_edit_work_order_date.assert_not_called()
        self.assertEqual(app.work_order_tree.selection(), ())

    def test_browse_filter_accepts_exact_asset_and_releases_grab(self):
        var = tk.StringVar(self.root, "unchanged")
        picker = SearchablePicker(self.root, textvariable=var, width=24, title="Choose trait")
        picker["values"] = ("Laser Specialist -- Laser_PilotTrait", "Missile Specialist -- Missile_PilotTrait")
        picker.pack()
        checked = []

        def choose():
            dialog = next(w for w in self.root.winfo_children() if isinstance(w, SearchChoiceDialog))
            dialog.query.set("laser")
            checked.append(dialog.results.get(0, "end"))
            dialog.ok()

        self.root.after(100, choose)
        picker._browse()
        self.assertEqual(checked, [("Laser Specialist -- Laser_PilotTrait",)])
        self.assertEqual(var.get(), "Laser Specialist -- Laser_PilotTrait")
        self.assertIsNone(self.root.grab_current())

    def test_cancel_retains_typed_value(self):
        var = tk.StringVar(self.root, "CustomAsset")
        picker = SearchablePicker(self.root, textvariable=var, width=24, title="Choose item")
        picker["values"] = ("ItemA", "ItemB")
        picker.pack()
        self.root.after(100, lambda: next(w for w in self.root.winfo_children()
                                        if isinstance(w, SearchChoiceDialog)).cancel())
        picker._browse()
        self.assertEqual(var.get(), "CustomAsset")
        self.assertIsNone(self.root.grab_current())


if __name__ == "__main__":
    unittest.main()
