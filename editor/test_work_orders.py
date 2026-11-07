import datetime
import struct
import unittest
from types import SimpleNamespace

from savefile import SaveFile, WorkOrder
from ue_property import ArrayValue, Property, PropertyList, Writer, write_property_list


TICKS_PER_DAY = 864_000_000_000


def _scalar(name, kind, value):
    if isinstance(value, bytes):
        payload = value
    else:
        string = Writer()
        string.fstring(value)
        payload = string.bytes()
    header = Writer()
    header.i64(len(payload))
    header.write(b"\x00")
    return Property(name, kind, header.bytes(), payload)


def _struct(name, struct_name, properties=None, payload=b""):
    header = Writer()
    header.i64(len(payload))
    header.fstring(struct_name)
    header.write(b"\x00" * 16)
    return Property(name, "StructProperty", header.bytes(), payload,
                    decoded=properties, struct_leading_byte=b"\x00")


def _component_data(asset):
    asset_id = _struct("ID", "PrimaryAssetId", PropertyList([
        _scalar("PrimaryAssetName", "NameProperty", asset),
    ]))
    mech_data_id = _struct("MechDataAssetId", "MechDataAssetId", PropertyList([
        asset_id,
    ]))
    item_data = _struct("ItemData", "WorkOrderItemMechData", PropertyList([
        mech_data_id,
    ]))
    work_order_mech = _struct("WorkOrderItemMech", "WorkOrderItemMech",
                              PropertyList([item_data]))
    writer = Writer()
    write_property_list(writer, PropertyList([work_order_mech]))
    archive = writer.bytes()
    return struct.pack("<i", len(archive)) + archive + b"\x00" * 4


def _event(event_id, asset, date_text, class_name="MechRefitTimelineEvent"):
    days = datetime.date.fromisoformat(date_text).toordinal() - 1
    event_id_property = _struct("EventId", "TimelineEventId", PropertyList([
        Property("ID", "IntProperty", struct.pack("<q", 4) + b"\x00",
                 struct.pack("<i", event_id)),
    ]))
    event_data = _struct("EventData", "TimelineEventSaveData", PropertyList([
        event_id_property,
        _struct("ExecutionDate", "DateTime", payload=struct.pack(
            "<q", days * TICKS_PER_DAY + 1_234_567)),
    ]))
    return PropertyList([
        _scalar("TimelineEventClass", "ObjectProperty",
                f"/Game/Campaign/TimelineEvents/{class_name}.{class_name}_C"),
        event_data,
        Property("ComponentSaveData", "ArrayProperty", b"", _component_data(asset)),
    ])


class WorkOrderHarness(SaveFile):
    def __init__(self, events):
        array = ArrayValue("StructProperty", len(events), events)
        ordered_elements = []
        for event in events:
            event_data = event.get("EventData").decoded
            event_id = event_data.get("EventId").decoded.get("ID").raw_payload
            ordered_elements.append(PropertyList([
                Property("ID", "IntProperty", struct.pack("<q", 4) + b"\x00",
                         event_id),
            ]))
        timeline = PropertyList([
            Property("SavedTimelineEventData", "ArrayProperty", b"", b"", decoded=array),
            Property("OrderedTimelineEvents", "ArrayProperty", b"", b"",
                     decoded=ArrayValue("StructProperty", len(ordered_elements),
                                        ordered_elements)),
            _struct("CurrentEvent", "TimelineEventId", PropertyList([
                Property("ID", "IntProperty", struct.pack("<q", 4) + b"\x00",
                         events[0].get("EventData").decoded.get(
                             "EventId").decoded.get("ID").raw_payload),
            ])),
        ])
        self.parsed_timeline = SimpleNamespace(plist=timeline)

    def model(self, name):
        if name != "TimelineModel":
            raise KeyError(name)
        return self.parsed_timeline


class WorkOrderTests(unittest.TestCase):
    def test_refits_are_extracted_and_stably_sorted_by_execution_date(self):
        save = WorkOrderHarness([
            _event(10, "LATE_MDA", "3059-09-02"),
            _event(11, "FIRST_MDA", "3059-09-01"),
            _event(12, "SAME_DAY_MDA", "3059-09-01"),
            _event(13, "NOT_A_REFIT", "3059-08-31", "FinanceEvent"),
        ])

        orders = save.work_orders()

        self.assertEqual([(order.event_id, order.mech_asset) for order in orders], [
            (11, "FIRST_MDA"), (12, "SAME_DAY_MDA"), (10, "LATE_MDA"),
        ])
        self.assertEqual([order.event_index for order in orders], [1, 2, 0])

    def test_mission_launch_events_are_exposed_as_read_only_timeline_markers(self):
        save = WorkOrderHarness([
            _event(189, "CURRENT_MDA", "3059-08-27", "MissionLaunchTimelineEvent"),
            _event(180, "NOT_A_LAUNCH_MDA", "3059-08-28"),
            _event(190, "OTHER_LAUNCH_MDA", "3059-08-29", "MissionLaunchTimelineEvent"),
        ])

        markers = save.mission_launch_events()

        self.assertEqual(
            [(marker.event_id, marker.execution_date, marker.is_current)
             for marker in markers],
            [
                (189, datetime.date(3059, 8, 27), True),
                (190, datetime.date(3059, 8, 29), False),
            ],
        )

    def test_date_edit_preserves_time_ticks_and_rejects_non_iso_date(self):
        prop = _struct("ExecutionDate", "DateTime", payload=struct.pack(
            "<q", 10 * TICKS_PER_DAY + 7_654_321))
        order = WorkOrder(1, "TEST_MDA", 0, prop)

        order.set_execution_date_text("3059-09-01")

        self.assertEqual(order.execution_date_text, "3059-09-01")
        self.assertEqual(order.execution_ticks % TICKS_PER_DAY, 7_654_321)
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            order.set_execution_date_text("3059-9-1")

    def test_completion_must_be_at_least_one_day_after_current_date(self):
        current_date = datetime.date(3059, 9, 1)
        prop = _struct("ExecutionDate", "DateTime", payload=struct.pack(
            "<q", 10 * TICKS_PER_DAY))
        order = WorkOrder(1, "TEST_MDA", 0, prop)

        with self.assertRaisesRegex(ValueError, "at least one day"):
            order.set_execution_date_text("3059-09-01", current_date=current_date)
        with self.assertRaisesRegex(ValueError, "at least one day"):
            order.set_execution_date_text("3059-08-31", current_date=current_date)

        order.set_execution_date_text("3059-09-02", current_date=current_date)
        self.assertEqual(order.execution_date_text, "3059-09-02")

    def test_changing_work_order_date_resorts_the_game_timeline_queue(self):
        save = WorkOrderHarness([
            _event(11, "CURRENT_MDA", "3059-08-27"),
            _event(10, "LATE_MDA", "3059-08-31"),
            _event(12, "MIDDLE_MDA", "3059-09-05"),
        ])
        orders = {order.event_id: order for order in save.work_orders()}
        timeline = save.model("TimelineModel").plist

        save.set_work_order_execution_date(orders[12], "3059-08-28")

        queue = timeline.get("OrderedTimelineEvents").decoded.elements
        queue_ids = [int.from_bytes(element.get("ID").raw_payload,
                                    "little", signed=True) for element in queue]
        self.assertEqual(queue_ids, [11, 12, 10])
        self.assertEqual(queue_ids[0], 11)
        self.assertEqual([orders[event_id].execution_date_text for event_id in queue_ids[1:]],
                         ["3059-08-28", "3059-08-31"])


if __name__ == "__main__":
    unittest.main()
