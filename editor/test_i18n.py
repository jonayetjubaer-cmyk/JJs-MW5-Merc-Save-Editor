"""Localization must change presentation without changing save operations."""
import ast
import json
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

import gui
import i18n
from localized_widgets import LocalizedCombobox
from test_cantina import CantinaHarness
from test_pilot_appearance import _pilot_with_bio
from test_pilot_import import PilotHarness


class CatalogTests(unittest.TestCase):
    def tearDown(self):
        i18n.set_language('en')
        i18n.catalog.cache_clear()

    def test_all_catalogs_cover_source_messages_and_preserve_placeholders(self):
        folder = Path(i18n.__file__).parent / 'locales'
        english = json.loads((folder / 'en.json').read_text(encoding='utf-8'))
        for code in i18n.LANGUAGES:
            with self.subTest(language=code):
                data = json.loads((folder / f'{code}.json').read_text(encoding='utf-8'))
                self.assertEqual(set(data), set(english))
                for key, value in data.items():
                    self.assertTrue(value.strip(), key)
                    self.assertEqual(i18n.fields(key), i18n.fields(value), key)
                    self.assertNotIn('\ufffd', value)
                if code != 'en':
                    self.assertEqual(len(i18n.catalog(code)), len(data))
        for file in ('gui.py', 'localized_widgets.py'):
            tree = ast.parse((folder.parent / file).read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == '_' and node.args
                        and isinstance(node.args[0], ast.Constant)):
                    self.assertIn(node.args[0].value, english)

    def test_region_matching_and_unknown_locales(self):
        for language, expected in (('fr_CA', 'fr'), ('de-DE', 'de'), ('ru_RU', 'ru'),
                                   ('ja-JP', 'ja'), ('es_MX', 'es-419'),
                                   ('es-ES', 'es-419'), ('zh_CN', 'en'), (None, 'en')):
            self.assertEqual(i18n.normalize_language(language), expected)

    def test_missing_messages_and_invalid_catalogs_fall_back_to_english(self):
        with patch('i18n.Path.read_text', return_value='not json'):
            i18n.catalog.cache_clear()
            self.assertEqual(i18n.translate_for('ja', 'Save'), 'Save')
        with patch('i18n.Path.read_text', return_value='{"Save":"", "Value {p0}":"値 {bad}"}'):
            i18n.catalog.cache_clear()
            self.assertEqual(i18n.translate_for('ja', 'Value {p0}', p0='Asset_MDA'), 'Value Asset_MDA')
        self.assertEqual(i18n.translate_for('de', 'UnknownAsset_MDA'), 'UnknownAsset_MDA')

    def test_bad_placeholder_syntax_does_not_disable_other_translations(self):
        with patch('i18n.Path.read_text', return_value='{"Save":"保存", "Bad":"{broken"}'):
            i18n.catalog.cache_clear()
            self.assertEqual(i18n.translate_for('ja', 'Save'), '保存')
            self.assertEqual(i18n.translate_for('ja', 'Bad'), 'Bad')

    def test_formatting_preserves_raw_asset_ids_and_numeric_formats(self):
        for code in i18n.LANGUAGES:
            message = i18n.translate_for(code, 'Loaded {p0} — {p1} mechs, {p2} pilots, {p3:,} C-Bills. {p4}',
                                         p0='セーブ.sav', p1=5, p2=3, p3=123456, p4='Asset_MDA')
            self.assertIn('セーブ.sav', message)
            self.assertIn('123,456', message)
            self.assertIn('Asset_MDA', message)


class LocalizedUiTests(unittest.TestCase):
    def tearDown(self):
        i18n.set_language('en')

    def make_app(self, code):
        with patch('gui.load_pref', side_effect=lambda key, default=None:
                   code if key == 'language' else False if key == 'check_updates' else default):
            app = gui.EditorApp()
        self.addCleanup(lambda: self.close_app(app))
        app.update()
        return app

    @staticmethod
    def close_app(app):
        try:
            app.destroy()
        except tk.TclError:
            pass

    def test_each_language_opens_and_filters_keep_canonical_values(self):
        for code in i18n.LANGUAGES:
            with self.subTest(language=code):
                app = self.make_app(code)
                self.assertEqual(app.nb.tab(app.inv_tab, 'text'), i18n.tr('Inventory'))
                combos = []
                def walk(widget):
                    for child in widget.winfo_children():
                        if isinstance(child, LocalizedCombobox):
                            combos.append(child)
                        walk(child)
                walk(app)
                # The editor installs its own event handlers after construction.
                # They must still see the canonical keys from our widget.
                inventory = next(w for w in combos if w.canonical is app.inv_type_var)
                observed = []
                inventory.bind('<<ComboboxSelected>>', lambda e: observed.append(app.inv_type_var.get()))
                inventory.current(2)
                inventory.event_generate('<<ComboboxSelected>>')
                app.update()
                self.assertEqual(observed, ['ammo'])
                self.assertEqual(app.inv_type_var.get(), 'ammo')
                # Minimum supported window width must keep both toolbar rows usable.
                app.geometry('820x600')
                app.update()
                for toolbar in app.winfo_children():
                    if not isinstance(toolbar, gui.ttk.Frame):
                        continue
                    for widget in toolbar.winfo_children():
                        self.assertGreaterEqual(widget.winfo_width(), widget.winfo_reqwidth())
                app.inv_sort_var.set('Column order')
                sort = next(w for w in combos if w.canonical is app.inv_sort_var)
                self.assertEqual(sort.get(), i18n.tr('Column order'))
                sort.current(1)
                sort.event_generate('<<ComboboxSelected>>')
                app.update()
                self.assertEqual(app.inv_sort_var.get(), 'Z–A')
                self.assertEqual(app._inv_sort, ('item', True))
                app.destroy()

    def test_language_selection_keeps_pending_edits_and_loaded_save(self):
        app = self.make_app('en')
        pilot = _pilot_with_bio()
        app.save = PilotHarness([pilot.element])
        app._refresh_pilots()
        app.pilot_vars['callsign'].set('Unsaved name')
        app.pilot_bio_text.insert('end', ' Unsaved bio')
        before = app.save.pilots()[0].bio_parts()
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'prefs.json'
            config.write_text('{"theme":"dark","catalog_dir":"keep"}', encoding='utf-8')
            with patch('gui._CONFIG_PATH', str(config)):
                app.language_var.set('日本語')
                app._on_language_change()
                self.assertEqual(json.loads(config.read_text()),
                                 {'theme':'dark', 'catalog_dir':'keep', 'language':'ja'})
        self.assertEqual(i18n.get_language(), 'en')
        self.assertEqual(app.pilot_vars['callsign'].get(), 'Unsaved name')
        self.assertIn('Unsaved bio', app.pilot_bio_text.get('1.0', 'end'))
        self.assertEqual(app.save.pilots()[0].bio_parts(), before)
        self.assertEqual(app.nb.tab(app.pilot_tab, 'text'), 'Pilots')

    def test_translated_empty_slot_returns_the_canonical_sentinel(self):
        app = self.make_app('ja')
        var = tk.StringVar(app, 'WeaponAsset_MDA')
        combo = gui._readable_combobox(app, textvariable=var, width=20,
                                      values=('(empty)', 'WeaponAsset_MDA'), state='readonly')
        self.assertEqual(combo['values'][1], 'WeaponAsset_MDA')
        combo.current(0)
        self.assertEqual(var.get(), '(empty)')
        self.assertEqual(combo.get(), i18n.tr('(empty)'))

    def test_translated_cantina_browsing_preserves_bytes(self):
        for code in ('fr','de','ru','ja','es-419'):
            app = self.make_app(code)
            app.save = CantinaHarness()
            before = app.save.bytes()
            app._refresh_cantina()
            row = app.cantina_tree.item('0', 'values')
            self.assertEqual(row[-1], i18n.tr('Not started'))
            self.assertEqual(app.save.bytes(), before)
            app.destroy()


if __name__ == '__main__':
    unittest.main()
