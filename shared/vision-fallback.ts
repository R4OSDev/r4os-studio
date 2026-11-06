export interface VisionSelection { providerId: string; modelId: string }
export interface VisionSettings {
 revision: number; vision: VisionSelection | null; state: 'Not configured' | 'Configured' | 'Unavailable'; reason: string | null; csrfToken: string;
 providers: { id: string; name: string; enabled: boolean; reason: string | null;
  models: { id: string; name: string; available: boolean; reason: string | null }[] }[];
}
export interface VisionSettingsInput { requestId: string; revision: number; vision: VisionSelection | null }

export type ImageGenerationSettings = Omit<VisionSettings,'vision'> & { imageGeneration: VisionSelection | null };
export interface ImageGenerationSettingsInput { requestId: string; revision: number; imageGeneration: VisionSelection | null }
