export type EvidenceStatus = "conflict" | "context-gap";

export type EvidenceRecord = {
  id: string;
  title: string;
  source: string;
  sourceRef: string;
  recordedAt: string;
  recordType: "Field note" | "Progress log" | "Scope note";
  status: EvidenceStatus;
  observed: string;
  interpretation: string;
  missing: string;
};

export type EvidenceRelationship = {
  id: string;
  from: string;
  to: string;
  kind: "conflict" | "context-gap";
  summary: string;
};

// Entirely invented records for interface prototyping; never customer evidence.
export const SAMPLE_EVIDENCE: readonly EvidenceRecord[] = [
  {
    id: "EV-SYN-014",
    title: "Cedar pilot go-live",
    source: "Synthetic field note A",
    sourceRef: "Fixture scenario 01 · entry 04",
    recordedAt: "2025-04-08",
    recordType: "Field note",
    status: "conflict",
    observed: "The fictional Cedar pilot went live on 8 April 2025.",
    interpretation:
      "This note records one date. It does not establish which event the source counts as “going live.”",
    missing:
      "The sample contains no shared definition of go-live or independent launch record.",
  },
  {
    id: "EV-SYN-027",
    title: "Cedar pilot go-live",
    source: "Synthetic planning sheet B",
    sourceRef: "Fixture scenario 01 · row 12",
    recordedAt: "2025-05-02",
    recordType: "Field note",
    status: "conflict",
    observed: "The fictional Cedar pilot's go-live date is listed as 2 May 2025.",
    interpretation:
      "The date differs from the field note. The sample does not show whether both sources use the same definition.",
    missing:
      "No source in this sample reconciles the two dates or identifies a primary record.",
  },
  {
    id: "EV-SYN-031",
    title: "June onboarding count",
    source: "Synthetic progress log C",
    sourceRef: "Fixture scenario 02 · line 08",
    recordedAt: "2025-06-30",
    recordType: "Progress log",
    status: "conflict",
    observed:
      "The fictional progress log counts 18 completed onboarding sessions through 30 June.",
    interpretation:
      "This is a reported total from one synthetic record, not a validated aggregate.",
    missing:
      "The sample does not include session-level entries or a shared counting rule.",
  },
  {
    id: "EV-SYN-036",
    title: "June onboarding count",
    source: "Synthetic handover note D",
    sourceRef: "Fixture scenario 02 · paragraph 3",
    recordedAt: "2025-06-30",
    recordType: "Progress log",
    status: "conflict",
    observed:
      "The fictional handover note records 14 completed onboarding sessions by 30 June.",
    interpretation:
      "This total differs from the synthetic progress log; neither record explains the discrepancy.",
    missing:
      "No underlying session list or reconciliation is present in the sample.",
  },
  {
    id: "EV-SYN-052",
    title: "Meaning of “go-live”",
    source: "Synthetic scope note",
    sourceRef: "Fixture scenario 01 · note 02",
    recordedAt: "2025-05-05",
    recordType: "Scope note",
    status: "context-gap",
    observed:
      "The sample does not define whether “go-live” means internal kickoff or first participant access.",
    interpretation:
      "The term is left unresolved here. This note does not choose between the dates in the field records.",
    missing:
      "A common definition and an authoritative date are not included in this fixture.",
  },
];

// Every edge below is an explicit, synthetic fixture relationship. None is causal.
export const SAMPLE_RELATIONSHIPS: readonly EvidenceRelationship[] = [
  {
    id: "REL-SYN-01",
    from: "EV-SYN-014",
    to: "EV-SYN-027",
    kind: "conflict",
    summary: "The two records report different go-live dates.",
  },
  {
    id: "REL-SYN-02",
    from: "EV-SYN-031",
    to: "EV-SYN-036",
    kind: "conflict",
    summary: "The two records report different completed-session totals.",
  },
  {
    id: "REL-SYN-03",
    from: "EV-SYN-014",
    to: "EV-SYN-052",
    kind: "context-gap",
    summary: "The term used for the date is not defined in the sample.",
  },
  {
    id: "REL-SYN-04",
    from: "EV-SYN-027",
    to: "EV-SYN-052",
    kind: "context-gap",
    summary: "The term used for the date is not defined in the sample.",
  },
];

export type EvidenceFilters = {
  query: string;
  recordType: string;
  status: string;
};

export function filterEvidence(
  records: readonly EvidenceRecord[],
  filters: EvidenceFilters,
): EvidenceRecord[] {
  const normalizedQuery = filters.query.trim().toLocaleLowerCase();

  return records.filter((record) => {
    const matchesQuery =
      normalizedQuery.length === 0 ||
      [
        record.id,
        record.title,
        record.source,
        record.sourceRef,
        record.observed,
        record.interpretation,
      ]
        .join(" ")
        .toLocaleLowerCase()
        .includes(normalizedQuery);
    const matchesType =
      filters.recordType === "all" || record.recordType === filters.recordType;
    const matchesStatus =
      filters.status === "all" || record.status === filters.status;

    return matchesQuery && matchesType && matchesStatus;
  });
}
