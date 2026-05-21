from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from rdflib import Graph, Literal, RDF, URIRef

from common import (
    IDENTIFIER_CQS,
    POLICY_FACET_CQS,
    PREFIXES,
    T1_FIELDS,
    T2_CQS,
    canonical_cq_id,
    has_abstention,
    read_jsonl,
)

FIELD_LABELS = dict(T1_FIELDS)
CQ_TO_FIELD = {cq: field for cq, field, _ in T2_CQS}
CQ_LABELS = {cq: label for cq, _, label in T2_CQS}
IDENTIFIER_FIELDS_T1 = {
    "agreement_metadata",
    "parties_roles",
    "dataset_retention_disposal",
    "population_rights_transparency",
    "governance_incident_exit",
    "assessments",
    "international_transfer",
    "children_safeguards",
}

ABSTAIN_PATTERNS = [
    r"not\s+(?:specified|stated|provided|available|mentioned|included|given)",
    r"no\s+(?:information|explicit\s+information|value|data)\s+(?:is\s+)?(?:specified|stated|provided|available|mentioned|included|given)",
    r"(?:missing|absent|unavailable|unknown)",
    r"not\s+stated\s+in\s+the\s+ttl",
]

FIELD_LABEL_ALIASES = {
    "agreement_metadata": ["agreement metadata", "dsa identifier", "version", "creation date", "created"],
    "parties_roles": ["parties", "roles", "data controller", "recipient", "processor"],
    "purposes_processing_legal_basis_data": ["purposes", "processing", "legal basis", "legal bases", "data categories", "uses data"],
    "dataset_retention_disposal": ["dataset", "retention", "disposal", "storage", "conforms"],
    "population_rights_transparency": ["population", "rights", "transparency", "notice", "procedure"],
    "governance_incident_exit": ["governance", "incident", "exit", "audit", "notification deadline", "contact point", "termination"],
    "assessments": ["assessment", "dpia", "tra", "risk assessment"],
    "international_transfer": ["international transfer", "destination country", "transfer mechanism"],
    "children_safeguards": ["children", "child", "minor", "vulnerable", "enhanced safeguard"],
}

GENERIC_RDF_LOCAL_NAMES = {
    "Party", "DataSharingAgreement", "ProcessingActivity", "SharedDataset", "Dataset", "Storage",
    "InternationalTransfer", "RightsHandling", "TransparencyArrangement", "Assessment", "GovernancePlan",
    "IncidentResponsePlan", "ExitPlan", "Population", "ReviewNote", "PersonalDataCategory", "Purpose",
    "LegalBasis",
}


def norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


@lru_cache(maxsize=30000)
def norm_for_match(s: str) -> str:
    """Normalise only for lexical matching, not exact identifier preservation."""
    s = (s or "").lower()
    s = re.sub(r"[`*_#>]", " ", s)
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"[^a-z0-9:/.@<=]+", " ", s)
    return norm_space(s)


@lru_cache(maxsize=30000)
def split_camel(s: str) -> str:
    return re.sub(r"([a-z])([A-Z])", r"\1 \2", s or "")


def is_abstention(text: str) -> bool:
    t = (text or "").lower()
    return has_abstention(t) or any(re.search(p, t) for p in ABSTAIN_PATTERNS)


def remove_abstention_phrases(text: str) -> str:
    t = text or ""
    for p in ABSTAIN_PATTERNS:
        t = re.sub(p, " ", t, flags=re.I)
    return norm_space(t)


def is_concrete_answer(text: str) -> bool:
    t = remove_abstention_phrases(text)
    return bool(re.search(r"[A-Za-z0-9]", t))


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


def local_name(uri: str) -> str:
    uri = str(uri)
    if uri.startswith("mailto:"):
        return uri
    for prefix, ns in PREFIXES.items():
        if ns and uri.startswith(ns):
            local = uri[len(ns):]
            return f"{prefix + ':' if prefix else ''}{local}"
    if "#" in uri:
        return uri.rsplit("#", 1)[1]
    return uri.rstrip("/").rsplit("/", 1)[-1]


def prefixed_or_local(uri: str) -> list[str]:
    uri = str(uri)
    out = []
    for prefix, ns in PREFIXES.items():
        if ns and uri.startswith(ns):
            local = uri[len(ns):]
            if prefix:
                out.append(f"{prefix}:{local}")
            out.append(local)
            break
    else:
        out.append(local_name(uri))
    out.append(uri)
    # de-duplicate, preserve order
    seen, final = set(), []
    for x in out:
        if x and x not in seen:
            seen.add(x); final.append(x)
    return final


def normalise_ttl_text(ttl_text: str) -> str:
    for repeated_predicate in [", dpv:hasPurpose ", ", dsao:usesData ", ", dsao:hasSafeguard "]:
        ttl_text = ttl_text.replace(repeated_predicate, "; " + repeated_predicate[2:])
    return ttl_text


def duration_aliases(v: str) -> set[str]:
    out = {v}
    mapping = {
        "P6M": ["6 months", "six months", "6 month"],
        "P12M": ["12 months", "twelve months", "12 month", "1 year", "one year", "P1Y"],
        "P1Y": ["1 year", "one year", "12 months", "twelve months", "P12M"],
        "P1Y6M": ["18 months", "eighteen months", "1 year 6 months", "one year six months", "one year and six months"],
        "PT72H": ["72 hours", "72h", "72 h", "seventy two hours", "P3D", "3 days", "three days"],
        "P3D": ["72 hours", "72h", "72 h", "seventy two hours", "PT72H", "3 days", "three days"],
    }
    out.update(mapping.get(v, []))
    m = re.fullmatch(r"P(\d+)M", v)
    if m:
        n = int(m.group(1)); out.add(f"{n} months"); out.add(f"{n} month")
        if n == 12: out.update(["1 year", "one year"])
    m = re.fullmatch(r"PT(\d+)H", v)
    if m:
        n = int(m.group(1)); out.add(f"{n} hours"); out.add(f"{n}h"); out.add(f"{n} h")
    return out


def datetime_aliases(v: str) -> set[str]:
    out = {v}
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(Z|\+00:00)", v)
    if m:
        date, clock, suffix = m.group(1), m.group(2), m.group(3)
        out.add(date)
        out.add(date + " " + clock)
        out.add(date + "T" + clock + "Z")
        out.add(date + "T" + clock + "+00:00")
    return out


def value_aliases(v: str) -> set[str]:
    if not v:
        return set()
    v = str(v).strip().strip(".;,")
    aliases = {v, v.strip("\"'")}
    aliases.update(datetime_aliases(v))
    if ":" in v and not v.startswith("mailto:"):
        prefix, local = v.split(":", 1)
        aliases.add(local)
        aliases.add(local.replace("_", " "))
        aliases.add(local.replace("_", "-"))
        aliases.add(split_camel(local))
    aliases.add(v.replace("_", " "))
    aliases.add(v.replace("_", "-"))
    aliases.add(split_camel(v))
    aliases.update(duration_aliases(v))
    low = v.lower()
    if low == "securedelete": aliases.update(["secure delete", "secure deletion", "delete securely"])
    if low == "anonymise": aliases.update(["anonymize", "anonymisation", "anonymization", "anonymised", "anonymized"])
    if low == "return": aliases.update(["returned", "return data", "data return"])
    if low == "sccs": aliases.update(["standard contractual clauses", "scc"])
    if low == "contract_end": aliases.update(["contract end", "end of contract"])
    if low == "no_redisclosure": aliases.update(["no redisclosure", "no re-disclosure"])
    if low == "remote_audit": aliases.update(["remote audit"])
    return {a for a in aliases if a and len(a.strip()) > 0}


def contains_alias(text: str, aliases: set[str]) -> bool:
    if not text:
        return False
    raw = text.lower()
    norm = norm_for_match(text)
    for a in sorted(aliases, key=lambda x: -len(x)):
        al = a.lower().strip()
        if not al:
            continue
        if any(ch in al for ch in [":", "_", "/", "@", "<", "=", ">", "-"]) or re.search(r"\d", al):
            patt = r"(?<![a-z0-9_:/@.-])" + re.escape(al) + r"(?![a-z0-9_:/@.-])"
            if re.search(patt, raw):
                return True
        an = norm_for_match(al)
        if not an:
            continue
        patt = r"(?<![a-z0-9])" + re.escape(an) + r"(?![a-z0-9])"
        if re.search(patt, norm):
            return True
    return False


def exact_contains(text: str, v: str) -> bool:
    if not text or not v:
        return False
    raw, val = text.lower(), v.lower()
    patt = r"(?<![a-z0-9_:/@-])" + re.escape(val) + r"(?![a-z0-9_:/@-])"
    return re.search(patt, raw) is not None


def ttl_values_and_aliases(ttl_path: Path, ref_values: Iterable[str]) -> tuple[set[str], dict[str, set[str]]]:
    vals = set(str(v) for v in ref_values if v)
    ttl_text = ttl_path.read_text(encoding="utf-8") if ttl_path and ttl_path.exists() else ""
    if ttl_text:
        try:
            g = Graph()
            g.parse(data=normalise_ttl_text(ttl_text), format="turtle")
            for subj, pred, obj in g:
                if pred == RDF.type:
                    continue
                if isinstance(obj, Literal):
                    vals.add(str(obj))
                elif isinstance(obj, URIRef):
                    vals.update(prefixed_or_local(str(obj)))
        except Exception:
            pass
        # Fallback extraction for visible literals/compact objects even when parsing fails.
        for lit in re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"(?:\^\^[\w:]+)?', ttl_text):
            vals.add(lit)
        for iso in re.findall(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", ttl_text):
            vals.add(iso)
        for compact in re.findall(r"\b(?:dpv|dsao|dct|dcat|foaf|odrl):[A-Za-z][A-Za-z0-9_:-]*", ttl_text):
            vals.add(compact)
            vals.add(compact.split(":", 1)[1])
    vals = {
        v for v in vals
        if v not in GENERIC_RDF_LOCAL_NAMES
        and not (isinstance(v, str) and v.startswith("dsao:") and v.split(":", 1)[-1] in GENERIC_RDF_LOCAL_NAMES)
    }
    alias_map = {v: value_aliases(v) for v in vals if v and len(str(v)) > 1}
    return vals, alias_map


def build_ttl_alias_maps(ref_rows: list[dict], ttl_dir: Path | None) -> dict[str, tuple[set[str], dict[str, set[str]]]]:
    maps = {}
    for rec in ref_rows:
        dsa_id = rec["dsa_id"]
        ref_values: list[str] = []
        for f in rec.get("T1", {}).get("fields", []):
            ref_values.extend(f.get("values", []))
        for item in rec.get("T2", {}).get("items", []):
            ref_values.extend(item.get("values", []))
        ttl_path = (ttl_dir / rec.get("ttl_file", f"{dsa_id}.ttl")) if ttl_dir else None
        if not ttl_path or not ttl_path.exists():
            ttl_path = (ttl_dir / f"{dsa_id}.ttl") if ttl_dir else None
        maps[dsa_id] = ttl_values_and_aliases(ttl_path, ref_values) if ttl_path and ttl_path.exists() else (set(ref_values), {v: value_aliases(v) for v in ref_values})
    return maps


def text_has_any_ttl_value(text: str, ttl_alias_map: dict[str, set[str]], expected_values: set[str] | None = None) -> tuple[bool, list[str]]:
    expected_values = expected_values or set()
    found = []
    for v, aliases in ttl_alias_map.items():
        if v in expected_values:
            continue
        if contains_alias(text, aliases):
            found.append(v)
    return bool(found), sorted(set(found))


def found_expected(text: str, values: list[str]) -> list[str]:
    return [v for v in values if contains_alias(text, value_aliases(v))]


def found_exact(text: str, values: list[str]) -> list[str]:
    return [v for v in values if exact_contains(text, v)]


def model_outputs_by_key(output_rows: list[dict]) -> dict[tuple[str, str, str], dict]:
    out = {}
    for row in output_rows:
        if row.get("status", "ok") != "ok":
            continue
        out[(row.get("model", "unknown"), row.get("task"), row.get("dsa_id"))] = row
    return out


def output_models(output_rows: list[dict]) -> list[str]:
    return sorted({r.get("model", "unknown") for r in output_rows if r.get("status", "ok") == "ok"})


def parse_t2_answers(output: str) -> dict[str, str]:
    answers: dict[str, str] = {}
    for line in output.splitlines():
        m = re.search(r"\bCQ\s*-?\s*(\d{1,2})\b\s*(?:[—–\-:]+)\s*(.*)$", line, flags=re.I)
        if m:
            answers[canonical_cq_id(m.group(1))] = m.group(2).strip()
    if not answers:
        for m in re.finditer(r"\bCQ\s*-?\s*(\d{1,2})\b\s*(?:[—–\-:]+)\s*(.*?)(?=\bCQ\s*-?\s*\d{1,2}\b|$)", output, flags=re.I | re.S):
            answers[canonical_cq_id(m.group(1))] = norm_space(m.group(2))
    return answers


def answer_other_field_values(text: str, values_by_field: dict[str, set[str]], own_field: str, expected_values: set[str] | None = None) -> list[str]:
    expected_values = expected_values or set()
    expected_alias_norms = {norm_for_match(a) for e in expected_values for a in value_aliases(e) if norm_for_match(a)}
    other_values = set()
    for field_id, values in values_by_field.items():
        if field_id != own_field:
            other_values.update(values)
    found = []
    for v in other_values:
        if v in expected_values:
            continue
        v_alias_norms = {norm_for_match(a) for a in value_aliases(v) if norm_for_match(a)}
        if v_alias_norms & expected_alias_norms:
            continue
        nested = False
        for aa in v_alias_norms:
            min_len = 3 if re.search(r"\d", aa) else 4
            if len(aa) < min_len:
                continue
            for ee in expected_alias_norms:
                if len(ee) >= 4 and (aa in ee or ee in aa):
                    nested = True
                    break
            if nested:
                break
        if nested:
            continue
        if contains_alias(text, value_aliases(v)):
            found.append(v)
    return sorted(set(found))

def score_t2(ref_rows: list[dict], output_rows: list[dict], ttl_maps) -> tuple[list[dict], list[dict], list[dict]]:
    by_out = model_outputs_by_key(output_rows)
    models = output_models(output_rows)
    item_scores: list[dict] = []
    for model in models:
        for rec in ref_rows:
            row = by_out.get((model, "T2", rec["dsa_id"]))
            if not row:
                continue
            output = row.get("output", "")
            ansmap = parse_t2_answers(output)
            _, ttl_alias = ttl_maps.get(rec["dsa_id"], (set(), {}))
            values_by_field: dict[str, set[str]] = defaultdict(set)
            for item in rec["T2"]["items"]:
                for v in item.get("values", []):
                    values_by_field[item["field_id"]].add(v)
            for item in rec["T2"]["items"]:
                cq = canonical_cq_id(item["cq_id"])
                vals = item.get("values", [])
                text = ansmap.get(cq, "")
                expected = set(vals)
                found_ref = found_expected(text, vals)
                exact = found_exact(text, vals)
                has_abs = is_abstention(text)
                ttl_concrete, ttl_extra_values = text_has_any_ttl_value(text, ttl_alias, expected_values=expected)
                other_found = answer_other_field_values(text, values_by_field, item["field_id"], expected)
                if item["answerable"]:
                    semantic = len(found_ref) == len(vals)
                    strict = semantic and not other_found
                    abst_corr = None
                    unsupported = False
                    ttl_supported_wrong = False
                else:
                    semantic = has_abs and not ttl_concrete
                    strict = semantic
                    abst_corr = semantic
                    unsupported = (not has_abs) and (not ttl_concrete) and is_concrete_answer(text)
                    ttl_supported_wrong = (not has_abs) and ttl_concrete
                ident_exact = (len(exact) == len(vals)) if (cq in IDENTIFIER_CQS and item["answerable"]) else None
                facet_ok = None
                if cq in POLICY_FACET_CQS:
                    if item["answerable"]:
                        facet_ok = (len(found_ref) == len(vals)) and not other_found
                    else:
                        facet_ok = has_abs and not ttl_concrete
                item_scores.append({
                    "task": "T2",
                    "model": model,
                    "dsa_id": rec["dsa_id"],
                    "cq_id": cq,
                    "field_id": item["field_id"],
                    "label": item["label"],
                    "answerable": item["answerable"],
                    "partial": item.get("partial", False),
                    "reference_values": vals,
                    "answer_text": text,
                    "found_reference_values": found_ref,
                    "exact_reference_values": exact,
                    "found_other_field_values": other_found,
                    "strict": strict,
                    "semantic": semantic,
                    "abstention_correct": abst_corr,
                    "unsupported": unsupported,
                    "ttl_supported_wrong_field": ttl_supported_wrong,
                    "ttl_extra_values_in_answer": ttl_extra_values[:20],
                    "identifier_exact": ident_exact,
                    "policy_facet_ok": facet_ok,
                })
    return item_scores, aggregate_t2(item_scores), aggregate_cq(item_scores)


def aggregate_t2(rows: list[dict]) -> list[dict]:
    by_model = defaultdict(list)
    for r in rows:
        by_model[r["model"]].append(r)
    out = []
    for model, rs in sorted(by_model.items()):
        answerable = [r for r in rs if r["answerable"] and not r.get("partial")]
        unanswerable = [r for r in rs if not r["answerable"]]
        partial = [r for r in rs if r.get("partial")]
        id_rows = [r for r in rs if r["identifier_exact"] is not None]
        policy = [r for r in rs if r["policy_facet_ok"] is not None]
        out.append({
            "model": model,
            "task": "T2",
            "items": len(rs),
            "answerable_items": len(answerable),
            "unanswerable_items": len(unanswerable),
            "partial_items": len(partial),
            "strict_accuracy": mean([r["strict"] for r in rs]) if rs else None,
            "semantic_match": mean([r["semantic"] for r in rs]) if rs else None,
            "answerable_accuracy": mean([r["strict"] for r in answerable]) if answerable else None,
            "abstention_accuracy": mean([r["abstention_correct"] for r in unanswerable]) if unanswerable else None,
            "unsupported_answer_rate": mean([r["unsupported"] for r in unanswerable]) if unanswerable else None,
            "ttl_supported_wrong_field_rate": mean([r["ttl_supported_wrong_field"] for r in unanswerable]) if unanswerable else None,
            "identifier_sensitive_exactness": mean([r["identifier_exact"] for r in id_rows]) if id_rows else None,
            "policy_facet_separation": mean([r["policy_facet_ok"] for r in policy]) if policy else None,
            "partial_information_accuracy": mean([r["semantic"] for r in partial]) if partial else None,
        })
    return out


def aggregate_cq(rows: list[dict]) -> list[dict]:
    by = defaultdict(list)
    for r in rows:
        by[(r["model"], r["cq_id"])].append(r)
    out = []
    order = {cq: i for i, (cq, _, _) in enumerate(T2_CQS)}
    for (model, cq), rs in sorted(by.items(), key=lambda kv: (kv[0][0], order.get(kv[0][1], 999))):
        answerable = [r for r in rs if r["answerable"]]
        unanswerable = [r for r in rs if not r["answerable"]]
        out.append({
            "model": model,
            "cq_id": cq,
            "label": rs[0]["label"],
            "items": len(rs),
            "answerable": len(answerable),
            "missing": len(unanswerable),
            "strict": mean([r["strict"] for r in rs]) if rs else None,
            "semantic": mean([r["semantic"] for r in rs]) if rs else None,
            "abstention": mean([r["abstention_correct"] for r in unanswerable]) if unanswerable else None,
            "unsupported": mean([r["unsupported"] for r in unanswerable]) if unanswerable else None,
            "ttl_supported_wrong_field_rate": mean([r["ttl_supported_wrong_field"] for r in unanswerable]) if unanswerable else None,
        })
    return out


def field_is_mentioned(text: str, field_id: str) -> bool:
    norm = norm_for_match(text)
    for label in FIELD_LABEL_ALIASES.get(field_id, [FIELD_LABELS.get(field_id, field_id)]):
        ln = norm_for_match(label)
        if not ln:
            continue
        # Require token/phrase boundaries so short aliases such as TRA do not
        # match inside unrelated words such as transparency.
        patt = r"(?<![a-z0-9])" + re.escape(ln) + r"(?![a-z0-9])"
        if re.search(patt, norm):
            return True
    return False


def snippet_for_field(text: str, field_id: str) -> str:
    # T1 is a paragraph, not a fixed labelled output.  For answerable facets,
    # score against the full output.  For missing facets, use a small window
    # around facet labels when possible so unrelated graph values in the summary
    # are not treated as wrong answers for an omitted optional facet.
    aliases = FIELD_LABEL_ALIASES.get(field_id, [])
    if not aliases:
        return text
    lower = text.lower()
    positions = []
    for a in aliases:
        pos = lower.find(a.lower())
        if pos >= 0:
            positions.append(pos)
    if not positions:
        return ""
    pos = min(positions)
    return text[max(0, pos - 120): pos + 260]


def score_t1(ref_rows: list[dict], output_rows: list[dict], ttl_maps) -> tuple[list[dict], list[dict], list[dict]]:
    by_out = model_outputs_by_key(output_rows)
    models = output_models(output_rows)
    field_scores: list[dict] = []
    for model in models:
        for rec in ref_rows:
            row = by_out.get((model, "T1", rec["dsa_id"]))
            if not row:
                continue
            output = row.get("output", "")
            wc = word_count(output)
            word_limit_ok = wc <= 180
            _, ttl_alias = ttl_maps.get(rec["dsa_id"], (set(), {}))
            for f in rec["T1"]["fields"]:
                field_id = f["field_id"]
                label = f["label"]
                ref_values = f.get("values", [])
                answerable = f["answerable"]
                text_for_match = output if answerable else snippet_for_field(output, field_id)
                mentioned = field_is_mentioned(output, field_id)
                found_ref = found_expected(text_for_match, ref_values)
                expected = set(ref_values)
                ttl_concrete, ttl_extra_values = text_has_any_ttl_value(text_for_match, ttl_alias, expected_values=expected)
                has_abs = is_abstention(text_for_match)
                if answerable:
                    value_coverage = (len(found_ref) / len(ref_values)) if ref_values else None
                    facet_present = len(found_ref) > 0
                    complete_facet = len(found_ref) == len(ref_values)
                    missing_behavior_ok = None
                    unsupported = False
                    ttl_supported_wrong = False
                    exact = found_exact(text_for_match, ref_values)
                    identifier_exact = (len(exact) == len(ref_values)) if field_id in IDENTIFIER_FIELDS_T1 else None
                else:
                    value_coverage = None
                    facet_present = None
                    complete_facet = None
                    # Missing optional facets may be omitted.  If mentioned, they
                    # should be abstained/not specified and should not contain a
                    # concrete value borrowed from another facet.
                    missing_behavior_ok = (not mentioned) or (has_abs and not ttl_concrete)
                    unsupported = mentioned and (not has_abs) and (not ttl_concrete) and is_concrete_answer(text_for_match)
                    ttl_supported_wrong = mentioned and (not has_abs) and ttl_concrete
                    identifier_exact = None
                field_scores.append({
                    "task": "T1",
                    "model": model,
                    "dsa_id": rec["dsa_id"],
                    "field_id": field_id,
                    "label": label,
                    "answerable": answerable,
                    "reference_values": ref_values,
                    "field_text": text_for_match,
                    "field_label_present": mentioned,
                    "found_reference_values": found_ref,
                    "value_coverage": value_coverage,
                    "prompt_facet_present": facet_present,
                    "complete_facet": complete_facet,
                    "ttl_extra_values_in_field": ttl_extra_values[:20],
                    "unsupported": unsupported,
                    "ttl_supported_wrong_field": ttl_supported_wrong,
                    "identifier_exact": identifier_exact,
                    "word_count": wc,
                    "word_limit_ok": word_limit_ok,
                    "missing_behavior_ok": missing_behavior_ok,
                    # Backward-compatible names used by older tables/scripts.
                    "field_supported": complete_facet,
                })
    return field_scores, aggregate_t1(field_scores), aggregate_t1_fields(field_scores)


def aggregate_t1(rows: list[dict]) -> list[dict]:
    by_model = defaultdict(list)
    for r in rows:
        by_model[r["model"]].append(r)
    out = []
    for model, rs in sorted(by_model.items()):
        answerable = [r for r in rs if r["answerable"]]
        missing = [r for r in rs if not r["answerable"]]
        id_rows = [r for r in rs if r["identifier_exact"] is not None]
        per_summary = defaultdict(list)
        for r in rs:
            per_summary[r["dsa_id"]].append(r["word_limit_ok"])
        prompt_facet_coverage = mean([r["prompt_facet_present"] for r in answerable]) if answerable else None
        complete_facet_coverage = mean([r["complete_facet"] for r in answerable]) if answerable else None
        value_level_coverage = None
        total_expected = sum(len(r["reference_values"]) for r in answerable)
        if total_expected:
            total_found = sum(len(r["found_reference_values"]) for r in answerable)
            value_level_coverage = total_found / total_expected
        out.append({
            "model": model,
            "task": "T1",
            "facet_items": len(rs),
            "answerable_facet_items": len(answerable),
            "missing_facet_items": len(missing),
            "prompt_facet_coverage": prompt_facet_coverage,
            "value_level_coverage": value_level_coverage,
            "complete_facet_coverage": complete_facet_coverage,
            "missing_facet_behavior_accuracy": mean([r["missing_behavior_ok"] for r in missing]) if missing else None,
            "unsupported_missing_facet_rate": mean([r["unsupported"] for r in missing]) if missing else None,
            "ttl_supported_wrong_facet_rate": mean([r["ttl_supported_wrong_field"] for r in missing]) if missing else None,
            "identifier_sensitive_exactness": mean([r["identifier_exact"] for r in id_rows]) if id_rows else None,
            "word_limit_pass_rate": mean([all(v) for v in per_summary.values()]) if per_summary else None,
            # Backward-compatible aliases for previous scripts/paper tables.
            "field_items": len(rs),
            "answerable_field_items": len(answerable),
            "missing_field_items": len(missing),
            "supported_field_coverage": complete_facet_coverage,
            "missing_field_behavior_accuracy": mean([r["missing_behavior_ok"] for r in missing]) if missing else None,
            "unsupported_missing_field_rate": mean([r["unsupported"] for r in missing]) if missing else None,
            "ttl_supported_wrong_field_rate": mean([r["ttl_supported_wrong_field"] for r in missing]) if missing else None,
        })
    return out


def aggregate_t1_fields(rows: list[dict]) -> list[dict]:
    out = []
    by_model_field = defaultdict(list)
    for r in rows:
        by_model_field[(r["model"], r["field_id"])].append(r)
    for (model, field_id), rs in sorted(by_model_field.items()):
        answerable = [r for r in rs if r["answerable"]]
        missing = [r for r in rs if not r["answerable"]]
        total_expected = sum(len(r["reference_values"]) for r in answerable)
        total_found = sum(len(r["found_reference_values"]) for r in answerable)
        out.append({
            "model": model,
            "field_id": field_id,
            "label": rs[0]["label"],
            "items": len(rs),
            "answerable": len(answerable),
            "missing": len(missing),
            "prompt_facet_coverage": mean([r["prompt_facet_present"] for r in answerable]) if answerable else None,
            "value_level_coverage": (total_found / total_expected) if total_expected else None,
            "complete_facet_coverage": mean([r["complete_facet"] for r in answerable]) if answerable else None,
            "missing_ok": mean([r["missing_behavior_ok"] for r in missing]) if missing else None,
            "unsupported": mean([r["unsupported"] for r in missing]) if missing else None,
            "ttl_supported_wrong_field_rate": mean([r["ttl_supported_wrong_field"] for r in missing]) if missing else None,
            # Compatibility columns.
            "coverage": mean([r["complete_facet"] for r in answerable]) if answerable else None,
        })
    return out


def pct(v: Any) -> str:
    return "--" if v is None else f"{100 * float(v):.1f}"


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    keys: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def write_tables(t2_metrics: list[dict], t1_metrics: list[dict], cq_rows: list[dict], tables_dir: Path) -> None:
    tables_dir.mkdir(parents=True, exist_ok=True)
    with (tables_dir / "t2_model_metrics.tex").open("w", encoding="utf-8") as f:
        f.write("% Auto-generated by src/evaluate_outputs.py\n")
        f.write("\\begin{table*}[t]\n")
        f.write("\\caption{T2 best-set competency-question answering metrics over the DSA corpus. Matching accepts Turtle-derived lexical variants, including compact URI objects and local names.}\n")
        f.write("\\label{tab:t2-model-metrics}\n\\scriptsize\n\\resizebox{\\textwidth}{!}{%\n")
        f.write("\\begin{tabular}{lrrrrrrrrr}\n\\toprule\n")
        f.write("Model & Items & Strict & Semantic & Ans. acc. & Abstention & Unsupported & TTL wrong facet & Identifier exact & Facet sep. \\\\ \n\\midrule\n")
        for r in t2_metrics:
            f.write(
                f"{r['model']} & {r['items']} & {pct(r['strict_accuracy'])} & {pct(r['semantic_match'])} & "
                f"{pct(r['answerable_accuracy'])} & {pct(r['abstention_accuracy'])} & {pct(r['unsupported_answer_rate'])} & "
                f"{pct(r['ttl_supported_wrong_field_rate'])} & {pct(r['identifier_sensitive_exactness'])} & {pct(r['policy_facet_separation'])} \\\\ \n"
            )
        f.write("\\bottomrule\n\\end{tabular}}\n\\end{table*}\n")

    with (tables_dir / "t1_summary_metrics.tex").open("w", encoding="utf-8") as f:
        f.write("% Auto-generated by src/evaluate_outputs.py\n")
        f.write("\\begin{table*}[t]\n")
        f.write("\\caption{T1 executive-summary prompt-facet metrics. The summary is evaluated by graph-supported facet/value coverage rather than whole-text exact match.}\n")
        f.write("\\label{tab:t1-summary-metrics}\n\\scriptsize\n\\resizebox{\\textwidth}{!}{%\n")
        f.write("\\begin{tabular}{lrrrrrrrr}\n\\toprule\n")
        f.write("Model & Facets & Facet cov. & Value cov. & Complete facets & Missing behavior & Unsupported missing & TTL wrong facet & Word limit \\\\ \n\\midrule\n")
        for r in t1_metrics:
            f.write(
                f"{r['model']} & {r['facet_items']} & {pct(r['prompt_facet_coverage'])} & "
                f"{pct(r['value_level_coverage'])} & {pct(r['complete_facet_coverage'])} & "
                f"{pct(r['missing_facet_behavior_accuracy'])} & {pct(r['unsupported_missing_facet_rate'])} & "
                f"{pct(r['ttl_supported_wrong_facet_rate'])} & {pct(r['word_limit_pass_rate'])} \\\\ \n"
            )
        f.write("\\bottomrule\n\\end{tabular}}\n\\end{table*}\n")

    if cq_rows:
        models = sorted({r["model"] for r in cq_rows})
        by_cq_model = {(r["cq_id"], r["model"]): r for r in cq_rows}
        labels = {r["cq_id"]: r["label"] for r in cq_rows}
        order = [cq for cq, _, _ in T2_CQS]
        with (tables_dir / "t2_per_cq_semantic.tex").open("w", encoding="utf-8") as f:
            f.write("% Auto-generated by src/evaluate_outputs.py\n")
            f.write("\\begin{table*}[t]\n")
            f.write("\\caption{T2 best-set per-competency-question semantic match by model. Values are percentages.}\n")
            f.write("\\label{tab:t2-per-cq-semantic}\n\\scriptsize\n\\resizebox{\\textwidth}{!}{%\n")
            f.write("\\begin{tabular}{ll" + "r" * len(models) + "}\n\\toprule\n")
            f.write("CQ & Question facet & " + " & ".join(models) + " \\\\ \n\\midrule\n")
            for cq in order:
                vals = [pct(by_cq_model.get((cq, model), {}).get("semantic")) for model in models]
                f.write(f"{cq} & {labels.get(cq, '')} & " + " & ".join(vals) + " \\\\ \n")
            f.write("\\bottomrule\n\\end{tabular}}\n\\end{table*}\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate T1 summaries and T2 best-set competency-question answers with Turtle-aware matching.")
    ap.add_argument("--reference", type=Path, default=Path("results/reference/jsonl/reference_answers.jsonl"))
    ap.add_argument("--outputs", type=Path, default=Path("results/raw_jsonl/model_outputs.jsonl"))
    ap.add_argument("--ttl-dir", type=Path, default=Path("data/ttl"), help="Directory containing the original Turtle files used to build lexical aliases.")
    ap.add_argument("--out-dir", type=Path, default=Path("results/metrics"))
    ap.add_argument("--tables-dir", type=Path, default=Path("results/tables"))
    args = ap.parse_args()

    ref_rows = read_jsonl(args.reference)
    output_rows = read_jsonl(args.outputs)
    ttl_maps = build_ttl_alias_maps(ref_rows, args.ttl_dir if args.ttl_dir.exists() else None)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    t2_items, t2_metrics, cq_metrics = score_t2(ref_rows, output_rows, ttl_maps)
    t1_items, t1_metrics, field_metrics = score_t1(ref_rows, output_rows, ttl_maps)

    write_jsonl(args.out_dir / "t2_item_scores.jsonl", t2_items)
    write_jsonl(args.out_dir / "t1_field_scores.jsonl", t1_items)
    (args.out_dir / "t2_model_metrics.json").write_text(json.dumps(t2_metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    (args.out_dir / "t1_summary_metrics.json").write_text(json.dumps(t1_metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    (args.out_dir / "t2_cq_level_metrics.json").write_text(json.dumps(cq_metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    (args.out_dir / "t1_field_level_metrics.json").write_text(json.dumps(field_metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    write_csv(args.out_dir / "t2_cq_level_metrics.csv", cq_metrics)
    write_csv(args.out_dir / "t1_field_level_metrics.csv", field_metrics)

    write_tables(t2_metrics, t1_metrics, cq_metrics, args.tables_dir)
    print(json.dumps({"T1": t1_metrics, "T2": t2_metrics}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
