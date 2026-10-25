export interface Skill {
  id: string; name: string; revision: number; formatName: string | null; description: string;
  activeRevision: number; activeHash: string | null; createdAt: string; updatedAt: string;
}
export interface SkillFile { path: string; sha256: string; bytes: number; executable: boolean }
export interface SkillDetail { skill: Skill; files: SkillFile[]; draftHash: string }
export interface SkillFileContent extends SkillFile { encoding: 'utf8' | 'base64'; content: string }
export interface SkillValidation { valid: boolean; errors: string[]; metadata?: { name: string; description: string }; draftHash: string }
export interface SkillList { skills: Skill[]; csrfToken: string }
