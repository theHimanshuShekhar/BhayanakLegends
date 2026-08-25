"""Guard tracked and reachable Git content against Riot identity leakage."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

# SHA-256 digests are intentionally non-reversible. The source identities are
# never stored in this repository or included in guard output.
DENYLIST = {
    "f199f4a609dd4ca1e70932c88bdda55ef947eebf1dad065835178002eae8e959",
    "73475b7dddfc2a322c06e77ac31974bb36747c65bcdcb4984f85b2086295e183",
    "00b6fccfd3fda0ddc975e7c6c26177f458faeecaafc37879d5678b890d49585f",
    "1ff9bf1552fc0270041e150d7e05c0505244e124200b5b9ca56113caf169e573",
    "1208e6081999792d3dd6cea12354ba1f86130436b37864970f4b558604aa20bb",
    "1c1bdc66925f64bf703de82760faeff6ed524eb7760b96ece01a94b0c72c162d",
    "baa40ede5535eb99562fc67a2ac96711ce1e4d8e2dddf008fa265d93044f91dc",
    "de5241092148cd78e44d30a00fa070365f079ddc341542a4ba9fadbf3137963e",
    "032624bf952a3ddae0e7ce326f11b801193fc852e0161fd2f6b03370622ae6de",
    "4b4916def8b83abad3eb557b0c76d024b184cbc07d00ebe6e4190f849e27fea9",
    "52d3f90b3c05259fcf58aa20dfc2b1d36d928b19974f4821a57babb6aa3af52d",
"c28ceba24bbbe23d4545a455aedc4bffb9d81831dba758081220663f4ff13440",
    "6d395bd98bfc8f307f7bc468e106422e5d6419ada98fe68d1faa586116a48f54",
    "d3325d5645928fef85277e6e12c61473682cf1fba66df37c53edaa59e1a74628",
    "119651cab93057dfd389463e9e56787e7eff81912acc5cc72d5c98b974fb635d",
    "d8cd593043976f0ea5e313c789f7404c6b146d07c8e8e8b09ce8f62e80f40f4f",
    "e7f625620aa80a567536594c61a9d8f12e15eb724ddc94f59c97322fd80f6e80",
    "82bc3fdc51c55d0362fa9e604dc0939179c207d00085520f27a4041b83fd4e75",
    "1006dc661a6c993362506276fd01ee2b3395eb1c226a619036365795686aec5f",
    "c84e0615e0cd0252d2e9c204537ae8cd8d136a2e7523b8aa490aeb519aea903a",
    "2d230da17045b128dc9dcca0a2fa1f8b2bd2648ed4b63fde5f394d49015e4b45",
    "d51d58c9b042819df04ee1bf18c66ab827f33ba2d878bc247c799cdb8101025b",
    "92295c05818ce9d792de519cfbc69cb1f9027bf0a9e03577a85edffe85e86edb",
    "2f7675f943b25e061676e850642149ce592955a729d47f90df5ff50df3ad8a59",
    "9798fca9d0b952b0e377f2ba292235144d8e16aeea3cd2b7e260c3633aff03d5",
    "127556035516994578ac83fa96204aefcf2b7d400688779201ad7c25b52cb673",
"a1b3841bb6cb42adab5fe225228586160406dddb6c4a41f1d117e3aa03f81768",
    "ad384dcdf0f04ac09137b112dcd5f555b80bfcad62419fa388cb7fe29075ce7a",
    "d9b696dac08ca0265eb67d144b7f506f137b04d261769561d7cc3da32466e482",
    "190f212da9b4214973b57444ced7ae6cdb06ed70be1736cc441f00dc32a322ca",
    "ea7023912bfd6c470fdb9f26aac8ed4165d40b8eb4888654858b50df4d63521d",
    "e144c8f70cf23e0b96894296b363a6276fc622c38baa95e094020946a6cd1e96",
    "fc12a82fb38be0322f3928ffe395f007f5a7bfa3adb259b2aa261514b6923026",
    "a046d485e3cb0cb7165b2afa57ce507194e56b1d2b1a22028171a391fc6f437e",
    "8e294315670f72ace53120c353d4dc8bcad652318c533f77f653d3c9b392d0f2",
    "5cc5f1245e510652973971bb0bfc09d9a65d80e1abe1350d4744bff6798f4f74",
    "8623e9d91dbdab71a370d832129592b861242f47558e1c0aba03f567aa5a0195",
    "25dbd7ca6d959934a35be92313dff16e932b40612e8343910f908794d278f030",
    "3b73259f57bea3bf2ef991c6b02fe37ecbb304e4be83c9a707493f19cc542328",
    "df787c7ca85b7f3c28ae48a13063e0584bc1d85da9d74ca3e03e26dbbd47c1a0",
    "c5d4ae74948d7c6d7271612fc291c66af0f64dc7537266b9d04e9b47a34920ed",
    "a44c028b98dded8d3b592ab1adb02c42217a61398e6d503a1a13059ed4eb3591",
    "1977629e85139fe06839bcf235d1b004bcf8ced983cb231d864a46054f724c9c",
    "aff37888b45f5f5bd81780db25fb85b9b66c47eebbc37dcdb9a4da641176b11f",
    "2488d1f0a3ac8858afdfd912b82445f7f9941f91f455ea391ba187ab03df87b9",
}

IDENTITY_FIELDS = {
    "puuid": re.compile(r"(?:fixture|parity)-puuid-[0-9]{2}"),
    "summonerId": re.compile(r"fixture-summoner-[0-9]{2}"),
    "riotIdGameName": re.compile(r"FixturePlayer[0-9]{2}"),
    "riotIdTagline": re.compile(r"BL[0-9]{2}"),
    "summonerName": re.compile(r"FixturePlayer[0-9]{2}"),
    "KillerName": re.compile(r"FixturePlayer[0-9]{2}|Order|Chaos"),
    "VictimName": re.compile(r"FixturePlayer[0-9]{2}|Order|Chaos"),
    "Assisting": re.compile(r"FixturePlayer[0-9]{2}|Order|Chaos"),
    "riot_id": re.compile(r"FixturePlayer[0-9]{2}#BL[0-9]{2}"),
    "riotId": re.compile(r"FixturePlayer[0-9]{2}#BL[0-9]{2}"),
}


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _finding(path: str, field: str, value: str) -> tuple[str, str, str]:
    return path, field, fingerprint(value)


def _walk_json(value: Any, field: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_field = f"{field}.{key}" if field else key
            if isinstance(child, str):
                yield child_field, child
            yield from _walk_json(child, child_field)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_json(child, f"{field}[{index}]")


def _scan_text(path: str, text: str) -> list[tuple[str, str, str]]:
    findings: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    candidates = re.findall(r"[A-Za-z0-9_#-]{4,}(?: [A-Za-z0-9_#-]+)?", text)
    candidates += [match.group(2) for match in re.finditer(r'''([\"'])(.*?)\1''', text, re.DOTALL)]
    for candidate in candidates:
        if len(candidate) < 7:
            continue
        digest = fingerprint(candidate)
        if digest in DENYLIST:
            item = _finding(path, "text", candidate)
            if item not in seen:
                seen.add(item)
                findings.append(item)
    return findings


def scan_blob(path: str, data: bytes) -> list[tuple[str, str, str]]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return []
    findings = _scan_text(path, text)
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        return findings
    for field, value in _walk_json(document):
        key = field.rsplit(".", 1)[-1].split("[", 1)[0]
        rule = IDENTITY_FIELDS.get(key)
        if rule is None:
            continue
        if not value:
            continue
        if fingerprint(value) in DENYLIST or not rule.fullmatch(value):
            findings.append(_finding(path, field, value))
    return sorted(set(findings))


def tracked_blobs(root: Path) -> Iterable[tuple[str, bytes]]:
    names = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"])
    for name in names.decode().split("\0"):
        if not name:
            continue
        path = root / name
        try:
            yield name, path.read_bytes()
        except OSError:
            continue


def history_blobs(root: Path) -> Iterable[tuple[str, bytes]]:
    listing = subprocess.check_output(["git", "-C", str(root), "rev-list", "--objects", "--all"]).decode()
    entries = [line.split(maxsplit=1) for line in listing.splitlines() if line]
    object_ids = "".join(f"{parts[0]}\n" for parts in entries).encode()
    process = subprocess.Popen(["git", "-C", str(root), "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    output, _ = process.communicate(object_ids)
    offset = 0
    paths = {parts[0]: (parts[1] if len(parts) > 1 else parts[0]) for parts in entries}
    while offset < len(output):
        header_end = output.find(b"\n", offset)
        if header_end < 0:
            break
        oid, kind, size_text = output[offset:header_end].decode().split()
        offset = header_end + 1
        size = int(size_text)
        blob = output[offset : offset + size]
        offset += size + 1
        if kind == "blob":
            yield f"{paths.get(oid, oid)}@{oid[:12]}", blob


def run(root: Path, history: bool) -> int:
    blobs = history_blobs(root) if history else tracked_blobs(root)
    findings: set[tuple[str, str, str]] = set()
    for path, data in blobs:
        findings.update(scan_blob(path, data))
    for path, field, digest in sorted(findings):
        print(f"{path}: {field}: sha256:{digest}")
    return int(bool(findings))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tracked", action="store_true")
    group.add_argument("--history", action="store_true")
    args = parser.parse_args()
    return run(Path(__file__).resolve().parents[2], args.history)


if __name__ == "__main__":
    raise SystemExit(main())
