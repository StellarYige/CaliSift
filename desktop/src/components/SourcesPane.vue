<script setup lang="ts">
import { ref } from "vue";
import { call } from "../bridge";
import { useActions } from "../actions";
import ChangePreview from "./ChangePreview.vue";
const props = defineProps<{ workspace: any }>(),
  emit = defineEmits(["rules", "import", "refresh"]);
const { run, busy, notify } = useActions(),
  preview = ref<any>(null);
</script>
<template>
  <section class="page-stack">
    <div class="page-heading">
      <div>
        <p class="eyebrow">每份安排，保留清楚的来处</p>
        <h1>来源与历史</h1>
        <p class="muted">保存最近三个导入版本，个人修正独立保留。</p>
      </div>
      <div class="button-row">
        <button
          v-if="workspace.can_undo"
          class="secondary"
          @click="
            run(async () => {
              preview = await call('preview_change', {
                workspace_id: workspace.id,
                expected_version: workspace.version,
                operation: { type: 'undo' },
              });
            })
          "
        >
          撤销最近来源更新</button
        ><button class="primary" @click="emit('import')">导入新版文件</button>
      </div>
    </div>
    <div v-if="!workspace.sources.length" class="card empty">
      <span class="empty-star">✦</span>
      <h2>还没有来源</h2>
      <p>导入排班、课程或培训文件后，版本会保留在这里。</p>
      <button class="primary" @click="emit('import')">前往导入</button>
    </div>
    <article
      v-for="source in workspace.sources"
      :key="source.id"
      class="card source-card"
    >
      <header class="panel-heading">
        <div>
          <h2>{{ source.name }}</h2>
          <p class="muted">
            {{ source.rules.shifts?.length || 0 }} 个班次规则 ·
            {{ source.rules.template ? "已保存表格模板" : "自动识别布局" }}
          </p>
        </div>
        <button class="secondary" @click="emit('rules', source.id)">
          配置来源规则
        </button>
      </header>
      <div class="revision-list">
        <div
          v-for="(revision, i) in [...source.revisions].reverse()"
          :key="revision.id"
        >
          <span class="revision-dot"></span>
          <div>
            <b>{{ i === 0 ? "当前版本" : "历史版本" }}</b>
            <p>
              {{ revision.imported_at.slice(0, 16).replace("T", " ") }} UTC ·
              {{ revision.count }} 项原始提取
            </p>
            <small>{{
              revision.coverage
                ? revision.coverage.join(" 至 ")
                : "追加导入，没有覆盖取消范围"
            }}</small>
          </div>
        </div>
      </div>
    </article>
    <ChangePreview
      v-if="preview"
      :preview="preview"
      :busy="busy"
      @close="preview = null"
      @commit="
        run(async () => {
          await call('commit_change', {
            preview_id: preview.preview_id,
            expected_version: preview.base_version,
          });
          preview = null;
          emit('refresh');
          notify('最近来源更新已撤销');
        })
      "
    />
  </section>
</template>
