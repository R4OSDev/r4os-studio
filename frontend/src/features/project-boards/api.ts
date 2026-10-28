import type { BoardCreate, BoardOrder, BoardReceipt, BoardSnapshot, BoardsListing, BoardUpdate } from '../../../../shared/project-boards';
import { projectRequest } from '../projects/api';

export function boardRequest<T>(projectId: string, path = '', token = '', method = 'GET', body?: unknown, signal?: AbortSignal) {
  return projectRequest<T>(`/${projectId}/boards${path}`, token, method, body, signal);
}
export const listBoards = (projectId: string, signal?: AbortSignal) => boardRequest<BoardsListing>(projectId, '', '', 'GET', undefined, signal);
export const loadBoard = (projectId: string, boardId: string, signal?: AbortSignal) => boardRequest<BoardSnapshot>(projectId, '/' + boardId, '', 'GET', undefined, signal);
export const readBoardReceipt = (projectId: string, requestId: string, signal?: AbortSignal) => boardRequest<BoardReceipt>(projectId, '/receipts/' + requestId, '', 'GET', undefined, signal);
export const createBoard = (projectId: string, token: string, input: BoardCreate) => boardRequest<BoardReceipt>(projectId, '', token, 'POST', input);
export const updateBoard = (projectId: string, boardId: string, token: string, input: BoardUpdate) => boardRequest<BoardReceipt>(projectId, '/' + boardId, token, 'PATCH', input);
export const orderBoards = (projectId: string, token: string, input: BoardOrder) => boardRequest<BoardReceipt>(projectId, '/order', token, 'POST', input);
