from __future__ import annotations


def test_event_hub_basic_subscribe_unsubscribe() -> None:
    from assethub.core.events.event_hub import DbChanged, EventHub

    hub = EventHub()
    seen: list[str] = []

    def handler(evt: DbChanged) -> None:
        seen.append(evt.reason)

    unsub = hub.db_changed.subscribe(handler)
    hub.db_changed.emit(DbChanged(reason="a", payload={}))
    assert seen == ["a"]

    unsub()
    hub.db_changed.emit(DbChanged(reason="b", payload={}))
    assert seen == ["a"]
