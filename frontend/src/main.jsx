import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const api = async (path, options = {}) => {
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((item) => item.msg).join("; ")
      : data.detail;
    throw new Error(detail || "Something went wrong.");
  }
  return data;
};

const labels = {
  invitation_sent: "Invitation sent",
  identity_verified: "Identity verified",
  identity_locked: "Identity locked",
  patient_mismatch: "Patient mismatch",
  parse_failed: "Parsing failed",
  processing: "Processing",
  filed: "Filed in FHIR",
  revoked: "Revoked",
  filing_failed: "Filing failed",
};

function Brand({ compact = false }) {
  return <div className={`brand ${compact ? "compact" : ""}`}>
    <span className="brand-mark" aria-hidden="true">D</span>
    <span><strong>DocBinder</strong><small>Secure clinical exchange</small></span>
  </div>;
}

function Status({ value }) {
  return <span className={`status status-${value}`}>{labels[value] || value}</span>;
}

const labExample = {
  patient_id: "maria-beispiel",
  patient_name: "Maria Beispiel",
  patient_birth_date: "1961-03-12",
  patient_phone: "+43 660 000 0199",
  recipient_name: "Dr. Eva Brandl",
  recipient_role: "Lab physician at Labor Kanalstraße",
  channel: "email",
  contact: "eva.brandl@labor-kanal.example",
  document_type_code: "laboratory_results",
  purpose_or_legal_basis: "necessary for treatment",
  reason: "Latest blood clotting results before a planned procedure",
};

const rehabExample = {
  ...labExample,
  recipient_name: "Stefan Kern",
  recipient_role: "Discharge manager at Reha Waldblick",
  channel: "sms",
  contact: "+43 660 000 0101",
  document_type_code: "rehabilitation_report",
  purpose_or_legal_basis: "transfer of patient",
  reason: "Rehabilitation discharge report for continued treatment",
};

function Shell({ tab, setTab, children, title, action }) {
  return <div className="app-shell">
    <aside className="sidebar">
      <Brand />
      <nav aria-label="Main navigation">
        <button className={tab === "requests" ? "active" : ""} onClick={() => setTab?.("requests")}>Requests</button>
        <button className={tab === "new" ? "active" : ""} onClick={() => setTab?.("new")}>New request</button>
        <button className={tab === "sms" ? "active" : ""} onClick={() => setTab?.("sms")}>SMS simulator</button>
      </nav>
      <div className="doctor-card"><span>LH</span><div><strong>Dr. Lena Hofer</strong><small>Internal medicine</small></div></div>
    </aside>
    <main className="main">
      <header className="topbar"><div><span className="eyebrow">Klinikum Beispielstadt</span><h1>{title}</h1></div>{action}</header>
      {children}
    </main>
  </div>;
}

function Dashboard() {
  const initialTab = new URLSearchParams(window.location.search).get("tab");
  const [tab, setTab] = useState(["requests", "new", "sms"].includes(initialTab) ? initialTab : "requests");
  const [requests, setRequests] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [form, setForm] = useState(labExample);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const refresh = async () => {
    const [requestRows, notificationRows] = await Promise.all([
      api("/api/requests"), api("/api/demo/notifications"),
    ]);
    setRequests(requestRows); setNotifications(notificationRows);
  };
  useEffect(() => { refresh().catch((err) => setError(err.message)); }, []);
  const set = (key) => (event) => setForm((current) => ({ ...current, [key]: event.target.value }));

  const submit = async (event) => {
    event.preventDefault(); setBusy(true); setError(""); setResult(null);
    try {
      const created = await api("/api/requests", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form),
      });
      setResult(created); await refresh();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };

  const revoke = async (event, id) => {
    event.stopPropagation();
    if (!window.confirm(`Revoke request ${id}?`)) return;
    await api(`/api/requests/${id}/revoke`, { method: "POST" });
    refresh();
  };

  const sms = useMemo(() => notifications.filter((item) => item.channel === "sms"), [notifications]);
  const title = tab === "new" ? "Create document request" : tab === "sms" ? "Simulated SMS outbox" : "Document requests";
  return <Shell tab={tab} setTab={setTab} title={title} action={tab === "requests" && <button className="primary" onClick={() => setTab("new")}>+ New request</button>}>
    {error && <div className="alert error">{error}</div>}
    {tab === "requests" && <section className="panel">
      <div className="panel-heading"><div><h2>Recent activity</h2><p>Select a request to inspect its clinical summary, sources, FHIR, and audit history.</p></div><button className="ghost" onClick={refresh}>Refresh</button></div>
      {requests.length === 0 ? <div className="empty"><strong>No requests yet</strong><p>Create the first secure document request.</p></div> :
        <div className="table-wrap"><table><thead><tr><th>Reference</th><th>Patient</th><th>Recipient</th><th>Document</th><th>Status</th><th></th></tr></thead><tbody>
          {requests.map((item) => <tr className="clickable-row" key={item.id} onClick={() => { window.location.href = `/requests/${item.id}`; }}>
            <td><strong>{item.id}</strong><small>{new Date(item.created_at).toLocaleString()}</small></td>
            <td>{item.patient_display}<small>{item.patient_birth_date}</small></td>
            <td>{item.recipient_name}<small>{item.recipient_role}</small></td>
            <td>{item.document_type_code || item.document_type}</td><td><Status value={item.status} /></td>
            <td>{!["filed", "revoked"].includes(item.status) && <button className="text-button danger" onClick={(event) => revoke(event, item.id)}>Revoke</button>}</td>
          </tr>)}
        </tbody></table></div>}
    </section>}

    {tab === "new" && <form className="request-grid" onSubmit={submit}>
      <section className="panel form-panel">
        <div className="step-title"><span>1</span><div><h2>Patient</h2><p>Maria is prefilled; synthetic patients are also supported.</p></div></div>
        <div className="two-col"><label>Patient ID<input value={form.patient_id} onChange={set("patient_id")} required /></label><label>Full name<input value={form.patient_name} onChange={set("patient_name")} required /></label></div>
        <div className="two-col"><label>Birth date<input type="date" value={form.patient_birth_date} onChange={set("patient_birth_date")} required /></label><label>Mobile<input value={form.patient_phone} onChange={set("patient_phone")} /></label></div>
        <div className="step-title section-step"><span>2</span><div><h2>External professional</h2><p>Enter any synthetic recipient for the demo.</p></div></div>
        <div className="example-actions"><button type="button" className="ghost" onClick={() => setForm(labExample)}>Use lab example</button><button type="button" className="ghost" onClick={() => setForm(rehabExample)}>Use rehab example</button></div>
        <div className="two-col"><label>Recipient name<input value={form.recipient_name} onChange={set("recipient_name")} required /></label><label>Role<input value={form.recipient_role} onChange={set("recipient_role")} required /></label></div>
        <div className="two-col"><label>Channel<select value={form.channel} onChange={set("channel")}><option value="email">Email</option><option value="sms">SMS</option></select></label><label>Contact<input value={form.contact} onChange={set("contact")} required /></label></div>
      </section>
      <section className="panel form-panel">
        <div className="step-title"><span>3</span><div><h2>Clinical request</h2><p>Structured fields prevent ambiguous document processing.</p></div></div>
        <label>Document type<select value={form.document_type_code} onChange={set("document_type_code")}><option value="laboratory_results">Laboratory results</option><option value="rehabilitation_report">Rehabilitation discharge report</option></select></label>
        <label>Purpose / legal basis<select value={form.purpose_or_legal_basis} onChange={set("purpose_or_legal_basis")}><option>necessary for treatment</option><option>transfer of patient</option><option>optimize treatment</option></select></label>
        <label>Reason<textarea value={form.reason} onChange={set("reason")} rows="4" required /></label>
        <div className="privacy-note"><strong>Privacy boundary</strong><p>The invitation contains no patient, birth date, reason, or document type. Details appear only after simulated name matching.</p></div>
        <button className="primary wide" disabled={busy}>{busy ? "Creating…" : "Confirm and send request"}</button>
        {result && <div className="success-card"><strong>{result.id} created</strong><p>The privacy-safe invitation and patient SMS were queued.</p><a href={result.invitation_url}>Open invitation for demo →</a>{result.warnings?.map((warning) => <small key={warning}>⚠ {warning}</small>)}</div>}
      </section>
    </form>}

    {tab === "sms" && <section className="panel">
      <div className="panel-heading"><div><h2>SMS simulator</h2><p>Replies, six-hour escalation, and calling are storyboarded only; no real message leaves this environment.</p></div><button className="ghost" onClick={refresh}>Refresh</button></div>
      <div className="phone-list">{sms.length === 0 ? <div className="empty">No simulated messages yet.</div> : sms.map((item) => <article className="message-card" key={item.id}><div className="message-meta"><span className={`audience ${item.audience}`}>{item.audience === "patient" ? "Patient message · simulated" : "External invitation · simulated"}</span><time>{new Date(item.created_at).toLocaleString()}</time></div><strong>{item.destination}</strong><p>{item.body}</p>{item.action_url && <a href={item.action_url}>Open secure invitation →</a>}</article>)}</div>
    </section>}
  </Shell>;
}

function RequestDetail({ requestId }) {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => { api(`/api/requests/${requestId}/detail`).then(setDetail).catch((err) => setError(err.message)); }, [requestId]);
  return <Shell tab="requests" setTab={(tab) => { window.location.href = tab === "requests" ? "/" : `/?tab=${tab}`; }} title={requestId} action={<button className="ghost" onClick={() => { window.location.href = "/"; }}>← All requests</button>}>
    {error && <div className="alert error">{error}</div>}
    {!detail ? <section className="panel loading">Loading request…</section> : <>
      <section className="detail-hero panel"><div><span className="eyebrow">Internal clinical view</span><h2>{detail.request.patient_display}</h2><p>{detail.request.document_type_code || detail.request.document_type} requested from {detail.request.recipient_name}</p></div><Status value={detail.request.status} /></section>
      <div className="detail-grid">
        <section className="panel detail-card"><h2>Request</h2><dl><dt>Patient</dt><dd>{detail.request.patient_display} · {detail.request.patient_birth_date}</dd><dt>Recipient</dt><dd>{detail.request.recipient_name} · {detail.request.recipient_role}</dd><dt>Delivery</dt><dd>{detail.request.channel} · {detail.request.contact}</dd><dt>Document type</dt><dd>{detail.request.document_type_code || detail.request.document_type}</dd><dt>Purpose / legal basis</dt><dd>{detail.request.purpose_or_legal_basis || detail.request.legal_basis}</dd><dt>Reason</dt><dd>{detail.request.reason}</dd></dl></section>
        <section className="panel detail-card summary-card"><h2>Clinical summary</h2><p className="summary-disclaimer">Deterministic view of coded readings; no clinical interpretation.</p>{detail.summary.groups.length === 0 ? <p>{detail.summary.text}</p> : detail.summary.groups.map((group) => <article className="trend" key={`${group.loinc}-${group.unit}`}><strong>{group.name}</strong><span>LOINC {group.loinc}</span><div>{group.readings.map((reading, index) => <React.Fragment key={`${reading.date}-${index}`}><b>{reading.value} {reading.unit}</b><small>{new Date(reading.date).toLocaleDateString()}</small>{index < group.readings.length - 1 && <i>→</i>}</React.Fragment>)}</div></article>)}</section>
      </div>
      <section className="panel detail-section"><div className="panel-heading"><div><h2>Source documents</h2><p>{detail.submissions.length} preserved submission(s)</p></div></div><div className="detail-list">{detail.submissions.length === 0 ? <p className="empty">No source document submitted yet.</p> : detail.submissions.map((source) => <details key={source.id}><summary><span><strong>{source.filename || "Legacy submission"}</strong><small>{new Date(source.created_at).toLocaleString()} · SHA-256 {source.content_hash.slice(0, 12)}…</small></span><Status value={source.status} /></summary><pre>{source.original_text}</pre></details>)}</div></section>
      <section className="panel detail-section"><div className="panel-heading"><div><h2>FHIR resources</h2><p>{detail.fhir_resources.length} generated resource(s)</p></div></div><div className="detail-list">{detail.fhir_resources.length === 0 ? <p className="empty">No FHIR resources generated yet.</p> : detail.fhir_resources.map((item) => <details key={item.id}><summary><span><strong>{item.resource_type}/{item.id}</strong><small>{item.stored_remotely ? "Stored in HAPI FHIR" : "Not confirmed remotely"}</small></span>{item.remote_url && <a href={item.remote_url} onClick={(event) => event.stopPropagation()}>Open in HAPI ↗</a>}</summary><pre>{JSON.stringify(item.resource, null, 2)}</pre></details>)}</div></section>
      <section className="panel detail-section"><div className="panel-heading"><div><h2>Audit timeline</h2><p>Who, what, when, and outcome</p></div></div><ol className="timeline">{detail.audit.map((event) => <li key={event.id}><span className={`timeline-dot ${event.outcome}`}></span><div><strong>{event.event_type.replaceAll("_", " ")}</strong><small>{event.actor_id} · {event.outcome}</small></div><time>{new Date(event.created_at).toLocaleString()}</time></li>)}</ol></section>
    </>}
  </Shell>;
}

function Invitation({ token }) {
  const [stage, setStage] = useState("loading");
  const [reference, setReference] = useState("");
  const [fullName, setFullName] = useState("");
  const [verification, setVerification] = useState("");
  const [details, setDetails] = useState(null);
  const [patientName, setPatientName] = useState("");
  const [patientBirthDate, setPatientBirthDate] = useState("");
  const [markdown, setMarkdown] = useState("");
  const [files, setFiles] = useState([]);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  useEffect(() => { api(`/api/invitations/${token}`).then((data) => { setReference(data.request_reference); setStage("verify"); }).catch((err) => { setError(err.message); setStage("error"); }); }, [token]);
  const verify = async () => {
    setError("");
    try {
      const data = await api(`/api/invitations/${token}/verify`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ full_name: fullName }) });
      setVerification(data.verification_token);
      const request = await api(`/api/invitations/${token}/details`, { headers: { "X-Verification-Token": data.verification_token } });
      setDetails(request); setPatientName(request.patient_display); setPatientBirthDate(request.patient_birth_date); setStage("submit");
    } catch (err) { setError(err.message); }
  };
  const submit = async (event) => {
    event.preventDefault(); setError(""); setStage("processing");
    const body = new FormData(); body.append("patient_name", patientName); body.append("patient_birth_date", patientBirthDate); body.append("markdown", markdown);
    files.forEach((file) => body.append("files", file));
    try {
      const filed = await api(`/api/invitations/${token}/submit`, { method: "POST", headers: { "X-Verification-Token": verification }, body });
      setResult(filed); setStage("done");
    } catch (err) { setError(err.message); setStage("submit"); }
  };
  return <div className="portal-page"><header><Brand compact /><span className="secure-pill">Secure connection</span></header><main className="portal-card">
    {stage === "loading" && <div className="loading">Loading secure request…</div>}
    {stage === "error" && <><div className="icon-circle error-icon">×</div><h1>Invitation unavailable</h1><p>{error}</p></>}
    {stage === "verify" && <><span className="eyebrow">Request {reference}</span><h1>Verify your name</h1><p className="lead">Patient and document details stay hidden until your name matches the intended recipient.</p><div className="id-austria"><div className="id-logo">ID</div><div><strong>Simulated ID Austria — name matching</strong><small>Demo only; this is not real eID authentication.</small></div></div><label>Full name as shown in ID Austria<input autoFocus value={fullName} onChange={(event) => setFullName(event.target.value)} placeholder="Enter your full name" /></label>{error && <div className="alert error">{error}</div>}<button className="primary wide" disabled={!fullName.trim()} onClick={verify}>Verify and continue</button><p className="fine-print">No account is created. Failed attempts are audited.</p></>}
    {(stage === "submit" || stage === "processing") && details && <form onSubmit={submit}><span className="eyebrow">Name matched</span><h1>Submit requested documents</h1><div className="request-details"><div><small>Patient</small><strong>{details.patient_display}</strong><span>Born {details.patient_birth_date}</span></div><div><small>Requested document</small><strong>{details.document_type}</strong><span>From {details.requesting_clinician}</span></div></div><div className="two-col"><label>Patient full name<input value={patientName} onChange={(event) => setPatientName(event.target.value)} required /></label><label>Birth date<input type="date" value={patientBirthDate} onChange={(event) => setPatientBirthDate(event.target.value)} required /></label></div><label>Upload one to three Markdown files<input type="file" multiple accept=".md,text/markdown" onChange={(event) => setFiles(Array.from(event.target.files).slice(0, 3))} /></label>{files.length > 0 && <div className="file-chips">{files.map((file) => <span key={file.name}>{file.name}</span>)}</div>}<div className="divider"><span>or paste one document</span></div><label>Markdown content<textarea rows="8" value={markdown} onChange={(event) => setMarkdown(event.target.value)} placeholder="# Report…" /></label>{error && <div className="alert error">{error}</div>}<button className="primary wide" disabled={stage === "processing" || (!files.length && !markdown.trim())}>{stage === "processing" ? "Checking and filing batch…" : "Submit securely"}</button></form>}
    {stage === "done" && <><div className="icon-circle success-icon">✓</div><h1>Documents filed securely</h1><p>DocBinder checked the patient, converted the batch to FHIR, and queued the doctor notification.</p><div className="receipt"><span>Reference</span><strong>{result.request_id}</strong><span>Documents</span><strong>{result.documents}</strong><span>FHIR resources</span><strong>{result.resources}</strong></div></>}
  </main><footer>DocBinder prototype · Synthetic data only</footer></div>;
}

const invitationMatch = window.location.pathname.match(/^\/invite\/([^/]+)/);
const requestMatch = window.location.pathname.match(/^\/requests\/([^/]+)/);
createRoot(document.getElementById("root")).render(invitationMatch ? <Invitation token={invitationMatch[1]} /> : requestMatch ? <RequestDetail requestId={requestMatch[1]} /> : <Dashboard />);
