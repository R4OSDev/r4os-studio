import type { BoardCard, BoardCreate, BoardMutation, BoardOrder, BoardReceipt, BoardSnapshot, BoardsListing, BoardUpdate } from '../../../../shared/project-boards';
import { projectRequest } from '../projects/api';

export function boardRequest<T>(projectId: string, path = '', token = '', method = 'GET', body?: unknown, signal?: AbortSignal) {
  return projectRequest<T>(`/${projectId}/boards${path}${path.includes('?') ? '&' : '?'}clientLevel=2`, token, method, body, signal);
}
export const listBoards = (projectId: string, signal?: AbortSignal) => boardRequest<BoardsListing>(projectId, '', '', 'GET', undefined, signal);
export const loadBoard = (projectId: string, boardId: string, signal?: AbortSignal) => boardRequest<BoardSnapshot>(projectId, '/' + boardId, '', 'GET', undefined, signal);
export const readBoardReceipt = (projectId: string, requestId: string, signal?: AbortSignal) => boardRequest<BoardReceipt>(projectId, '/receipts/' + requestId, '', 'GET', undefined, signal);
export const createBoard = (projectId: string, token: string, input: BoardCreate) => boardRequest<BoardReceipt>(projectId, '', token, 'POST', input);
export const updateBoard = (projectId: string, boardId: string, token: string, input: BoardUpdate) => boardRequest<BoardReceipt>(projectId, '/' + boardId, token, 'PATCH', input);
export const orderBoards = (projectId: string, token: string, input: BoardOrder) => boardRequest<BoardReceipt>(projectId, '/order', token, 'POST', input);
export const mutateBoard = (projectId: string, boardId: string, token: string, input: BoardMutation) => boardRequest<BoardReceipt>(projectId, '/' + boardId + '/mutations', token, 'POST', input);
export const loadCard = (projectId: string, boardId: string, cardId: string, signal?: AbortSignal) => boardRequest<{ card: BoardCard; boardRevision: number }>(projectId, '/' + boardId + '/cards/' + cardId, '', 'GET', undefined, signal);
