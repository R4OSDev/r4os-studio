# R4OS Studio · App

Lokales Grundgerüst einer browserbasierten Entwicklungsumgebung für R4OS.

## Repository

Dieses Verzeichnis ist das lokale Git-Repository. Remote: `https://gitea.r4public.r4network/R4mbo/R4OS_Studio.git`, Branch `main`. Jede fertiggestellte Unterversion wird committed und gepusht. Aus dem übergeordneten Workspace unter Linux: `./Tools/Push.sh "Kurze Commit-Beschreibung"`; unter Windows: `Tools\Push.bat "Kurze Commit-Beschreibung"`.

`Data/` wird beim Start beziehungsweise bei der Dienstinstallation angelegt und gehört einschließlich aller Unterordner nicht ins Repository. Leere ignorierte Ordner werden von Git nicht übertragen.

`AGENTS.md` und `Tools/` liegen im übergeordneten Workspace und werden nicht in dieses Repository aufgenommen. Lokale Git-Einstellungen erlauben das selbstsignierte Gitea-Zertifikat und lösen `gitea.r4public.r4network` bei Bedarf über `10.0.0.2` auf. Zugangsdaten stehen im außerhalb dieses Repositories abgelegten Push-Skript; die Remote-URL enthält keine Zugangsdaten.

Im übergeordneten Workspace liegen außerdem separate Quellcode-Checkouts unter `Research/Codex/`, `Research/OpenClaw/` und `Research/OpenCode/`. Herkunft und genaue Revisionen stehen in `Research/sources.json`. Der Codex-Checkout enthält die öffentlichen CLI-/SDK-/App-Server-Komponenten; ein öffentliches Repository für die vollständige Desktop-Oberfläche wurde nicht bestätigt. Diese Quellen dienen der Recherche und sind keine installierten App-Abhängigkeiten oder Bestandteil dieses Gitea-Repositories.

## Starten

Voraussetzungen: Node.js 20 ab 20.19, 22 ab 22.13 oder ab Version 24, außerdem Corepack (alternativ pnpm 10.18.3 direkt installieren). Für neue Installationen Node.js 24 LTS verwenden.

```bash
cd App
corepack pnpm install --frozen-lockfile
corepack pnpm dev
```

Frontend: <http://127.0.0.1:5173> · Backend: <http://127.0.0.1:3001/api/health>

`dev` startet beide Prozesse; Strg+C beendet sie gemeinsam. Einzeln starten: `corepack pnpm dev:frontend` bzw. `corepack pnpm dev:backend`. Die Ports 5173 und 3001 müssen frei sein. `PORT` kann den Backend-Port ändern; dann auch das Proxy-Ziel in `frontend/vite.config.ts` anpassen.

## Enthalten

- Purple/Dark-Design mit dunkelvioletten Flächen, lavendelfarbener Schrift und violetten Akzenten für Auswahl, Tabs und Tastaturfokus. Favicon und Browser-Theme-Farbe sind darauf abgestimmt.
- Vollständig englische Benutzeroberfläche, einschließlich zugänglicher Beschriftungen und Browser-Metadaten (`lang="en"`). Neue UI-Texte werden auf Englisch ergänzt.
- Obere Tab-Leiste mit **System** und **Projects**, ohne Workspace-Kennung rechts. Auch mit Pfeiltasten, Pos1 und Ende bedienbar.
- Links drei gleich breite Navigationsspalten: **Areas → Components → Views**. Die Spalten enthalten keine wiederholten Kontextüberschriften und keine Management-Fußnoten. Ihre Breite entspricht auf dem Desktop der bisherigen dritten Spalte; der übrige Platz steht dem Hauptbereich zur Verfügung.
- Im Tab **System** gibt es ausschließlich **Settings → LLM Provider**. **New Provider** steht in **Views** immer zuerst, darunter stehen die gespeicherten Provider.
- Rechts ein Hauptbereich mit Breadcrumb, Seitentitel und Platzhalter.
- Die untere Leiste enthält ausschließlich linksbündig **R4OS Studio | Version …**. Die Versionsnummer stammt aus `shared/version.json`.
- Die Auswahl bleibt pro Tab im Speicher erhalten; Neuladen setzt sie zurück.
- Auf schmalen Bildschirmen stehen die drei Navigationsspalten oberhalb des Hauptbereichs.
- Ein Fastify-Backend mit `GET /api/health`. Der Status beschreibt ausschließlich den Studio-Server, keine R4OS-Instanz.

Die Projektansichten einschließlich „Example Project“ sind Dummys. Die OpenAI-Provider-Verwaltung ist implementiert. Es werden noch keine R4OS-Projekte gespeichert oder R4OS-Tools gestartet. Die Oberfläche lädt keine externen Schriftarten oder anderen Medien.

## OpenAI mit ChatGPT-Abonnement

1. **System → Settings → LLM Provider → New Provider** öffnen.
2. **OpenAI** auswählen, einen Anzeigenamen vergeben und **Add OpenAI provider** anklicken.
3. Im gespeicherten Provider **Continue with ChatGPT** anklicken. R4OS Studio zeigt einen einmaligen Code.
4. **Open OpenAI sign-in** öffnet die offizielle OpenAI-Anmeldung in einem eigenen Tab. Dort anmelden und den Code bestätigen.
5. R4OS Studio erkennt den Abschluss automatisch und zeigt Konto, Plan und **Connected**. Die Verbindung bleibt nach einem Dienstneustart gespeichert.

Es wird kein API-Key benötigt. Die Zugangsmöglichkeiten hängen vom ChatGPT-Konto und dessen Codex-Berechtigungen ab. Der Provider kann lokal getrennt und erneut verbunden oder vollständig entfernt werden. **Disconnect** und **Remove** löschen die lokalen Zugangsdaten dieser Verbindung; eine globale Abmeldung oder bestätigte Remote-Widerrufung wird nicht behauptet. Bestehende Codex-CLI-Anmeldungen bleiben getrennt. Derzeit werden Kontoverbindungen verwaltet; ein Chat-/Inference-Endpunkt ist noch nicht implementiert.

Die Anmeldung verwendet ausschließlich die Account-RPCs des offiziellen Codex-App-Servers, keine nachgebauten OpenAI-OAuth-Endpunkte oder kopierten Client-IDs. Getestete Binary: **codex-cli 0.162.1**. Der Dienst-Installer kopiert die vorhandene eigenständige CLI-Binary nach `/opt/r4os-studio/bin/codex`; auf neuen Hosts vorher die offizielle eigenständige Codex CLI installieren. Für die Entwicklung lässt sich deren Pfad über `CODEX_BINARY` setzen. `STUDIO_DATA_DIR` bestimmt direkt das Provider-Datenverzeichnis; ohne Vorgabe wird `App/Data/LLMProvider/` verwendet. Diese Vorgabe gilt für Entwicklung und Produktion. Die Anwendung ist für den privaten LAN-/VPN-Betrieb eingerichtet. Für öffentliche oder kommerziell gehostete Angebote ist der reguläre, von OpenAI freigegebene **Sign in with ChatGPT**-Web-Client erforderlich; der aktuelle Device-Code-Adapter ist dafür nicht vorgesehen.

Jeder Provider hat einen eigenen geschützten Server-Speicher. Das lokale Verzeichnis `Data/LLMProvider/` erhält Modus `0700`; Metadaten liegen atomar geschrieben mit `0600` in `providers.json`. Die jeweiligen Codex-Anmeldedaten liegen in UUID-Unterordnern. `/Data/` und sämtliche Unterordner sind durch `.gitignore` ausgeschlossen. Beide Push-Skripte beachten diese Regeln und brechen zusätzlich ab, falls Data-Dateien bereits versioniert sind oder die Ausschlussregel fehlt. Auth-Tokens verbleiben im jeweiligen Codex-Speicher auf dem Server. Der Browser erhält ausschließlich öffentliche Konto-, Quoten- und Reset-Metadaten sowie während seines eigenen Login-Vorgangs den kurzlebigen Benutzer-Code. `HttpOnly`-/`SameSite=Strict`-Cookies binden Login-Vorgänge an die Browser-Sitzung; Änderungen benötigen zusätzlich einen CSRF-Token. Es gibt keine Mehrbenutzerkonten oder Rollen: Provider-Verwaltung gehört zum gemeinsamen, vertrauenswürdigen Studio-Workspace im LAN/VPN. Für weitere Hostnamen `STUDIO_ALLOWED_HOSTS` als kommagetrennte Liste setzen; standardmäßig werden lokale Interface-Adressen, localhost und der Rechnername akzeptiert. TLS ist für den Betrieb außerhalb dieser vertrauenswürdigen Netze erforderlich.

Die Analyse der drei Referenzprojekte und die genaue Herkunft stehen im Workspace unter `Docs/OpenAI-Subscription.md` und `Research/sources.json`.

## Usage limits und verfügbare Resets

Einen verbundenen OpenAI-Provider auswählen. **Usage limits** zeigt alle von OpenAI gemeldeten Quoten mit verbrauchtem und verbleibendem Anteil, Fensterdauer und nächstem Reset. Absolute Zeitpunkte enthalten die Browser-Zeitzone; zusätzlich steht die verbleibende Zeit dabei. Es werden nur tatsächlich gemeldete Fenster angezeigt, ohne eine feste Annahme über Tages- oder Wochenlimits. Fehlende Werte heißen **Not reported**. Ein vergangener Reset-Zeitpunkt setzt die Anzeige nicht automatisch auf frei: Erst eine neue Antwort von OpenAI bestimmt den aktuellen Stand.

Die Ansicht lädt beim Öffnen, danach ungefähr einmal pro Minute bei sichtbarer Seite und über **Refresh usage**. Der Server hält erfolgreiche Werte maximal 15 Sekunden im Arbeitsspeicher pro Provider; manuelles Aktualisieren umgeht diesen Cache. Bei einem Fehler bleiben zuvor geladene Werte als möglicherweise veraltet gekennzeichnet.

**Available resets** zeigt die gemeldete Gesamtzahl zusätzlicher Reset-Guthaben sowie verfügbare Titel, Status, Vergabe- und Ablaufzeiten. Die Anzahl bleibt maßgeblich, falls OpenAI nur einen Teil der Einzelheiten liefert. Nicht gemeldete Verfügbarkeit wird nicht als null verfügbare Resets dargestellt. Diese Guthaben sind unabhängig von den normalen zeitgesteuerten Quoten-Resets.

**Use a reset** öffnet zunächst eine Bestätigung. Erst **Confirm reset** sendet den Verbrauch an OpenAI. OpenAI wählt standardmäßig das nächste verfügbare Guthaben und entscheidet, welche Fenster zurückgesetzt werden können. Studio aktualisiert danach die Quoten anhand einer neuen Abfrage. Es gibt keine automatische Nutzung von Reset-Guthaben, keine Käufe und keine Modellaufrufe.

Jeder logische Einlöseversuch hat eine UUID als Idempotenzschlüssel. Der Browser speichert ihn vor dem Senden im Sitzungsspeicher, damit ein unklarer Ausgang auch nach Navigation oder Neuladen mit derselben ID erneut geprüft werden kann. **Retry previous reset** / **Retry same reset** verwenden diese ID weiter. Die Ablage enthält ausschließlich die Anfrage-ID und ihren Sendestatus, keine Auth-Tokens. Ein bestätigter Verbrauch mit anschließend fehlgeschlagener Quotenabfrage wird als bestätigtes Ergebnis angezeigt; die Quoten können separat nachgeladen werden. Der Sitzungsspeicher gilt für den jeweiligen Browser-Tab.

- `GET /api/providers/:id/usage`: lesende Abfrage; optional `?refresh=true`.
- `POST /api/providers/:id/usage/resets`: ausschließlich für ausdrücklich bestätigtes Einlösen mit Sitzung, CSRF-Token, `confirm: true` und `idempotencyKey`. Optional kann ein bekanntes `creditId` übergeben werden; die Oberfläche überlässt die Auswahl OpenAI.

Die Umsetzung verwendet die offiziellen Account-RPCs `account/rateLimits/read` und `account/rateLimitResetCredit/consume`. Herkunft und Protokollgrenzen sind unter `Docs/OpenAI-Subscription.md` dokumentiert. Verbrauchende Tests verwenden ausschließlich kontrollierte Fake-Clients. Die bestehende persönliche Verbindung wurde nur lesend geprüft; kein echtes Reset-Guthaben wurde eingelöst.

## Versionsnummer

Die maßgebliche App-Version steht ausschließlich in `shared/version.json` im Format `major.minor.patch`. Für eine neue Unterversion diese Datei anpassen. Das Frontend liest sie direkt für die untere Leiste; das Backend verwendet dieselbe Version für die Codex-Client-Metadaten.

`node scripts/sync-version.mjs` überträgt die Version in die Paketmetadaten von `package.json`. `corepack pnpm build` führt diesen Schritt automatisch vor dem Bauen aus. `package.json` deshalb nicht unabhängig versionieren. `shared/version.json` gehört auch beim Produktionsstart zur Anwendung und muss zusammen mit den Build-Dateien vorhanden sein.

## Aufbau und Entscheidungen

```text
App/
├── frontend/src/
│   ├── app/                         Layout, Navigation, gemeinsame Icons und Styles
│   ├── features/llm-providers/       Provider-Oberfläche, API-Client und React-Zustand
│   │   └── components/              NewProvider, ProviderDetails, ProviderPanel, Usage-Ansichten
│   └── main.tsx                     Browser-Einstieg
├── backend/src/
│   ├── app.ts                       HTTP-App zusammenstellen und konfigurieren
│   ├── server.ts                    Prozessstart und Beenden
│   └── modules/llm-providers/
│       ├── routes.ts                HTTP-Routen und Eingabevalidierung
│       ├── sessions.ts              Browser-Sitzungen, Origin-/Host-Prüfung und CSRF
│       ├── service.ts               Provider- und Login-Lebenszyklus
│       ├── store.ts                 Persistenz und private Provider-Verzeichnisse
│       ├── errors.ts                HTTP-Fehler des Moduls
│       └── openai/                  Codex-Prozess und Usage-/Reset-Adapter
├── backend/test/                    Isolierte Provider-Integrationstests
├── shared/
│   ├── llm-providers.d.ts            Öffentliche Datenverträge, keine Zugangstokens
│   └── version.json                 Maßgebliche App-Versionsnummer
├── Data/LLMProvider/                Lokale Laufzeitdaten; vollständig ignoriert
├── scripts/                         Gemeinsamer Entwicklungsstart
└── pnpm-lock.yaml                   Aufgelöste Abhängigkeitsversionen
```

React und TypeScript strukturieren die interaktive Studio-Oberfläche. Vite übernimmt Entwicklungsserver und Frontend-Build. Fastify stellt die lokale HTTP-API bereit; `@fastify/static` liefert beim Produktionsstart das gebaute Frontend über denselben Ursprung aus. ESLint prüft TypeScript und die React-Hook-Regeln. Die genaue Paketauflösung steht im Lockfile.

Browser: Layout, Navigation, Provider-Verwaltung und Anmeldecode. Der Feature-API-Client ist von React getrennt; `useProviders.ts` verwaltet den React-Zustand. Server: Health-Endpunkt, Provider-API, isolierte Codex-Kindprozesse, Persistenz und statische Frontend-Dateien. Ausschließlich `frontend/dist/` wird statisch ausgeliefert; `Data/` ist über HTTP nicht zugänglich. Im Entwicklungsbetrieb leitet Vite `/api` zum Backend weiter; dadurch ist keine zusätzliche CORS-Freigabe nötig. Die Entwicklungsserver binden an `127.0.0.1`. Im Produktionsbetrieb liefert ein gemeinsamer Server Frontend und API über `0.0.0.0:5010` aus. `HOST` und `PORT` überschreiben die jeweiligen Vorgaben.

Geplant: Monaco-Editor, Projektpersistenz, versionierte R4OS-Dokumentation sowie ein eigener Runner für SDK, Builds und isolierte QEMU-Testinstanzen. Diese Komponenten kommen bei konkretem Bedarf hinzu. Die aktuelle App integriert noch keine R4OS-API oder Toolchain; daher gibt es noch keine eingebundenen R4OS-Revisionen.

## Prüfen und bauen

```bash
corepack pnpm typecheck
corepack pnpm lint
corepack pnpm test
corepack pnpm build
corepack pnpm start
```

`build` prüft TypeScript und erzeugt `frontend/dist/` sowie `backend/dist/`. `start` stellt die gebaute Anwendung auf Port **5010** für LAN und VPN bereit, lokal unter <http://127.0.0.1:5010>. Der systemd-Dienst und die Skripte in [`../Tools/`](../Tools/README.md) übernehmen den dauerhaften Betrieb. Ein laufender Dienst belegt Port 5010; für einen parallelen manuellen Test einen anderen `PORT` setzen. Die Entwicklungsports 5173/3001 bleiben davon unabhängig.

Das Studio selbst hat noch keine Benutzeranmeldung oder Mehrbenutzerrollen. Die OpenAI-Kontoanmeldung erfolgt separat wie oben beschrieben. Die vorhandene Host-Firewall begrenzt den Zugriff auf die erlaubten Netze; der Installer ergänzt nur TCP 5010 auf dem VPN-Interface `sdwan0`. Eine öffentliche Freigabe und R4OS-Testinstanzen sind nicht Teil dieses Dienstes.

Die Backendtests verwenden isolierte temporäre Daten und einen kontrollierten Auth-Client. Sie prüfen Login-Besitz, Kontentrennung, Persistenz, CSRF/Origin/Host-Schutz, OpenAI-only-Validierung, Abbruch, Ablauf, Quoten-Cache und Kontentrennung, fehlende Nutzungsdaten, Reset-Bestätigung und Idempotenz sowie Fehler ohne Token-Leaks. Sie melden keinen simulierten Login als echten OpenAI-Test an. Zusätzlich wurden mit der offiziellen Binary Initialisierung, ein abgemeldetes isoliertes Konto sowie eine echte Device-Code-Anfrage mit anschließendem Abbruch geprüft. Eine vollständige persönliche Anmeldung muss der Benutzer selbst bei OpenAI abschließen.

Bei UI-Änderungen beide Tabs, alle drei Navigationsebenen, Tastatursteuerung und schmale Ansichten im Browser prüfen; `/api/health` muss HTTP 200 liefern. Unbekannte API-Pfade müssen HTTP 404 liefern.
