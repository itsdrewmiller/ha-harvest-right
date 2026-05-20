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
