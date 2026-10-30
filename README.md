## Potential Issues & Pitfalls in CareBridge

After reviewing all provided files, the system is well‑architected and nearly complete. However, several critical issues could affect the hackathon metrics. I’ve prioritized them by severity.

---

### 🔴 Critical (will cause metric failure)

1. **Invalid UCUM unit codes for lab values**  
   - `parser.py` uses raw unit strings directly as UCUM `code`.  
   - **Platelets** unit is `10^9/L`, but the correct UCUM code is `10*9/L`.  
   - The HL7 validator will flag `10^9/L` as an invalid code.  
   - **Fix:** Add a unit mapping (e.g., `10^9/L → 10*9/L`, `10^12/L → 10*12/L`) in `parser.py` or `fhir.py` when constructing `valueQuantity`.

2. **No automated HL7 validation**  
   - The submission flow does **not** run the official validator; it sends resources directly to HAPI.  
   - The metric requires **0 errors from the HL7 validator** on every resource.  
   - You must either:  
     - Integrate `validator_cli.jar` into the backend (preferred, but time‑consuming), or  
     - Manually export resources and run `./scripts/validate-fhir.sh` before the demo, then present the output.  
   - **Note:** Even if you run manually, the invalid UCUM codes will produce errors. Fix unit codes first.

3. **Missing `effectiveDateTime` in `Observation`**  
   - The validator does not require it, but clinical usefulness is improved. The challenge asks for useful FHIR. Adding the sample/report time would strengthen the resource. Not a hard failure, but recommended.

---

### 🟠 High (could break functionality or demo)

4. **HAPI FHIR readiness**  
   - Backend attempts to PUT patient and POST transaction bundle without retry. If HAPI isn’t fully started, the request fails with 503.  
   - **Mitigation:** Wait for HAPI health (`http://localhost:8081/fhir/metadata`) before testing; consider adding a simple retry loop.

5. **Patient resource file path**  
   - `main.py` uses `Path("/scenario/patient.json")`. In the Docker container, this path may not exist unless the backend image includes the `scenario` directory.  
   - **Check:** Verify that the backend Dockerfile copies the `scenario` folder (or change the path to `/app/scenario/patient.json`). If missing, the patient PUT will fail.

6. **Invitation URL host**  
   - `PUBLIC_BASE_URL` defaults to `http://localhost:3000`. If the jury tests from a different machine, the link won’t work.  
   - **Fix:** Set `PUBLIC_BASE_URL` to the machine’s LAN IP or a public tunnel URL in `.env`.

7. **Matrix bot environment variable mismatch**  
   - `matrix-bot` expects `MATRIX_PASSWORD`, but `docker-compose.yml` passes `MATRIX_PASSWORD: ${BOT_MATRIX_PASSWORD:-carebridge-bot-demo}`. This is correct, but ensure `.env` defines `BOT_MATRIX_PASSWORD`. The script `matrix-create-users.sh` also reads that variable.

---

### 🟡 Medium (quality and usability)

8. **Frontend form does not ask for patient name/birthdate**  
   - The React invitation component automatically uses the verified request’s patient details and sends them as hidden form fields.  
   - The challenge says the form *must* ask for patient name and birthdate.  
   - **Solution:** Add two input fields pre‑filled with `details.patient_display` and `details.patient_birth_date` but **editable** (or at least visible) so the outside person confirms them. This also better satisfies the metric “effort for the outside person” (they should consciously confirm). The backend will still validate.

9. **Observation `code.display`**  
   - `fhir.py` sets `display` to the test name (e.g., “INR (prothrombin time)”). The LOINC code `6301-6` official display is “INR in Platelet poor plasma by Coagulation assay”. The validator may complain if the display does not match the code, but usually it’s a warning, not error. To be safe, you can remove `display` or use the official term.

10. **Reference range missing**  
    - The supplied lab report includes reference ranges, but the generated `Observation` does not include `referenceRange`. Not required, but clinically useful and easy to add.

11. **Matrix rooms unencrypted**  
    - The README acknowledges this. It is acceptable for the hackathon, but note it in the pitch.

---

## Step‑by‑Step Testing Guide

### 0. Prerequisites

- Docker Desktop (with Compose) running.
- Java (for HL7 validator, if you choose to run it manually).
- Clone the repository and navigate to its root.

---

### 1. Environment Setup

```bash
cd CareBridge   # or whatever the folder is named
cp .env.example .env
# Edit .env if you want to change passwords or BASE_URL
```

Generate Synapse configuration:

```bash
./scripts/matrix-init.sh
```

---

### 2. Start the Stack

```bash
docker compose up -d --build
```

Wait for all services to be ready. Check status:

```bash
docker compose ps
docker compose logs -f backend hapi-fhir
```

**Wait until HAPI FHIR is ready** (open `http://localhost:8081/fhir/metadata` in a browser – it should return JSON).

---

### 3. Create Matrix Users

```bash
./scripts/matrix-create-users.sh
```

This creates:
- `@lena.hofer:klinikum.example` (password from `.env`)
- `@carebridge:klinikum.example` (bot)

---

### 4. Open Services

| Service | URL |
|---------|-----|
| CareBridge dashboard (doctor) | http://localhost:3000 |
| Element Web (Matrix client) | http://localhost:8080 |
| Mailpit (email) | http://localhost:8025 |
| FastAPI docs | http://localhost:8000/docs |
| HAPI FHIR | http://localhost:8081/fhir |

---

### 5. Test Doctor Flow via Matrix

1. Open Element Web (`http://localhost:8080`).
2. Sign in as `@lena.hofer:klinikum.example` with the doctor password (from `.env`, default `carebridge-doctor-demo`).
3. Create a new **private, unencrypted** room.
4. Invite the bot: `@carebridge:klinikum.example`.
5. In the room, send `!request-document`.
6. Follow the guided prompts:
   - Choose `1` for Dr. Eva Brandl (lab) or `2` for Stefan Kern (rehab).
   - Enter role, channel, contact, document type, legal basis, reason.
   - Review summary and reply `confirm`.
7. The bot should respond with “✅ Request CBR-… created…”.

---

### 6. Inspect Invitation Delivery

- **Lab request:** Open Mailpit (`http://localhost:8025`). Find the email to `eva.brandl@labor-kanal.example`. It should contain **only** a generic message and a link. No patient name, birthdate, or document type.
- **Rehab request:** Open the CareBridge dashboard (`http://localhost:3000`), click the “SMS outbox” tab. You’ll see an entry for Stefan Kern’s number. It also contains only a generic link.

---

### 7. Test External Professional Flow

#### 7.1 Open Invitation Link

Click the link from the email (Mailpit) or the SMS outbox.

- You will be taken to the invitation portal (`/invite/<token>`).
- Initially, you see only “Verify your identity” with a simulated ID Austria selection.

#### 7.2 Verify Identity

- **Correct identity:** Choose “Dr. Eva Brandl” (for lab) or “Stefan Kern” (for rehab). Click continue.
- After successful verification, you will see the patient details and document type (now visible).

#### 7.3 Submit Document

- Upload `scenario/documents/lab-result-maria-beispiel.md` (for lab) or `rehab-report-maria-beispiel.md` (for rehab), **or** paste the Markdown content.
- The form will show patient name and birthdate (pre‑filled). In the current version they are not editable; we’ll fix that later.
- Click “Submit securely”.
- You should see a success page: “Document filed securely” with reference and number of resources.

#### 7.4 Verify FHIR Storage

- Go to HAPI FHIR (`http://localhost:8081/fhir/Observation`) – you should see 4 observations (for lab) or `DocumentReference` (for rehab).
- Check that the `Provenance` resource exists.

#### 7.5 Check Audit Log

- In the CareBridge dashboard, click on the request (or use API):
  - `GET http://localhost:8000/api/requests/{request-id}/audit`
- Confirm the six required events appear: `request_sent`, `link_opened`, `identity_checked`, `answer_sent`, `answer_filed`, and no `misdelivery_caught` (unless testing).

---

### 8. Test Misdelivery Scenarios

#### M1 – Wrong Address

- Create a lab request but mistype the email address (e.g., `eva.brandl@labor-kanaI.example` with capital I). You can do this via the dashboard “New request” form (edit contact) or Matrix bot.
- Open the link from Mailpit.
- On the identity page, choose **“Colleague (misdelivery test)”**.
- Submit. You should be blocked with a generic failure page.
- Check audit log: `identity_checked` (failure) and `misdelivery_caught` events.

#### M2 – Forwarded Request

- Use a valid request for Dr. Brandl. Open the link, but on identity page choose “Colleague”.
- Same as M1: blocked, audit records failure.

#### M3 – Wrong Patient

- Use a valid lab request for Dr. Brandl. Verify correctly as Dr. Brandl.
- Upload `scenario/documents/lab-result-max-beispiel.md` (or paste its content).
- The backend will detect the patient mismatch (from document content) and reject before FHIR storage.
- You should see an error message (or a “Not sent on” equivalent). The audit log will contain `patient_mismatch` and `misdelivery_caught`.

---

### 9. Run HL7 Validator (Manual)

1. Download `validator_cli.jar` from the official HAPI releases and place it in the repository root.
2. Export the FHIR resources for a request via API:
   - `GET http://localhost:8000/api/requests/{request-id}/fhir` returns a JSON list of resources.
3. Save each resource to a separate `.json` file.
4. Run the validation script:
   ```bash
   ./scripts/validate-fhir.sh path/to/resource1.json path/to/resource2.json ...
   ```
5. Confirm **0 errors** for every resource. If you see errors about invalid UCUM units, fix the unit mapping first.

---

### 10. Run Automated Tests

```bash
PYTHONPATH=backend python3 -m pytest -q backend/tests
PYTHONPATH=matrix-bot python3 -m pytest -q matrix-bot/tests
docker compose config --quiet
```

With the stack running:

```bash
docker compose exec -T backend python tests/integration_smoke.py
docker compose exec -T backend python tests/matrix_smoke.py
```

---

### 11. Prepare for Demo

- Record a 2‑minute video showing:
  1. Doctor creating request in Matrix.
  2. Invitation in Mailpit/SMS with privacy preserved.
  3. Identity verification and document submission.
  4. FHIR resources in HAPI.
  5. Audit log with six events.
  6. Misdelivery test (e.g., wrong identity or wrong patient).
- Update README with metric results and design answers (already mostly done).

---

## Immediate Action Items

1. **Fix UCUM unit mapping** in `parser.py` or `fhir.py`.
2. **Add patient name/birthdate inputs** (visible, editable) to the React invitation form.
3. **Test HAPI readiness** and possibly add retry logic.
4. **Decide on HL7 validation strategy** – integrate or manual.
5. **Ensure patient.json path** is correct inside backend container.

If you address the critical issues above, the system should meet all hackathon requirements.





# Track 2: Health Data Interoperability

Austrian doctors are piloting PGK, a closed document network built on Matrix. Patients, labs and rehab clinics outside the network are still reached by fax or unencrypted email and their results come back as scans that someone types in by hand.

## What to build

A service that lets a doctor in the network request a document from someone outside it and files the answer as FHIR R4.

1. Dr. Lena Hofer requests the document from her Matrix room, through a bot or a widget.
2. The outside person gets a link by email or SMS, proves who they are and answers in the browser. They need no account and install nothing. You can simulate an electronic ID such as ID Austria.
3. Your service turns the answer into FHIR resources plus a Provenance resource: who sent it, when and how their identity was checked.
4. It stores the resources on a FHIR server and tells Dr. Hofer in Matrix.

Also:

- Lab values become Observations with their LOINC codes. The rehab report can be a DocumentReference with the text attached.
- Write an audit entry at each of the six steps listed under Metrics.
- Catch misdeliveries, such as a request sent to the wrong address.
- Emails and SMS must not contain the patient's name, birth date or the type of document.
- You may use commercial products, FTAPI's included, as long as each one could be replaced by another.

You do not need your own Matrix app or end-to-end encryption. Element Web and an upload over HTTPS are enough.

## What you get

- `scenario/README.md`: the people, the two requests (lab result by email, rehab report by SMS) and suggested tools.
- `scenario/patient.json`: the patient, Maria Beispiel, as a FHIR Patient.
- `scenario/documents/`: the answers as Markdown, plus a lab result for a different patient.
- `scenario/misdelivery.md`: three misdelivery tests.

There is no starter code.

## Metrics

Measure these on the scenario. The jury also tests with other outside people and documents in the same Markdown format, some of them for the wrong patient.

| Metric | How to measure | Target |
|---|---|---|
| FHIR validation | Errors from the HL7 validator on every resource you file (command in `scenario/README.md`) | 0 |
| Effort for the outside person | Someone new answers request 1. Count the installs and accounts they need and the time from opening the email to sending | 0, 0, under 2 min |
| Misdeliveries caught | The three tests in `scenario/misdelivery.md`, run on request 1 | 3 of 3 |
| Audit coverage | Steps logged with who, what and when: request sent, link opened, identity checked, answer sent, answer filed, misdelivery caught | 6 of 6 |

## Your design

Answer these in your repository README:

1. How does an outside person prove who they are if they are in no directory?
2. Which identity check do you require for each type of document and why?
3. Which FHIR resources do you create and how do they reference each other and the patient?
4. How do you notice a misdelivery?
5. Where does your service run: at the clinic, at the outside organisation or at a third party?

## Rules

Use only synthetic data.

## Judging

| Criterion | Weight | Question |
|---|---|---|
| Clinical approach and impact | 33.3% | Would a lab, rehab clinic or patient answer this way? Could a clinic run it? |
| Technical quality and AI | 33.3% | Is the FHIR data valid and useful? Is the identity check strong enough without burdening the outside person? If you use AI, is its output correct? |
| Execution and prototype | 33.3% | Does the whole flow work, on this scenario and on new documents? |

The jury scores each criterion from 1 to 10 and takes your metric results into account.

## Submission

1. A video of up to 2 minutes showing your demo. Say what works and what does not.
2. A link to your public repository with instructions to run it and your design answers. Its README has to explain your technical architecture: which components you built, how they work together and which models or services you use.
3. Your metric results on this scenario.

---

## CareBridge prototype

This repository now contains a runnable end-to-end prototype:

- **Element Web + Synapse** for Dr. Hofer's internal workflow.
- **Python Matrix bot** with a guided `!request-document` conversation.
- **FastAPI + SQLite** for request state, hashed invitations, identity checks, audit events and notifications.
- **React portal** for simulated ID Austria verification and Markdown upload/paste.
- **Mailpit** for external email and an in-app SMS outbox for external and patient messages.
- **Deterministic Markdown parsing** for the supplied lab and rehabilitation reports.
- **FHIR R4 generation** and transaction filing into HAPI FHIR.

Only synthetic scenario data is supported. This is a local hackathon prototype, not a production deployment.

## Quick start

Requirements: Docker Desktop with Docker Compose. Java is needed only for the optional standalone HL7 validator.

```bash
cd TRACK-2-interoperability
cp .env.example .env
./scripts/matrix-init.sh
docker compose up -d --build
```

HAPI FHIR can take a minute or two to become ready on its first start. Inspect the stack with:

```bash
docker compose ps
docker compose logs -f backend hapi-fhir
```

Create the two local Matrix accounts after Synapse is running:

```bash
./scripts/matrix-create-users.sh
```

The bot retries login while the accounts are being created, so no manual bot restart is normally required.

Open the services:

| Service | URL |
|---|---|
| CareBridge portal/dashboard | http://localhost:3000 |
| Element Web | http://localhost:8080 |
| Mailpit | http://localhost:8025 |
| FastAPI documentation | http://localhost:8000/docs |
| HAPI FHIR | http://localhost:8081/fhir |
| Synapse client API | http://localhost:8008 |

The default synthetic credentials from `.env.example` are:

```text
Matrix user: @lena.hofer:klinikum.example
Password: carebridge-doctor-demo
```

Change these values if the environment will be accessible to anyone else.

### Element and bot demo

1. Sign in to Element as `@lena.hofer:klinikum.example`.
2. Create a private **unencrypted** room. Encryption is intentionally out of scope for this local challenge.
3. Invite `@carebridge:klinikum.example`.
4. Send `!request-document`.
5. Follow the prompts and reply `confirm` after the summary.
6. Use `!requests` to show recent workflow state or `!revoke CBR-...` to revoke an active request.

Element reserves slash commands, so the demo uses `!request-document`, although the bot also accepts `/request-document` if another client sends it literally.

### External professional demo

For the laboratory flow:

1. Create Eva's request in Matrix or on the CareBridge dashboard.
2. Open Mailpit and select the invitation sent to `eva.brandl@labor-kanal.example`.
3. Open its secure link.
4. Choose the simulated identity **Dr. Eva Brandl**.
5. Upload `scenario/documents/lab-result-maria-beispiel.md` or paste its content.
6. Submit. CareBridge checks the patient, creates four Observations plus Provenance, files them in HAPI FHIR and queues the Matrix success notification.

For the rehabilitation flow, choose Stefan Kern, obtain the invitation from the dashboard's **SMS outbox**, verify as Stefan and upload `rehab-report-maria-beispiel.md`.

The SMS outbox also shows Maria's informational patient notice separately from the external invitation. That notice is not presented as consent or approval.

## Misdelivery demo

- **Wrong/forwarded recipient:** choose the “Colleague” identity. The request stays hidden and a `misdelivery_caught` audit event is written. Five failed checks lock the invitation and notify Dr. Hofer.
- **Wrong patient:** verify as Eva but upload `lab-result-max-beispiel.md`. CareBridge rejects it before FHIR storage and notifies Dr. Hofer.
- **Invitation privacy:** inspect the Mailpit or SMS message before verification. It includes only a request reference and generic action link—not the patient, birth date, reason or document type.

View audit events and generated resources through the API:

```text
GET http://localhost:8000/api/requests/{request-id}/audit
GET http://localhost:8000/api/requests/{request-id}/fhir
```

## Tests

The core tests intentionally use only the Python standard library and pytest, so they run before container dependencies are installed:

```bash
PYTHONPATH=backend python3 -m pytest -q backend/tests
PYTHONPATH=matrix-bot python3 -m pytest -q matrix-bot/tests
docker compose config --quiet
```

With the Compose stack running, the live API/FHIR and Matrix smoke scripts are:

```bash
docker compose exec -T backend python tests/integration_smoke.py
docker compose exec -T backend python tests/matrix_smoke.py
```

The first script files Maria's lab result and verifies rejection of Max's wrong-patient report. The second creates a private Matrix demo room, invites the bot and checks its `!help` reply. The Matrix script uses the default synthetic password from `.env.example`; update it if you change that credential.

For formal HL7 FHIR R4 validation, place the official `validator_cli.jar` in the repository root, export API resources as individual JSON files and run:

```bash
./scripts/validate-fhir.sh path/to/resource.json
```

## Architecture and design answers

### 1. How does an outside person prove who they are?

The invitation reveals no clinical details. The recipient first completes a simulated ID Austria flow that returns an immutable synthetic subject identifier. FastAPI compares that identifier with the named recipient stored on the request. The browser cannot decide the match. A failed match reveals neither the expected person nor the patient.

### 2. Which identity check is required and why?

Both document types require the same simulated eID check because both contain sensitive health data and must be attributed to a named professional. Name or link possession alone is not sufficient. The architecture keeps the identity provider behind an adapter so a production eID service can replace the simulator.

The doctor must also attest a legal basis and enter a reason. This is auditable but is not claimed to be independent proof of patient consent. Maria receives a synthetic informational SMS; direct patient approval is deferred.

### 3. Which FHIR resources are created?

The lab report becomes four `Observation` resources coded with the supplied LOINC identifiers and referencing `Patient/maria-beispiel`. The rehabilitation report becomes a `DocumentReference` containing the original Markdown. Each submission also creates `Provenance`, recording the verified submitter and preserving the distinction between report author and submitter.

Resources are sent to HAPI in one FHIR transaction Bundle. Failed filing does not mark the request as successfully filed.

### 4. How is a misdelivery noticed?

The external link is only a capability to begin verification. It is not sufficient to view or answer the request. An identity mismatch is blocked and audited, repeated failures lock the invitation, and wrong-patient content is rejected by name and birth-date matching before FHIR conversion/storage. Dr. Hofer receives Matrix notifications for lockout, mismatches and processing failures.

### 5. Where does the service run?

The prototype runs as a clinic-controlled Docker Compose deployment. External professionals access only the browser invitation portal. Mail, SMS, identity and FHIR services are replaceable adapters; the local demo uses Mailpit, an SMS outbox, simulated eID and HAPI FHIR.

## Known prototype limitations

- Matrix rooms are deliberately unencrypted for the local hackathon demo.
- Invitation links do not automatically expire, per the agreed MVP decision; they are hashed, revocable, single-use and subject to identity lockout.
- The internal demo API has no separate web login and must remain on a trusted local machine.
- The FHIR CLI validator is not bundled because its JAR must be obtained from the official HL7/HAPI release.
- OCR, scanned PDFs, AI extraction, real SMS/email, real ID Austria and direct patient approval are deferred.
