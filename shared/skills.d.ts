export interface Skill {
  id: string; name: string; revision: number; formatName: string | null; description: string;
  activeRevision: number; activeHash: string | null; createdAt: string; updatedAt: string;
}
export interface SkillFile { path: string; sha256: string; bytes: number; executable: boolean }
export interface SkillDetail { skill: Skill; files: SkillFile[]; draftHash: string }
export interface SkillFileContent extends SkillFile { encoding: 'utf8' | 'base64'; content: string }
export interface SkillValidation { valid: boolean; errors: string[]; metadata?: { name: string; description: string }; draftHash: string }
export interface SkillList { skills: Skill[]; csrfToken: string }
export interface SkillDeletionPreview { id:string;name:string;revision:number;scopeHash:string;files:number;revisions:number;sessions:number;allowed:boolean;blockers:{reason:string;ownerType?:'project'|'skill';ownerId?:string;sessionId?:string;runId?:string}[] }
export interface SkillDeletionInput {requestId:string;revision:number;scopeHash:string;confirmName:string}
export interface SkillDeletionReceipt {requestId:string;id:string;state:'deleting'|'deleted'|'unknown';phase:string;reason?:string}
