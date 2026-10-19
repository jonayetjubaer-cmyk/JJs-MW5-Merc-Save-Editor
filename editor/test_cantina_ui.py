import tkinter as tk
import unittest
from unittest.mock import patch

import gui
from test_cantina import CantinaHarness, record, unlocked_names, blob
from cantina import TIERS


class CantinaUiTests(unittest.TestCase):
    def setUp(self):
        try:
            with patch('gui.load_pref', side_effect=lambda key, default=None:
                       False if key == 'check_updates' else default):
                self.app = gui.EditorApp()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.app.save = CantinaHarness()
        self.app._refresh_cantina()
        self.app.update()

    def tearDown(self):
        if hasattr(self, 'app'):
            self.app.destroy()

    def test_all_zero_paths_are_selectable_and_open_does_not_modify_save(self):
        before = self.app.save.bytes()
        self.app._refresh_cantina()
        self.app.nb.select(self.app.cantina_tab)
        self.app.update()
        self.assertEqual(len(self.app.cantina_tree.get_children()), 5)
        self.assertEqual(self.app.cantina_tree.item('0', 'values')[1:], ('0', '0', 'Not started'))
        self.assertTrue(all(str(button['state']) == 'normal' for button in self.app._cantina_buttons))
        self.assertEqual(self.app.save.bytes(), before)

    def test_set_tier_on_not_started_path_persists_and_updates_row(self):
        self.app.cantina_tree.selection_set('0')
        with patch.object(gui.simpledialog, 'askinteger', return_value=2):
            self.app._edit_cantina(True)
        self.assertEqual(self.app.cantina_tree.item('0', 'values')[1:], ('17', '2', 'Saved'))
        self.assertEqual(len(unlocked_names(self.app.save)), 2)

    def test_max_all_and_cancellation(self):
        before = self.app.save.bytes()
        with patch.object(gui.messagebox, 'askyesno', return_value=False):
            self.app._max_cantina()
        self.assertEqual(self.app.save.bytes(), before)
        with patch.object(gui.messagebox, 'askyesno', return_value=True):
            self.app._max_cantina()
        self.assertEqual(len(unlocked_names(self.app.save)), 50)
        self.assertTrue(all(self.app.cantina_tree.item(i, 'values')[2] == '10'
                            for i in self.app.cantina_tree.get_children()))

    def test_selection_follows_newly_created_path_when_saved_rows_move_first(self):
        self.app.cantina_tree.selection_set('4')
        label = self.app.cantina_tree.item('4', 'values')[0]
        with patch.object(gui.simpledialog, 'askinteger', return_value=2):
            self.app._edit_cantina(True)
        selected = self.app.cantina_tree.selection()[0]
        self.assertEqual(self.app.cantina_tree.item(selected, 'values')[0], label)

    def test_sync_existing_maxed_points_leaves_errands_unchanged(self):
        self.app.save = CantinaHarness([record(name, 349) for name in TIERS])
        self.app._refresh_cantina()
        before = blob(self.app.save.model('ErrandModel').plist)
        with patch.object(gui.messagebox, 'askyesno', return_value=True):
            self.app._sync_cantina_unlocks()
        self.assertEqual(len(unlocked_names(self.app.save)), 50)
        self.assertEqual(blob(self.app.save.model('ErrandModel').plist), before)
        self.assertIn('Added 50', self.app.status.get())

    def test_unsupported_unlock_model_shows_error_without_partial_edit(self):
        del self.app.save.models['MechTraitModel']
        self.app.cantina_tree.selection_set('0')
        before = self.app.save.bytes()
        with patch.object(gui.simpledialog, 'askinteger', return_value=10), \
             patch.object(gui.messagebox, 'showerror') as error:
            self.app._edit_cantina(True)
        error.assert_called_once()
        self.assertIs(error.call_args.kwargs['parent'], self.app)
        self.assertEqual(self.app.save.bytes(), before)


if __name__ == '__main__':
    unittest.main()
