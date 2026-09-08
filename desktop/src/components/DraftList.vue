<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { DraftEvent } from "../types";
const props = defineProps<{ entries: DraftEvent[]; checked: number[] }>();
const emit = defineEmits(["update:checked", "edit", "evidence"]);
const onlyPending = ref(false),
  page = ref(0);
const visible = computed(() =>
  props.entries
    .map((event, index) => ({ event, index }))
    .filter((v) => !onlyPending.value || v.event.status === "pending")
    .sort(
      (a, b) =>
        Number(b.event.status === "pending") -
        Number(a.event.status === "pending"),
    ),
);
watch([onlyPending, () => props.entries], () => (page.value = 0));
function toggle(index: number, selected: boolean) {
  emit(
    "update:checked",
    selected
      ? [...props.checked.filter((i) => i !== index), index]
      : props.checked.filter((i) => i !== index),
  );
}
</script>
<template>
  <div class="draft-summary">
    <label class="check"
      ><input
        type="checkbox"
        :checked="
          visible.length > 0 && visible.every((v) => checked.includes(v.index))
        "
        @change="
          emit(
            'update:checked',
            ($event.target as HTMLInputElement).checked
              ? visible.map((v) => v.index)
              : [],
          )
        "
      />选择当前范围</label
    ><label class="check"
      ><input type="checkbox" v-model="onlyPending" />只看待确认</label
    >
  </div>
  <p class="muted">
    {{ entries.length }} 项提取结果 ·
    {{ entries.filter((e) => e.status === "pending").length }} 项待确认
  </p>
  <div class="draft-list">
    <article
      v-for="{ event, index } in visible.slice(page * 50, (page + 1) * 50)"
      :key="index"
      class="event-row"
    >
      <input
        type="checkbox"
        :checked="checked.includes(index)"
        :aria-label="'选择 ' + event.title"
        @change="toggle(index, ($event.target as HTMLInputElement).checked)"
      />
      <div class="event-body" @click="emit('evidence', event)">
        <div class="event-date">
          {{ event.date || "日期待确认" }}
          <span v-if="event.status === 'pending'" class="badge warning"
            >待确认</span
          >
        </div>
        <h3>{{ event.title }}</h3>
        <p>
          {{ event.all_day ? "全天" : event.start || "时间未注明"
          }}{{ event.end ? " — " + event.end : ""
          }}<span v-if="event.end_date && event.end_date !== event.date"
            >（次日）</span
          >
        </p>
        <small>{{ event.location || "地点未注明" }}</small>
        <p
          v-for="warning in event.warnings"
          :key="warning"
          class="field-warning"
        >
          {{ warning }}
        </p>
      </div>
      <button class="text-button" @click="emit('edit', index)">修正</button>
    </article>
  </div>
  <p v-if="!visible.length" class="muted">当前范围没有待核对项。</p>
  <div v-if="visible.length > 50" class="pagination">
    <button @click="page--" :disabled="page === 0">上一页</button
    ><span>{{ page + 1 }} / {{ Math.ceil(visible.length / 50) }}</span
    ><button @click="page++" :disabled="(page + 1) * 50 >= visible.length">
      下一页
    </button>
  </div>
</template>
