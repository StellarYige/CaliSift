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
