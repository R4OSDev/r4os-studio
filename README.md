# R4OS Studio · App

Lokales Grundgerüst einer browserbasierten Entwicklungsumgebung für R4OS.

## Repository

Dieses Verzeichnis ist das lokale Git-Repository. Remote: `https://gitea.r4public.r4network/R4mbo/R4OS_Studio.git`, Branch `main`. Jede fertiggestellte Unterversion wird committed und gepusht. Aus dem übergeordneten Workspace unter Linux: `./Tools/Push.sh "Kurze Commit-Beschreibung"`; unter Windows: `Tools\Push.bat "Kurze Commit-Beschreibung"`.

`AGENTS.md` und `Tools/` liegen im übergeordneten Workspace und werden nicht in dieses Repository aufgenommen. Lokale Git-Einstellungen erlauben das selbstsignierte Gitea-Zertifikat und lösen `gitea.r4public.r4network` bei Bedarf über `10.0.0.2` auf. Zugangsdaten stehen im außerhalb dieses Repositories abgelegten Push-Skript; die Remote-URL enthält keine Zugangsdaten.

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
- Obere Tab-Leiste mit **System** und **Projects**. Auch mit Pfeiltasten, Pos1 und Ende bedienbar.
- Links drei gleich breite Navigationsspalten: **Areas → Components → Views**. Ihre Breite entspricht auf dem Desktop der bisherigen dritten Spalte; der übrige Platz steht dem Hauptbereich zur Verfügung.
- Im Tab **System** gibt es ausschließlich **Settings → LLM Provider**. Die Liste **Views** ist dort leer; der Hauptbereich enthält noch keine Konfigurationsfunktion.
- Rechts ein Hauptbereich mit Breadcrumb, Seitentitel und Platzhalter.
- Die Auswahl bleibt pro Tab im Speicher erhalten; Neuladen setzt sie zurück.
- Auf schmalen Bildschirmen stehen die drei Navigationsspalten oberhalb des Hauptbereichs.
- Ein Fastify-Backend mit `GET /api/health`. Der Status beschreibt ausschließlich den Studio-Server, keine R4OS-Instanz.

Alle Navigationsinhalte sind Dummys, einschließlich „Example Project“. Es werden weder Projekte gespeichert noch R4OS-Tools gestartet. Die Oberfläche lädt keine externen Schriftarten oder anderen Medien.

## Aufbau und Entscheidungen

```text
App/
├── frontend/         React-Oberfläche und Vite-Konfiguration
│   └── src/          Layout, Navigation und Styles
├── backend/          Fastify-Server
├── scripts/          Gemeinsamer Entwicklungsstart
└── pnpm-lock.yaml    Aufgelöste Abhängigkeitsversionen
```

React und TypeScript strukturieren die interaktive Studio-Oberfläche. Vite übernimmt Entwicklungsserver und Frontend-Build. Fastify stellt die lokale HTTP-API bereit; `@fastify/static` liefert beim Produktionsstart das gebaute Frontend über denselben Ursprung aus. ESLint prüft TypeScript und die React-Hook-Regeln. Die genaue Paketauflösung steht im Lockfile.

Browser: Layout, Navigation und Platzhalteransichten. Server: Health-Endpunkt und statische Dateien. Im Entwicklungsbetrieb leitet Vite `/api` zum Backend weiter; dadurch ist keine zusätzliche CORS-Freigabe nötig. Die Entwicklungsserver binden an `127.0.0.1`. Im Produktionsbetrieb liefert ein gemeinsamer Server Frontend und API über `0.0.0.0:5010` aus. `HOST` und `PORT` überschreiben die jeweiligen Vorgaben.

Geplant: Monaco-Editor, Projektpersistenz, versionierte R4OS-Dokumentation sowie ein eigener Runner für SDK, Builds und isolierte QEMU-Testinstanzen. Diese Komponenten kommen bei konkretem Bedarf hinzu. Die aktuelle App integriert noch keine R4OS-API oder Toolchain; daher gibt es noch keine eingebundenen R4OS-Revisionen.

## Prüfen und bauen

```bash
corepack pnpm typecheck
corepack pnpm lint
corepack pnpm build
corepack pnpm start
```

`build` prüft TypeScript und erzeugt `frontend/dist/` sowie `backend/dist/`. `start` stellt die gebaute Anwendung auf Port **5010** für LAN und VPN bereit, lokal unter <http://127.0.0.1:5010>. Der systemd-Dienst und die Skripte in [`../Tools/`](../Tools/README.md) übernehmen den dauerhaften Betrieb. Ein laufender Dienst belegt Port 5010; für einen parallelen manuellen Test einen anderen `PORT` setzen. Die Entwicklungsports 5173/3001 bleiben davon unabhängig.

Es sind keine Zugangsdaten nötig. Authentifizierung und Mehrbenutzerabsicherung sind noch nicht implementiert. Die vorhandene Host-Firewall begrenzt den Zugriff auf die erlaubten Netze; der Installer ergänzt nur TCP 5010 auf dem VPN-Interface `sdwan0`. Eine öffentliche Freigabe und R4OS-Testinstanzen sind nicht Teil dieses Dienstes.

Ein automatisierter Funktionstestsatz ist noch nicht eingerichtet. Für den aktuellen Stand: beide Tabs, alle drei Navigationsebenen, Tastatursteuerung und schmale Ansichten im Browser prüfen; `/api/health` muss HTTP 200 liefern. Unbekannte API-Pfade müssen HTTP 404 liefern.
