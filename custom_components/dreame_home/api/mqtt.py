"""Optional MQTT updates, retaining unknown device methods and identifiers."""

from __future__ import annotations

import asyncio
import hashlib
import ssl
from typing import Any, Callable

from .client import DreameHomeClient
from .models import Device, decode_push
from .mqtt_tls import mqtt_tls_context


async def _finish_task(task: asyncio.Task[Any]) -> Any:
    """Finish owned I/O/cleanup before propagating caller cancellation.

    Cancelling ``to_thread`` only detaches its future; it does not stop a socket
    operation. Shield and drain the actual worker, including repeated cancels.
    """
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError:
            if task.cancelled():
                raise
            cancelled = True
        except Exception:
            if cancelled:
                raise asyncio.CancelledError from None
            raise
    if cancelled:
        raise asyncio.CancelledError
    return result


def connect_packet(packet: bytes | bytearray) -> bytearray:
    """Upstream's proprietary bit in the MQTT 3.1.1 CONNECT flags."""
    result = bytearray(packet)
    if not result or result[0] != 0x10:
        return result
    index = 1
    while index < len(result) and result[index] & 0x80:
        index += 1
    if index + 8 >= len(result):
        raise ValueError("Truncated MQTT CONNECT packet")
    result[index + 8] |= 0x08
    return result


def device_topics(device: Device, region: str, account_uid: str) -> list[str]:
    uid = device.owner_uid or account_uid
    regions = ["sg", "kr"] if region == "kr" else [region]
    return [f"/status/{device.did}/{uid}/{device.model}/{country}/" for country in regions]


class DeviceSubscription:
    """One MQTT client per device, matching upstream's observed broker routing.

    Callback runs on the asyncio event loop. TLS verification is enabled;
    acceptance of the standard TLS fingerprint needs live validation.
    """

    def __init__(self, api: DreameHomeClient, device: Device, callback: Callable[[dict[str, Any]], None]):
        self.api, self.device, self.callback = api, device, callback
        self._client = None
        self._loop = None
        self.connected = False
        self.last_error: str | None = None
        self._access_token = None
        self._refresh_task = None
        self._lifecycle_lock = asyncio.Lock()
        self._stopping = False

    async def start(self):
        async with self._lifecycle_lock:
            if self._stopping:
                raise ValueError("Subscription has been stopped")
            if self._client is not None:
                raise RuntimeError("Subscription already started")
            try:
                result = await self._start_locked()
                if self._stopping:
                    await _finish_task(asyncio.create_task(self._close_locked()))
                return result
            except BaseException:
                await _finish_task(asyncio.create_task(self._close_locked()))
                raise

    async def _start_locked(self):
        import paho.mqtt.client as mqtt

        session = await self.api.ensure_session()
        device = self.device
        if not device.bind_domain or not device.owner_uid:
            info = await self.api.get_device_info(device.did)
            device = Device.from_record({**device.raw, **info})
            self.device = device
        if not device.bind_domain:
            raise ValueError("Device record has no MQTT bindDomain")
        host, port = device.bind_domain.rsplit(":", 1)
        if self.api.region == "kr":
            host = host.replace("10100", "10000")
        self._loop = asyncio.get_running_loop()
        parent = self

        class CloudMqttClient(mqtt.Client):
            def _packet_queue(self, command, packet, *args, **kwargs):
                if command == 0x10:
                    packet = connect_packet(packet)
                return super()._packet_queue(command, packet, *args, **kwargs)

        client_id = "p_" + hashlib.md5((device.did + "mqtt" + self.api.visitor_id).encode()).hexdigest()
        client = CloudMqttClient(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id, clean_session=True, protocol=mqtt.MQTTv311)
        self._client = client
        client.username_pw_set(session.uid, session.access_token)
        client.tls_set_context(await asyncio.to_thread(mqtt_tls_context, host, int(port), self.api.region, self.api.account_type))
        client.reconnect_delay_set(1, 15)
        client.connect_timeout = 10
        client.suppress_exceptions = True

        def on_connect(client, userdata, flags, reason, properties):
            if parent._stopping:
                return
            if reason == 0:
                for topic in device_topics(device, parent.api.region, session.uid):
                    client.subscribe(topic)
                parent._loop.call_soon_threadsafe(parent._set_connected, True)
            else:
                parent._loop.call_soon_threadsafe(parent._set_error, "MQTT connection rejected")

        def on_disconnect(client, userdata, flags, reason, properties):
            parent._loop.call_soon_threadsafe(parent._set_connected, False)

        def on_message(client, userdata, message):
            try:
                decoded = decode_push(message.payload)
            except (ValueError, UnicodeDecodeError):
                parent._loop.call_soon_threadsafe(parent._set_error, "Invalid MQTT JSON payload")
                return
            parent._loop.call_soon_threadsafe(parent._deliver, decoded)

        client.on_connect, client.on_disconnect, client.on_message = on_connect, on_disconnect, on_message
        self._access_token = session.access_token
        await _finish_task(asyncio.create_task(asyncio.to_thread(client.connect, host, int(port), 60)))
        if not self._stopping:
            client.loop_start()
            self._refresh_task = asyncio.create_task(self._refresh_credentials())
        return self

    def _set_connected(self, value):
        self.connected = bool(value and not self._stopping and self._client is not None)

    def _deliver(self, payload):
        if not self._stopping and self._client is not None:
            self.callback(payload)

    def _set_error(self, message):
        self.last_error = message
        self.connected = False

    async def _refresh_credentials(self):
        while True:
            await asyncio.sleep(60)
            try:
                session = await self.api.ensure_session()
                async with self._lifecycle_lock:
                    if self._stopping or self._client is None:
                        return
                    if session.access_token != self._access_token:
                        self._client.username_pw_set(session.uid, session.access_token)
                        self._access_token = session.access_token
                        await _finish_task(asyncio.create_task(asyncio.to_thread(self._client.reconnect)))
            except Exception:
                self._set_error("MQTT credential refresh failed")

    async def stop(self):
        self._stopping = True
        await _finish_task(asyncio.create_task(self._stop_locked()))

    async def _stop_locked(self):
        async with self._lifecycle_lock:
            await self._close_locked()

    async def _close_locked(self):
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            self._refresh_task = None
        client, self._client = self._client, None
        try:
            if client:
                try:
                    await asyncio.to_thread(client.disconnect)
                finally:
                    await asyncio.to_thread(client.loop_stop)
        finally:
            self.connected = False
