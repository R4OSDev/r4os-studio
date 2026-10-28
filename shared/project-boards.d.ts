/** Browser-only Kanban contracts. No agent tools or workspace data. */
export interface BoardSummary {
  id: string; name: string; description: string; position: number; revision: number;
  orderRevision: number; archived: boolean; cardCount: number; createdAt: string; updatedAt: string;
}
export interface BoardColumn { id: string; boardId: string; title: string; position: number; revision: number; cardCount: number }
export type BoardColor = 'purple' | 'blue' | 'green' | 'yellow' | 'orange' | 'pink' | 'gray';
export interface BoardLabel { id: string; boardId: string; name: string; color: BoardColor; revision: number }
export interface BoardChecklistItem { id: string; text: string; checked: boolean; position: number; revision: number }
export interface BoardCard {
  id: string; boardId: string; columnId: string; title: string; description: string; position: number;
  revision: number; archived: boolean; priority: 'low' | 'normal' | 'high'; dueDate: string | null;
  labelIds: string[]; checklist: BoardChecklistItem[]; createdAt: string; updatedAt: string;
}
export type BoardCardSummary = Omit<BoardCard, 'description' | 'checklist'> & { descriptionPreview: string; checked: number; checklistCount: number };
export interface BoardsListing { projectId: string; revision: number; boards: BoardSummary[] }
export interface BoardSnapshot { projectId: string; revision: number; board: BoardSummary; columns: BoardColumn[]; cards: BoardCardSummary[]; labels: BoardLabel[] }
export interface BoardCreate { requestId: string; expectedRevision: number; name: string; description?: string }
export interface BoardUpdate { requestId: string; expectedRevision: number; name?: string; description?: string }
export interface BoardOrder { requestId: string; expectedRevision: number; ids: string[] }
export type BoardEntryAction = 'create_column' | 'update_column' | 'delete_column' | 'create_card' | 'update_card' | 'delete_card' | 'move_card' | 'move_column';
export interface BoardMutation {
  requestId: string; expectedRevision: number; expectedOrderRevision?: number; action: BoardEntryAction;
  input: { columnId?: string; sourceColumnId?: string; targetColumnId?: string; expectedColumnRevision?: number; cardId?: string; expectedCardRevision?: number; position?: number; title?: string; description?: string; confirm?: true };
}
export interface BoardReceipt { requestId: string; projectRevision: number; boardId?: string; revision?: number; board?: BoardSummary; cardId?: string; columnId?: string; deleted?: boolean; movedCards?: number; unchanged?: boolean }
