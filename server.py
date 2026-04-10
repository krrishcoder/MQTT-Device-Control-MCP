"""MCP server for controlling home light devices via MQTT.

This server exposes tools intended for natural-language assistant requests.
If a user asks anything related to switching a home light/bulb/device ON or OFF
(examples: "turn on my home light", "switch off bedroom bulb", "lights off"),
the assistant should call `control_bulb` with action `ON` or `OFF`.
"""

from __future__ import annotations

import os
import ssl
import uuid
from typing import Any

import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

MQTT_HOST = os.getenv("MQTT_HOST", "")
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
MQTT_CONTROL_TOPIC = os.getenv("MQTT_CONTROL_TOPIC", "home/bulb/control")
MQTT_STATUS_TOPIC = os.getenv("MQTT_STATUS_TOPIC", "home/bulb/status")
MQTT_USE_TLS = os.getenv("MQTT_USE_TLS", "true").lower() in {"1", "true", "yes"}

# MCP transport/runtime config
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")
MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("PORT", os.getenv("MCP_PORT", "8000")))

mcp = FastMCP("mqtt-bulb-mcp", host=MCP_HOST, port=MCP_PORT)


def _validate_base_config() -> None:
    if not MQTT_HOST:
        raise ValueError("MQTT_HOST is required")
    if not MQTT_USERNAME:
        raise ValueError("MQTT_USERNAME is required")
    if not MQTT_PASSWORD:
        raise ValueError("MQTT_PASSWORD is required")


def _publish_once(topic: str, payload: str, qos: int = 1, retain: bool = False) -> dict[str, Any]:
    _validate_base_config()

    client_id = f"mcp-{uuid.uuid4().hex[:10]}"
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id, protocol=mqtt.MQTTv311)
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    if MQTT_USE_TLS:
        client.tls_set(cert_reqs=ssl.CERT_REQUIRED)

    client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    info = client.publish(topic, payload, qos=qos, retain=retain)
    info.wait_for_publish(timeout=5)
    client.disconnect()

    if info.rc != mqtt.MQTT_ERR_SUCCESS:
        raise RuntimeError(f"MQTT publish failed, rc={info.rc}")

    return {
        "ok": True,
        "topic": topic,
        "payload": payload,
        "qos": qos,
        "retain": retain,
    }


@mcp.tool()
def control_bulb(action: str) -> dict[str, Any]:
    """Control the home light power state via MQTT.

    Natural language intent mapping:
    - Use this tool when the user asks to turn on/off a home light, bulb,
      lamp, or similar lighting device.
    - Examples that should map here:
      - "turn on my home light"
      - "turn off the bulb"
      - "switch on lights"
      - "lights off"

    Behavior:
    - Publishes `ON` or `OFF` to `MQTT_CONTROL_TOPIC`.
    - ESP32 subscriber receives command and updates GPIO output.

    Args:
        action: Desired state, must be `ON` or `OFF` (case-insensitive).
    """
    normalized = action.strip().upper()
    if normalized not in {"ON", "OFF"}:
        raise ValueError("action must be ON or OFF")

    return _publish_once(MQTT_CONTROL_TOPIC, normalized, qos=1, retain=False)


@mcp.tool()
def publish_raw(topic: str, payload: str, qos: int = 1, retain: bool = False) -> dict[str, Any]:
    """Publish any MQTT payload to any topic."""
    if not topic.strip():
        raise ValueError("topic cannot be empty")
    if qos not in {0, 1, 2}:
        raise ValueError("qos must be 0, 1, or 2")

    return _publish_once(topic=topic.strip(), payload=payload, qos=qos, retain=retain)


@mcp.tool()
def get_config() -> dict[str, Any]:
    """Show non-sensitive runtime config."""
    return {
        "mqtt_host": MQTT_HOST,
        "mqtt_port": MQTT_PORT,
        "mqtt_username_set": bool(MQTT_USERNAME),
        "mqtt_password_set": bool(MQTT_PASSWORD),
        "mqtt_control_topic": MQTT_CONTROL_TOPIC,
        "mqtt_status_topic": MQTT_STATUS_TOPIC,
        "mqtt_use_tls": MQTT_USE_TLS,
    }


if __name__ == "__main__":
    print("Starting SmartHome Lighting MCP Gateway...", flush=True)
    print(f"MQTT host: {MQTT_HOST}:{MQTT_PORT}", flush=True)
    print(f"MCP transport: {MCP_TRANSPORT}", flush=True)
    print(f"MCP bind: {MCP_HOST}:{MCP_PORT}", flush=True)
    print("MCP server is ready and waiting for client requests.", flush=True)
    mcp.run(transport=MCP_TRANSPORT)
