from __future__ import annotations

import argparse
import json
from pathlib import Path
from rdflib import RDF, URIRef

from common import (
    ABSTENTION, DSAO, DPV, DCT, DCAT, FOAF, ODRL, T1_FIELDS, T2_CQS,
    clean_value, label_for, labels_for_parties, local_name, parse_ttl_graph,
    uniq, write_jsonl,
)


def _objects(g, predicates, subjects=None):
    vals = []
    if subjects is None:
        for p in predicates:
            vals.extend(list(g.objects(None, p)))
    else:
        for s in subjects:
            for p in predicates:
                vals.extend(list(g.objects(s, p)))
    return vals


def _subjects_of_type(g, types):
    out = set()
    for t in types:
        out.update(g.subjects(RDF.type, t))
    return sorted(out, key=lambda x: local_name(x))


def _dsa_node(g, ttl_path: Path):
    dsa_nodes = sorted(g.subjects(RDF.type, DSAO.DataSharingAgreement), key=lambda x: local_name(x))
    return dsa_nodes[0] if dsa_nodes else URIRef(f"https://example.org/dsao/inst/{ttl_path.stem}")


def _role_values(g, party_labels):
    values = []
    pairs = []
    for party, label in sorted(party_labels.items(), key=lambda kv: kv[1]):
        roles = uniq(g.objects(party, DPV.hasRole))
        if roles:
            for role in roles:
                pairs.append(f"{label} as {role}")
                values.extend([label, role])
        else:
            pairs.append(label)
            values.append(label)
    return uniq(values), pairs


def _processing_values(g):
    rows = []
    values = []
    for activity in _subjects_of_type(g, [DSAO.ProcessingActivity]):
        purposes = uniq(g.objects(activity, DPV.hasPurpose))
        legal_bases = uniq(g.objects(activity, DPV.hasLegalBasis))
        data = uniq(g.objects(activity, DSAO.usesData))
        # The activity URI is retained in the human-readable reference, but not
        # required as an expected value because many good answers verbalise the
        # purpose/legal-basis link rather than the local activity identifier.
        left = ", ".join(purposes) if purposes else local_name(activity)
        right = ", ".join(legal_bases) if legal_bases else "legal basis not stated"
        rows.append(f"{left} -> {right}")
        values.extend(purposes + legal_bases)
    return uniq(values), rows


def _dataset_values(g):
    datasets = _subjects_of_type(g, [DSAO.SharedDataset, DCAT.Dataset])
    vals = []
    for ds in datasets:
        vals.append(label_for(g, ds))
        vals.extend(g.objects(ds, DCT.conformsTo))
        vals.extend(g.objects(ds, DPV.hasDuration))
        vals.extend(g.objects(ds, DSAO.disposalMethod))
        for storage in g.objects(ds, DPV.hasStorage):
            vals.extend(g.objects(storage, DPV.hasDuration))
            vals.extend(g.objects(storage, DSAO.disposalMethod))
    # storage/disposal can also appear outside the dataset node.
    vals.extend(_objects(g, [DPV.hasDuration, DPV.hasStorageDuration, DSAO.disposalMethod]))
    return uniq(vals)


def _population_values(g, dsa):
    vals = []
    for pop in set(g.objects(dsa, DSAO.population)) | set(g.subjects(RDF.type, DSAO.Population)):
        vals.append(label_for(g, pop))
    return uniq(vals)


def _rights_values(g):
    vals = []
    for rh in _subjects_of_type(g, [DSAO.RightsHandling]):
        vals.extend(g.objects(rh, DSAO.forRight))
        for party in g.objects(rh, DSAO.responsibleParty):
            vals.append(label_for(g, party))
        vals.extend(g.objects(rh, DSAO.procedureURL))
    return uniq(vals)


def _transparency_values(g):
    vals = []
    for ta in _subjects_of_type(g, [DSAO.TransparencyArrangement]):
        vals.extend(g.objects(ta, DSAO.noticeType))
        for issuer in g.objects(ta, DSAO.issuer):
            vals.append(label_for(g, issuer))
        vals.extend(g.objects(ta, FOAF.page))
    return uniq(vals)


def _assessment_values(g, dsa):
    vals = []
    assessments = set(g.objects(dsa, DSAO.hasAssessment)) | set(g.subjects(RDF.type, DSAO.Assessment))
    for a in assessments:
        vals.extend(g.objects(a, DSAO.assessmentType))
        vals.extend(g.objects(a, DSAO.assessmentOutcome))
        vals.extend(g.objects(a, DSAO.assessmentTrigger))
        for party in g.objects(a, DSAO.responsibleParty):
            vals.append(label_for(g, party))
        vals.extend(g.objects(a, DCT.references))
    return uniq(vals)


def _transfer_values(g):
    vals = []
    for tr in _subjects_of_type(g, [DSAO.InternationalTransfer]):
        vals.extend(g.objects(tr, DSAO.destinationCountry))
        vals.extend(g.objects(tr, DSAO.transferMechanism))
        vals.extend(g.objects(tr, DSAO.hasSafeguard))
    return uniq(vals)


def _governance_values(g, dsa):
    vals = []
    nodes = set(g.objects(dsa, DSAO.hasGovernancePlan)) | set(g.subjects(RDF.type, DSAO.GovernancePlan))
    for gov in nodes:
        vals.extend(g.objects(gov, DSAO.reviewFrequency))
        vals.extend(g.objects(gov, DSAO.metric))
        vals.extend(g.objects(gov, DSAO.auditRight))
    return uniq(vals)


def _incident_values(g, dsa):
    vals = []
    nodes = set(g.objects(dsa, DSAO.hasIncidentResponsePlan)) | set(g.subjects(RDF.type, DSAO.IncidentResponsePlan))
    for irp in nodes:
        vals.extend(g.objects(irp, DSAO.notificationDeadline))
        vals.extend(g.objects(irp, DSAO.contactPoint))
    return uniq(vals)


def _exit_values(g, dsa):
    vals = []
    nodes = set(g.objects(dsa, DSAO.hasExitPlan)) | set(g.subjects(RDF.type, DSAO.ExitPlan))
    for ep in nodes:
        vals.extend(g.objects(ep, DSAO.exitTrigger))
        vals.extend(g.objects(ep, DSAO.dataDisposition))
        vals.extend(g.objects(ep, DSAO.postTerminationObligation))
    return uniq(vals)


def _children_safeguard_values(g, dsa, population_values):
    vals = []
    for pop in population_values:
        if "child" in pop.lower() or "minor" in pop.lower() or "vulnerable" in pop.lower():
            vals.append(pop)
    vals.extend(g.objects(dsa, DSAO.enhancedSafeguard))
    vals.extend(_objects(g, [DSAO.enhancedSafeguard]))
    return uniq(vals)


def _purpose_values(g, dsa):
    return uniq(list(g.objects(dsa, DPV.hasPurpose)) + list(g.objects(None, DPV.hasPurpose)))


def _data_category_values(g):
    return uniq(list(g.objects(None, DSAO.usesData)) + list(g.objects(None, DPV.hasPersonalDataCategory)))


def extract_field_values(ttl_path: Path) -> dict:
    g = parse_ttl_graph(ttl_path)
    dsa = _dsa_node(g, ttl_path)
    party_labels = labels_for_parties(g)

    agreement_metadata = uniq([local_name(dsa)] + list(g.objects(dsa, DCT.hasVersion)) + list(g.objects(dsa, DCT.created)))
    parties_roles_values, parties_roles_pairs = _role_values(g, party_labels)
    purpose_values = _purpose_values(g, dsa)
    processing_values, processing_pairs = _processing_values(g)
    data_categories = _data_category_values(g)
    dataset_values = _dataset_values(g)
    population_values = _population_values(g, dsa)
    rights_values = _rights_values(g)
    transparency_values = _transparency_values(g)
    governance_values = _governance_values(g, dsa)
    incident_values = _incident_values(g, dsa)
    exit_values = _exit_values(g, dsa)
    assessment_values = _assessment_values(g, dsa)
    transfer_values = _transfer_values(g)
    children_values = _children_safeguard_values(g, dsa, population_values)

    retention_disposal = uniq(_objects(g, [DPV.hasDuration, DPV.hasStorageDuration, DSAO.disposalMethod]))
    fields = {
        # T1 facets
        "agreement_metadata": agreement_metadata,
        "parties_roles": parties_roles_values,
        "purposes_processing_legal_basis_data": uniq(purpose_values + processing_values + data_categories),
        "dataset_retention_disposal": dataset_values,
        "population_rights_transparency": uniq(population_values + rights_values + transparency_values),
        "governance_incident_exit": uniq(governance_values + incident_values + exit_values),
        "assessments": assessment_values,
        "international_transfer": transfer_values,
        "children_safeguards": children_values,
        # T2 facets
        "purposes": purpose_values,
        "processing_legal_bases": uniq(processing_values),
        "data_categories": data_categories,
        "retention_disposal": retention_disposal,
        "rights_handling": rights_values,
        "transparency": transparency_values,
        "governance_audit": governance_values,
        "incident_response": incident_values,
        "exit_termination": exit_values,
        # human-readable helper rows for reference answers
        "_processing_pairs": processing_pairs,
        "_parties_roles_pairs": parties_roles_pairs,
    }
    return fields


def field_answer(label: str, values: list[str]) -> str:
    return f"{label}: {', '.join(values) if values else 'not specified'}"


def t1_reference_summary(fields: dict[str, list[str]]) -> str:
    parts = []
    for field_id, label in T1_FIELDS:
        vals = fields.get(field_id, [])
        if vals:
            parts.append(field_answer(label, vals))
    if not parts:
        return ABSTENTION
    return "; ".join(parts) + "."


def cq_answer(cq_id: str, field_id: str, label: str, fields: dict[str, list[str]]) -> tuple[str, list[str], bool, bool]:
    values = fields.get(field_id, [])
    partial = False
    if values:
        if cq_id == "CQ-2" and fields.get("_processing_pairs"):
            return f"Processing activities and legal bases: {'; '.join(fields['_processing_pairs'])}.", values, True, partial
        if cq_id == "CQ-3" and fields.get("_parties_roles_pairs"):
            return f"Parties and roles: {'; '.join(fields['_parties_roles_pairs'])}.", values, True, partial
        if cq_id == "CQ-6":
            return f"International transfer details: {', '.join(values)}.", values, True, partial
        if cq_id == "CQ-12":
            return f"Child or vulnerable-population information: {', '.join(values)}.", values, True, partial
        return f"{label}: {', '.join(values)}.", values, True, partial
    return ABSTENTION, [], False, partial


def build_reference_record(ttl_path: Path) -> dict:
    fields = extract_field_values(ttl_path)
    t1_fields = []
    for field_id, label in T1_FIELDS:
        vals = fields.get(field_id, [])
        t1_fields.append({
            "field_id": field_id,
            "label": label,
            "values": vals,
            "answerable": bool(vals),
            "reference": field_answer(label, vals),
        })
    t2_items = []
    for cq_id, field_id, label in T2_CQS:
        answer, values, answerable, partial = cq_answer(cq_id, field_id, label, fields)
        t2_items.append({
            "cq_id": cq_id,
            "field_id": field_id,
            "label": label,
            "values": values,
            "answerable": answerable,
            "partial": partial,
            "reference_answer": answer,
        })
    return {
        "dsa_id": ttl_path.stem,
        "ttl_file": ttl_path.name,
        "fields": {k: v for k, v in fields.items() if not k.startswith("_")},
        "T1": {
            "reference_summary": t1_reference_summary(fields),
            "fields": t1_fields,
        },
        "T2": {
            "items": t2_items,
            "reference_answers": "\n".join([f"{item['cq_id']} — {item['reference_answer']}" for item in t2_items]),
        },
    }


def write_reference_txt(records: list[dict], txt_dir: Path) -> None:
    for rec in records:
        dsa_id = rec["dsa_id"]
        t1_path = txt_dir / "T1" / f"{dsa_id}.txt"
        t2_path = txt_dir / "T2" / f"{dsa_id}.txt"
        t1_path.parent.mkdir(parents=True, exist_ok=True)
        t2_path.parent.mkdir(parents=True, exist_ok=True)
        t1_path.write_text(rec["T1"]["reference_summary"] + "\n", encoding="utf-8")
        t2_path.write_text(rec["T2"]["reference_answers"] + "\n", encoding="utf-8")


def stats(records: list[dict]) -> dict:
    t1 = []
    for field_id, label in T1_FIELDS:
        answerable = sum(1 for r in records if any(f["field_id"] == field_id and f["answerable"] for f in r["T1"]["fields"]))
        avg_values = sum(len(next(f for f in r["T1"]["fields"] if f["field_id"] == field_id)["values"]) for r in records) / len(records)
        t1.append({"field_id": field_id, "label": label, "answerable": answerable, "unanswerable": len(records)-answerable, "avg_values": round(avg_values, 2)})
    t2 = []
    for cq_id, field_id, label in T2_CQS:
        vals = [next(i for i in r["T2"]["items"] if i["cq_id"] == cq_id) for r in records]
        answerable = sum(1 for item in vals if item["answerable"])
        t2.append({"cq_id": cq_id, "field_id": field_id, "label": label, "answerable": answerable, "unanswerable": len(vals)-answerable, "avg_values": round(sum(len(i["values"]) for i in vals)/len(vals), 2)})
    return {"num_dsas": len(records), "T1_prompt_facets": t1, "T2_cqs": t2}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", type=Path, default=Path("data/ttl"))
    ap.add_argument("--jsonl", type=Path, default=Path("results/reference/jsonl/reference_answers.jsonl"))
    ap.add_argument("--txt-dir", type=Path, default=Path("results/reference/txt"))
    ap.add_argument("--stats", type=Path, default=Path("results/reference/jsonl/reference_stats.json"))
    args = ap.parse_args()
    ttl_files = sorted([p for p in args.input_dir.glob("*.ttl") if p.is_file()])
    records = [build_reference_record(p) for p in ttl_files]
    write_jsonl(args.jsonl, records)
    write_reference_txt(records, args.txt_dir)
    st = stats(records)
    args.stats.parent.mkdir(parents=True, exist_ok=True)
    args.stats.write_text(json.dumps(st, indent=2), encoding="utf-8")
    print(json.dumps(st, indent=2))

if __name__ == "__main__":
    main()
