export type Tab = 'Status' | 'System' | 'Projects' | 'Tools';

export interface NavigationGroup {
  name: string;
  icon: 'system' | 'box' | 'book' | 'flask' | 'folder' | 'settings' | 'statistics';
  items: string[];
}

export const navigation: NavigationGroup[] = [
  { name: 'Settings', icon: 'settings', items: ['AI Provider', 'System Prompt', 'GitHub', 'Skill Manager Prompt', 'Fallback', 'Context', 'Tools'] },
  { name: 'Virtual Machines', icon: 'system', items: [] },
  { name: 'Remote Hosts', icon: 'system', items: [] },
  { name: 'Updates', icon: 'box', items: ['R4OS Studio', 'Components', 'Tools', 'R4OS Releases'] },
  { name: 'Statistics', icon: 'statistics', items: [] },
  { name: 'Tools', icon: 'box', items: [] },
];
