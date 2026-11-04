export interface Skill {
  id: string; name: string; revision: number; formatName: string | null; description: string;
  activeRevision: number; activeHash: string | null; createdAt: string; updatedAt: string;
}
export interface SkillFile { path: string; sha256: string; bytes: number; executable: boolean }
export interface SkillSourceConfiguration {
  repository: string; ref: string; skillPath: string; recipe: 'rea' | null; connectionId: string | null;
}
export interface SkillSource {
  configuration: SkillSourceConfiguration; revision: number; status: string; commit: string | null;
  active: { commit: string; packageHash: string; importedHash: string; draftHash: string; repository: string;
    runtime: { path: string; manifestHash: string; version: string } | null } | null;
  lastRequestId: string | null; updatedAt: string;
}
export interface SkillSourceJob {
  requestId: string; skillId: string; action: 'activate' | 'update'; phase: string;
  sourceRevision: number; skillRevision: number; draftHash: string;
  configuration: SkillSourceConfiguration; commit: string | null; pid: number | null;
  result: Record<string, unknown> | null; error: string | null; createdAt: string; updatedAt: string;
}
export interface SkillDetail { skill: Skill; files: SkillFile[]; draftHash: string; activeDraftHash?: string | null; source?: SkillSource | null }
export interface SkillFileContent extends SkillFile { encoding: 'utf8' | 'base64'; content: string }
export interface SkillValidation { valid: boolean; errors: string[]; metadata?: { name: string; description: string }; draftHash: string }
export interface SkillList { skills: Skill[]; csrfToken: string }
export interface SkillDeletionPreview { id:string;name:string;revision:number;scopeHash:string;files:number;revisions:number;sessions:number;sessionIds?:string[];allowed:boolean;blockers:{reason:string;ownerType?:'project'|'skill';ownerId?:string;sessionId?:string;runId?:string}[] }
export interface SkillDeletionInput {requestId:string;revision:number;scopeHash:string;confirmName:string}
export interface SkillDeletionReceipt {requestId:string;id:string;state:'deleting'|'deleted'|'unknown';phase:string;reason?:string}
