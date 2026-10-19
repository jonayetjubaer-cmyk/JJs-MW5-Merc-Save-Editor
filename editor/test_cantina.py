"""Cantina progress, zero-point paths, and the separate upgrade-unlock model."""
from types import SimpleNamespace
import unittest

from cantina import TIERS, REWARDS, paths, max_paths, sync_unlocks
from savefile import write_int, write_fstring_payload, read_fstring_payload, _path
from test_pilot_import import _leaf, _struct
from ue_property import ArrayValue, Property, PropertyList, Reader, Writer, read_property_list, write_property_list


def asset_id(kind, asset):
    return _struct('ID', [
        _struct('PrimaryAssetType', [
            _leaf('Name', 'NameProperty', write_fstring_payload(kind))], 'PrimaryAssetType'),
        _leaf('PrimaryAssetName', 'NameProperty', write_fstring_payload(asset))], 'PrimaryAssetId')


def record(asset, points):
    return PropertyList([
        _struct('Career', [asset_id('MWCareerPathAsset', asset)], 'CareerPathAssetId'),
        _leaf('Progress', 'IntProperty', write_int(points)),
    ])


def array(name, kind, elements):
    w = Writer()
    w.i64(0)
    w.fstring('StructProperty')
    return Property(name, 'ArrayProperty', w.bytes(), b'',
                    ArrayValue('StructProperty', len(elements), elements,
                               inner_tag_name=name, inner_struct_name=kind,
                               inner_struct_guid=bytes(16), elements_leading_byte=b'\0'),
                    array_leading_byte=b'\0')


def blob(plist):
    writer = Writer()
    write_property_list(writer, plist)
    return writer.bytes()


def unlocked_names(save):
    prop = save.model('MechTraitModel').plist.get('UnlockedMechTraitsList')
    return [read_fstring_payload(_path(el, 'ID', 'PrimaryAssetName').raw_payload)
            for el in prop.decoded.elements] if prop else []


class CantinaHarness:
    def __init__(self, records=None, unlocks=None):
        errand = PropertyList([
            _leaf('CareerRewardClaimList', 'UnknownProperty', b'claims untouched'),
            _leaf('OfferSaveData', 'UnknownProperty', b'jobs untouched')])
        if records is not None:
            errand.properties.append(_struct('CareerPathList', [
                array('Progress', 'CareerPathProgress', records)], 'CareerPathProgressList'))
        traits = PropertyList([_leaf('OtherField', 'UnknownProperty', b'untouched')])
        if unlocks is not None:
            traits.properties.append(array('UnlockedMechTraitsList', 'MechTraitDataAssetId', [
                PropertyList([asset_id('MWMechTraitDataAsset', name)]) for name in unlocks]))
        self.models = {name: SimpleNamespace(plist=pl) for name, pl in
                       [('ErrandModel', errand), ('MechTraitModel', traits)]}

    def model(self, name):
        return self.models[name]

    def bytes(self):
        return {name: blob(model.plist) for name, model in self.models.items()}

    def reload(self):
        for model in self.models.values():
            model.plist = read_property_list(Reader(blob(model.plist)))


class CantinaTests(unittest.TestCase):
    def test_zero_point_paths_are_visible_without_creating_records_on_read(self):
        for records in (None, []):
            with self.subTest(records=records):
                save = CantinaHarness(records)
                before = save.bytes()
                result = paths(save)
                self.assertEqual({p.asset for p in result}, set(TIERS))
                self.assertEqual([(p.points, p.tier, p.progress) for p in result], [(0, 0, None)] * 5)
                self.assertEqual(save.bytes(), before)

    def test_only_edited_missing_path_is_created_and_survives_serialization(self):
        save = CantinaHarness()
        target = next(p for p in paths(save) if p.asset == 'WarDogCareerPath')
        target.set_tier(2)
        save.reload()
        result = paths(save)
        self.assertEqual([(p.asset, p.points) for p in result if p.progress is not None],
                         [('WarDogCareerPath', 17)])
        self.assertEqual(unlocked_names(save), ['IncreasedSensorRange_Trait1',
                                               'IncreasedLockRetentionAndLoseLockTime_Trait1'])
        errand = save.model('ErrandModel').plist
        self.assertEqual(errand.get('CareerRewardClaimList').raw_payload, b'claims untouched')
        self.assertEqual(errand.get('OfferSaveData').raw_payload, b'jobs untouched')
        self.assertEqual(save.model('MechTraitModel').plist.get('OtherField').raw_payload, b'untouched')

    def test_setting_subtier_points_creates_progress_without_unlocking_upgrades(self):
        save = CantinaHarness()
        paths(save)[0].set_points(4)
        save.reload()
        self.assertEqual(paths(save)[0].points, 4)
        self.assertEqual(unlocked_names(save), [])

    def test_max_creates_all_paths_and_50_rewards_and_is_idempotent(self):
        save = CantinaHarness()
        self.assertEqual(max_paths(paths(save)), 5)
        save.reload()
        self.assertTrue(all(p.points == 349 and p.tier == 10 for p in paths(save)))
        self.assertEqual(len(unlocked_names(save)), 50)
        self.assertEqual(len(set(unlocked_names(save))), 50)
        for final_reward in ('ReducedWeaponCooldown_Trait1', 'ReducedHeatGeneration_Trait1',
                             'IncreasedHeatCapacity_Trait2', 'ReducedWeaponHeat_Trait1',
                             'IncreasedTopSpeed_Trait1'):
            self.assertIn(final_reward, unlocked_names(save))
        before = save.bytes()
        max_paths(paths(save))
        self.assertEqual(sync_unlocks(save), 0)
        self.assertEqual(save.bytes(), before)

    def test_sync_repairs_already_maxed_points_without_changing_errands(self):
        existing = [name for rewards in REWARDS.values() for name in rewards][:8]
        save = CantinaHarness([record(name, 349) for name in TIERS], existing)
        before = blob(save.model('ErrandModel').plist)
        self.assertEqual(sync_unlocks(save), 42)
        save.reload()
        self.assertEqual(len(unlocked_names(save)), 50)
        self.assertEqual(blob(save.model('ErrandModel').plist), before)

    def test_lowering_points_never_revokes_existing_or_mod_upgrades(self):
        save = CantinaHarness([record('WarDogCareerPath', 349)],
                             ['ModTrait', 'IncreasedTopSpeed_Trait1'])
        item = paths(save)[0]
        item.set_tier(2)
        self.assertIn('ModTrait', unlocked_names(save))
        self.assertIn('IncreasedTopSpeed_Trait1', unlocked_names(save))
        self.assertEqual(len(unlocked_names(save)), 4)
        item.set_tier(0)
        self.assertEqual(item.points, 0)
        self.assertEqual(len(unlocked_names(save)), 4)

    def test_duplicate_threshold_unlocks_both_mech_collector_rewards(self):
        save = CantinaHarness([record('MechCollectorCareerPath', 0)])
        item = paths(save)[0]
        item.set_tier(5)
        self.assertEqual((item.points, item.tier), (95, 6))
        self.assertEqual(len(unlocked_names(save)), 6)
        self.assertIn('ReducedMissileHeat_Trait1', unlocked_names(save))
        self.assertIn('IncreasedEnergyDamage_Trait2', unlocked_names(save))

    def test_mod_paths_and_higher_progress_are_preserved(self):
        save = CantinaHarness([record('WarDogCareerPath', 400), record('ModCareerPath', 27)], ['ModTrait'])
        max_paths(paths(save))
        self.assertEqual([(p.asset, p.points) for p in paths(save)[:2]],
                         [('WarDogCareerPath', 400), ('ModCareerPath', 27)])
        self.assertEqual(len(unlocked_names(save)), 51)
        mod = paths(save)[1]
        self.assertIsNone(mod.tier)
        before = blob(save.model('MechTraitModel').plist)
        mod.set_points(30)
        self.assertEqual(mod.points, 30)
        self.assertEqual(blob(save.model('MechTraitModel').plist), before)
        with self.assertRaises(ValueError):
            mod.set_tier(1)

    def test_missing_mech_trait_model_fails_before_points_change(self):
        save = CantinaHarness([record('WarDogCareerPath', 17)])
        del save.models['MechTraitModel']
        before = save.bytes()
        with self.assertRaises(ValueError):
            paths(save)[0].set_tier(10)
        self.assertEqual(save.bytes(), before)

    def test_malformed_unlocks_fail_before_any_points_or_records_change(self):
        for records in (None, [record('WarDogCareerPath', 17)]):
            save = CantinaHarness(records)
            corrupt = array('UnlockedMechTraitsList', 'MechTraitDataAssetId', [])
            corrupt.decoded = None
            corrupt.raw_payload = b'unsupported'
            save.model('MechTraitModel').plist.properties.append(corrupt)
            before = save.bytes()
            for action in (lambda: max_paths(paths(save)), lambda: paths(save)[0].set_tier(10)):
                with self.assertRaises(ValueError):
                    action()
                self.assertEqual(save.bytes(), before)

    def test_duplicate_and_unsupported_progress_are_rejected_without_rewrite(self):
        for records in ([record('WarDogCareerPath', 5)] * 2, [record('WarDogCareerPath', -1)]):
            save = CantinaHarness(records)
            before = save.bytes()
            with self.assertRaises(ValueError):
                paths(save)
            self.assertEqual(save.bytes(), before)
        save = CantinaHarness([])
        progress = save.model('ErrandModel').plist.get('CareerPathList').decoded.get('Progress')
        progress.decoded.inner_struct_name = 'UnknownCareerSchema'
        with self.assertRaises(ValueError):
            paths(save)

    def test_invalid_values_leave_both_models_unchanged(self):
        save = CantinaHarness()
        before = save.bytes()
        item = paths(save)[0]
        for value in (-1, 2147483648, True, 1.5):
            with self.assertRaises(ValueError):
                item.set_points(value)
        for value in (-1, 11, True, 1.5):
            with self.assertRaises(ValueError):
                item.set_tier(value)
        self.assertEqual(save.bytes(), before)

    def test_missing_errand_model_is_unavailable(self):
        save = CantinaHarness()
        del save.models['ErrandModel']
        self.assertEqual(paths(save), [])

    def test_omitted_zero_progress_field_is_read_only_until_explicit_edit(self):
        element = record('WarDogCareerPath', 0)
        element.properties.pop()
        save = CantinaHarness([element])
        before = save.bytes()
        self.assertEqual(paths(save)[0].points, 0)
        self.assertEqual(sync_unlocks(save), 0)
        self.assertEqual(save.bytes(), before)
        paths(save)[0].set_tier(1)
        save.reload()
        self.assertEqual(paths(save)[0].points, 5)
        self.assertEqual(len(unlocked_names(save)), 1)


if __name__ == '__main__':
    unittest.main()
