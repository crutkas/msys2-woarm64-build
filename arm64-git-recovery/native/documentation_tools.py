"""Validate the separately classified documentation bootstrap and generated API evidence."""

import json
import html
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from sources import ContractError, digest, verify_tree


def verify_documentation(root, required_names=("documentation_probe", "documentation_probe_count"), html_dir="html"):
    root = Path(root)
    index = root / "xml/index.xml"
    names = {item.text for item in ET.parse(index).getroot().iter("name")}
    if not set(required_names).issubset(names):
        raise ContractError("Doxygen did not generate the actual documented API elements")
    html = root / html_dir / "index.html"
    if not html.is_file():
        raise ContractError("Doxygen did not generate HTML documentation")
    return {"documented_elements": sorted(names), "html_sha256": digest(html), "xml_sha256": digest(index)}


def verify_documentation_driver(prefix, manifest):
    prefix, manifest = Path(prefix).resolve(), Path(manifest).resolve()
    record = json.loads(manifest.read_text(encoding="utf-8"))
    if (record.get("status") != "emulated-documentation-driver-qualified" or
            Path(record.get("prefix", "")).resolve() != prefix or
            record.get("architecture") != "x86_64 emulated on Windows ARM64" or
            record.get("binary", {}).get("id") != "doxygen-windows-x64-doc-bootstrap"):
        raise ContractError("Expected the explicitly emulated, qualified documentation bootstrap")
    verify_tree(prefix, manifest)
    probe = prefix.with_name(prefix.name + ".probe")
    if (digest(probe / "expected-nonnative-pe.json") != record["native_pe_rejection_sha256"] or
            verify_documentation(probe / "generated") != record["documentation"]):
        raise ContractError("Documentation bootstrap qualification evidence changed")
    return {"prefix": str(prefix), "manifest_sha256": digest(manifest), "architecture": record["architecture"],
            "scope": "Documentation driver only; not native target/toolchain or distribution payload"}


def verify_xz_documentation(api, version):
    api = Path(api)
    required = ("index.html", "structlzma__stream.html", "lzma12_8h.html", "version_8h.html")
    if any(not (api / name).is_file() or not (api / name).stat().st_size for name in required):
        raise ContractError("Actual XZ API documentation omitted a required public API page")
    match = re.search(r'<span id="projectnumber">(.*?)</span>', (api / "index.html").read_text(encoding="utf-8"), re.S)
    if match is None or html.unescape(match[1]).strip() != version:
        raise ContractError("Generated XZ documentation does not identify the pinned source version")
    return {"project_version": version, "required_pages": {name: digest(api / name) for name in required}}
