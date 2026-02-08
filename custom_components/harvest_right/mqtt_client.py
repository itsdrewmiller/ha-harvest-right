"""MQTT over WebSocket client for Harvest Right."""

import json
import logging
import ssl
import uuid
from collections.abc import Callable

import paho.mqtt.client as mqtt

from homeassistant.core import HomeAssistant

from .const import MQTT_BROKER, MQTT_KEEPALIVE, MQTT_PORT

_LOGGER = logging.getLogger(__name__)

# Message types to subscribe to per dryer
SUBSCRIBE_MSG_TYPES = [
    "telemetry",
    "system",
    "name-update",
]

MessageCallback = Callable[[int, str, dict], None]


class HarvestRightMqttClient:
    """MQTT client for Harvest Right freeze dryers using WebSocket transport."""

    def __init__(
        self,
        hass: HomeAssistant,
        customer_id: int,
        email: str,
        access_token: str,
        on_message: MessageCallback,
    ) -> None:
        self._hass = hass
        self._customer_id = customer_id
        self._email = email
        self._access_token = access_token
        self._on_message = on_message
        self._subscribed_dryers: set[int] = set()

        suffix = uuid.uuid4().hex[:8]
        client_id = f"ha-{customer_id}-{suffix}"

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            transport="websockets",
            protocol=mqtt.MQTTv5,
        )
        self._client.ws_set_options(path="/mqtt")
        self._client.tls_set(tls_version=ssl.PROTOCOL_TLS_CLIENT)
        self._client.username_pw_set(email, access_token)
        self._client.reconnect_delay_set(min_delay=1, max_delay=120)

        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_mqtt_message
        self._client.on_disconnect = self._on_disconnect

    async def connect(self) -> None:
        """Connect to the MQTT broker."""
        _LOGGER.debug("Connecting to MQTT broker %s:%s", MQTT_BROKER, MQTT_PORT)
        self._client.connect_async(MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE)
        self._client.loop_start()

    async def disconnect(self) -> None:
        """Disconnect from the MQTT broker."""
        _LOGGER.debug("Disconnecting from MQTT broker")
        self._client.loop_stop()
        self._client.disconnect()

    async def subscribe_dryer(self, dryer_id: int) -> None:
        """Subscribe to topics for a specific dryer."""
        self._subscribed_dryers.add(dryer_id)
        self._subscribe_dryer_topics(dryer_id)

    def _subscribe_dryer_topics(self, dryer_id: int) -> None:
        """Subscribe to MQTT topics for a dryer."""
        for msg_type in SUBSCRIBE_MSG_TYPES:
            topic = f"act/{self._customer_id}/ed/{dryer_id}/m/{msg_type}"
            self._client.subscribe(topic, qos=0)
            _LOGGER.debug("Subscribed to %s", topic)

        # Online/offline status
        online_topic = f"act/{self._customer_id}/on"
        self._client.subscribe(online_topic, qos=0)

    async def publish(self, dryer_id: int, command: str, payload: dict) -> None:
        """Publish a command to a dryer."""
        topic = f"act/{self._customer_id}/ed/{dryer_id}/{command}"
        self._client.publish(topic, json.dumps(payload), qos=0)

    def update_token(self, access_token: str) -> None:
        """Update the access token for reconnection."""
        self._access_token = access_token
        self._client.username_pw_set(self._email, access_token)

    def _on_connect(self, client, userdata, flags, rc, properties=None) -> None:
        """Handle MQTT connection."""
        if rc == 0:
            _LOGGER.debug("Connected to MQTT broker")
            # Resubscribe on reconnect
            for dryer_id in self._subscribed_dryers:
                self._subscribe_dryer_topics(dryer_id)
        else:
            _LOGGER.error("MQTT connection failed with code %s", rc)

    def _on_mqtt_message(self, client, userdata, msg) -> None:
        """Handle incoming MQTT message — runs on paho's network thread."""
        # Online/offline topic sends plain strings ("on", "continue"), not JSON
        if msg.topic.endswith("/on"):
            text = msg.payload.decode("utf-8", errors="replace")
            _LOGGER.debug("Online status update: %s", text)
            return

        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            _LOGGER.warning("Failed to decode MQTT message on %s", msg.topic)
            return

        # Parse topic: act/{custId}/ed/{dryerId}/m/{msgType}
        parts = msg.topic.split("/")
        if len(parts) >= 6 and parts[2] == "ed" and parts[4] == "m":
            try:
                dryer_id = int(parts[3])
            except ValueError:
                _LOGGER.warning("Invalid dryer ID in topic %s", msg.topic)
                return
            msg_type = parts[5]
            self._on_message(dryer_id, msg_type, payload)
        else:
            _LOGGER.debug("Unhandled topic: %s", msg.topic)

    def _on_disconnect(self, client, userdata, flags, rc, properties=None) -> None:
        """Handle MQTT disconnection."""
        if rc != 0:
            _LOGGER.warning("Unexpected MQTT disconnect (code %s), will reconnect", rc)
        else:
            _LOGGER.debug("MQTT disconnected cleanly")
