from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from rdflib import Graph, Namespace, RDF, URIRef

ABSTENTION = "Not stated in the TTL"
NOT_SPECIFIED = "not specified"

PREFIXES = {
    "": "https://example.org/dsao/inst/",
    "dsao": "https://w3id.org/dsao#",
    "dpv": "https://w3id.org/dpv#",
    "dct": "http://purl.org/dc/terms/",
    "dcat": "http://www.w3.org/ns/dcat#",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "odrl": "http://www.w3.org/ns/odrl/2/",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}

DSAO = Namespace(PREFIXES["dsao"])
DPV = Namespace(PREFIXES["dpv"])
DCT = Namespace(PREFIXES["dct"])
DCAT = Namespace(PREFIXES["dcat"])
FOAF = Namespace(PREFIXES["foaf"])
ODRL = Namespace(PREFIXES["odrl"])

# T1 is no longer evaluated with the legacy business-field checklist.  The
# current T1 prompt asks for one concise executive paragraph prioritising the
# DSAO/DPV facets below.  They are treated as prompt facets, not as mandatory
# labelled sections in the output.
T1_FIELDS = [
    ("agreement_metadata", "Agreement metadata"),
    ("parties_roles", "Parties and roles"),
    ("purposes_processing_legal_basis_data", "Purposes, processing, legal bases, and data"),
    ("dataset_retention_disposal", "Dataset, retention, and disposal"),
    ("population_rights_transparency", "Population, rights, and transparency"),
    ("governance_incident_exit", "Governance, incident response, and exit"),
    ("assessments", "Assessment information"),
    ("international_transfer", "International transfer information"),
    ("children_safeguards", "Children or vulnerable-population safeguards"),
]

# T2 is aligned with prompts/T2_competency_questions.txt best set.  IDs use the
# canonical hyphenated form from the prompt; parsers also accept CQ1/CQ 1.
T2_CQS = [
    ("CQ-1", "purposes", "Purpose"),
    ("CQ-2", "processing_legal_bases", "Processing activity / Legal basis"),
    ("CQ-3", "parties_roles", "Parties and roles"),
    ("CQ-4", "data_categories", "Data categories"),
    ("CQ-5", "retention_disposal", "Retention and disposal"),
    ("CQ-6", "international_transfer", "International transfer"),
    ("CQ-7", "rights_handling", "Rights handling"),
    ("CQ-8", "transparency", "Transparency"),
    ("CQ-9", "assessments", "Risk assessment"),
    ("CQ-10", "incident_response", "Incident response"),
    ("CQ-11", "governance_audit", "Governance and audit"),
    ("CQ-12", "children_safeguards", "Children / vulnerable data subjects"),
    ("CQ-13", "exit_termination", "Exit and termination"),
]

IDENTIFIER_CQS = {cq for cq, _, _ in T2_CQS}
POLICY_FACET_CQS = {cq for cq, _, _ in T2_CQS}


def canonical_cq_id(value: str | int) -> str:
    """Return CQ IDs in the canonical prompt form CQ-<number>."""
    m = re.search(r"(\d{1,2})", str(value))
    if not m:
        return str(value)
    return f"CQ-{int(m.group(1))}"


def local_name(value: Any) -> str:
    s = str(value)
    if s.startswith("mailto:"):
        return s
    for prefix, ns in PREFIXES.items():
        if ns and s.startswith(ns):
            tail = s[len(ns):]
            return f"{prefix + ':' if prefix else ''}{tail}"
    if "#" in s:
        return s.rsplit("#", 1)[1]
    if "/" in s:
        return s.rstrip("/").rsplit("/", 1)[-1]
    return s


def clean_value(v: Any) -> str | None:
    if v is None:
        return None
    s = local_name(v).strip()
    s = re.sub(r"\s+", " ", s)
    if not s or s.lower() in {"na", "n/a", "none", "null", "empty", ""}:
        return None
    return s


def uniq(values: Iterable[Any]) -> list[str]:
    out, seen = [], set()
    for value in values:
        c = clean_value(value)
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return sorted(out)


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def normalise_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def has_abstention(text: str) -> bool:
    t = (text or "").lower()
    return (
        "not stated in the ttl" in t
        or "not specified" in t
        or "not stated" in t
        or "no information" in t
        or "not provided" in t
        or "not available" in t
    )


def token_contains(text: str, value: str) -> bool:
    if not text or not value:
        return False
    pattern = r"(?<![A-Za-z0-9_:/-])" + re.escape(value) + r"(?![A-Za-z0-9_:/-])"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _normalise_ttl_text(ttl_text: str) -> str:
    # Some generated files repeat a predicate after a comma, e.g.
    # dpv:hasPurpose dpv:analytics , dpv:hasPurpose dpv:fraud_detection .
    # This is semantically intended as a repeated predicate.  Normalise the
    # known shortcuts before RDF parsing.
    for repeated_predicate in [", dpv:hasPurpose ", ", dsao:usesData ", ", dsao:hasSafeguard "]:
        ttl_text = ttl_text.replace(repeated_predicate, "; " + repeated_predicate[2:])
    return ttl_text


def parse_ttl_graph(ttl_path: Path) -> Graph:
    ttl_text = ttl_path.read_text(encoding="utf-8")
    g = Graph()
    g.parse(data=_normalise_ttl_text(ttl_text), format="turtle")
    return g


def values_for(g: Graph, s: Any, p: Any) -> list[Any]:
    return list(g.objects(s, p))


def labels_for_parties(g: Graph) -> dict[Any, str]:
    parties = set(g.subjects(RDF.type, DSAO.Party)) | set(g.objects(None, DSAO.hasParty))
    labels: dict[Any, str] = {}
    for p in parties:
        vals = list(g.objects(p, DCT.title)) + list(g.objects(p, FOAF.name))
        labels[p] = clean_value(vals[0]) if vals else local_name(p)
    return labels


def label_for(g: Graph, node: Any) -> str:
    vals = list(g.objects(node, DCT.title)) + list(g.objects(node, FOAF.name))
    return clean_value(vals[0]) if vals else local_name(node)
