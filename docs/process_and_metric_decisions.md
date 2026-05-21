# Prompt-aligned 100-DSA evaluation process

This project evaluates two tasks over the Turtle-encoded DSA corpus:

- **Task T1:** executive-summary generation from a DSAO/DPV Turtle graph.
- **Task T2:** best-set competency-question answering over the same graph.

Both tasks use the same evidence policy: the Turtle graph is the only ground truth. If a value is absent, the expected behavior is omission or explicit abstention, depending on the prompt.

## Prompt files

The runner uses exactly these prompt files:

```text
prompts/system.txt
prompts/T1_executive_summary.txt
prompts/T2_competency_questions.txt
```

The T2 prompt has been replaced with the best set using canonical `CQ-1` to `CQ-13` identifiers.

## Reference-answer extraction

`src/extract_references.py` parses each TTL graph and writes:

```text
results/reference/jsonl/reference_answers.jsonl
results/reference/jsonl/reference_stats.json
results/reference/txt/T1/<DSA_ID>.txt
results/reference/txt/T2/<DSA_ID>.txt
```

The extractor is shared by T1 and T2 through constants in `src/common.py`, so changes in the prompt facets are reflected consistently across reference generation and scoring.

## T1 prompt facets

The current T1 prompt is a concise executive-summary task, not a fixed labelled-field extraction task. The evaluator therefore scores graph-supported **prompt facets**:

| T1 prompt facet | Main graph-grounded extraction rule |
|---|---|
| Agreement metadata | DSA local identifier, `dct:hasVersion`, and `dct:created`. |
| Parties and roles | `dsao:hasParty`, party labels, and `dpv:hasRole`. |
| Purposes, processing, legal bases, and data | `dpv:hasPurpose`, `dsao:ProcessingActivity`, `dpv:hasLegalBasis`, and `dsao:usesData`. |
| Dataset, retention, and disposal | `dsao:SharedDataset` / `dcat:Dataset`, `dct:conformsTo`, `dpv:hasStorage`, `dpv:hasDuration`, and `dsao:disposalMethod`. |
| Population, rights, and transparency | `dsao:population`, `dsao:RightsHandling`, `dsao:forRight`, `dsao:responsibleParty`, `dsao:procedureURL`, `dsao:TransparencyArrangement`, `dsao:noticeType`, `dsao:issuer`, and `foaf:page`. |
| Governance, incident response, and exit | `dsao:GovernancePlan`, `dsao:reviewFrequency`, `dsao:metric`, `dsao:auditRight`, `dsao:IncidentResponsePlan`, `dsao:notificationDeadline`, `dsao:contactPoint`, `dsao:ExitPlan`, `dsao:exitTrigger`, `dsao:dataDisposition`, and `dsao:postTerminationObligation`. |
| Assessment information | `dsao:Assessment`, `dsao:assessmentType`, `dsao:assessmentOutcome`, and `dct:references`; only expected when present. |
| International transfer information | `dsao:InternationalTransfer`, `dsao:destinationCountry`, `dsao:transferMechanism`, and `dsao:hasSafeguard`; only expected when present. |
| Children or vulnerable-population safeguards | Child/vulnerable population labels and `dsao:enhancedSafeguard`; only expected when present. |

## T2 best-set competency questions

The current T2 prompt uses the following 13 facets:

| CQ | Facet | Main graph-grounded extraction rule |
|---|---|---|
| CQ-1 | Purpose | DSA-level and activity-level `dpv:hasPurpose`. |
| CQ-2 | Processing activity / Legal basis | Purpose/legal-basis links in `dsao:ProcessingActivity` nodes. |
| CQ-3 | Parties and roles | `dsao:hasParty`, party labels, and `dpv:hasRole`. |
| CQ-4 | Data categories | `dsao:usesData` and `dpv:hasPersonalDataCategory`. |
| CQ-5 | Retention and disposal | `dpv:hasDuration`, storage-duration values, and `dsao:disposalMethod`. |
| CQ-6 | International transfer | Destination, transfer mechanism, and safeguards on `dsao:InternationalTransfer`. |
| CQ-7 | Rights handling | Right, responsible party, and procedure URL on `dsao:RightsHandling`. |
| CQ-8 | Transparency | Notice type, issuer, and page on `dsao:TransparencyArrangement`. |
| CQ-9 | Risk assessment | Assessment type, outcome, trigger/responsible party when present, and references. |
| CQ-10 | Incident response | Notification deadline and contact point. |
| CQ-11 | Governance and audit | Review frequency, metric, and audit right. |
| CQ-12 | Children / vulnerable data subjects | Child/vulnerable population label and enhanced safeguard. |
| CQ-13 | Exit and termination | Exit trigger, data disposition, and post-termination obligation. |

## Metric mapping

| Metric family | T1 executive summary | T2 best-set QA |
|---|---|---|
| Strict accuracy | Not used as whole-summary exact match; replaced by complete prompt-facet coverage. | Exact value-set match or correct abstention. |
| Semantic match | Value-level coverage and prompt-facet coverage. | All graph-supported reference values must be present, accepting Turtle lexical variants. |
| Abstention accuracy | Missing-facet behavior: omitted or explicitly not stated/not specified. | Missing CQ answers must use `Not stated in the TTL` or equivalent abstention. |
| Unsupported-answer rate | Concrete unsupported claims for absent optional T1 facets. | Concrete unsupported answers to unanswerable CQs. |
| Identifier-sensitive exactness | Exact preservation for identifier-bearing T1 facets. | Exact preservation for identifier-bearing CQ values. |
| Policy-facet separation | Wrong-facet values are reported as `ttl_supported_wrong_facet_rate`. | Wrong-facet values are reported as `ttl_supported_wrong_field_rate` and affect `policy_facet_separation`. |

## Turtle-aware matching

The evaluator does not require the answer string to match a reference literal exactly when the answer is still grounded in the Turtle graph. It builds aliases from the original TTL object values and literals. For instance, the following are accepted as equivalent evidence for a DPV purpose object:

```text
dpv:hasPurpose dpv:reporting
dpv:reporting
reporting
```

The same matching layer handles full URI/local-name variants, underscore/space variants, and common duration/date aliases. This is important because the source files are Turtle and good model answers may surface the object value, local name, or verbalized literal rather than the exact reference rendering.

## Sanity check

The reference-oracle sanity check should return 100% for T1 and T2. Use:

```bash
make oracle
```

A full model run should be regenerated after prompt changes:

```bash
make llm-all
```
