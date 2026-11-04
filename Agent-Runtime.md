# Common Studio agent runtime

Version 0.10.1 fixes the design and transition boundary. Direct transports and
the common loop are delivered by the following 0.10 releases. Existing sessions
continue using their recorded runtime until an explicit supported transition.

## Ownership

The unprivileged Python run worker owns conversation state, input admission,
the model/tool loop, context, Goal, queue, cancellation and original receipts.
The existing Node transport code owns HTTP and streaming. A protocol connector
serializes requests and returns model events; it never executes tools or starts
another agent. Keep the existing Python/Node boundary instead of introducing a
framework, generic plugin host, new daemon or language.

The web server retains its protected API and durable SSE projection. The browser
renders those events and sends deliberate user actions. Neither runs inference.
Project and skill sessions use the same core, differentiated by their existing
typed owner and tool scope.

| Current responsibility | Common implementation | Boundary that remains |
| --- | --- | --- |
| Codex/Claude conversation files | Existing Sessions.sqlite extended with Studio-owned messages and checkpoints | Private original native history retained for import and provenance |
| Codex turn RPC and Claude SDK query | One Python model/tool loop | Responses, Chat Completions and Messages wire serialization |
| API Responses relay and Chat translation | Direct request from the common context | Required endpoint dialect and authentication |
| Worker.execute/bound_tool | Existing Studio tool catalog, dispatcher, permissions and receipts | Tool implementation and actual resource capability |
| Native Goal RPC and separate Claude Goal loop | Common Studio Goal state and continuation | Reported model usage and real account limits |
| MessageWorker/native steer | Existing inbox/queue at a common safe request boundary | An already-sent HTTP request cannot be rewritten |
| Native context compaction | Common prompt builder and confirmed local checkpoint | Supported content and actual context window |
| Native usage observers | Direct reported usage and existing statistics receipts | Provider-specific reported counters and quota endpoints |
| Native web/image tools | Existing Studio tool/asset lifecycle with an available configured service | Actual service access and feature capability |
| Stop and recovery | Existing process ownership, cgroup, receipt and Unknown rules | Actual original remote/process termination evidence |

## Small common contract

Since 0.10.2, `conversation.py` supplies this private durable context store in
the existing Sessions.sqlite. Two additive tables hold explicit initialization
and immutable message/checkpoint records. Reads create no tables or records.
The store verifies session/run ownership and deduplicates a record together
with its existing durable event in one SQLite transaction. A conflicting
identity fails; private provider payloads are excluded from the public cursor
event. Original messages survive later checkpoints. This storage primitive
does not migrate native sessions or select a new runtime by itself.

A session keeps its existing Studio UUID and owner. Each accepted input freezes
its request ID, connection/model/protocol and credential revision, instructions,
permissions, skills and ready attachments. External thread/turn/response IDs are
provenance, not the local conversation identity.

Messages contain ordered text, tool calls/results and supported asset references.
Required signed, encrypted or provider-specific reasoning is retained unchanged
with its route and original response. It is not replaced by a text projection or
forwarded to another provider as if it were portable.

The transport consumes a frozen connection, complete required context, selected
parameters and allowed tool definitions. It produces text deltas, complete
content, complete tool calls, reported usage, actual origin and a terminal
outcome. It accepts cancellation. The core alone dispatches tools and decides
whether to request another model response. Tool arguments are validated in full
before effects; a missing terminal frame never authorizes partial calls.

Completed, failed, interrupted and unknown retain their existing meanings.
Confirmed tool effects survive a later model failure. Repeated original calls
read their receipts; changed arguments conflict. Unknown work is never replayed
because a browser reconnects or a controller disappears.

Use the existing SQLite stores, durable events, SSE cursors and tool ledger.
Do not create a second transcript store or event-sourcing service. Necessary
additions are local and additive. Reads and upgrades never migrate sessions or
start saved goals automatically.

## Access is separate from model transport

Since 0.10.5, `model_messages.py` connects Messages through that same private
HTTP/SSE transport. It retains ordered text, signed thinking and complete tool
blocks, with cumulative reported usage. Required signatures and tool pairs are
preserved for same-route continuation. No Claude SDK/CLI is used on this path.
Only an explicitly configured API connection may use it; existing Claude
subscription credentials are not converted. Thinking controls come from actual
selected facts/options, without model-name gates. Messages requires a per-call
output budget: the request defaults to 8192 tokens unless an explicit smaller
or larger `maxOutputTokens` budget is supplied. This is a requested bound, not
a claim about model capacity or an entire Goal's budget. Public connection/UI
activation is delivered with the common worker and subsequent shared UI work.

Since 0.10.4, the same transport/SSE path also handles direct Chat Completions
through `model_chat.py`. OpenRouter routing/attribution and Z.AI's existing
OpenCode wire identity remain small connector options. Custom, Ollama and
LM Studio use the same serializer and parser. Complete original assistant
messages retain reasoning strings/details and tool argument strings; same-route
continuation restores those originals. DONE and a valid complete call set are
required before any tool is returned. No Responses relay or provider agent is
started, and no model catalog or local server is probed by opening a connection.

Since 0.10.3, `model_transport.py` and `model_responses.py` provide a direct
Responses connector. `model_http.mjs` sends one private, pinned HTTP request
and returns bytes, not an agent protocol. Python owns the common SSE decoder
and context serialization, preserving exact large integer tool arguments.
The original complete provider output is retained for same-route continuation.
No tool is returned before a confirmed terminal response and complete argument
validation. Credentials travel only in the private bootstrap pipe. DNS/TLS and
endpoint checks are shared with the old native path. The connector itself does
not migrate sessions or dispatch tools; the common worker follows in 0.10.6.

| Connection | Direct common route | Remaining access constraint |
| --- | --- | --- |
| OpenAI API / compatible Responses | Responses | Explicit configured credentials and actual endpoint capabilities |
| ChatGPT/OpenAI Work plan | Responses when authorized for the direct route | Official Studio registration, granted inference scope and refresh; existing native credentials do not prove a new authorization |
| OpenRouter | Chat Completions | Existing routing, account/billing and original reasoning contract |
| Z.AI Coding Plan | Chat Completions | Existing subscription endpoint, approved OpenCode wire identity, original thinking and real quota windows |
| Custom / Ollama / LM Studio | Configured Responses or Chat Completions | Actual server capabilities; no discovery inference or model installation on open |
| Claude API / compatible Messages | Messages | Explicit API access; a Claude subscription alone does not establish API access |
| Claude subscription | A pure model route only if actually supported | Preserve the necessary native subscription path when no supported pure model transport exists; do not label it fully unified |

Account connection, catalog visibility and a completed inference are distinct
facts. Missing real access remains unavailable or unknown. The implementation
must not silently switch accounts, models, endpoints, billing or subscription
credentials to make a failed route succeed. Native exceptions are narrow and
explicit; they do not justify adding a new parallel agent engine.

The direct ChatGPT flow has its own registration and granted scopes. Browser
loopback and server loopback must be distinguished for a self-hosted web app.
Use the documented host flow; keep tokens outside browser storage, tool
namespaces, argv and logs. Do not copy native client IDs into a new client.

## Simplicity and qualification

All providers share the same core. Prefer one implementation per wire protocol;
keep only required authentication, quota and wire differences at the connector.
Reuse existing helpers and delete obsolete duplicate paths after their real
replacement and live references have been checked.

Only checks needed for an implemented feature belong in permanent product code.
This includes argument, permission, identity and protocol checks required for
correct effects. It excludes generic self-tests, model/version allowlists,
recurring probe inference, a new evaluation platform or a mandatory permanent
test matrix. Use focused existing validation for changed behavior; keep one-off
qualification scripts outside the repository.

No new model/version approval gate is part of this design. Unknown optional
metadata is not permission and does not automatically disqualify a model.
Reject only the operation whose required semantics cannot be preserved.

## Delivery boundaries

0.10.2 owns conversation storage; 0.10.3–5 implement the three direct protocols;
0.10.6 connects the common worker. 0.10.7–13 bring tools, context, Goal, input,
recovery, usage and optional media into that loop. 0.10.14 handles actual account
access; 0.10.15–17 provide explicit migration, switching and shared UI. 0.10.18
removes only truly obsolete native dependencies and qualifies the installed path.

Active runs keep their immutable release and accepted inputs. Existing native
histories and accounts are preserved. No user project, VM or SDK pin is a test
fixture. Preserve the ready production REA skill and its private runtime;
installed third-party sources/dependencies/programs remain excluded from Studio
Git and release archives.

Reference implementation: public Codex CLI/SDK/app-server source at
83086188ae0614bd882818ff1aa23f3194962012, especially core session/turn,
context management and tool dispatch; OpenCode at
501b15af26915ba52682e20e220e7e137e89e92f for existing connector behavior. Keep
upstream licenses if copying a necessary implementation; do not vendor either
complete codebase or claim the public checkout is the full desktop UI source.

Current access references:
[ChatGPT registration](https://developers.openai.com/siwc/token-sharing-open-source/sign-in),
[direct plan limits](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations),
[Claude API authentication](https://platform.claude.com/docs/en/manage-claude/authentication),
[Claude Code credential boundary](https://code.claude.com/docs/en/legal-and-compliance).

## Gemeinsame Schleife (0.10.6)

Neue explizite API-Sessions verwenden StudioWorker für alle drei Protokolle.
Der vorhandene systemd-Worker besitzt weiterhin UID, Release, Prozessgeburt,
Owner-/Workspace-Lock, Credentiallease, Sandbox und Werkzeugquittungen. Es gibt
keinen weiteren Agentenprozess oder Protokoll-Toolrunner. Bestehende Sessions
werden beim Lesen oder Upgrade nicht migriert. Die ausdrückliche Überführung
folgt in 0.10.15; Abozugänge folgen in 0.10.14.

Der Kern speichert jede bestätigte Modellantwort vor der Werkzeugrunde, prüft
den gesamten Callsatz einschließlich Schema und eingefrorener Rechte und führt
zulässige Aufrufe in Reihenfolge über Worker.bound_tool aus. Die sequenzielle
Ausführung schützt auch abhängige write/read-Paare; Anschlüsse disponieren keine
Hostparallelität. Originale Call-IDs bleiben im Modellverlauf; Quittungskennungen
sind zusätzlich an Run und Modellrunde gebunden. Ein verlorener Modellabschluss
verwirft weder gespeicherte Wirkungen noch gibt er einen Werkzeugreplay frei.
Öffentliche Textvorschauen sind begrenzt, vollständige Originale bleiben privat.

Normale Text-/Werkzeugrunden und Stop sind in diesem Schritt angebunden. Kontext-
verdichtung, GOAL, Queue/Steer, ausführliche Recovery, Quoten/Usage und Anhänge
werden in den jeweils folgenden Paketen ergänzt. Messages-API und deren
optionale Thinkingparameter benötigen ausdrückliche eigene Modellfakten; ein
vorhandenes Claude-Abo stellt keinen APIzugang her. Der bestehende eigenständige
Patchparser bleibt zunächst eine Dateihilfe und führt keine Agentenschleife aus.

## Gemeinsame Werkzeuge und Managed Skills (0.10.7)

Der Kern verwendet weiterhin ausschließlich shared/agent-tools.json und
Worker.bound_tool samt bestehender Datei-/Terminal-/Entwicklungs-/Roadmap-/
Notiz-/VM-/Skillbroker. Eine originale Call-ID innerhalb desselben Runs erhält
eine stabile interne Quittungskennung. Erneute Beobachtungen geben den gespeicherten
Inhalt zurück, geänderte Argumente scheitern vor der gesamten Werkzeugrunde.
Verlaufsnachrichten besitzen zusätzlich ihre Beobachtungsrunde; eine zweite
Beobachtung ist keine zweite Wirkung. Ein vollständig abgewiesener Aufrufsatz
bekommt eindeutige notAdmitted-Ergebnisse im Verlauf, ohne Hostquittungen oder
Werkzeugwirkungen vorzutäuschen.

System-/Projekt-/Skillanweisungen, UUID-Auswahl, unveränderliche Revisionen,
Ressourcen und Skripte stammen aus den vorhandenen eingefrorenen Quellen.
SkillTools und der bestehende private Session-MCP-Service behandeln vollständige
Kataloge, Schemas, Ergebnisreferenzen, Originalprozesse, Stop, Thaw, Controllerverlust
und Löschung für jeden Anschluss gleich. Es gibt keinen zweiten MCP-Client und
keine neue modellspezifische Teilmenge. Lesen/Öffnen installiert keine Skills.

Gewöhnliche Datei- und Terminaloperationen im Studio-Kern prüfen, laden und
mounten keine Codex-Modellruntime. Nur die ausdrücklich gewählte apply_patch-
Operation verwendet derzeit den vorhandenen eigenständigen offiziellen
Patchparser. Dieser ist eine Werkzeughilfe und führt keine Agentenschleife aus.

## Kontext und Verdichtung (0.10.8)

Alle direkten Anschlüsse verwenden dieselbe compose-Funktion einschließlich der
bestehenden Entwicklungs-/GUI-/Projektumgebungsanweisungen. Globale und lokale
Quellen bleiben unverändert gespeichert; aktuelle Werkzeugverträge ergänzen ihre
bestehende Priorität. Aufbewahrte Inhalte und Zusammenfassungen sind Taskdaten.

StudioContext rekonstruiert Originalnachrichten und den letzten bestätigten
Checkpoint. Die Planungsschätzung verwendet die Bytezahl des tatsächlich vom
Anschluss serialisierten Requests geteilt durch vier; sie ist kein Tokenizer
und wird ausdrücklich getrennt von der original gemeldeten Inputzahl angezeigt.
Das konfigurierte Kontextfenster kommt aus den akzeptierten Modellfakten.
Unbekannte Counts/Fenster bleiben unbekannt; für Messages sind unvollständige
Cachecounts keine vollständige Kontextmessung. Offene Werkzeugpaare erhalten
noch keine Schätzung eines versendbaren Folgeinputs. Lesen/Reload führt keine
Modellprüfung oder Verdichtung aus.

Bei Bedarf (80 Prozent des konfigurierten Fensters, als Messung oder ausdrücklich
gekennzeichnete Planungsschätzung, beziehungsweise Annäherung an die vorhandene
Transport-Bytegrenze) fordert der aktive Worker eine Zusammenfassung über dieselbe
Route an. Sie hat keine Tools und wird erst nach bestätigtem Protokollabschluss
als unveränderlicher Checkpoint samt Originalantwort, Quellhash und Wasserstand
gespeichert. Fehler erzeugen keinen Ersatzcheckpoint und keinen Routenwechsel.
Nur vollständig geschlossene Toolpaare werden verdichtet. Der aktuelle originale
Benutzerauftrag bleibt im aktiven Kontext exakt erhalten. Alle ursprünglichen
Nachrichten, opaken Providerdaten, Ergebnisse und Wirkungsquittungen bleiben
privat gespeichert; große Resultate behalten ihre vollständigen Originalreferenzen.

Ein gespeicherter Checkpoint ist kein neuer Auftrag und startet beim Öffnen keine
Fortsetzung. Tacho und Tooltip unterscheiden gemeldeten Input, konfiguriertes
Fenster und Schätzung; nach Abbruch/Fehler bleiben frühere Messungen als solche
kenntlich. Die Messages-Rollendarstellung folgt dem stateless Messages-Vertrag:
[offizielle APIreferenz](https://platform.claude.com/docs/en/api/messages/create).

## Gemeinsames GOAL (0.10.9)

StudioGoal verwendet den vorhandenen Goal-Commandstore, die originale Play-
Execution, den authentifizierten Worker-Controlsocket und GoalClock. Save und
Readback sind Metadatenaktionen. Nur ein ausdrücklich angenommenes Play aktiviert
Arbeit. Direkte Projekt- und Skill-Runs haben denselben Ablauf ohne native
thread/goal-RPCs. Vorhandene native Goal-Daten werden damit nicht umgedeutet.

Ein Live-Play bleibt bis zur sicheren Antwort-/Werkzeuggrenze im Originaljournal.
Es übernimmt denselben ursprünglichen Run und dessen eingefrorene Auswahl, ohne
Runconfig oder früheren Auftrag umzuschreiben. Vorher disponierte gewöhnliche
Modellaufrufe zählen nicht als neue GOAL-Tokenausgabe. Eine gültige normale Antwort
beendet ein aktives GOAL nicht. Die zentrale Schleife setzt es unter Bezug auf
das ursprüngliche menschliche Play fort; diese internen Kontrollnachrichten
sind als solche gekennzeichnet. studio_update_goal meldet complete/blocked mit
konkreter Begründung und gegebenenfalls eindeutigen bestätigten studioReceiptId-
Referenzen. Modelle ändern damit weder Ziel noch Budget oder Aktivierung.

Optionale tokenBudget/timeBudgetMs werden nur mit revisioniertem Save geändert.
Gemeldete Tokens und ihre dokumentierten Teilcounts bleiben von Providercredits
getrennt. Fehlende, widersprüchliche oder unbestätigte Usage bleibt unbekannt;
ein gesetztes Tokenbudget hält dann weitere Disposition an. Eine bereits laufende
Modellanfrage kann ihr tatsächliches Restbudget überschreiten; die gemeldeten
Kosten werden nicht auf das Budget gekürzt. Danach gibt der Kern keine weiteren
Werkzeugwirkungen oder Modellrunden frei. Aktivzeit stammt aus der vorhandenen
monotonen pro-Play-Uhr; ein Zeitlimit kann laufenden Transport/Arbeit abbrechen.
Originale Teilwirkungen bleiben erhalten. Nach Controllerverlust bleiben Goal-
Zustand, fehlende Zeitabdeckung und Usage unbestätigt; Öffnen führt keinen Resume aus.

## Gemeinsame Eingänge (0.10.10)

Messages/Inbox, Request-UUID, ursprüngliche FIFO, eingefrorene Auswahl und
Hostbelegung bleiben die einzigen Eingangswege. Der vorhandene authentifizierte
MessageWorker registriert direkte Studio-Eingaben dauerhaft. Erst an der nächsten
sicheren Grenze werden der originale menschliche Text und seine Annahme in einer
SQLite-Transaktion gespeichert. Eine schon laufende HTTPanfrage bleibt exakt
unverändert. Der Status unterscheidet die Registrierung von der tatsächlichen
Übernahme in den gemeinsamen Verlauf; Delivery heißt next-model-boundary.

After response bindet den ursprünglichen Run und die Studio-Conversation. Nach
der nächsten vollständigen Antwort ohne offene Toolaufrufe endet dieser Run; ein
aktives GOAL wird dabei pausiert. Der bestehende Host disponiert die FIFO erst
nach bestätigter Ressourcenfreigabe. Normale Queue-Eingaben warten bis zum Ende
des ursprünglichen Laufs. Ready-Anhänge bleiben an ihrem Queue-Original; direkte
Eingaben unterstützen weiterhin ausschließlich Text. Native Claude-Ziele und
Codex-Steerquittungen behalten ihre bisherigen Verträge.

Stop, Unknown, Quota und GOAL-Limits halten Folgearbeit. Ein ursprüngliches
Resume im vorhandenen Kontrolljournal bestätigt nur den vorherigen Endzustand,
keinen späteren Fehler. Neustart/Reload startet weder Queue noch GOAL. Verlorene
IPC-Antworten lesen den vorhandenen Request; eine bereits registrierte oder
angenommene Studio-Eingabe wird weder verworfen noch erneut gesendet.
Angenommene Studio-Aufträge verwenden ihre ursprüngliche unveränderliche
Workerrelease mit Version und Quellhash. Fehlt sie, hält die Queue ihre Eingabe
mit Begründung; ein neuer globaler Standard ersetzt sie nicht automatisch.

## Originale Prozessenden (0.10.11)

Der direkte Modelltransport meldet seinen tatsächlichen Kindprozess an den
vorhandenen Worker, bevor er Credentials oder Requestdaten an Node übergibt.
Im privaten SQLite-Journal studio_model_calls bleiben lokale Request-ID,
ursprüngliche Auswahl, PID/Geburt, Boot-ID, cgroup, Streamabschluss und
beobachtetes Prozessende getrennt. Eine verlorene Antwort bleibt unbestätigt,
auch wenn der ursprüngliche Prozess später nachweislich endet. Bestätigte
Wirkungsquittungen werden dabei weder zurückgenommen noch erneut ausgeführt.

Der bestehende Host rekonstruiert nach Verlust nur diese Originale. Er bindet
das Ende an Owner/Session/Run/Release, systemd-Invocation, ursprünglichen PID
und leere beziehungsweise bereits entfernte cgroup. Ein belegter Neustart des
Hosts oder eingesammelte Unitmetadaten ersetzen keine lebende Originalidentität.
Fehlen notwendige Endbelege, bleibt der ursprüngliche API-Lease geschützt.
Nach bestätigtem Ende kann derselbe Lease freigegeben werden; seine frühere
Unknown-Historie und fehlende Modellantwort bleiben erhalten. Dies verwendet
die vorhandenen Recovery-/Refreshpfade und keinen zusätzlichen Dienst.

Stop schließt die gemeinsame Zulassung und den ursprünglichen Transport;
Werkzeuge, Terminal- und MCP-Prozesse folgen ihren vorhandenen Besitzbelegen.
Die gezielte Thaw-vor-Stop-Mechanik unabhängiger MCP-Units bleibt bestehen.
Credentialfreigabe erfordert das tatsächliche Ende des eigenen Modelltransports.
Unbestätigte MCP-/Entwicklungswirkungen bleiben davon getrennte Lösch- und
Ressourcenblocker. Ein späterer bestätigter Prozessabschluss erfindet keine
verlorene Toolquittung. Laufende ältere Releases behalten ihren Originalpfad.

## Gemeinsame Usage, Limits und Wiederholung (0.10.12)

Direkte Modellaufrufe erzeugen dieselben vorhandenen numerischen Statistik-
quittungen wie andere Studio-Quellen. Die lokale Original-Request-ID bestimmt
die Ausgabeidentität, auch wenn ein Dienst Antwortkennungen wiederverwendet.
Verarbeitung, Restore und spätere Zahlenreconciliation zählen sie nicht erneut.
Unvollständige Antworten erzeugen eine Abdeckungslücke und bleiben samt
privatem Streampräfix erhalten; ihr fehlender Gesamtverbrauch ist keine Null.

Input, Output, Gesamt, Cache-Read/-Write und Reasoning werden nur aus gültigen
gemeldeten Ganzzahlen übernommen. Messages-Input besteht aus vollständigem
uncached Input plus Cache-Read und Cache-Write; fehlt ein erforderlicher Teil,
bleibt der Gesamtinput unbekannt. Kumulative Outputstände werden ersetzt,
nicht addiert. Detailtokens sind Teilmengen und werden nicht nochmals auf die
Gesamtausgabe gerechnet. Cache-Schreibwerte und Thinkingdetails bleiben bei
fehlender Meldung unbekannt. Die Feldverträge sind dokumentiert in den
[Responses-Usagefeldern](https://developers.openai.com/api/reference/resources/responses/methods/create),
[Chat-Usagefeldern](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/retrieve),
[Messages-Usagefeldern](https://platform.claude.com/docs/en/api/messages/create)
und der [Messages-Cacheaufteilung](https://platform.claude.com/docs/en/build-with-claude/prompt-caching).

Der vorhandene Fehlerpfad unterscheidet Authentifizierung, Zugriff, Billing,
Rate/Quota, Kontext, Dienstfehler und unvollständigen Transport. Originale
HTTP-Fehlerkörper und SSE-Payloads bleiben privat, öffentliche Meldungen sind
begrenzt und enthalten keine reflektierten Credentials. Das private Streamjournal
hat ein ausdrücklich markiertes Präfixlimit von96 MiB pro Session; vollständige
Conversation-Originale unterliegen weiterhin ihrem eigenen vorhandenen Vertrag.
Ein vollständiges Ergebnis wird nicht aus einem abgeschnittenen Präfix erfunden.

ProviderRetry verwendet sein vorhandenes Journal, fünf Wiederholungsversuche
und60 Sekunden Wartezeit. Für neue direkte Aufträge ist ausschließlich ein
bewiesener Verbindungsfehler vor TCP-/TLS-Verbindungsaufbau zulässig: der
Transport hat den Modellrequest nicht disponiert. Maßgeblich sind interne
Node-Prozessbelege und ausgewählte Systemfehler, keine Fehlermeldung eines
Anbieters. [Node beschreibt ECONNREFUSED als fehlgeschlagenen Verbindungsaufbau](https://nodejs.org/api/errors.html#common-system-errors).
Der neue Versuch behält den Originalinhalt mit identischem Requesthash und
demselben eingefrorenen Zugang. HTTP5xx, verlorene Bodies, Quota, Zugriff und
Billing autorisieren keine Wiederholung. Stop beendet den vorhandenen Timer.
Ältere eingefrorene Eingänge erhalten keine nachträgliche Retryfähigkeit.

Native Z.AI-Holds bleiben an ihren belegten ursprünglichen Keyscope gebunden.
Der gemeinsame Kern liest sie vor einer neuen Modellrunde und kann echte
native Fehlercodes in demselben bestehenden Limitstore speichern. Frische
Kontofenster und Resets kommen aus dem vorhandenen Accountleser; Unknown allein
ist keine Modellsperre. Ein Reset oder Readback startet keine Arbeit. Es gibt
keinen zusätzlichen Monitor, keine Tokenumrechnung von Credits und keinen
kostenpflichtigen Ausweichpfad. OpenAI-/Claude-Kontoleser behalten ihre echten
Accountgrenzen; fehlende direkte Aboentitlements werden separat qualifiziert.

Eine Rotation ersetzt keine bereits angenommene Auswahl. Laufende gemeinsame
Runs und bereits reservierte Queue-Eingänge behalten ihre originalen Fakten,
Credentialrevisionen und vollständigen Confighashes. Nur neue Eingänge verwenden
die aktuelle Konfiguration. Disconnect schließt weiterhin die Zulassung. Alte
Secrets bleiben bis zum bestätigten Ende aller eigenen Referenzen geschützt.

### 0.10.13: shared web and media

Studio web access uses `studio_web_search` and the existing frozen feature switch and tool receipt. Search requires an explicitly configured SearXNG JSON endpoint; public page fetch works independently. Reads retain private originals and hashes, bounded untrusted text and source links. Targets are DNS-pinned, redirects rechecked, and no provider credential, ambient cookie or proxy is forwarded. Opening settings performs no service probe. Saving service configuration affects future accepted inputs only. Stop closes and observes the original owned operation.

Ready attachments become durable session references; the transport resolves their verified bytes only for the outgoing request. PNG/JPEG/WebP require confirmed model image support. Document text is explicitly identified as an untrusted extraction, including the existing truncation/layout limitations. Image context token estimates remain unknown rather than treating image bytes as text tokens.

Selected MCP image services publish through the existing GeneratedImages registry with their original tool receipt, prompt/argument/result records and Stop lifecycle. Confirmed tool pictures are rendered and downloaded in their original raster format; nonvisual conversation models receive references only. Responses/Chat image observations follow the complete tool-result batch; Messages nests images in the original result. Native hosted ChatGPT image generation remains a limited legacy capability because no equivalent independent AI image service is configured. No AI image generation or complete native replacement is claimed by fixture qualification.

### 0.10.14: account authorization without another agent

ChatGPT plan connections use Studio's own public-client registration and the same Responses worker. They never reuse a native Codex account's tokens as a Studio grant. The private server account process performs OAuth only: fresh state/nonce/S256, a started `127.0.0.1` callback, the actual R4OS Studio name, the issued registration ID and a stable host UUID. It validates the official RS256 signature, issuer, audience, expiry, nonce and selected account identity. Direct plan permission is a separate granted-scope requirement. A registration or model list is not evidence of completed inference.

A local browser can return directly to the host loopback. A browser on another computer completes the same OpenAI sign-in and pastes the complete final loopback redirect address into Studio. The browser-owned, CSRF-protected route validates the original URI/state and records its digest before forwarding it once through the original account process's private pipe. This process consumes the same PKCE verifier/nonce and validates the issued registration. No helper download, terminal or credential transfer is required. A browser connection error at the final loopback address is expected on a remote computer; the copied address is sufficient. The address/code stays out of browser storage and public status, and a repeated or lost delivery reads the same original attempt. Tokens never enter browser storage, public account responses, tool environments or process arguments. No login, metadata request or inference starts on upgrade or opening settings.

The existing API store and run/queue leases refer to immutable grant identities. Token renewal retains the same issuer/account/client/host and logical credential revision. An uncertain rotating-refresh result is retained and never retried automatically. Original sign-in/publication can be read and completed by its original request ID; cancellation cannot silently activate an unfinished connection. Logout closes the existing admission and worker leases, then revokes only that connection's retained grants; an uncertain remote revocation remains unknown.

SIWC uses the public `/v1/responses` route with full context, `store:false`, `stream:true` and namespaced function tools. It does not request hosted image generation, file search, tool search or other unsupported hosted features. Original tool names and receipts still belong to the common loop. Account model metadata comes from the selected token's `/v1/models` response; model IDs are not an allowlist. Original structured plan errors and parameters remain available. Quota exhaustion differs from unavailable usage information; missing numeric plan limits stay unknown. ChatGPT itself controls the user's granted plan/credit permissions; Studio never switches to a separate billing credential.

Claude subscription access has no documented pure Messages transport for this integration. Its existing native account/runtime remains an explicit bounded legacy route. An independently configured Messages API connection already uses the common worker; it is never chosen as a billing fallback for an existing subscription.

Sources: [SIWC registration](https://developers.openai.com/siwc/token-sharing-open-source/sign-in), [models and inference](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference), [preview limits](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations), [self-hosted transfer](https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms), [account lifecycle](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions), [structured errors](https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery), [Claude account boundary](https://code.claude.com/docs/en/legal-and-compliance).

Pending sign-ins belong to their original browser administration session; another browser cannot read their authorization URL, cancel them or finish publication. Reauthorization also freezes the selected connection revision: a later logout or configuration change is preserved rather than overwritten by a delayed callback. Explicit logout closes pending authorization for that connection and records uncertain remote revocation separately from local disconnection. Returning browser sign-in reuses the saved issued client ID and this Studio host's stable identity. The server-only account script accepts private structured input; there is no downloadable or local CLI helper path.

### 0.10.16: explicit session conversion

Session settings offers a separate Runtime action for an idle native conversation. Reviewing the chosen direct connection reads its actual model facts and original source receipts; it starts no model or login. Conversion binds the session revision, original history hash and selected account/model metadata to one request UUID. The existing workspace lock and SQLite transaction commit the imported context, engine choice, paused Goal and receipt together. A repeated original ID reads its original result. Opening settings, reloads and upgrades never migrate a session.

The same local session UUID, original visible items, immutable run selections, native files, accepted attachments and effect receipts remain. Codex rollout bindings and Claude's confirmed transcript inventory are read without rewriting them. Confirmed closed tool pairs become explicitly labelled historical observations on every protocol. Opaque provider reasoning remains in the byte-preserved native archive. Unknown effects, incomplete history, unsupported native content, active work and accepted queue entries block conversion before a model request. Images retain their private byte/hash references and require the chosen model's image capability. Missing source data is a concrete hold, never an invented transcript.

Before any newly accepted run, queue input or Goal command, Return to original runtime restores only the migration's owned settings and Goal representation. Original files and receipts are never rewound. A new accepted action closes this return window. Legacy sessions and originally frozen workers remain supported by their original releases until explicitly converted or regularly deleted.

Pending browser sign-in now continues observing the original authorization through account publication. The initial controller identity is recorded before spawning its account process; transient read errors and the authorized-but-not-published interval no longer leave a completed login displaying Waiting. Account model catalogs may also list native delegation modes; their presence does not hide the model's documented Responses reasoning levels or alter its actual default. Unknown modes never become a fabricated None option.

### 0.10.17: choose the next conversation model

Common Studio sessions can select another direct connection or model with the existing Session settings Save action. Saving validates the actual current model facts, verified media and closed context without inference. The session UUID, thread identity, rights, paused Goal/budgets, original run selections, usage and effect receipts remain. An active run, pending Goal control or unresolved/queued input keeps its original choice; finish, cancel or reconcile that input before changing the selection. Saving a connection or reloading never starts a run or chooses a billing fallback.

One shared outgoing projection handles all protocols. On a different account, model, URL, protocol or connection/credential revision, it verifies that the stored visible text and calls match their original protocol payload. It then identifies those visible messages and confirmed closed tool observations as historical data. Encrypted/signed/private reasoning remains unchanged in the original SQLite records and is not repurposed or sent to the new route. Unsupported originals, unresolved pairs, unknown effects or missing/incompatible images reject the choice before any model request. An unchanged route retains its original provider payloads. Full route provenance for older common records is read from their immutable accepted run without rewriting those records.

The common transport also consumes verified event streams when the server omits Content-Type; an explicitly incompatible type or unsupported content encoding still fails. Responses can use contiguous `response.output_item.done` originals when the terminal `response.completed` aggregate is empty, as when it is omitted. Partial/added events never authorize a tool or fabricate a completed answer. This behavior was qualified against an actual token-authorized stream and local replays; only a separately completed installed Studio run qualifies the live plan acceptance.
