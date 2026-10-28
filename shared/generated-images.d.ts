export interface GeneratedImage {
  id: string; sessionId: string; runId: string; threadId: string; itemId: string;
  sha256: string; size: number; mediaType: 'image/png'; width: number; height: number;
  transparent: boolean; createdAt: string; presentation: { reference: string; markdown: string };
}
export interface GeneratedAsset {
  imageId: string; sourceSha256: string; path: string; format: 'original' | 'png' | 'ico' | 'rgba32';
  width: number; height: number; size: number; sha256: string; stage: 'Imported';
  transparent: boolean; pixelOrder?: string; stride?: number; rowOrder?: string; alpha?: string;
}
