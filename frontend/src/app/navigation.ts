export type Tab = 'System' | 'Projects';

export interface NavigationGroup {
  name: string;
  icon: 'system' | 'box' | 'book' | 'flask' | 'folder' | 'settings';
  items: string[];
}

export const navigation: Record<Tab, NavigationGroup[]> = {
  System: [
    { name: 'Settings', icon: 'settings', items: ['LLM Provider'] },
    { name: 'Virtual Machines', icon: 'system', items: [] },
    { name: 'Updates', icon: 'box', items: ['R4OS Studio', 'Components', 'Tools', 'R4OS Releases'] },
  ],
  Projects: [
    { name: 'Workspace', icon: 'folder', items: ['All Projects', 'Recently Opened', 'Templates'] },
    { name: 'Example Project', icon: 'box', items: ['Source', 'Build', 'Tests'] },
  ],
};

export const views: Record<Tab, string[]> = {
  System: [],
  Projects: ['Overview', 'Details', 'Settings'],
};
