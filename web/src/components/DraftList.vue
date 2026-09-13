<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { DraftEvent, DraftConflict } from "../types";
const props = withDefaults(
  defineProps<{
    entries: DraftEvent[];
    checked: number[];
    conflicts?: DraftConflict[];
  }>(),
  { conflicts: () => [] },
);
const emit = defineEmits(["update:checked", "edit", "evidence"]);
const filter = ref("all"),
  page = ref(0);
const rows = computed(() => {
  const conflicts = new Map<string, DraftConflict[]>();
  for (const conflict of props.conflicts) {
    for (const id of conflict.event_ids) {
      conflicts.set(id, [...(conflicts.get(id) || []), conflict]);
    }
  }
  return props.entries.map((event, index) => {
    const related = conflicts.get(event.id) || [];
    const missing = [
      !event.date && "日期待补全",
      !event.all_day &&
        !event.start &&
        "时间未注明：导出前需补全或明确设为全天",
      !event.all_day &&
        event.start &&
        !event.end &&
        "仅有开始时间：可导出，不补写结束时长",
      !event.location && "地点未注明",
    ].filter(Boolean) as string[];
    const pending = event.status === "pending";
    const warnings = event.warnings || [];
    const severity = pending
      ? 5
      : related.some((c) => c.kind === "definite")
        ? 4
        : related.length
          ? 3
          : !event.date || (!event.all_day && !event.start)
            ? 2
            : missing.length || warnings.length
              ? 1
              : 0;
    return { event, index, related, missing, pending, warnings, severity };
  });
});
const counts = computed(() => ({
  attention: rows.value.filter((r) => r.severity).length,
  pending: rows.value.filter((r) => r.pending).length,
  conflicts: rows.value.filter((r) => r.related.length).length,
  missing: rows.value.filter((r) => r.missing.length).length,
}));
const visible = computed(() =>
  rows.value
    .filter(
      (r) =>
        filter.value === "all" ||
        (filter.value === "attention" && r.severity > 0) ||
        (filter.value === "pending" && r.pending) ||
        (filter.value === "conflicts" && r.related.length > 0) ||
        (filter.value === "missing" && r.missing.length > 0),
    )
    .sort((a, b) => b.severity - a.severity || a.index - b.index),
);
watch(
  [filter, () => props.entries, () => props.conflicts],
  () => (page.value = 0),
);
function toggle(index: number, selected: boolean) {
  emit(
    "update:checked",
    selected
      ? [...props.checked.filter((i) => i !== index), index]
      : props.checked.filter((i) => i !== index),
  );
}
function toggleRange(selected: boolean) {
  const indexes = new Set(visible.value.map((r) => r.index));
  emit(
    "update:checked",
    selected
      ? [...new Set([...props.checked, ...indexes])]
      : props.checked.filter((i) => !indexes.has(i)),
  );
}
function partners(conflict: DraftConflict, id: string) {
  return props.entries.filter(
    (e) => e.id !== id && conflict.event_ids.includes(e.id),
  );
}
</script>
<template>
  <div class="review-counts" aria-label="核对概况" aria-live="polite">
    <span>{{ entries.length }} 项提取结果</span>
    <span>{{ counts.pending }} 项待确认</span>
    <span>{{ counts.conflicts }} 项涉及冲突</span>
    <span>{{ counts.missing }} 项信息未完整</span>
  </div>
  <div class="draft-summary">
    <label class="check"
      ><input
        type="checkbox"
        :checked="
          visible.length > 0 && visible.every((r) => checked.includes(r.index))
        "
        :indeterminate="
          visible.some((r) => checked.includes(r.index)) &&
          !visible.every((r) => checked.includes(r.index))
        "
        @change="toggleRange(($event.target as HTMLInputElement).checked)"
      />选择筛选结果（{{ visible.length }} 项）</label
    >
    <label
      >核对范围<select v-model="filter" aria-label="核对范围">
        <option value="all">全部，需留意的优先</option>
        <option value="attention">需留意（{{ counts.attention }}）</option>
        <option value="pending">待确认（{{ counts.pending }}）</option>
        <option value="conflicts">有冲突（{{ counts.conflicts }}）</option>
        <option value="missing">信息未完整（{{ counts.missing }}）</option>
      </select></label
    >
  </div>
  <p class="muted review-hint">
    缺少地点或结束时间仍可保存；待确认项不会导出。各类数量可能重叠。
  </p>
  <div class="draft-list">
    <article
      v-for="{
        event,
        index,
        related,
        missing,
        pending,
        warnings,
      } in visible.slice(page * 50, (page + 1) * 50)"
      :key="index"
      class="event-row"
      :class="{ 'needs-review': pending || related.length }"
    >
      <input
        type="checkbox"
        :checked="checked.includes(index)"
        :aria-label="'选择 ' + event.title"
        @change="toggle(index, ($event.target as HTMLInputElement).checked)"
      />
      <div class="event-body">
        <div class="event-date">
          {{ event.date || "日期待确认" }}
          <span v-if="pending" class="badge warning">待确认</span>
          <span v-if="related.length" class="badge warning">{{
            related.some((c) => c.kind === "definite") ? "时间冲突" : "可能重叠"
          }}</span>
          <span v-if="missing.length" class="badge soft">信息未完整</span>
        </div>
        <h3>{{ event.title }}</h3>
        <p>
          {{ event.all_day ? "全天" : event.start || "时间未注明"
          }}{{ event.end ? " — " + event.end : "" }}
          <span v-if="event.end_date && event.end_date !== event.date"
            >（结束于 {{ event.end_date }}）</span
          >
        </p>
        <small v-if="event.location">{{ event.location }}</small>
        <p v-for="item in missing" :key="item" class="field-missing">
          {{ item }}
        </p>
        <p v-for="warning in warnings" :key="warning" class="field-warning">
          {{ warning }}
        </p>
        <div v-for="(conflict, c) in related" :key="c" class="draft-conflict">
          <p>{{ conflict.message }}</p>
          <button
            v-for="other in partners(conflict, event.id)"
            :key="other.id"
            class="text-button"
            @click="emit('evidence', other)"
          >
            查看冲突项原文：{{ other.date }} {{ other.title }} {{ other.start }}
          </button>
        </div>
        <div class="draft-actions">
          <button class="text-button" @click="emit('edit', index)">修正</button>
          <button
            v-if="event.sources?.length"
            class="text-button"
            @click="emit('evidence', event, 0)"
          >
            查看原文
          </button>
          <small v-else class="muted">由个人规则或手动创建</small>
        </div>
        <small v-if="event.sources?.length" class="source-caption">
          {{ event.sources[0]!.filename }} · {{ event.sources[0]!.sheet }} ·
          {{ event.sources[0]!.name_cell }}
        </small>
        <details v-if="event.sources?.length > 1" class="other-evidence">
          <summary>另有 {{ event.sources.length - 1 }} 处原文</summary>
          <button
            v-for="(source, i) in event.sources.slice(1)"
            :key="i"
            class="text-button"
            @click="emit('evidence', event, i + 1)"
          >
            {{ source.filename }} · {{ source.sheet }} · {{ source.name_cell }}
          </button>
        </details>
      </div>
    </article>
  </div>
  <p v-if="!visible.length" class="muted">当前范围没有待核对项。</p>
  <div v-if="visible.length > 50" class="pagination">
    <button @click="page--" :disabled="page === 0">上一页</button>
    <span>{{ page + 1 }} / {{ Math.ceil(visible.length / 50) }}</span>
    <button @click="page++" :disabled="(page + 1) * 50 >= visible.length">
      下一页
    </button>
  </div>
</template>
