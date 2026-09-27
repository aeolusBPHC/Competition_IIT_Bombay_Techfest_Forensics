"""
Vendor-agnostic XMP extraction.

XMP properties are returned keyed by their *local name*, whatever namespace
prefix or URI the vendor used. Real files show why this matters: Autel
Robotics writes its telemetry under DJI's namespace URI (with DJI's own
misspelling "GpsLongtitude"), and senseFly and Pix4D both use a "Camera"
prefix for different URIs. Matching on vendor namespaces would miss data;
matching on local names does not.

Both XMP serialisations are handled: properties as attributes of
rdf:Description and properties as child elements (including rdf:Seq/Bag/Alt
lists).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

_PACKET = re.compile(rb"<x:xmpmeta\b.*?</x:xmpmeta>", re.S)
_RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
_CONTAINERS = {_RDF + "Seq", _RDF + "Bag", _RDF + "Alt"}
_SKIP_ATTRS = {_RDF + "about", _RDF + "parseType"}


@dataclass(frozen=True)
class XmpProperty:
    local_name: str
    namespace: str
    value: str | list[str]

    @property
    def qualified(self) -> str:
        return f"{{{self.namespace}}}{self.local_name}" if self.namespace else self.local_name


def _split(tag: str) -> tuple[str, str]:
    if tag.startswith("{"):
        ns, _, local = tag[1:].partition("}")
        return ns, local
    return "", tag


def find_packets(data: bytes) -> list[bytes]:
    return _PACKET.findall(data)


def _parse_packet(packet: bytes) -> list[XmpProperty]:
    try:
        root = ET.fromstring(packet)
    except ET.ParseError:
        return _parse_packet_regex(packet)
    props: list[XmpProperty] = []
    for desc in root.iter(_RDF + "Description"):
        for attr, value in desc.attrib.items():
            if attr in _SKIP_ATTRS:
                continue
            ns, local = _split(attr)
            props.append(XmpProperty(local, ns, value.strip()))
        for child in desc:
            ns, local = _split(child.tag)
            container = next((c for c in child if c.tag in _CONTAINERS), None)
            if container is not None:
                items = [(li.text or "").strip() for li in container.iter(_RDF + "li")]
                props.append(XmpProperty(local, ns, items))
            elif len(child) == 0:
                props.append(XmpProperty(local, ns, (child.text or "").strip()))
    return props


_ATTR_RE = re.compile(rb'([A-Za-z][\w-]*):([A-Za-z][\w-]*)\s*=\s*["\']([^"\']*)["\']')
_ELEM_RE = re.compile(rb"<([A-Za-z][\w-]*):([A-Za-z][\w-]*)>([^<]*)</\1:\2>")


def _parse_packet_regex(packet: bytes) -> list[XmpProperty]:
    """Fallback for malformed XML: salvage simple properties by pattern."""
    props = []
    for rx in (_ATTR_RE, _ELEM_RE):
        for prefix, local, value in rx.findall(packet):
            if prefix in (b"xmlns", b"rdf", b"x"):
                continue
            props.append(XmpProperty(local.decode("utf-8", "replace"),
                                     "prefix:" + prefix.decode("utf-8", "replace"),
                                     value.decode("utf-8", "replace").strip()))
    return props


def extract(data: bytes) -> list[XmpProperty]:
    props: list[XmpProperty] = []
    for packet in find_packets(data):
        props.extend(_parse_packet(packet))
    return props


def by_local_name(props: list[XmpProperty]) -> dict[str, list[XmpProperty]]:
    """Index properties by lower-cased local name (several may share one)."""
    index: dict[str, list[XmpProperty]] = {}
    for p in props:
        index.setdefault(p.local_name.lower(), []).append(p)
    return index
