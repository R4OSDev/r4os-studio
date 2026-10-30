# Project GitHub Issues (0.8.34)

Projects → GitHub now uses the third column for **Connection**, then **Issues**.
Connection starts by default and retains the existing setup, account/repository,
branch, diff, commit/push, pull and recovery UI. Without a bound repository,
Issues stays visible and disabled. Its right-aligned count shows all open issues,
independent of the displayed filter or page. Confirmed zero is `0`; pending and
unavailable reads are distinct. Old observations are labelled with their check
time and `~` count until refreshed.

The read-only Issues panel offers Open (default), Closed and All, 25-row pages,
Previous/Next/Refresh, number, title, state, label previews, update time and a
verified GitHub link. Issue text is rendered as plain React text, never HTML.
Links must match the confirmed repository and exact issue number. Label color
is restricted to six hexadecimal digits. There are no issue mutations or new
agent tools. The count/page read itself starts no Git job or repository action.

The protected `GET /api/projects/:id/github/issues` requires the current local
binding revision and accepts only state, signed cursor and explicit refresh.
It reuses the existing Projects browser session, host/origin gates and server-only
GitHub credential store. A fixed GraphQL query at `api.github.com/graphql` reads
viewer/repository identity, Issues enabled state, `issues(states:OPEN).totalCount`
and the selected IssueConnection page. Pull requests never enter this typed
connection. No query, URL, credential or arbitrary repository can be supplied by
the browser. Account ID, repository ID/name, full local binding and credential
revision are verified before/after the read. Deleting projects are unavailable.

GraphQL errors and partial data are rejected even with HTTP 200. Authentication,
Issues read denial/SSO, rate limits, disabled Issues, changed identity and network
errors remain explicit; none produces an invented zero. A concurrent denial or
binding change prevents an older successful response from restoring cached data.
No token, upstream error body or issue body enters the public DTO/log message.

The existing transport keeps TLS, fixed-host/no-redirect behavior, a ten-second
deadline and two-MiB response cap. Server reads share pending identical requests,
allow four distinct network reads and retain at most 64 pages for 30 seconds.
Keys bind project, full repository binding, credential revision, filter and
cursor. Signed ten-minute cursors expire on scope/filter/credential changes or
backend restart. Refresh returns to the first page without changing Git state.

The browser loads only the selected project's GitHub view. Connection and Issues
share the count/first-page state; switching between them requires no second read.
Leaving/filter/project changes abort obsolete browser reads and ignore late
responses. At most 25 rows and 50 previous-page cursors are retained; First-page
Refresh and Next remain available for longer lists. Focus, visibility restoration,
explicit Refresh and a completed connection change revalidate the selected view;
the local stale timer makes no network requests. There is no all-project poll.

Readonly Connection checks now reuse a matching pending opening check where
available. Their busy indicator no longer blocks global navigation; actual Git
writes/recovery and dirty-form guards retain their existing restrictions. Count
updates preserve mounted Connection forms and their unsaved text.

Focused backend groups cover fixed query/count/filter/cursor/zero and shared
requests, partial/PR/unsafe/denied/rate responses, binding/token replacement,
late success after denial and protected HTTP scope/query gates. The actual
ProjectsWorkspace browser passed at 1440/320 px with Connection/Issues order,
unbound state, paging/filter-independent count, zero/error distinction, plain
text/links, late project replies, preserved Connection draft/dirty guard, binding
changes and stale observation without polling. No model inference, real issue
write, user push/pull or VM action was required. Build, frontend/backend
TypeScript and strict ESLint complete the release checks.

Primary schema and behavior references:
[Repository and issues arguments](https://docs.github.com/en/graphql/reference/repos),
[IssueConnection](https://docs.github.com/en/graphql/reference/issues),
[authenticated GraphQL calls](https://docs.github.com/en/graphql/guides/forming-calls-with-graphql)
and [query limits/partial errors](https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api).
Evidence: `Research/R4OS/Roadmap-Implementation/0.8.34/` in the development workspace.
