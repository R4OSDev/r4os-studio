export type Tab = 'System' | 'Projects';

export interface NavigationGroup {
  name: string;
  icon: 'system' | 'box' | 'book' | 'flask' | 'folder' | 'settings';
  items: string[];
}

export const navigation: NavigationGroup[] = [
  { name: 'Settings', icon: 'settings', items: ['LLM Provider', 'System Prompt'] },
  { name: 'Virtual Machines', icon: 'system', items: [] },
  { name: 'Updates', icon: 'box', items: ['R4OS Studio', 'Components', 'Tools', 'R4OS Releases'] },
];
