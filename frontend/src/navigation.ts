export type Tab = 'System' | 'Projects';

export interface NavigationGroup {
  name: string;
  icon: 'system' | 'box' | 'book' | 'flask' | 'folder';
  items: string[];
}

export const navigation: Record<Tab, NavigationGroup[]> = {
  System: [
    { name: 'Umgebung', icon: 'system', items: ['Allgemein', 'Konfiguration', 'Verbindungen'] },
    { name: 'SDK & Toolchain', icon: 'box', items: ['SDK', 'Toolchain', 'Host-Werkzeuge'] },
    { name: 'API-Referenz', icon: 'book', items: ['Dokumentation', 'API', 'ABI'] },
    { name: 'Testumgebungen', icon: 'flask', items: ['Instanzen', 'Systemabbilder', 'QEMU'] },
  ],
  Projects: [
    { name: 'Arbeitsbereich', icon: 'folder', items: ['Alle Projekte', 'Zuletzt geöffnet', 'Vorlagen'] },
    { name: 'Beispielprojekt', icon: 'box', items: ['Quellcode', 'Build', 'Tests'] },
  ],
};

export const views = ['Übersicht', 'Details', 'Einstellungen'];
