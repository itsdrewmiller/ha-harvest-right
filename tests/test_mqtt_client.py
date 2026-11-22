"""Tests for the MQTT topic parsing logic."""

from unittest.mock import MagicMock

from custom_components.harvest_right.mqtt_client import (
    SUBSCRIBE_MSG_TYPES,
    HarvestRightMqttClient,
)


def _make_client(on_message) -> HarvestRightMqttClient:
    """Build a client with a mocked hass and the given message callback."""
    return HarvestRightMqttClient(
        MagicMock(),
        customer_id=100,
        email="e@x.com",
        access_token="tok",
        on_message=on_message,
    )


def _msg(topic: str, payload: bytes):
    """Build a fake paho MQTTMessage."""
    m = MagicMock()
    m.topic = topic
    m.payload = payload
    return m


def test_telemetry_message_dispatched() -> None:
    """A well-formed telemetry topic dispatches the parsed payload."""
    cb = MagicMock()
    client = _make_client(cb)
    msg = _msg("act/100/ed/42/m/telemetry", b'{"temp":5}')
    client._on_mqtt_message(None, None, msg)
    cb.assert_called_once_with(42, "telemetry", {"temp": 5})


def test_batch_summary_is_subscribed() -> None:
    """batch-summary is among the subscribed message types."""
    assert "batch-summary" in SUBSCRIBE_MSG_TYPES


def test_online_topic_ignored() -> None:
    """The plain-string /on topic does not dispatch a message."""
    cb = MagicMock()
    client = _make_client(cb)
    client._on_mqtt_message(None, None, _msg("act/100/on", b"on"))
    cb.assert_not_called()


def test_bad_json_ignored() -> None:
    """A non-JSON payload is dropped without dispatching."""
    cb = MagicMock()
    client = _make_client(cb)
    client._on_mqtt_message(None, None, _msg("act/100/ed/42/m/telemetry", b"not json"))
    cb.assert_not_called()


def test_invalid_dryer_id_ignored() -> None:
    """A non-numeric dryer id in the topic is dropped."""
    cb = MagicMock()
    client = _make_client(cb)
    client._on_mqtt_message(None, None, _msg("act/100/ed/xx/m/telemetry", b"{}"))
    cb.assert_not_called()


def test_short_topic_ignored() -> None:
    """A topic that does not match the expected shape is dropped."""
    cb = MagicMock()
    client = _make_client(cb)
    client._on_mqtt_message(None, None, _msg("act/100/weird", b"{}"))
    cb.assert_not_called()


def test_subscribe_dryer_records_id() -> None:
    """Registering a dryer adds it to the subscription set."""
    client = _make_client(MagicMock())
    client.subscribe_dryer(7)
    assert 7 in client._subscribed_dryers


def test_client_id_uses_allowed_pattern() -> None:
    """The broker bans "-ha-device."; the ID must use "-home-assist."."""
    client = _make_client(lambda *a: None)
    assert client.client_id.startswith("100-home-assist.")
    assert "ha-device" not in client.client_id


def test_client_id_is_stable() -> None:
    """The same account always presents the same client ID."""
    a = _make_client(lambda *a: None)
    b = _make_client(lambda *a: None)
    assert a.client_id == b.client_id


def test_build_client_uses_stable_id(monkeypatch) -> None:
    """Every paho client built (e.g. on reconnect) reuses the same ID."""
    seen = []

    def fake_client(*args, **kwargs):
        seen.append(kwargs["client_id"])
        return MagicMock()

    monkeypatch.setattr(
        "custom_components.harvest_right.mqtt_client.mqtt.Client", fake_client
    )
    client = _make_client(lambda *a: None)
    client._build_client()
    client._build_client()
    assert seen == [client.client_id, client.client_id]


def _connected_client() -> tuple[HarvestRightMqttClient, MagicMock]:
    client = _make_client(lambda *a: None)
    paho = MagicMock()
    paho.is_connected.return_value = True
    paho.publish.return_value.rc = 0
    client._client = paho
    return client, paho


def test_publish_online_defaults_to_continue() -> None:
    """The periodic keep-alive publishes "continue", not "on"."""
    client, paho = _connected_client()
    client.publish_online()
    paho.publish.assert_called_once_with("act/100/on", "continue", qos=0)


def test_publish_online_can_send_on() -> None:
    """An explicit refresh still publishes "on"."""
    client, paho = _connected_client()
    client.publish_online("on")
    paho.publish.assert_called_once_with("act/100/on", "on", qos=0)
