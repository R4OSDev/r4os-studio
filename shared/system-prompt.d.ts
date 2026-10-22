export interface SystemPrompt {
  text: string;
  defaultText: string;
  revision: number;
  isDefault: boolean;
}
export interface SystemPromptResponse extends SystemPrompt { csrfToken: string }
