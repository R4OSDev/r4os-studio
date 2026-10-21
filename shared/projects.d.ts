export interface ProjectSummary {
  id: string;
  name: string;
}

export interface ProjectsResponse {
  projects: ProjectSummary[];
  csrfToken: string;
}
