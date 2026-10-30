import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const api = async (path, options = {}) => {
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "Something went wrong.");
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
  return (
    <div className={`brand ${compact ? "compact" : ""}`}>
      <span className="brand-mark" aria-hidden="true">+</span>
      <span><strong>CareBridge</strong><small>Secure clinical exchange</small></span>
    </div>
  );
}

function Status({ value }) {
  return <span className={`status status-${value}`}>{labels[value] || value}</span>;
}

const initialForm = {
  recipient_name: "Dr. Eva Brandl",
  recipient_role: "Lab physician at Labor Kanalstraße",
  expected_identity_id: "AT-EID-EVA-BRANDL",
  channel: "email",
  contact: "eva.brandl@labor-kanal.example",
  document_type: "Laboratory result",
  legal_basis: "necessary_for_treatment",
  reason: "Latest blood clotting results before a planned procedure",
};

function Dashboard() {
  const [tab, setTab] = useState("requests");
  const [requests, setRequests] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [form, setForm] = useState(initialForm);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const refresh = async () => {
    const [reqs, notes] = await Promise.all([
      api("/api/requests"),
      api("/api/demo/notifications"),
    ]);
    setRequests(reqs);
    setNotifications(notes);
  };
  useEffect(() => { refresh().catch((err) => setError(err.message)); }, []);

  const set = (key) => (event) => {
    const value = event.target.value;
    if (key === "recipient_name" && value === "Dr. Eva Brandl") {
      setForm({ ...initialForm });
    } else if (key === "recipient_name" && value === "Stefan Kern") {
      setForm({
        recipient_name: "Stefan Kern",
        recipient_role: "Discharge manager at Reha Waldblick",
        expected_identity_id: "AT-EID-STEFAN-KERN",
        channel: "sms",
        contact: "+43 660 000 0101",
        document_type: "Rehabilitation discharge report",
        legal_basis: "necessary_for_treatment",
        reason: "Rehabilitation discharge report for continued treatment",
      });
    } else setForm((current) => ({ ...current, [key]: value }));
  };

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true); setError(""); setResult(null);
    try {
      const created = await api("/api/requests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      setResult(created);
      await refresh();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };

  const revoke = async (id) => {
    if (!window.confirm(`Revoke request ${id}?`)) return;
    await api(`/api/requests/${id}/revoke`, { method: "POST" });
    refresh();
  };

  const sms = useMemo(() => notifications.filter((item) => item.channel === "sms"), [notifications]);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Brand />
        <nav aria-label="Main navigation">
          <button className={tab === "requests" ? "active" : ""} onClick={() => setTab("requests")}>Requests</button>
          <button className={tab === "new" ? "active" : ""} onClick={() => setTab("new")}>New request</button>
          <button className={tab === "sms" ? "active" : ""} onClick={() => setTab("sms")}>SMS outbox <b>{sms.length}</b></button>
        </nav>
        <div className="doctor-card"><span>LH</span><div><strong>Dr. Lena Hofer</strong><small>Internal medicine</small></div></div>
      </aside>
      <main className="main">
        <header className="topbar">
          <div><span className="eyebrow">Klinikum Beispielstadt</span><h1>{tab === "new" ? "Create document request" : tab === "sms" ? "Simulated SMS outbox" : "Document requests"}</h1></div>
          {tab === "requests" && <button className="primary" onClick={() => setTab("new")}>+ New request</button>}
        </header>
        {error && <div className="alert error">{error}</div>}

        {tab === "requests" && (
          <section className="panel">
            <div className="panel-heading"><div><h2>Recent activity</h2><p>Track external document collection from request to FHIR filing.</p></div><button className="ghost" onClick={refresh}>Refresh</button></div>
            {requests.length === 0 ? <div className="empty"><strong>No requests yet</strong><p>Create the first secure document request.</p></div> :
              <div className="table-wrap"><table><thead><tr><th>Reference</th><th>Recipient</th><th>Document</th><th>Channel</th><th>Status</th><th></th></tr></thead><tbody>
              {requests.map((item) => <tr key={item.id}><td><strong>{item.id}</strong><small>{new Date(item.created_at).toLocaleString()}</small></td><td>{item.recipient_name}<small>{item.recipient_role}</small></td><td>{item.document_type}</td><td className="capitalize">{item.channel}</td><td><Status value={item.status} /></td><td>{!["filed", "revoked"].includes(item.status) && <button className="text-button danger" onClick={() => revoke(item.id)}>Revoke</button>}</td></tr>)}
              </tbody></table></div>}
          </section>
        )}

        {tab === "new" && (
          <form className="request-grid" onSubmit={submit}>
            <section className="panel form-panel">
              <div className="step-title"><span>1</span><div><h2>Patient and recipient</h2><p>Choose who should provide Maria's document.</p></div></div>
              <label>Patient<input value="Maria Beispiel · 12 Mar 1961 · KB-000123" disabled /></label>
              <div className="two-col">
                <label>External professional<select value={form.recipient_name} onChange={set("recipient_name")}><option>Dr. Eva Brandl</option><option>Stefan Kern</option></select></label>
                <label>Role<input value={form.recipient_role} onChange={set("recipient_role")} required /></label>
              </div>
              <div className="two-col">
                <label>Delivery channel<select value={form.channel} onChange={set("channel")}><option value="email">Email</option><option value="sms">SMS</option></select></label>
                <label>Contact<input value={form.contact} onChange={set("contact")} required /></label>
              </div>
              <label>Document type<input value={form.document_type} onChange={set("document_type")} required /></label>
            </section>
            <section className="panel form-panel">
              <div className="step-title"><span>2</span><div><h2>Purpose and legal basis</h2><p>This internal record is retained in the audit trail.</p></div></div>
              <label>Legal basis<select value={form.legal_basis} onChange={set("legal_basis")}><option value="patient_consent_recorded">Patient consent recorded</option><option value="necessary_for_treatment">Necessary for treatment</option><option value="other_documented_legal_basis">Other documented legal basis</option></select></label>
              <label>Reason<textarea value={form.reason} onChange={set("reason")} rows="4" minLength="3" required /></label>
              <div className="privacy-note"><strong>Privacy boundary</strong><p>The invitation contains no patient, birth-date, reason, or document-type details. These appear only after identity verification.</p></div>
              <button className="primary wide" disabled={busy}>{busy ? "Creating…" : "Confirm and send request"}</button>
              {result && <div className="success-card"><strong>{result.id} created</strong><p>The external invitation and patient notice were queued.</p><a href={result.invitation_url}>Open invitation for demo →</a>{result.warnings?.map((warning) => <small key={warning}>{warning}</small>)}</div>}
            </section>
          </form>
        )}

        {tab === "sms" && (
          <section className="panel">
            <div className="panel-heading"><div><h2>Local delivery simulator</h2><p>No real SMS messages leave this environment.</p></div><button className="ghost" onClick={refresh}>Refresh</button></div>
            <div className="phone-list">{sms.length === 0 ? <div className="empty">No simulated messages yet.</div> : sms.map((item) => <article className="message-card" key={item.id}><div className="message-meta"><span className={`audience ${item.audience}`}>{item.audience === "patient" ? "Patient notice" : "External invitation"}</span><time>{new Date(item.created_at).toLocaleString()}</time></div><strong>{item.destination}</strong><p>{item.body}</p>{item.action_url && <a href={item.action_url}>Open secure invitation →</a>}</article>)}</div>
          </section>
        )}
      </main>
    </div>
  );
}

function Invitation({ token }) {
  const [stage, setStage] = useState("loading");
  const [reference, setReference] = useState("");
  const [identity, setIdentity] = useState("AT-EID-EVA-BRANDL");
  const [verification, setVerification] = useState("");
  const [details, setDetails] = useState(null);
  const [markdown, setMarkdown] = useState("");
  const [file, setFile] = useState(null);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  useEffect(() => {
    api(`/api/invitations/${token}`).then((data) => { setReference(data.request_reference); setStage("verify"); }).catch((err) => { setError(err.message); setStage("error"); });
  }, [token]);

  const verify = async () => {
    setError("");
    try {
      const data = await api(`/api/invitations/${token}/verify`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ identity_id: identity }) });
      setVerification(data.verification_token);
      const request = await api(`/api/invitations/${token}/details`, { headers: { "X-Verification-Token": data.verification_token } });
      setDetails(request); setStage("submit");
    } catch (err) { setError(err.message); }
  };

  const submit = async (event) => {
    event.preventDefault(); setError(""); setStage("processing");
    const data = new FormData();
    data.append("patient_name", details.patient_display);
    data.append("patient_birth_date", details.patient_birth_date);
    data.append("markdown", markdown);
    if (file) data.append("file", file);
    try {
      const filed = await api(`/api/invitations/${token}/submit`, { method: "POST", headers: { "X-Verification-Token": verification }, body: data });
      setResult(filed); setStage("done");
    } catch (err) { setError(err.message); setStage("submit"); }
  };

  return (
    <div className="portal-page">
      <header><Brand compact /><span className="secure-pill">Secure connection</span></header>
      <main className="portal-card">
        {stage === "loading" && <div className="loading">Loading secure request…</div>}
        {stage === "error" && <><div className="icon-circle error-icon">×</div><h1>Invitation unavailable</h1><p>{error}</p></>}
        {stage === "verify" && <>
          <span className="eyebrow">Request {reference}</span><h1>Verify your identity</h1><p className="lead">Patient and document details stay hidden until CareBridge confirms you are the named recipient.</p>
          <div className="id-austria"><div className="id-logo">ID</div><div><strong>Simulated ID Austria</strong><small>Hackathon identity provider</small></div></div>
          <label>Choose a demo identity<select value={identity} onChange={(e) => setIdentity(e.target.value)}><option value="AT-EID-EVA-BRANDL">Dr. Eva Brandl</option><option value="AT-EID-STEFAN-KERN">Stefan Kern</option><option value="AT-EID-KOLLEGE">Colleague (misdelivery test)</option></select></label>
          {error && <div className="alert error">{error}</div>}
          <button className="primary wide" onClick={verify}>Continue with simulated ID Austria</button>
          <p className="fine-print">No account is created. Failed identity checks are audited.</p>
        </>}
        {(stage === "submit" || stage === "processing") && details && <form onSubmit={submit}>
          <span className="eyebrow">Identity confirmed</span><h1>Submit requested document</h1>
          <div className="request-details"><div><small>Patient</small><strong>{details.patient_display}</strong><span>Born {details.patient_birth_date}</span></div><div><small>Requested document</small><strong>{details.document_type}</strong><span>From {details.requesting_clinician}</span></div></div>
          <label>Upload Markdown file<input type="file" accept=".md,text/markdown" onChange={(e) => setFile(e.target.files[0])} /></label>
          <div className="divider"><span>or paste Markdown</span></div>
          <label>Markdown content<textarea rows="9" value={markdown} onChange={(e) => setMarkdown(e.target.value)} placeholder="# Report…" /></label>
          {error && <div className="alert error">{error}</div>}
          <button className="primary wide" disabled={stage === "processing" || (!file && !markdown.trim())}>{stage === "processing" ? "Checking and filing…" : "Submit securely"}</button>
        </form>}
        {stage === "done" && <><div className="icon-circle success-icon">✓</div><h1>Document filed securely</h1><p>CareBridge verified the patient, converted the document to FHIR, and notified the requesting doctor.</p><div className="receipt"><span>Reference</span><strong>{result.request_id}</strong><span>FHIR resources</span><strong>{result.resources}</strong></div></>}
      </main>
      <footer>CareBridge prototype · Synthetic data only</footer>
    </div>
  );
}

const match = window.location.pathname.match(/^\/invite\/([^/]+)/);
createRoot(document.getElementById("root")).render(match ? <Invitation token={match[1]} /> : <Dashboard />);

