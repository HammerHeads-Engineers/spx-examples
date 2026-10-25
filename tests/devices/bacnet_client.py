# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Lightweight BACnet test client built on BACpypes for integration checks."""

from __future__ import annotations

import queue
import threading
from typing import Any, Optional

try:  # pragma: no cover - optional dependency
    from bacpypes.app import BIPSimpleApplication
    from bacpypes.apdu import (
        Error,
        ReadPropertyACK,
        ReadPropertyRequest,
        SimpleAckPDU,
        WritePropertyRequest,
    )
    from bacpypes.constructeddata import Any as AnyData
    try:
        from bacpypes.core import call_later  # type: ignore
    except ImportError:
        from bacpypes.core import deferred

        def call_later(delay, func, *args, **kwargs):  # type: ignore
            if delay and delay > 0:
                raise RuntimeError("call_later with delay>0 not supported in this BACpypes version")
            deferred(func, *args, **kwargs)
    from bacpypes.core import enable_sleeping, run, stop
    from bacpypes.iocb import IOCB
    from bacpypes.local.device import LocalDeviceObject
    from bacpypes.pdu import Address
    from bacpypes.basetypes import BinaryPV
    from bacpypes.primitivedata import Boolean, Enumerated, Real, Unsigned
    BACPYPES_AVAILABLE = True
except Exception:  # pragma: no cover - handled by callers
    BACPYPES_AVAILABLE = False
    BIPSimpleApplication = object  # type: ignore
    LocalDeviceObject = object  # type: ignore
    ReadPropertyRequest = object  # type: ignore
    WritePropertyRequest = object  # type: ignore
    ReadPropertyACK = object  # type: ignore
    Error = object  # type: ignore
    SimpleAckPDU = object  # type: ignore
    AnyData = object  # type: ignore
    Address = object  # type: ignore
    Boolean = object  # type: ignore
    Enumerated = object  # type: ignore
    Real = object  # type: ignore
    Unsigned = object  # type: ignore
    BinaryPV = object  # type: ignore
    IOCB = object  # type: ignore


class BacnetTestClient(BIPSimpleApplication):  # pragma: no cover - integration helper
    """Minimal BACnet/IP client with its own BACpypes core loop.

    Note: `device_id` is the local (client) BACnet Device instance number and
    does not have to match the remote device `instance_id` configured in SPX.
    """

    def __init__(
        self,
        *,
        device_id: int,
        remote_host: str,
        remote_port: int,
        bind_host: str = "0.0.0.0",
        bind_port: int = 0,
    ):
        device = LocalDeviceObject(
            objectIdentifier=("device", device_id),
            objectName=f"bacnet_test_client_{device_id}",
            vendorIdentifier=999,
        )
        super().__init__(device, Address(f"{bind_host}:{bind_port}"))
        self._core_thread: Optional[threading.Thread] = None
        self._remote_addr = Address(f"{remote_host}:{remote_port}")

    # Core loop management -------------------------------------------------
    def start_core(self):
        if self._core_thread and self._core_thread.is_alive():
            return
        enable_sleeping()
        self._core_thread = threading.Thread(target=run, name="bacnet-client-core", daemon=True)
        self._core_thread.start()

    def stop_core(self):
        try:
            stop()
        finally:
            if self._core_thread and self._core_thread.is_alive():
                self._core_thread.join(timeout=2.0)

    # IO helpers ----------------------------------------------------------
    def _request(self, request) -> Any:
        """Send an IOCB and await response/error."""
        response_queue: "queue.Queue[Any]" = queue.Queue()

        def _callback(iocb: IOCB):
            if getattr(iocb, "ioResponse", None) is not None:
                response_queue.put(iocb.ioResponse)
            elif getattr(iocb, "ioError", None) is not None:
                response_queue.put(iocb.ioError)
            else:
                response_queue.put(RuntimeError("IOCB completed without response or error"))

        iocb = IOCB(request)
        iocb.add_callback(_callback)
        call_later(0, self.request_io, iocb)
        try:
            return response_queue.get(timeout=3.0)
        except queue.Empty as exc:
            raise TimeoutError(f"BACnet request timed out: {request!r}") from exc

    def read_property(self, obj: tuple, prop: str):
        req = ReadPropertyRequest(objectIdentifier=obj, propertyIdentifier=prop)
        req.pduDestination = self._remote_addr
        res = self._request(req)
        if isinstance(res, Exception):
            raise res
        if BACPYPES_AVAILABLE and isinstance(res, Error):
            raise RuntimeError(f"BACnet ReadProperty returned Error: {res}")
        if not isinstance(res, ReadPropertyACK):
            raise RuntimeError(f"Unexpected ReadProperty response: {res!r}")
        return res

    def write_property(self, obj: tuple, prop: str, payload: AnyData, priority: Optional[int] = None):
        req = WritePropertyRequest(objectIdentifier=obj, propertyIdentifier=prop)
        req.pduDestination = self._remote_addr
        req.propertyValue = payload
        if priority is not None:
            req.priority = priority
        res = self._request(req)
        if isinstance(res, Exception):
            raise res
        if BACPYPES_AVAILABLE and isinstance(res, Error):
            raise RuntimeError(f"BACnet WriteProperty returned Error: {res}")
        if not isinstance(res, SimpleAckPDU):
            raise RuntimeError(f"Unexpected WriteProperty response: {res!r}")
        return res

    # Convenience readers/writers ----------------------------------------
    def read_real(self, obj: tuple, prop: str) -> float:
        ack = self.read_property(obj, prop)
        return float(ack.propertyValue.cast_out(Real))

    def read_unsigned(self, obj: tuple, prop: str) -> int:
        ack = self.read_property(obj, prop)
        return int(ack.propertyValue.cast_out(Unsigned))

    def read_bool(self, obj: tuple, prop: str) -> int:
        ack = self.read_property(obj, prop)
        any_value = ack.propertyValue

        # BACnet "binary" presentValue is BinaryPV (Enumerated), not Boolean.
        try:
            return int(bool(any_value.cast_out(Boolean)))
        except Exception:
            pass
        try:
            return 1 if int(any_value.cast_out(Enumerated)) != 0 else 0
        except Exception:
            pass
        try:
            binary_pv = str(any_value.cast_out(BinaryPV)).lower()
        except Exception as exc:
            raise RuntimeError(f"Unable to decode boolean-like value from {any_value!r}") from exc
        return 1 if binary_pv in {"active", "1", "true"} else 0

    def write_bool(self, obj: tuple, prop: str, value: bool, priority: Optional[int] = None):
        payload = AnyData()
        obj_type = str(obj[0])
        if prop == "presentValue" and obj_type in {"binaryInput", "binaryOutput", "binaryValue"}:
            payload.cast_in(BinaryPV("active" if value else "inactive"))
        else:
            payload.cast_in(Boolean(bool(value)))
        return self.write_property(obj, prop, payload, priority=priority)

    def write_unsigned(self, obj: tuple, prop: str, value: int, priority: Optional[int] = None):
        payload = AnyData()
        payload.cast_in(Unsigned(int(value)))
        return self.write_property(obj, prop, payload, priority=priority)
