export interface SystemPrompt {
  sha256: string;
  text: string;
  defaultText: string;
  revision: number;
  isDefault: boolean;
}
export interface SystemPromptResponse extends SystemPrompt { csrfToken: string }
