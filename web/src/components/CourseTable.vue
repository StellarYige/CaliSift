<script setup lang="ts">
import { ref } from "vue";
import type { Course } from "../types";
const props = defineProps<{ busy: boolean }>();
const emit = defineEmits<{ expand: [courses: Course[]] }>();
type Row = {
  title: string;
  weekday: number;
  first: number;
  last: number;
  from: number;
  to: number;
  parity: Course["parity"];
  weeks: string;
  location: string;
};
const blank = (): Row => ({
  title: "",
  weekday: 1,
  first: 1,
  last: 2,
  from: 1,
  to: 16,
  parity: "all",
  weeks: "",
  location: "",
});
const rows = ref<Row[]>([blank()]);
const error = ref("");
function expand() {
  error.value = "";
  if (
    rows.value.some((r) => !r.title.trim() || r.first > r.last || r.from > r.to)
  ) {
    error.value = "请填写课程名称，并检查节次和周次范围";
    return;
  }
  emit(
    "expand",
    rows.value.map((r) => ({
      title: r.title.trim(),
      weekday: r.weekday,
      periods: Array.from(
        { length: r.last - r.first + 1 },
        (_, i) => r.first + i,
      ),
      week_from: r.from,
      week_to: r.to,
      parity: r.parity,
      location: r.location,
      ...(r.weeks.trim()
        ? {
            weeks: r.weeks
              .split(/[,，、\s]+/)
              .filter(Boolean)
              .map(Number),
          }
        : {}),
    })),
  );
}
</script>
<template>
  <section class="card">
    <header class="panel-heading">
      <h2>批量建立学期课程</h2>
      <span class="muted">使用上方学期与节次配置</span>
    </header>
    <form @submit.prevent="expand">
      <div class="table-scroll">
        <table class="course-table">
          <thead>
            <tr>
              <th>课程</th>
              <th>星期</th>
              <th>节次</th>
              <th>周次</th>
              <th>单双周</th>
              <th>指定周（可选）</th>
              <th>地点</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in rows" :key="i">
              <td>
                <input
                  v-model="row.title"
                  required
                  maxlength="2000"
                  aria-label="课程名称"
                />
              </td>
              <td>
                <select v-model.number="row.weekday" aria-label="星期">
                  <option
                    v-for="(day, n) in [
                      '一',
                      '二',
                      '三',
                      '四',
                      '五',
                      '六',
                      '日',
                    ]"
                    :value="n + 1"
                  >
                    {{ day }}
                  </option>
                </select>
              </td>
              <td>
                <input
                  v-model.number="row.first"
                  type="number"
                  min="1"
                  max="30"
                  required
                  aria-label="开始节次"
                />–<input
                  v-model.number="row.last"
                  type="number"
                  min="1"
                  max="30"
                  required
                  aria-label="结束节次"
                />
              </td>
              <td>
                <input
                  v-model.number="row.from"
                  type="number"
                  min="1"
                  max="60"
                  required
                  aria-label="开始周"
                />–<input
                  v-model.number="row.to"
                  type="number"
                  min="1"
                  max="60"
                  required
                  aria-label="结束周"
                />
              </td>
              <td>
                <select v-model="row.parity" aria-label="单双周">
                  <option value="all">全部</option>
                  <option value="odd">单周</option>
                  <option value="even">双周</option>
                </select>
              </td>
              <td>
                <input
                  v-model="row.weeks"
                  placeholder="1,3,7"
                  aria-label="指定周次"
                />
              </td>
              <td>
                <input
                  v-model="row.location"
                  aria-label="地点"
                  maxlength="2000"
                />
              </td>
              <td>
                <button
                  type="button"
                  @click="rows.splice(i + 1, 0, { ...row })"
                  :disabled="rows.length >= 100"
                >
                  复制</button
                ><button
                  type="button"
                  @click="rows.splice(i, 1)"
                  :disabled="rows.length === 1"
                >
                  移除
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="error" class="notice warning" role="alert">{{ error }}</p>
      <div class="button-row">
        <button
          type="button"
          class="secondary"
          @click="rows.push(blank())"
          :disabled="rows.length >= 100"
        >
          添加课程</button
        ><button class="primary" :disabled="props.busy">
          展开全部日期并核对
        </button>
      </div>
    </form>
  </section>
</template>
