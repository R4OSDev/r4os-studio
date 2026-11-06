/** Declared metadata only; registration never grants runtime or session rights. */
export interface ToolCatalogSource {
  id: string; identity: string; name: string; kind: 'studio' | 'native' | 'mcp'; scopes: string[];
  status: 'ready' | 'prepared' | 'partial' | 'notPrepared' | 'unknown'; count: number | null; reason?: string;
  revision?: number; sourceCommit?: string; runtimeVersion?: string;
  capabilities?: { id: string; callable: false; schemaProvided: false; defaultEnabled: boolean }[];
}
export interface ToolCatalogOverview {
  release: string; revision: string; sources: ToolCatalogSource[]; coverage: 'partial'; reason: string;
}
export interface ToolCatalogRow { id: string; name: string; title?: string; scopes: string[] }
export interface ToolCatalogPage {
  source: ToolCatalogSource; tools: ToolCatalogRow[]; next: string | null; complete: boolean;
}
export interface ToolCatalogDetail {
  source: ToolCatalogSource;
  tool: ToolCatalogRow & { description: string | null; inputSchema: Record<string, unknown>; outputSchema?: Record<string, unknown>; context: string };
}
