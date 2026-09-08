<script setup lang="ts">
import { ref, watch, computed, onUnmounted } from "vue";
import { call } from "../bridge";
import { useActions } from "../actions";
import EventForm from "./EventForm.vue";
import Modal from "./Modal.vue";
import ChangePreview from "./ChangePreview.vue";
const props = defineProps<{ workspace: any }>(),
  emit = defineEmits(["refresh", "export"]);
const { run, busy, notify } = useActions();
const result = ref<any>({ items: [], total: 0, page: 0, conflicts: 0 }),
  query = ref(""),
  source = ref(""),
  category = ref(""),
  view = ref("active"),
  from = ref(""),
  to = ref(""),
  display = ref("list"),
  month = ref(new Date().toISOString().slice(0, 7));
const editing = ref<any>(null),
  selected = ref<any>(null),
  preview = ref<any>(null),
  evidence = ref(""),
  evidenceInfo = ref<any>(null),
  monthEvents = ref<any[]>([]),
  archive = ref(false),
  archiveBefore = ref(new Date().toISOString().slice(0, 10));
let timer: ReturnType<typeof setTimeout> | undefined,
  seq = 0;
async function refresh(page = 0) {
  const s = ++seq;
  const p = {
    workspace_id: props.workspace.id,
    query: query.value,
    source_id: source.value,
    category: category.value,
    view: view.value,
    date_from: from.value,
    date_to: to.value,
    page,
  };
  const next = await call("events", p);
  if (s === seq) result.value = next;
  if (display.value === "month") await loadMonth();
}
async function loadMonth() {
  const first = month.value + "-01",
    next = new Date(first + "T00:00:00Z");
  next.setUTCMonth(next.getUTCMonth() + 1);
  next.setUTCDate(0);
  let items: any[] = [];
  for (let page = 0; page < 100; page++) {
    const data = await call("events", {
      workspace_id: props.workspace.id,
      query: query.value,
      source_id: source.value,
      category: category.value,
      view: view.value,
      date_from: first,
      date_to: next.toISOString().slice(0, 10),
      page,
    });
    items.push(...data.items);
    if (items.length >= data.total) break;
  }
  monthEvents.value = items;
}
const cells = computed(() => {
  const first = new Date(month.value + "-01T00:00:00Z");
  const offset =
    (first.getUTCDay() - (props.workspace.settings.week_start ?? 1) + 7) % 7;
  return Array.from({ length: 42 }, (_, i) => {
    const day = new Date(first);
    day.setUTCDate(i - offset + 1);
    const iso = day.toISOString().slice(0, 10);
    return {
      date: iso,
      day: day.getUTCDate(),
      active: iso.startsWith(month.value),
      events: monthEvents.value.filter(
        (e) => e.date <= iso && (e.end_date || e.date) >= iso,
      ),
    };
  });
});
async function makePreview(operation: any) {
  preview.value = await call("preview_change", {
    workspace_id: props.workspace.id,
    expected_version: props.workspace.version,
    operation,
  });
}
async function save(values: any) {
  await run(async () => {
    const candidate = await call("preview_change", {
      workspace_id: props.workspace.id,
      expected_version: props.workspace.version,
      operation: selected.value
        ? { type: "edit", event_id: selected.value.id, values }
        : { type: "manual", values },
    });
    const output = await call("commit_change", {
      preview_id: candidate.preview_id,
      expected_version: candidate.base_version,
    });
    editing.value = null;
    emit("refresh");
    await refresh(result.value.page);
    notify(output.warning || "安排已保存");
  });
}
async function commit() {
  await run(async () => {
    const output = await call("commit_change", {
      preview_id: preview.value.preview_id,
      expected_version: preview.value.base_version,
    });
    preview.value = null;
    archive.value = false;
    emit("refresh");
    await refresh(result.value.page);
    notify(output.warning || "变化已保存");
  });
}
async function showEvidence(event: any) {
  await run(async () => {
    evidenceInfo.value = event;
    evidence.value = "";
    const image = event.sources.find((s: any) => s.evidence?.image)?.evidence
      .image;
    if (image) evidence.value = await call("evidence", { id: image });
  });
}
function newEvent() {
  selected.value = null;
  editing.value = {
    date: new Date().toISOString().slice(0, 10),
    title: "",
    start: null,
    end: null,
    location: "",
    category: "其他",
    status: "confirmed",
    notes: [],
    sources: [],
  };
}
function edit(event: any) {
  selected.value = event;
  editing.value = event;
}
watch([query, source, category, view, from, to], () => {
  if (timer) clearTimeout(timer);
  timer = setTimeout(() => run(() => refresh()), 200);
});
watch(
  () => props.workspace.version,
  () => run(() => refresh()),
  { immediate: true },
);
onUnmounted(() => {
  if (timer) clearTimeout(timer);
  seq++;
});
watch([month, display], () => {
  if (display.value === "month") run(loadMonth);
});
</script>
<template>
  <section class="page-stack">
    <div class="button-row">
      <button class="primary" @click="emit('export')">
        导出日历 / 查看导出记录
      </button>
    </div>
    <div class="page-heading">
      <div>
        <p class="eyebrow">核对日期，找回每条安排的来处</p>
        <h1>安排预览</h1>
        <p class="muted">
          共 {{ result.total }} 项安排<span v-if="result.conflicts">
            · {{ result.conflicts }} 组时间冲突</span
          >
        </p>
      </div>
      <div class="button-row">
        <button class="secondary" @click="archive = true">归档旧安排</button
        ><button class="primary" @click="newEvent">＋ 手动新增</button>
      </div>
    </div>
    <div class="card filters">
      <input
        v-model="query"
        type="search"
        placeholder="搜索事项、地点、日期或来源"
        aria-label="搜索安排"
      /><select v-model="source" aria-label="来源">
        <option value="">全部来源</option>
        <option v-for="s in workspace.sources" :key="s.id" :value="s.id">
          {{ s.name }}
        </option></select
      ><select v-model="category" aria-label="分类">
        <option value="">全部分类</option>
        <option
          v-for="category in workspace.settings.categories"
          :key="category.name"
        >
          {{ category.name }}
        </option></select
      ><select v-model="view" aria-label="显示范围">
        <option value="active">当前安排</option>
        <option value="hidden">已隐藏</option>
        <option value="archived">已归档</option>
        <option value="all">含隐藏和取消</option></select
      ><input type="date" v-model="from" aria-label="开始日期" /><span>—</span
      ><input type="date" v-model="to" aria-label="结束日期" />
      <div class="segmented">
        <button
          :class="{ active: display === 'list' }"
          @click="display = 'list'"
        >
          时间线</button
        ><button
          :class="{ active: display === 'month' }"
          @click="display = 'month'"
        >
          月历
        </button>
      </div>
    </div>
    <div v-if="display === 'list'" class="card">
      <div v-if="!result.items.length" class="empty">
        <span class="empty-star">✦</span>
        <h2>这里暂时没有安排</h2>
        <p>调整筛选条件，或从导入工作台加入文件。</p>
      </div>
      <article
        v-for="event in result.items"
        :key="event.id"
        class="event-row calendar-event"
      >
        <div class="date-block">
          <b>{{ event.date?.slice(8) || "?" }}</b
          ><small>{{ event.date?.slice(0, 7) || "日期待确认" }}</small>
        </div>
        <div class="event-body">
          <div class="button-row">
            <h3>{{ event.title }}</h3>
            <span v-if="event.status === 'pending'" class="badge warning"
              >待确认</span
            ><span v-if="event.conflict" class="badge warning">时间冲突</span
            ><span v-if="event.cancelled" class="badge">来源已取消</span
            ><span v-if="event.archived" class="badge">已归档</span>
          </div>
          <p>
            {{ event.all_day ? "全天" : event.start || "时间未注明"
            }}{{ event.end ? " — " + event.end : "" }}
            <span v-if="event.end_date && event.end_date !== event.date"
              >（次日结束）</span
            >
            · {{ event.location || "地点未注明" }}
          </p>
          <small
            ><span
              class="category-dot"
              :style="{
                background:
                  workspace.settings.colors?.[event.category] || '#8876c6',
              }"
            ></span
            >{{ event.category }} ·
            {{ event.source_names.join("、") || "手动新增" }}</small
          >
        </div>
        <div class="row-actions">
          <button class="text-button" @click="showEvidence(event)">依据</button
          ><button class="text-button" @click="edit(event)">修改</button
          ><button
            class="text-button"
            v-if="event.archived"
            @click="
              run(() =>
                makePreview({
                  type: 'archive',
                  restore: true,
                  event_ids: [event.id],
                }),
              )
            "
          >
            恢复归档</button
          ><button
            class="text-button"
            v-else
            @click="
              run(() =>
                makePreview({
                  type: event.hidden ? 'restore' : 'hide',
                  event_id: event.id,
                }),
              )
            "
          >
            {{ event.hidden ? "恢复" : "隐藏" }}
          </button>
        </div>
      </article>
      <div v-if="result.total > 50" class="pagination">
        <button
          @click="run(() => refresh(result.page - 1))"
          :disabled="!result.page"
        >
          上一页</button
        ><span>{{ result.page + 1 }} / {{ Math.ceil(result.total / 50) }}</span
        ><button
          @click="run(() => refresh(result.page + 1))"
          :disabled="(result.page + 1) * 50 >= result.total"
        >
          下一页
        </button>
      </div>
    </div>
    <div v-else class="card">
      <div class="panel-heading">
        <h2>按月核对</h2>
        <input v-model="month" type="month" aria-label="月份" />
      </div>
      <div class="month-week">
        <span
          v-for="day in workspace.settings.week_start === 0
            ? ['日', '一', '二', '三', '四', '五', '六']
            : ['一', '二', '三', '四', '五', '六', '日']"
          :key="day"
          >星期{{ day }}</span
        >
      </div>
      <div class="month-grid">
        <div
          v-for="cell in cells"
          :key="cell.date"
          class="month-cell"
          :class="{ inactive: !cell.active }"
        >
          <b>{{ cell.day }}</b
          ><button
            v-for="event in cell.events.slice(0, 3)"
            :key="event.id"
            @click="edit(event)"
            :title="event.title"
          >
            {{ event.start }} {{ event.title }}</button
          ><button
            v-if="cell.events.length > 3"
            @click="
              from = cell.date;
              to = cell.date;
              display = 'list';
            "
          >
            另有 {{ cell.events.length - 3 }} 项
          </button>
        </div>
      </div>
    </div>
    <Modal
      v-if="editing"
      :title="selected ? '修改个人安排' : '手动新增安排'"
      @close="editing = null"
      ><EventForm :event="editing" @save="save" @cancel="editing = null"
    /></Modal>
    <Modal
      v-if="evidenceInfo"
      title="这条安排的依据"
      wide
      @close="evidenceInfo = null"
      ><h3>{{ evidenceInfo.date }} {{ evidenceInfo.title }}</h3>
      <img v-if="evidence" :src="evidence" class="ocr-overview" />
      <div
        v-for="(source, i) in evidenceInfo.sources"
        :key="i"
        class="evidence-detail"
      >
        <b
          >{{ source.filename }} · {{ source.sheet }} ·
          {{ source.name_cell }}</b
        >
        <p>{{ source.excerpt }}</p>
        <dl>
          <template v-for="(value, key) in source.evidence" :key="key"
            ><dt v-if="key !== 'image'">{{ key }}</dt>
            <dd v-if="key !== 'image'">{{ value }}</dd></template
          >
        </dl>
      </div>
      <p v-if="!evidenceInfo.sources.length" class="muted">
        这条安排由你手动建立。
      </p>
      <h3>字段依据</h3>
      <dl>
        <template v-for="(value, key) in evidenceInfo.field_basis" :key="key"
          ><dt>{{ key }}</dt>
          <dd>{{ value }}</dd></template
        >
      </dl>
      <h3>修正历史</h3>
      <div v-for="(review, i) in evidenceInfo.reviews" :key="i" class="notice">
        <b>{{ review.edited_at }}</b>
        <p>
          修改前：{{ review.before.date }} {{ review.before.title }}
          {{ review.before.start }} {{ review.before.location }}
        </p>
      </div>
      <p v-if="!evidenceInfo.reviews?.length" class="muted">
        暂无个人修正。
      </p></Modal
    >
    <Modal v-if="archive" title="归档旧安排" @close="archive = false"
      ><p>归档后可在“已归档”中查询和恢复。跨夜安排按实际结束日期筛选。</p>
      <label
        >归档此日期之前结束的安排<input
          v-model="archiveBefore"
          type="date" /></label
      ><template #footer
        ><button class="secondary" @click="archive = false">取消</button
        ><button
          class="primary"
          @click="
            run(async () => {
              await makePreview({ type: 'archive', before: archiveBefore });
              archive = false;
            })
          "
        >
          预览归档范围
        </button></template
      ></Modal
    >
    <ChangePreview
      v-if="preview"
      :preview="preview"
      :busy="busy"
      @close="preview = null"
      @commit="commit"
    />
  </section>
</template>
