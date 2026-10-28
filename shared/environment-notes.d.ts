export type EnvironmentNoteKind='problem'|'suggestion';
export type EnvironmentNoteCategory='tools'|'capabilities'|'workflow'|'interface'|'documentation';
export interface EnvironmentNoteContent {kind:EnvironmentNoteKind;category:EnvironmentNoteCategory;title:string;description:string;impact?:string;workaround?:string;suggestion?:string}
export interface EnvironmentNote extends EnvironmentNoteContent {schemaVersion:1;id:string;revision:number;createdAt:string;origin:{owner:import('./agent-sessions.js').SessionOwner;sessionId:string;runId:string;callId:string;studioVersion:string}}
export interface EnvironmentNotePage {schemaVersion:1;owner:import('./agent-sessions.js').SessionOwner;sessionId:string;revision:number;count:number;entries:EnvironmentNote[];nextBefore:number|null;limits:{maxNotes:number;maxTitleCharacters:number;maxEntryBytes:number}}
export interface EnvironmentNoteDeletion {requestId:string;state:'confirmed';deleted:number;revision:number;count:number}
