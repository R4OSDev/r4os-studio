# Session screenshot data (0.8.26)

The protected session `screenshots` read lists registered agent VM captures
across all original runs/jobs, with stable publication order and signed,
session/source/snapshot-bound cursors. Pages contain at most 32 references.
Neither the 100-job overview nor the 32-image job summary limits this list.

A derived reference index lives in the session catalog. Each read projects at
most 256 newly registered evidence rows and a small batch of unresolved legacy
references. The existing development catalog is read-only: one evidence/job
join and batched original tool/action receipts, no transcript scan or browser
request for each job. The index contains metadata, not copied PNGs. Backfill
reports incomplete coverage until it reaches its source watermark. Missing or
ambiguous legacy provenance is counted separately; it never becomes an image
by guessing from model text. Source replacement expires cursors and rebuilds
only derived references.

Membership requires the registered screenshot kind, QMP/source/scope, project,
job, observer session/run, original Studio capture/input call and immutable
image metadata. Legacy original tool/image or completed action receipts can
establish the relationship. New capture publications also retain the original
capture/input request ID before its response can be lost. This includes
optional gesture observations. A published image can therefore be discovered
without replaying the tool or declaring an unconfirmed tool successful.

Manual console images, uploads/generated assets, assessment actions and foreign
sessions are excluded. Separate original evidence IDs remain separate even if
their PNG bytes are identical. Historical VM/boot bindings remain visible;
changing the current VM or model/capture permission does not remove old images.
Skills currently return an explicit unavailable/empty result, without VM rights.

Gallery image reads check the exact indexed session/job/evidence membership
before reusing the existing protected development evidence read. Original
no-follow/type/size/SHA checks are retained; the browser route additionally
checks the exact metadata, PNG header/dimensions and SHA before returning
`image/png` with private/no-store and nosniff. Missing/corrupt originals remain
errors; no replacement image or new VM capture is requested.

Session cleanup removes its own reference/scan/gap tables. Original development
jobs/PNG lifetime and statistics are unchanged. Showing saved images needs no
running VM and proves neither current guest readiness nor visual acceptance.
## Gallery overlay (0.8.27)

An image icon immediately left of Session statistics opens the modal gallery
without changing the composer draft or model selection. The latest registered
image appears above a horizontal, paged strip of older captures. Images retain
their full aspect ratio. Arrow buttons, touch/trackpad and keyboard navigation
reach older pages without mounting the whole collection.

Latest follows the newest confirmed metadata when it is read. Selecting an
older image holds that original selection; refreshed metadata can report a new
capture without replacing it. Latest resumes following, and reopening starts
with the latest image. Background metadata for the same page does not reset
its scroll position. Automatic observation and further image resource limits
follow in 0.8.28.

The dialog uses the common Studio design and native modal focus behavior,
Close/Escape and return focus. Stop current run stays reachable. Loading,
empty/unavailable, missing-image and expired-auth states are separate. All
browser images reuse registered protected evidence; no gallery action captures
a VM image or causes inference. Stored captures are labelled with their saved
time and dimensions, not as current guest state.
