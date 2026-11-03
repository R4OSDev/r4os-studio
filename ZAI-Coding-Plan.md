# Z.AI GLM Coding Plan

0.9.39 adds a distinct subscription connection on the existing private API-key
store. Select **Z.AI · GLM Coding Plan** and enter your own plan API key. Keys
remain write-only; the normal revision, lease, original-request, rotation and
confirmed disconnect/delete contracts apply.

This product uses only `https://api.z.ai/api/coding/paas/v4` with Chat
Completions and Bearer auth. General prepaid API endpoints, other regions,
other protocols and local server presets are rejected. No paid fallback or
extra-usage option is enabled. Actual account rights are not established by
saving a connection. Model inference becomes available with the later GLM
transport integration; this release only delivers connection management.

The browser handles connection forms. The host owns keys and all transport.
Existing providers, sessions, model histories and SDK bindings are preserved.
