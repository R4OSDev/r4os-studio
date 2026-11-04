/** Studio-owned context; protocol connectors do not execute tools or agents. */
export type ModelProtocol = 'responses' | 'chat-completions' | 'messages';
export type ConversationPart =
  | { type: 'text'; text: string }
  | { type: 'tool_call'; callId: string; name: string; arguments: Record<string, unknown> }
  | { type: 'tool_result'; callId: string; result: Record<string, unknown> }
  | { type: 'image' | 'document'; reference: string; mediaType?: string }
  | { type: 'provider'; protocol: ModelProtocol; value: string };
export interface ConversationRecord {
  sequence: number;
  id: string;
  runId: string;
  kind: 'message' | 'checkpoint';
  role: 'user' | 'assistant' | 'tool';
  content: ConversationPart[];
  origin: Record<string, unknown>;
  throughSequence: number | null;
  createdAt: string;
}
