# CareBridge hackathon review

**Most of the intended workflow is implemented, but the project has not yet fulfilled all requirements.** The largest jury risks are the missing privacy boundary, weak simulated identity boundary, support limited to predefined recipients, incorrect document classification, unreliable notifications, and missing metric evidence.

This report combines the Codex review and the supplied Claude review. It prioritizes demonstrated issues and distinguishes requirements from optional improvements.

**Evidence and limitations:** Codex read both READMEs, the misdelivery scenarios, and application code; all eight existing unit tests passed, and `docker compose config --quiet` passed. Additional isolated API checks used a temporary database and mocked FHIR responses. The Docker stack was stopped, so live HAPI storage and Matrix delivery were not verified. Neither review ran the official HL7 validator or a timed usability trial. Claude's supplied review was based on code inspection. Successful mocked filing is not evidence of live FHIR conformance or delivery.

**The most important findings, in priority order:**

1. **Critical: an unverified visitor can access patient information through the internal API.**

   `GET /api/requests` and `GET /api/requests/{id}` require no authentication. Isolated checks confirmed exposure of patient name, birth date, requested document, reason, and expected identity ID. The notifications endpoint exposes invitation URLs, and unauthenticated revocation succeeds.

   Nginx proxies all `/api/` routes through the same frontend used by outside recipients. Navigating to the root also opens the dashboard. Calling the API “internal” or describing the deployment as local does not establish an access boundary.

   **Jury challenge:** “You blocked the colleague on the verification screen. What happens if they open `/api/requests`?”

   This directly undermines M1: the wrong recipient must not see patient or document details.

   **Fix:** authenticate and authorize internal routes, protect the dashboard and demo outboxes, and limit public routes to the invitation workflow. See [main.py](backend/app/main.py) and [nginx.conf](frontend/nginx.conf).

2. **High: the simulated identity check trusts a browser-selected identity.**

   Simulated eID is explicitly allowed; a real ID Austria integration is not required. However, the backend currently compares a browser-supplied `identity_id` with the expected string. There is no assertion from an independent simulator. Replaying the expected identity successfully unlocks details.

   The dropdown defaults to Eva. Anyone opening Eva's forwarded or misaddressed invitation can press Continue as Eva. Conversely, Stefan's invitation also defaults to Eva, so accepting the default creates a failed attempt.

   The README claim that “the browser cannot decide the match” is technically narrow: the server compares the values, but the browser chooses the identity being compared.

   **Fix:** use a separate synthetic identity-provider step, with per-person test credentials and a server-verifiable assertion bound to the verification flow. Do not expose signing credentials or identity proof in the browser, and do not preselect an identity. Clearly label the simulation and its assumptions. See [verification endpoint](backend/app/main.py) and [portal](frontend/src/main.jsx).

3. **High: the normal workflow cannot handle new outside people.**

   Both the bot and dashboard restrict recipients to Eva and Stefan, while the portal offers fixed identities. The backend accepts arbitrary expected identity IDs, but there is no complete user-facing workflow for another recipient. The README explicitly says the jury will test other outside people.

   There is also an unanswered design question: Dr. Hofer knows only the person's name, role, and contact. How does she obtain the expected immutable eID subject? The implementation preloads that knowledge.

   Maria is hardcoded in the ordinary workflow. Supporting arbitrary patients would improve reuse, but the explicit jury requirement concerns other outside people and documents, including wrong-patient documents; do not confuse these scopes.

   **Fix:** support arbitrary synthetic recipients and explain how verified identity attributes are matched to the intended named person without assuming a pre-existing directory. See [workflow.py](matrix-bot/carebridge_bot/workflow.py).

4. **High: ordinary wording can produce the wrong FHIR resource type.**

   The backend selects the lab converter only when `document_type` contains `lab`. Everything else becomes a rehabilitation `DocumentReference`.

   **Confirmed reproduction:** requesting “Blood clotting tests” and submitting Maria's valid lab report produced a `DocumentReference` and `Provenance`, with zero Observations. This is plausible during the demo because the bot asks for free text.

   **Fix:** use a structured document-type field, separate from its description. Reject unsupported types rather than defaulting to rehab. See [main.py](backend/app/main.py).

5. **High: parsing can silently lose results and is limited to the supplied lab codes.**

   `ALLOWED_LOINC` contains only the four scenario codes. A new coded laboratory test in the same Markdown layout is rejected. Rows with unexpected cell counts are silently skipped.

   **Confirmed reproduction:** adding an extra cell to the platelet row yielded a successful submission with three Observations plus Provenance. The missing measurement was not reported. An impossible birth date, `31 February 1961`, returned HTTP 500 instead of a controlled parsing error.

   **Fix:** reject malformed result rows explicitly, validate dates and finite numeric values, and define a policy for validating new supplied LOINC codes and units. Do not blindly trust arbitrary codes or silently omit clinical data. See [parser.py](backend/app/parser.py).

6. **High: dashboard-created requests do not reach Matrix.**

   Dashboard requests omit `matrix_room_id`. Notifications then target `@lena.hofer:klinikum.example`, but the bot only delivers destinations starting with `!`, indicating a room.

   **Confirmed:** an isolated wrong-patient submission created through the dashboard queued a notice to the user ID. Code inspection shows the delivery loop skips it. This fails M3's requirement to tell Dr. Hofer in her Matrix room through that path. Matrix-created requests supply a room, but their live delivery remains unverified.

   The bot also discards the return value from `room_send`, so delivery acknowledgment is not tied to checking a successful Matrix response. The portal claims the doctor was notified immediately after queuing.

   **Fix:** require or resolve a destination room, check send results, retain failed notifications for retry, and distinguish queued from delivered. See [notifications.py](backend/app/notifications.py), [bot](matrix-bot/carebridge_bot/__main__.py), and [portal](frontend/src/main.jsx).

7. **High: required metric results are missing.**

   The repository describes how to test but does not publish measured results for the four required metrics. The validator helper is not a validation report, and passing unit tests does not establish zero FHIR validation errors.

   **Fix:** validate every filed resource, run M1–M3 end to end, demonstrate all six audit categories, and time a first-time external user. Publish results with commands, dates, and supporting artifacts. See [README](README.md) and [validator helper](scripts/validate-fhir.sh).

8. **Medium: retry handling produces misleading storage records and risks duplicates.**

   Each retry generates new resource IDs. After a simulated filing timeout followed by a successful retry, ten local resources were marked remotely stored, although only the second batch had a confirmed successful response. The update marks all resources for the request, including the failed batch.

   If HAPI committed before the response timed out, retrying with fresh IDs can also create duplicate clinical results. The local FHIR endpoint returns both batches.

   **Fix:** preserve submission and resource IDs across retries, reconcile ambiguous outcomes, and track storage per submission. Add explicit state transitions and atomic submission claims. Concurrent submission behavior has not been tested; it should not be claimed safe based on the current tests. See [main.py](backend/app/main.py).

9. **Medium: FHIR output loses clinical context and uses Provenance fields poorly.**

   Observations omit the supplied sample/report times and performer. Reference ranges exist only as notes. These omissions weaken clinical usefulness even if structural validation succeeds. Matrix success messages provide neither a result summary nor a link to the filed resources.

   Provenance correctly separates report author and submitter, but places the verification method and identity ID in `agent.onBehalfOf.display`. That field describes the represented person or organization, not the authentication method. Use a stable agent identifier and an explicitly modeled verification record. See [fhir.py](backend/app/fhir.py) and the [FHIR R4 definition](https://hl7.org/fhir/R4/provenance-definitions.html#Provenance.agent.onBehalfOf).

   `Provenance.recorded` is present. Adding `occurredDateTime` could distinguish activity time from recording time, but its absence alone is not an R4 validation error: it is optional.

   **Fix:** preserve clinical timestamps, structured reference ranges, and attribution; improve verification metadata; give the doctor a useful result link or summary.

**FHIR concerns that require careful wording:**

- **Do not report `10^9/L` as invalid UCUM.** Claude's proposed correction is unnecessary: UCUM defines both `10^` and `10*` for powers of ten. See the [UCUM specification](https://ucum.org/ucum). This does not replace validation of the complete resources.
- The generator copies document test labels into `Coding.display`. Whether these agree with accepted LOINC displays needs terminology validation. This is an unverified concern, not a demonstrated validator error. Preserve local wording in `code.text`; use a validated display or omit the optional coding display.
- No formal validator results are available. Do not claim either zero errors or confirmed validation failures based only on these reviews.

**Requirement-by-requirement assessment:**

| Requirement | Assessment |
|---|---|
| Request initiated through Matrix | Implemented; live flow not verified |
| Email lab invitation and simulated SMS rehab invitation | Implemented; templates contain no prohibited clinical details |
| Browser response without account or installation | Implemented |
| Named recipient verification | Partial: fixed simulator identities and privacy bypass |
| Lab Observations with LOINC codes | Works for supplied fixture when correctly classified; isolated test used mocked storage |
| Rehab DocumentReference with attached text | Implemented; isolated test used mocked storage |
| Provenance: sender, time, verification method | Present, but identity semantics need improvement |
| FHIR storage and Matrix notification | Implemented with retry/delivery gaps; live success unverified |
| Other outside people and same-format documents | Not adequately supported |
| Six audit categories | All six observed across isolated success/misdelivery checks |
| Five README design answers and architecture | Present; some claims exceed implementation |
| Replaceable services | Standard protocols/configuration help; claimed adapter boundaries are incomplete |
| HTTPS upload | Not configured in supplied deployment |
| Synthetic data | Supplied fixtures and demo identities comply |
| Required metric results | No measured results found |
| Two-minute video and public repository submission | Not verifiable from the local checkout |

**Current evidence for the four metrics:**

| Metric | Target | Current evidence and remaining work |
|---|---|---|
| FHIR validation | Zero errors on every filed resource | Not measured. Run official HL7 validation, including Patient and Provenance, and retain output. |
| Outside-person effort | Zero installs, zero accounts, under two minutes | Accountless browser flow exists. Time someone unfamiliar with the app, starting from the email. |
| Misdeliveries | Three of three caught, with audit evidence | Wrong identity is rejected within the simulator, but M1/M2 have bypasses. Max's report is rejected before FHIR calls; M3 Matrix delivery remains unproven and fails through the dashboard path. |
| Audit coverage | Six of six steps, with who/what/when | All six categories observed in isolated checks. Demonstrate them against the complete live scenarios and distinguish queued from delivered events. |

**Additional weaknesses a jury may raise:**

- **The patient form check is circular.** The portal submits name and birth date from the server's expected details rather than independently collecting them. The document-header check performs the real matching and successfully rejects Max. Make this clear; for the typed-form interpretation of the scenario, collect the patient details from the submitted document rather than silently echoing the request.
- **Email warnings can arrive too late.** The backend's uppercase-domain warning is returned after invitation creation/delivery. The bot warns earlier about `.con`, but not uppercase domains. Surface useful warnings before confirmation. A warning is not a replacement for recipient verification.
- **Failed email delivery has no retry worker.** SMTP failures leave a queued notification, while the request and audit say sent. Make queued/delivered/failed states accurate and retry delivery.
- **Lockout permits denial of service.** A link holder can force five failures and lock out the intended recipient. There is no dedicated reissue/recovery flow. Preserve the required lockout, but provide an auditable recovery path.
- **Audit attribution has limits.** Failed checks record the client-claimed identity. Label it as claimed, not verified. Rejected submissions do not reach the later `answer_sent` event. Review event semantics. Tamper evidence and additional request metadata are hardening options, not explicit hackathon requirements.
- **Adapter claims are stronger than the code.** SMTP and FHIR calls are embedded in workflow code; the simulator and SMS outbox have no clear replacement interfaces. Thin boundaries would help, but standard protocols already provide some portability. An adapter class hierarchy is not itself a judging requirement.
- **Design answer Q2 can be more convincing.** Requiring the same eID assurance for both document types is defensible. Explain why identity assurance is independent of email/SMS delivery, and why the verified submitter can differ from the document author. Using the same check is not itself a failure.
- **External deployment is underspecified.** Links point to `http://localhost:3000`, and the UI says “Secure connection” despite HTTP. Explain the reachable hostname, TLS termination, and separation of external and clinic interfaces. A particular DMZ design is not mandated.
- **Build reproducibility is limited.** Several images use `:latest`, and frontend installation has no committed lockfile. Pin a tested release set before the jury runs it.

**What already works well:**

- The architecture covers the requested components and keeps the external workflow simple.
- Invitation text excludes patient name, birth date, and document type.
- Invitation lookup uses a token hash; used, revoked, and locked invitations are rejected. However, raw invitation URLs also persist in notification records, so tokens are not stored exclusively as hashes across the database.
- Wrong-patient checking reads the document itself and rejects the supplied Max report before filing.
- Single-use behavior and five-attempt lockout passed isolated checks.
- Lab conversion and rehab attachment generation work for the supplied fixtures under the intended type selections.
- Author and submitter remain distinct in the rehab resources.
- All six audit categories exist, and `answer_filed` is recorded after a successful storage response.
- The README explains architecture, design decisions, setup, and known prototype limits.

**Recommended order before submission:**

1. Close the public/internal API boundary and make the synthetic identity flow credible.
2. Fix Matrix routing and delivery acknowledgment; demonstrate wrong-patient notifications in the actual room.
3. Support a new named recipient and use structured document types.
4. Reject malformed lab rows without silent loss and support additional validated codes in the same layout.
5. Fix retry identity/state handling and inaccurate delivery/storage status.
6. Run both supplied workflows end to end, M1–M3, official FHIR validation, and a first-time-user timing trial. Publish the four metric results with evidence.
7. Improve clinical context, reconcile README claims with implementation, pin the demonstrated stack, and record the two-minute video.

Do not spend the remaining time adding AI, OCR, real SMS, or Matrix end-to-end encryption: these are not required. Prioritize a reliable demonstration with a new outside person, a new report, and a wrong-patient report, with evidence that the correct outcome reached Dr. Hofer.
