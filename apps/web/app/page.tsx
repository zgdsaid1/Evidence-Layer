"use client";

import { useEffect, useMemo, useState } from "react";
import {
  filterEvidence,
  SAMPLE_EVIDENCE,
  SAMPLE_RELATIONSHIPS,
  type EvidenceRecord,
  type EvidenceRelationship,
} from "./evidence-data";

const NODE_POSITIONS: Record<string, { x: number; y: number }> = {
  "EV-SYN-014": { x: 102, y: 78 },
  "EV-SYN-027": { x: 302, y: 78 },
  "EV-SYN-052": { x: 202, y: 184 },
  "EV-SYN-031": { x: 466, y: 78 },
  "EV-SYN-036": { x: 646, y: 78 },
};

function SearchIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none">
      <circle cx="10.8" cy="10.8" r="6.8" />
      <path d="m16 16 4.2 4.2" />
    </svg>
  );
}

function MenuIcon({ open }: { open: boolean }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none">
      {open ? <path d="m6 6 12 12M18 6 6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
    </svg>
  );
}

function StatusMark({ status }: { status: EvidenceRecord["status"] }) {
  return (
    <span className={`status-mark status-mark--${status}`} aria-hidden="true">
      {status === "conflict" ? "↔" : "?"}
    </span>
  );
}

function statusName(status: EvidenceRecord["status"]) {
  return status === "conflict" ? "In tension" : "Context gap";
}

function recordDate(date: string) {
  return new Intl.DateTimeFormat("en", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${date}T12:00:00Z`));
}

function relationLabel(kind: EvidenceRelationship["kind"]) {
  return kind === "conflict" ? "Conflicting accounts" : "Definition gap";
}

function relationshipQuestion(relations: EvidenceRelationship[]) {
  const includesConflict = relations.some((relation) => relation.kind === "conflict");
  const includesContextGap = relations.some((relation) => relation.kind === "context-gap");

  if (includesConflict && includesContextGap) return "How do these records relate?";
  if (includesConflict) return "How do the linked accounts differ?";
  return "What context do these links leave open?";
}

const NAVIGATION_SECTIONS = [
  {
    label: "This prototype",
    items: [
      { kind: "available", id: "explorer", label: "Evidence Explorer", glyph: "⌕", href: "#explorer", index: "01" },
      { kind: "available", id: "relationships", label: "Relationships", glyph: "⌘", href: "#relationships" },
      { kind: "available", id: "reading-guide", label: "Reading guide", glyph: "≡", href: "#reading-guide" },
    ],
  },
  {
    label: "Planned",
    items: [
      { kind: "planned", label: "Verification", glyph: "◇" },
      { kind: "planned", label: "Evaluation", glyph: "▤" },
      { kind: "planned", label: "Cost & Performance", glyph: "↗" },
      { kind: "planned", label: "Integrations", glyph: "⇄" },
      { kind: "planned", label: "Settings & Access", glyph: "⚙" },
    ],
  },
] as const;

type InquiryTopic = "observed" | "unknown" | "relationships";

function inquiryAnswer(
  topic: InquiryTopic,
  record: EvidenceRecord,
  relations: EvidenceRelationship[],
): { question: string; answer: string; references: string[] } {
  if (topic === "observed") {
    return {
      question: "What does this source state?",
      answer: record.observed,
      references: [record.source, record.sourceRef],
    };
  }

  if (topic === "unknown") {
    return {
      question: "What is not established?",
      answer: record.missing,
      references: [record.sourceRef],
    };
  }

  const recordById = new Map(SAMPLE_EVIDENCE.map((item) => [item.id, item]));
  const relatedRecords = relations.map((relation) => {
    const relatedId = relation.from === record.id ? relation.to : relation.from;
    const relatedRecord = recordById.get(relatedId);
    return {
      id: relatedId,
      sourceRef: relatedRecord?.sourceRef ?? "Reference unavailable in this sample",
      summary: relation.summary,
    };
  });

  return {
    question: relationshipQuestion(relations),
    answer: relatedRecords.map((item) => `${item.id} · ${item.summary}`).join(" "),
    references: relatedRecords.map((item) => `${item.id} · ${item.sourceRef}`),
  };
}

function RelationshipMap({
  selectedId,
  onSelect,
}: {
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const recordById = new Map(SAMPLE_EVIDENCE.map((record) => [record.id, record]));
  const selectedRelations = selectedId
    ? SAMPLE_RELATIONSHIPS.filter((relation) => relation.from === selectedId || relation.to === selectedId)
    : SAMPLE_RELATIONSHIPS;
  const connectedIds = new Set(
    selectedRelations.flatMap((relation) => [relation.from, relation.to]),
  );

  return (
    <section className="relationship-panel" id="relationships" aria-labelledby="relationships-title">
      <div className="relationship-heading">
        <div>
          <p className="eyebrow eyebrow--light">Evidence links / fixture-defined</p>
          <h2 id="relationships-title">
            {selectedId ? `Links around ${selectedId}` : "Relationships to inspect"}
          </h2>
        </div>
        <span className="map-count">
          {selectedId ? `${selectedRelations.length} linked records` : `${SAMPLE_RELATIONSHIPS.length} links · ${SAMPLE_EVIDENCE.length} records`}
        </span>
        <span className="visually-hidden" role="status" aria-live="polite">
          {selectedId
            ? `${selectedRelations.length} explicit fixture relationships connected to ${selectedId}.`
            : `${SAMPLE_RELATIONSHIPS.length} explicit fixture relationships shown.`}
        </span>
      </div>

      <div
        className="map-scroll"
        role="region"
        aria-label="Evidence relationship map. Scroll horizontally to inspect all records."
        tabIndex={0}
      >
        <div className="map-stage">
          <svg className="map-lines" viewBox="0 0 720 250" aria-hidden="true">
            {SAMPLE_RELATIONSHIPS.map((relation) => {
              const from = NODE_POSITIONS[relation.from];
              const to = NODE_POSITIONS[relation.to];
              const isRelevant = selectedRelations.some((item) => item.id === relation.id);
              return (
                <line
                  key={relation.id}
                  className={`map-line map-line--${relation.kind}${selectedId && !isRelevant ? " is-dimmed" : ""}`}
                  x1={from.x}
                  y1={from.y}
                  x2={to.x}
                  y2={to.y}
                />
              );
            })}
          </svg>

          <div className="map-node-layer">
            {SAMPLE_EVIDENCE.map((record) => {
              const point = NODE_POSITIONS[record.id];
              const isSelected = selectedId === record.id;
              const isDimmed = selectedId !== null && !connectedIds.has(record.id);
              return (
                <button
                  className={`map-node map-node--${record.status}${isSelected ? " is-selected" : ""}${isDimmed ? " is-dimmed" : ""}`}
                  key={record.id}
                  onClick={() => onSelect(record.id)}
                  aria-pressed={isSelected}
                  aria-label={`Inspect ${record.id}, ${record.title}, ${statusName(record.status)}`}
                  style={{ left: `${(point.x / 720) * 100}%`, top: `${(point.y / 250) * 100}%` }}
                  type="button"
                >
                  <span className="map-node-id">{record.id}</span>
                  <span className="map-node-title">{record.title}</span>
                  <span className="map-node-kind">{statusName(record.status)}</span>
                </button>
              );
            })}
          </div>
          <span className="map-axis-label">Fixture relationships · no causal claims</span>
        </div>
      </div>

      <div className="relationship-legend" aria-label="Relationship legend">
        <span><i className="legend-line legend-line--conflict" aria-hidden="true" />Conflict recorded</span>
        <span><i className="legend-line legend-line--context" aria-hidden="true" />Context gap noted</span>
        <span className="legend-note">Labels describe only the synthetic fixture.</span>
      </div>

      <ul className="relationship-list" aria-label="Relationship descriptions">
        {selectedRelations.map((relation) => {
          const from = recordById.get(relation.from);
          const to = recordById.get(relation.to);
          if (!from || !to) return null;
          return (
            <li key={relation.id}>
              <span className={`relationship-type relationship-type--${relation.kind}`}>
                {relationLabel(relation.kind)}
              </span>
              <span className="relationship-pair">
                {from.id} <span aria-hidden="true">↔</span> {to.id}
              </span>
              <span className="relationship-summary">{relation.summary}</span>
            </li>
          );
        })}
      </ul>
      {selectedRelations.length === 0 && (
        <p className="relationship-list-empty">No explicit fixture relationship is recorded for this selection.</p>
      )}
    </section>
  );
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [recordType, setRecordType] = useState("all");
  const [status, setStatus] = useState("all");
  const [selectedId, setSelectedId] = useState("EV-SYN-014");
  const [menuOpen, setMenuOpen] = useState(false);
  const [activeSection, setActiveSection] = useState("explorer");
  const [inquiryOpen, setInquiryOpen] = useState(false);
  const [inquiryTopic, setInquiryTopic] = useState<InquiryTopic | null>(null);

  useEffect(() => {
    const sectionIds = NAVIGATION_SECTIONS[0].items.map((item) => item.id);
    const updateActiveSection = () => {
      const isAtBottom =
        window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2;
      if (isAtBottom) {
        setActiveSection("reading-guide");
        return;
      }

      const marker = window.scrollY + 180;
      const currentSection = sectionIds.reduce((current, sectionId) => {
        const section = document.getElementById(sectionId);
        if (section && section.getBoundingClientRect().top + window.scrollY <= marker) {
          return sectionId;
        }
        return current;
      }, "explorer");

      setActiveSection(currentSection);
    };

    updateActiveSection();
    window.addEventListener("scroll", updateActiveSection, { passive: true });
    window.addEventListener("hashchange", updateActiveSection);
    return () => {
      window.removeEventListener("scroll", updateActiveSection);
      window.removeEventListener("hashchange", updateActiveSection);
    };
  }, []);

  const records = useMemo(
    () => filterEvidence(SAMPLE_EVIDENCE, { query, recordType, status }),
    [query, recordType, status],
  );
  const selectedRecord =
    records.find((record) => record.id === selectedId) ?? records[0] ?? null;
  const selectedRelations = selectedRecord
    ? SAMPLE_RELATIONSHIPS.filter(
        (relation) => relation.from === selectedRecord.id || relation.to === selectedRecord.id,
      )
    : [];
  const inquiry = selectedRecord && inquiryTopic
    ? inquiryAnswer(inquiryTopic, selectedRecord, selectedRelations)
    : null;
  const hasFilters = query.length > 0 || recordType !== "all" || status !== "all";

  function clearFilters() {
    setQuery("");
    setRecordType("all");
    setStatus("all");
    setInquiryTopic(null);
  }

  function selectRecord(id: string) {
    if (!records.some((record) => record.id === id)) clearFilters();
    setSelectedId(id);
    setInquiryTopic(null);
    setMenuOpen(false);
  }

  function navigateToSection(sectionId: string) {
    setActiveSection(sectionId);
    setMenuOpen(false);
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#explorer">Skip to Evidence Explorer</a>

      <div className="mobile-bar">
        <a className="brand-lockup" href="#explorer" aria-label="Evidence Layer home">
          <span className="brand-name">evidence<span>layer</span></span>
        </a>
        <button
          className="mobile-menu-button"
          type="button"
          aria-controls="primary-navigation"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((open) => !open)}
          onKeyDown={(event) => {
            if (event.key === "Escape") setMenuOpen(false);
          }}
        >
          <MenuIcon open={menuOpen} />
          <span className="visually-hidden">{menuOpen ? "Close navigation" : "Open navigation"}</span>
        </button>
      </div>

      <aside
        className={`sidebar${menuOpen ? " sidebar--open" : ""}`}
        onKeyDown={(event) => {
          if (event.key === "Escape") setMenuOpen(false);
        }}
      >
        <a className="brand-lockup brand-lockup--sidebar" href="#explorer" aria-label="Evidence Layer home" onClick={() => navigateToSection("explorer")}>
          <span className="brand-name">evidence<span>layer</span></span>
        </a>

        <p className="sidebar-caption">A workspace for examining evidence.</p>

        <nav className="primary-navigation" id="primary-navigation" aria-label="Primary navigation">
          {NAVIGATION_SECTIONS.map((section) => (
            <div className="nav-group" key={section.label}>
              <p className="nav-group-label">{section.label}</p>
              {section.items.map((item) => item.kind === "available" ? (
                <a
                  className={`nav-link${activeSection === item.id ? " nav-link--active" : ""}`}
                  href={item.href}
                  aria-current={activeSection === item.id ? "location" : undefined}
                  key={item.id}
                  onClick={() => navigateToSection(item.id)}
                >
                  <span className={`nav-glyph${item.id === "explorer" ? " nav-glyph--focus" : ""}`} aria-hidden="true">{item.glyph}</span>
                  <span>{item.label}</span>
                  {"index" in item && <span className="nav-index">{item.index}</span>}
                </a>
              ) : (
                <div className="nav-link nav-link--planned" key={item.label}>
                  <span className="nav-glyph" aria-hidden="true">{item.glyph}</span>
                  <span>{item.label}</span>
                  <span className="nav-status">Planned</span>
                </div>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <span className="sidebar-label">CURRENT VIEW</span>
          <div className="sidebar-dataset">
            <span className="dataset-indicator" aria-hidden="true" />
            <span><strong>Local sample</strong><small>5 synthetic records</small></span>
          </div>
          <p>No connected sources or live services.</p>
        </div>
      </aside>

      <div className="main-column">
        <header className="topbar">
          <div className="breadcrumb"><span>Workspace</span><span aria-hidden="true">/</span><strong>Evidence Explorer</strong></div>
          <div className="topbar-state"><span className="status-dot" aria-hidden="true" />Local prototype <span className="topbar-divider" /> <span>Synthetic data only</span></div>
        </header>

        <main id="explorer" className="page-content">
          <section className="page-intro" aria-labelledby="page-title">
            <div>
              <p className="eyebrow">Examine · compare · verify</p>
              <h1 id="page-title">Evidence Explorer</h1>
              <p className="page-description">
                Follow each record back to its source, see where accounts diverge, and keep what is unknown in view.
              </p>
            </div>
            <div className="sample-stamp" aria-label="This screen uses synthetic sample data only">
              <span className="sample-stamp-mark" aria-hidden="true">S</span>
              <span><strong>Synthetic sample</strong><small>Fictional records · no live sources</small></span>
            </div>
          </section>

          <section className="explorer-workspace" aria-label="Evidence workspace">
            <div className="filter-bar">
              <label className="search-field">
                <span className="search-icon"><SearchIcon /></span>
                <span className="visually-hidden">Search this synthetic sample</span>
                <input
                  type="search"
                  value={query}
                  onChange={(event) => {
                    setQuery(event.target.value);
                    setInquiryTopic(null);
                  }}
                  placeholder="Search IDs, sources, or observed text"
                  autoComplete="off"
                />
              </label>
              <label className="filter-select">
                <span className="visually-hidden">Filter by record type</span>
                <select value={recordType} onChange={(event) => {
                  setRecordType(event.target.value);
                  setInquiryTopic(null);
                }}>
                  <option value="all">All record types</option>
                  <option value="Field note">Field notes</option>
                  <option value="Progress log">Progress logs</option>
                  <option value="Scope note">Scope notes</option>
                </select>
              </label>
              <label className="filter-select filter-select--status">
                <span className="visually-hidden">Filter by review status</span>
                <select value={status} onChange={(event) => {
                  setStatus(event.target.value);
                  setInquiryTopic(null);
                }}>
                  <option value="all">All states</option>
                  <option value="conflict">In tension</option>
                  <option value="context-gap">Context gap</option>
                </select>
              </label>
              {hasFilters && <button className="clear-filters" type="button" onClick={clearFilters}>Clear</button>}
            </div>

            <p className="result-summary" aria-live="polite">
              <span><strong>{records.length}</strong> of {SAMPLE_EVIDENCE.length} sample records</span>
              <span className="summary-divider" aria-hidden="true" />
              <span>Search runs locally in this sample</span>
            </p>

            <div className="explorer-grid">
              <section className="record-panel" aria-labelledby="records-heading">
                <div className="panel-heading">
                  <div>
                    <p className="eyebrow">Evidence set / 01</p>
                    <h2 id="records-heading">Records</h2>
                  </div>
                  <span className="record-total">{records.length.toString().padStart(2, "0")}</span>
                </div>

                {SAMPLE_EVIDENCE.length === 0 ? (
                  <div className="empty-state">
                    <span className="empty-state-symbol" aria-hidden="true">∅</span>
                    <h3>No sample records</h3>
                    <p>This prototype has no local evidence to display.</p>
                  </div>
                ) : records.length === 0 ? (
                  <div className="empty-state">
                    <span className="empty-state-symbol" aria-hidden="true">⌕</span>
                    <h3>No matching records</h3>
                    <p>Try a different term or clear the current filters.</p>
                    <button className="text-button" type="button" onClick={clearFilters}>Clear filters <span aria-hidden="true">→</span></button>
                  </div>
                ) : (
                  <ul className="record-list" aria-label="Evidence records">
                    {records.map((record, index) => {
                      const isSelected = selectedRecord?.id === record.id;
                      return (
                        <li className="record-list-item" key={record.id}>
                          <button
                            className={`record-row${isSelected ? " record-row--selected" : ""}`}
                            type="button"
                            aria-pressed={isSelected}
                            onClick={() => selectRecord(record.id)}
                          >
                            <span className="record-row-index">{String(index + 1).padStart(2, "0")}</span>
                            <span className="record-row-main">
                              <span className="record-row-topline"><span className="record-id">{record.id}</span><span className="record-date">{recordDate(record.recordedAt)}</span></span>
                              <strong className="record-title">{record.title}</strong>
                              <span className="record-source">{record.source}</span>
                              <span className={`status-chip status-chip--${record.status}`}><StatusMark status={record.status} />{statusName(record.status)}</span>
                            </span>
                            <span className="record-row-arrow" aria-hidden="true">↗</span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
                <div className="panel-footnote"><span className="footnote-rule" />Every item is invented for this prototype.</div>
              </section>

              <section className="detail-panel" aria-labelledby="detail-heading" aria-live="polite">
                {selectedRecord ? (
                  <>
                    <div className="detail-topline">
                      <p className="eyebrow">Selected record <span aria-hidden="true">/</span> {selectedRecord.recordType}</p>
                      <span className={`status-chip status-chip--${selectedRecord.status}`}><StatusMark status={selectedRecord.status} />{statusName(selectedRecord.status)}</span>
                    </div>
                    <div className="detail-title-row">
                      <div>
                        <span className="detail-id">{selectedRecord.id}</span>
                        <h2 id="detail-heading">{selectedRecord.title}</h2>
                      </div>
                      <span className="detail-mark" aria-hidden="true">↗</span>
                    </div>

                    <div className="inquiry-disclosure">
                      <button
                        className="inquiry-toggle"
                        type="button"
                        aria-expanded={inquiryOpen}
                        aria-controls="contextual-inquiry"
                        onClick={() => {
                          setInquiryOpen((open) => !open);
                          setInquiryTopic(null);
                        }}
                      >
                        <span>
                          <strong>Ask about this evidence</strong>
                          <small>Contextual questions · local sample only</small>
                        </span>
                        <span className="inquiry-toggle-mark" aria-hidden="true">{inquiryOpen ? "−" : "+"}</span>
                      </button>

                      {inquiryOpen && (
                        <section className="contextual-inquiry" id="contextual-inquiry" aria-labelledby="inquiry-heading">
                          <div className="inquiry-heading">
                            <div>
                              <p className="eyebrow">Selected evidence / {selectedRecord.id}</p>
                              <h3 id="inquiry-heading">Explore a question</h3>
                            </div>
                            <p className="inquiry-limit">Answers use fixture fields only. No model or provider is connected.</p>
                          </div>

                          <div className="inquiry-prompts" aria-label="Suggested questions">
                            <button type="button" aria-pressed={inquiryTopic === "observed"} onClick={() => setInquiryTopic("observed")}>
                              What does this source state?
                            </button>
                            <button type="button" aria-pressed={inquiryTopic === "unknown"} onClick={() => setInquiryTopic("unknown")}>
                              What is not established?
                            </button>
                            {selectedRelations.length > 0 && (
                              <button type="button" aria-pressed={inquiryTopic === "relationships"} onClick={() => setInquiryTopic("relationships")}>
                                {relationshipQuestion(selectedRelations)}
                              </button>
                            )}
                          </div>

                          {inquiry && (
                            <div className="inquiry-exchange" aria-live="polite">
                              <p className="inquiry-question"><span>Question</span>{inquiry.question}</p>
                              <div className="inquiry-answer">
                                <p className="inquiry-answer-label">Evidence note · {selectedRecord.id}</p>
                                <p>{inquiry.answer}</p>
                                <small>Reference: {inquiry.references.join(" · ")}</small>
                              </div>
                            </div>
                          )}
                        </section>
                      )}
                    </div>

                    <dl className="provenance-grid">
                      <div><dt>Source</dt><dd>{selectedRecord.source}</dd></div>
                      <div><dt>Record date</dt><dd>{recordDate(selectedRecord.recordedAt)}</dd></div>
                      <div className="provenance-location"><dt>Provenance</dt><dd>{selectedRecord.sourceRef}</dd></div>
                    </dl>

                    <div className="detail-sections">
                      <section className="evidence-block evidence-block--observed" aria-labelledby="observed-heading">
                        <div className="block-heading"><span className="block-index">01</span><h3 id="observed-heading">Observed in source</h3><span className="block-tag">Record text</span></div>
                        <blockquote>{selectedRecord.observed}</blockquote>
                      </section>
                      <section className="evidence-block evidence-block--interpretation" aria-labelledby="interpretation-heading">
                        <div className="block-heading"><span className="block-index">02</span><h3 id="interpretation-heading">Interpretation</h3><span className="block-tag">Reading, not fact</span></div>
                        <p>{selectedRecord.interpretation}</p>
                      </section>
                      <section className="evidence-block evidence-block--unknown" aria-labelledby="unknown-heading">
                        <div className="block-heading"><span className="block-index">03</span><h3 id="unknown-heading">Not established</h3><span className="block-tag">Open question</span></div>
                        <p>{selectedRecord.missing}</p>
                      </section>
                    </div>

                    <div className="detail-links">
                      <span>Relationships in sample</span>
                      <span>{selectedRelations.length} linked records</span>
                      <a href="#relationships">Inspect map <span aria-hidden="true">↓</span></a>
                    </div>

                  </>
                ) : (
                  <div className="empty-detail">
                    <span className="empty-state-symbol" aria-hidden="true">⌖</span>
                    <h2 id="detail-heading">Select a record</h2>
                    <p>Choose an item from the evidence set to inspect its source and limits.</p>
                    <p className="empty-detail-hint">Select a record above to ask about its evidence.</p>
                  </div>
                )}
              </section>
            </div>

            <RelationshipMap selectedId={selectedRecord?.id ?? null} onSelect={selectRecord} />
          </section>

          <section className="reading-guide" id="reading-guide" aria-labelledby="guide-heading">
            <div className="guide-heading">
              <p className="eyebrow">A note on interpretation</p>
              <h2 id="guide-heading">Keep the record separate from the reading.</h2>
            </div>
            <div className="guide-copy">
              <p>“Observed in source” reproduces a synthetic fixture statement. “Interpretation” describes one careful reading of it. “Not established” names what this sample cannot answer.</p>
              <p>Relationship lines reproduce fixture labels only. They show no causal connection and do not resolve conflicting records.</p>
            </div>
            <div className="guide-signoff"><span>HUMAN INTELLIGENCE / 01</span><span>Evidence first. Conclusions remain inspectable.</span></div>
          </section>

          <footer className="page-footer" id="prototype-notes">
            <span>Evidence Layer · Human Intelligence prototype</span>
            <span>Local synthetic data only <i aria-hidden="true">·</i> No backend or providers connected</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
