# Translating the editor

MW5 lists six interface languages on its [Steam page](https://store.steampowered.com/app/784080/MechWarrior_5_Mercenaries/):
English (`en`), French (`fr`), German (`de`), Russian (`ru`), Japanese (`ja`),
and Latin American Spanish (`es-419`). These files translate the editor's UI;
they are not extracted from, or endorsed as official translations by, the game.
The initial translations were AI-assisted and benefit from native-speaker review.

Each UTF-8 JSON file maps an English source message to a translated message.
`en.json` is the source inventory. Keep its keys unchanged in the other files.
Preserve placeholders such as `{p0}`, `{p1}` and `{p0:,}` exactly, but rearrange
them as the language requires. Preserve paths, file extensions, asset IDs and
numeric limits. `\n` represents a line break. Do not translate JSON keys, engine
identifiers or user-authored content in the save.

For a new UI message, use `_("English message")` in Python, or
`_("Message {p0}", p0=value)` for a dynamic value. Add its key to `en.json` and
all five translated catalogs. Enum labels are translated only at the widget
boundary: their bound variables must retain the canonical model value. Use
`LocalizedCombobox` for UI enums, and translate only the `(empty)` sentinel in
loadout asset choices. Catalog asset names themselves stay verbatim.

Run from the repository root:

```text
python -m unittest discover -s editor -p "test_*.py"
```

The localization tests check catalog coverage, format placeholders, fallback,
canonical choice values and preservation of pending edits. Inspect the affected
screens for clipping too. Native OS file dialogs/message-box buttons follow the
operating system's localization. Scarab output and low-level exceptions remain
technical diagnostic text for support.

The release workflow includes the whole `locales` directory. Keep it alongside
the executable in the extracted download. No network translation service is used
by the editor.
