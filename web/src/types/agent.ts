export interface AgentProfile {
  name: string;
  display_name: string;
  description: string;
  role: string;
  skill_plugin: string;
  soul_file?: string;
  model_preference?: string;
  max_context_tokens?: number;
}

export interface TeamConfig {
  name: string;
  display_name: string;
  captain: string;
  members: string[];
  description: string;
}

export interface TaskItem {
  task_id: string;
  description: string;
  status: string;
  assignee?: string;
  result?: string;
}