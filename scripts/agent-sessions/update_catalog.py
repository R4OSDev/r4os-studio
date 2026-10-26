"""Studio v5 update contracts, distinct from the source-bound native SYSUPD interface."""
def obj(properties,required=()):
    return {'type':'object','properties':properties,'required':list(required),'additionalProperties':False}
ID={'type':'string','maxLength':36,'description':'Opaque Studio UUID from a confirmed result.'}
V={'type':'integer','minimum':1,'maximum':9007199254740991}
HASH={'type':'string','pattern':'^[a-f0-9]{64}$'}
VERSION={'type':'string','maxLength':24}
META=obj({'packageId':{'type':'string','minLength':1,'maxLength':48},'packageVersion':VERSION,
    'targetRelease':VERSION,'title':{'type':'string','maxLength':96},'description':{'type':'string','maxLength':2048}},
    ['packageId','packageVersion','targetRelease','title','description'])
REQUIREMENT=obj({'kind':{'type':'string','enum':['KERNEL','R4X','R4L','R4D','R4P']},'name':{'type':'string','maxLength':48},
    'target':{'type':'string','maxLength':1023},'minVersion':VERSION,'state':{'type':'string','enum':['installed','active']}},
    ['kind','name','target','minVersion','state'])
BASE={'updateId':ID,'updateRevision':V}
EFFECT={**BASE,'vmRevision':{'type':'string','maxLength':100},'targetRelease':VERSION}
REBOOT={**EFFECT,'confirmReboot':{'type':'boolean','const':True}}
DEFS={
'read_update_package':('Read only this project/session package options, plan, package artifact, update list or update record. IDs come from confirmed results. Use jobs to find original admitted requests after a lost response. No guest command or inference.',
    obj({'action':{'type':'string','enum':['options','plan','package','updates','update','jobs']},'id':ID},['action'])),
'plan_update_package':('Create an immutable update plan from this session’s confirmed native build artifact IDs. Supply explicit distinct package/component/release metadata and requirements; preserve SDK catalogue targets. No payload build or VM action. A package request ID is derived by the harness.',
    obj({'configurationRevision':V,'metadata':META,'artifactIds':{'type':'array','minItems':1,'maxItems':32,'uniqueItems':True,'items':ID},
    'requirements':{'type':'array','maxItems':32,'items':REQUIREMENT}},['configurationRevision','metadata','artifactIds','requirements'])),
'build_update_package':('Build the exact confirmed plan with its frozen qualified R4UPack profile. Wait internally for the original package job; do not poll/resubmit. Native exit0 plus immutable R4U2 size/hash is required. No VM action.',
    obj({'planId':ID,'planSha256':HASH},['planId','planSha256'])),
'check_update_vm':('Read fresh assigned-VM VER, native SYSUPD STATUS, installed release and full inventory under its reservation. Never starts/reboots or uploads. STATUS may materialize update directories. Wait for this one original observation; it is not native VERIFY.',
    obj({'packageArtifactId':ID},['packageArtifactId'])),
'upload_update_package':('Publish this session’s immutable package through the fixed own Inbox path after fresh preflight, confirmed CLOSE and complete size/SHA-256 readback, then create-only rename. Never installs or reboots. Wait internally; no retry of unconfirmed write/close/rename.',
    obj({'packageArtifactId':ID},['packageArtifactId'])),
'install_update_package':('Native VERIFY then STAGE for 1–16 explicit own published transfer jobs at one target release. STAGE can perform persistent live APPLY; report installation only from confirmed native outcome/proof. A prepared batch is awaiting commit. No automatic COMMIT/reboot. Wait in the harness for the original result.',
    obj({'transferJobIds':{'type':'array','minItems':1,'maxItems':16,'uniqueItems':True,'items':ID}},['transferJobIds'])),
'commit_update':('Commit the exact current own batch and reboot only for a concrete user request authorizing that VM/update/reboot and this frozen commit permission. Supply values from its current record, confirmReboot=true. Sent once, then bounded read-only postboot proof. Unknown is never a reason to repeat COMMIT.',
    obj({**REBOOT,'batchId':{'type':'string','pattern':'^[0-9]{1,20}$'}},list(REBOOT)+['batchId'])),
'verify_update':('Read-only bounded proof of the original own update, including after a lost COMMIT response. Correlate native terminal IDs, components and requested full artifact hashes. Never sends COMMIT/RESUME-BATCH or starts the VM. Default120s, full hashes on. Rollback is a separate result.',
    obj({**BASE,'deadlineSeconds':{'type':'integer','minimum':30,'maximum':300},'fullArtifactHashes':{'type':'boolean'}},list(BASE))),
'resume_update':('Explicitly resume only the freshly proved own transaction or batch. Batch resume can COMMIT/reboot and additionally requires the frozen commit permission, concrete user reboot authorization and confirmReboot=true. Native rolled_back journal plus rolling-back batch needs explicit batch finalization. No foreign/uncorrelated adoption or command replay.',
    obj({**EFFECT,'mode':{'type':'string','enum':['transaction','batch']},'confirmReboot':{'type':'boolean'}},list(EFFECT)+['mode','confirmReboot'])),
'abort_update':('Abort only this exact own prepared batch before a durable batch transaction. Persistent installation is not undone by abort/Stop. Native state is freshly checked; wait for the original abort proof.',
    obj(EFFECT,list(EFFECT))),
'rollback_update':('Explicitly request native ROLLBACK-LAST for this exact latest proved own update only when the user authorizes rollback of this VM and possible reboot, with its separate frozen rollback permission. ConfirmReboot=true. A reverted outcome is not installation success. Do not repeat an unknown rollback.',
    obj(REBOOT,list(REBOOT))),
'cleanup_update_transport':('After native terminal proof/own prepared abort, remove only original own Inbox TMP/R4U bytes matching full size/hash. Preserve partial/different/foreign files and every diagnostic/hash. Unknown removal is reconciled by reading original paths, never replayed.',
    obj(EFFECT,list(EFFECT))),
}
