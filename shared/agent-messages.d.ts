import type { FrozenAttachment } from './agent-inputs.js';

export type SessionMessageState = 'pending' | 'queued' | 'dispatching' | 'accepted' | 'rejected' | 'cancelled' | 'unknown';
export interface MessageTarget { runId: string; threadId: string; turnId: string }
export interface SessionMessageInput {
  requestId: string; revision: number; mode: 'queue' | 'steer'; text: string;
  attachments?: string[]; target?: MessageTarget;
}
export interface SessionMessage {
  requestId: string; sessionId: string; sequence: number; mode: 'queue' | 'steer'; state: SessionMessageState;
  text: string; attachments: FrozenAttachment[]; target: MessageTarget | null;
  runId: string | null; error: string | null; createdAt: string; updatedAt: string;
}
export interface SessionInbox {
  messages: SessionMessage[]; nextBefore: number | null;
  held: boolean; reason: string | null; revision: number;
}
