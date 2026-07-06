from dataclasses import dataclass
from pathlib import Path

from app.config import Settings


@dataclass(frozen=True)
class SnmpReadResult:
    value: str | None
    error: str | None = None


class SnmpClient:
    async def get_value(self, oid: str) -> SnmpReadResult:
        raise NotImplementedError


class PySnmpClient(SnmpClient):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def get_value(self, oid: str) -> SnmpReadResult:
        try:
            value = await self._read_oid(oid)
            return SnmpReadResult(value=value)
        except Exception as exc:
            return SnmpReadResult(value=None, error=str(exc))

    async def _read_oid(self, oid: str) -> str:
        from pysnmp.hlapi import v1arch

        auth = v1arch.CommunityData(
            self._settings.snmp_community,
            mpModel=0 if self._settings.snmp_version == "1" else 1,
        )
        target = await v1arch.UdpTransportTarget.create(
            (self._settings.snmp_host, self._settings.snmp_port),
            timeout=self._settings.snmp_timeout,
            retries=self._settings.snmp_retries,
        )
        mib_source = str(Path(self._settings.snmp_mib_dir).resolve())
        object_identity = self._build_object_identity(v1arch, oid)
        if Path(mib_source).exists():
            object_identity.add_mib_source(mib_source)
            object_identity.add_asn1_mib_source(f"file://{mib_source}")

        error_indication, error_status, error_index, var_binds = await v1arch.get_cmd(
            v1arch.SnmpDispatcher(),
            auth,
            target,
            v1arch.ObjectType(object_identity),
        )

        if error_indication:
            raise RuntimeError(str(error_indication))
        if error_status:
            detail = error_status.prettyPrint()
            if error_index:
                detail = f"{detail} at {error_index}"
            raise RuntimeError(detail)
        if not var_binds:
            raise RuntimeError("SNMP response did not include var binds")

        value = var_binds[0][1]
        pretty_value = value.prettyPrint()
        if not pretty_value:
            raise RuntimeError("SNMP returned empty value")
        if pretty_value.lower().startswith("no such"):
            raise RuntimeError(pretty_value)

        return pretty_value

    def _build_object_identity(self, v1arch: object, oid: str) -> object:
        if "::" in oid:
            mib_name, symbol = oid.split("::", maxsplit=1)
            return self._build_symbol_identity(v1arch, mib_name, symbol)
        if self._settings.snmp_mib_name and not oid.startswith(".1."):
            return self._build_symbol_identity(
                v1arch,
                self._settings.snmp_mib_name,
                oid,
            )
        return v1arch.ObjectIdentity(oid)

    def _build_symbol_identity(
        self,
        v1arch: object,
        mib_name: str,
        symbol: str,
    ) -> object:
        if "." not in symbol:
            return v1arch.ObjectIdentity(mib_name, symbol)

        symbol_name, index = symbol.rsplit(".", maxsplit=1)
        if index.isdigit():
            return v1arch.ObjectIdentity(mib_name, symbol_name, int(index))
        return v1arch.ObjectIdentity(mib_name, symbol)
