<script setup lang="ts">
import { computed, ref } from "vue";
const props = defineProps<{ preview: any }>();
const emit = defineEmits(["preview"]);
const mappings = defineModel<Record<string, string>>("mappings", {
  required: true,
});
const cancellations = defineModel<string[]>("cancellations", {
  required: true,
});
const corrections = defineModel<Record<string, string>>("corrections", {
  required: true,
});
const search = ref("");
const candidates = computed(() =>
  props.preview.old_candidates
    .filter((e: any) => `${e.date} ${e.title}`.includes(search.value))
    .slice(0, 200),
);
</script>
<template>
  <section class="card update-matching">
    <h2>核对新版与旧安排</h2>
    <p class="muted">
      只有你明确选定的旧安排会作为变更对应；完全相同的记录已自动对应。
    </p>
    <input
      v-model="search"
      placeholder="按旧事项或日期筛选候选（最多显示 200 项）"
    />
    <div
      v-for="added in preview.summary.added"
      :key="added.draft_index"
      class="mapping-row"
    >
      <span>{{ added.date }} {{ added.title }} {{ added.start }}</span
      ><select v-model="mappings[String(added.draft_index)]">
        <option value="">作为新增安排</option>
        <option v-for="old in candidates" :key="old.id" :value="old.id">
          {{ old.date }} {{ old.title }} {{ old.start }}
        </option>
      </select>
    </div>
    <label
      v-for="old in preview.summary.cancelled"
      :key="old.id"
      class="check cancellation"
      ><input
        type="checkbox"
        v-model="cancellations"
        :value="old.id"
      />确认取消：{{ old.date }} {{ old.title }} {{ old.start }}</label
    >
    <div
      v-for="conflict in preview.summary.correction_conflicts"
      :key="conflict.id"
      class="mapping-row"
    >
      <span>个人修正与新版冲突：{{ conflict.fields.join("、") }}</span
      ><select v-model="corrections[conflict.id]">
        <option value="">请选择</option>
        <option value="keep">保留个人修正</option>
        <option value="new">采用新版</option>
      </select>
    </div>
    <button class="primary" @click="emit('preview')">重新预览</button>
  </section>
</template>
