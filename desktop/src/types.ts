export type Category = { name: string; color: string; active: boolean };
export type Preferences = {
  theme: "system" | "light" | "dark";
  font_size: 14 | 17 | 20;
  density: "comfortable" | "compact";
  week_start: 0 | 1;
  scenario: "general" | "work" | "study";
  hide_rest: boolean;
  categories: Category[];
};
export type PreferenceSnapshot = { revision: number; values: Preferences };
export type DevicePreferences = {
  last_workspace: string;
  width: number;
  height: number;
  panel_ratio: number;
};
export type Semester = {
  monday: string;
  weeks: number;
  periods: { start: string; end: string }[];
};
export type Course = {
  title: string;
  weekday: number;
  periods: number[];
  week_from: number;
  week_to: number;
  parity: "all" | "odd" | "even";
  location: string;
  weeks?: number[];
};
export type Rules = {
  shifts?: {
    name: string;
    aliases: string[];
    start: string;
    end: string;
    next_day?: boolean;
  }[];
  semester?: Semester;
  template?: {
    layout: string;
    header_row: number;
    mapping: Record<string, number>;
    [key: string]: unknown;
  };
};
export type RuleTemplate = {
  id: string;
  name: string;
  description: string;
  rules: Rules;
  version: number;
};
export type Evidence = {
  file_id: string;
  filename: string;
  sheet: string;
  name_cell: string;
  evidence: Record<string, string>;
  excerpt: string;
  hidden: boolean;
};
export type DraftEvent = {
  id: string;
  date: string | null;
  title: string;
  shift: string;
  start: string | null;
  end: string | null;
  end_date: string | null;
  precision: "date" | "point" | "interval";
  status: "pending" | "confirmed";
  sources: Evidence[];
  notes: string[];
  warnings: string[];
  location: string;
  all_day?: boolean;
  category?: string;
  field_basis?: Record<string, string>;
};
export type ImportJob = {
  id: string;
  workspace_id: string;
  status: string;
  year: number;
  source_id: string;
  rules: Rules;
  files: {
    id: string;
    filename: string;
    suffix: string;
    status: string;
    error?: string;
    options?: Record<string, unknown>;
  }[];
  report?: {
    events: DraftEvent[];
    pending: DraftEvent[];
    files: Record<string, unknown>[];
    warnings: string[];
    conflicts: Record<string, unknown>[];
  } | null;
};
export type NativeRequests = {
  get_preferences: [{ workspace_id: string }, PreferenceSnapshot];
  save_preferences: [
    { workspace_id: string; expected_revision: number; values: Preferences },
    PreferenceSnapshot,
  ];
  device_preferences: [
    { values?: Partial<DevicePreferences> },
    DevicePreferences,
  ];
  delete_template: [{ template_id: string }, boolean];
  last_semester: [{ workspace_id: string }, Semester | null];
  course_draft: [
    (
      | { workspace_id: string; semester: Semester; courses: Course[] }
      | { workspace_id: string; semester: Semester; course: Course }
    ),
    ImportJob,
  ];
  get_job: [{ job_id: string }, ImportJob];
  list_jobs: [{ workspace_id: string }, ImportJob[]];
};
export const defaultCategories: Category[] = [
  "工作",
  "学习",
  "培训",
  "考试",
  "休息",
  "其他",
].map((name, i) => ({
  name,
  color: ["#8876c6", "#5d96a5", "#c69553", "#d37f87", "#8b9b88", "#9893a0"][i]!,
  active: true,
}));
