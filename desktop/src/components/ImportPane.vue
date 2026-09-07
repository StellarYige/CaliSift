<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from "vue";
import { call } from "../bridge";
import { useActions } from "../actions";
import Modal from "./Modal.vue";
import EventForm from "./EventForm.vue";
import CropImage from "./CropImage.vue";
import ChangePreview from "./ChangePreview.vue";
const props = defineProps<{ workspace: any; jobId?: string }>();
const emit = defineEmits(["refresh", "job"]);
const { run, busy, notify } = useActions();
const job = ref<any>(null),
  jobs = ref<any[]>([]),
  templates = ref<any[]>([]),
  templateId = ref(""),
  sourceId = ref(""),
  sourceName = ref(""),
  mode = ref("append"),
  year = ref(new Date().getFullYear());
const from = ref(""),
  to = ref(""),
  selected = ref(""),
  table = ref<any>(null),
  sheetIndex = ref(0),
  image = ref(""),
  ocr = ref<any>({}),
  ocrEdits = ref<Record<string, string>>({}),
  imageOptions = ref<Record<string, any>>({}),
  showOcr = ref(false);
const preview = ref<any>(null),
  showPreview = ref(false),
  editing = ref<any>(null),
  editIndex = ref(0),
  page = ref(0),
  checked = ref<number[]>([]),
  batch = ref(false),
  batchDate = ref(""),
  batchStart = ref(""),
  batchEnd = ref(""),
  batchPlace = ref(""),
  batchCategory = ref(""),
  batchPreview = ref<any[]>([]);
const mappings = ref<Record<string, string>>({}),
  cancellations = ref<string[]>([]),
  corrections = ref<Record<string, string>>({}),
  oldSearch = ref(""),
  locate = ref<string[]>([]);
const evidenceImage = ref("");
const mappingOpen = ref(false),
  mapField = ref("header"),
  mapLayout = ref("records"),
  headerRow = ref(0),
  mapValues = ref<Record<string, number>>({
    name: 0,
    date: 1,
    title: 2,
    time: 3,
  }),
  mapName = ref(""),
  mapHeaders = ref<string[]>([]),
  localRules = ref<any>(null);
const currentFile = computed(() =>
  job.value?.files.find((f: any) => f.id === selected.value),
);
const entries = computed<any[]>(() => [
  ...(job.value?.report?.events || []),
  ...(job.value?.report?.pending || []),
]);
const running = computed(() =>
  ["queued", "running"].includes(job.value?.status),
);
const rules = computed(
  () =>
    localRules.value ||
    templates.value.find((t) => t.id === templateId.value)?.rules ||
    props.workspace.sources.find((s: any) => s.id === sourceId.value)?.rules ||
    {},
);
const candidates = computed(() =>
  ((preview.value?.old_candidates || []) as any[])
    .filter((e) => `${e.date} ${e.title}`.includes(oldSearch.value))
    .slice(0, 200),
);
const statusLabel: Record<string, string> = {
  ready: "待识别",
  queued: "排队中",
  running: "识别中",
  done: "已提取",
  error: "失败",
  review: "待核对",
  paused: "已暂停",
  cancelled: "已取消",
  committed: "已保存",
  discarded: "已丢弃",
};
let timer: ReturnType<typeof setInterval> | undefined,
  polling = false,
  sequence = 0;
async function refreshJobs() {
  jobs.value = await call("list_jobs", { workspace_id: props.workspace.id });
  templates.value = await call("templates");
}
async function accept(value: any) {
  if (!value || value.workspace_id !== props.workspace.id) return;
  imageOptions.value = Object.fromEntries(
    value.files.map((f: any) => [f.id, f.options || {}]),
  );
  localRules.value = value.rules;
  templateId.value = "";
  job.value = value;
  year.value = value.year;
  sourceId.value = value.source_id || "";
  sourceName.value =
    value.files
      .map((f: any) => f.filename.replace(/\.[^.]+$/, ""))
      .join("、")
      .slice(0, 100) || "课程安排";
  selected.value = value.files[0]?.id || "";
  preview.value = null;
  page.value = 0;
  checked.value = [];
  emit("job", value.id);
  await loadFile();
  localRules.value = Object.keys(value.rules || {}).length ? value.rules : null;
  await refreshJobs();
}
async function choose(kind: string) {
  await run(async () =>
    accept(await call(kind, { workspace_id: props.workspace.id })),
  );
}
async function resume(id: string) {
  await run(async () => accept(await call("get_job", { job_id: id })));
}
async function loadFile() {
  const seq = ++sequence;
  table.value = null;
  image.value = "";
  ocr.value = {};
  ocrEdits.value = {};
  locate.value = [];
  evidenceImage.value = "";
  if (!currentFile.value || job.value.status === "committed") return;
  if ([".png", ".jpg", ".jpeg"].includes(currentFile.value.suffix)) {
    const value = await call("image_preview", {
      job_id: job.value.id,
      file_id: selected.value,
    });
    if (seq !== sequence) return;
    image.value = value;
    const details = await call("ocr_details", {
      job_id: job.value.id,
      file_id: selected.value,
    });
    if (seq === sequence) {
      ocr.value = details;
      ocrEdits.value = Object.fromEntries(
        (details.blocks || []).map((b: any) => [b.id, b.text]),
      );
    }
  } else {
    const value = await call("table", {
      job_id: job.value.id,
      file_id: selected.value,
    });
    if (seq === sequence) table.value = value;
  }
}
async function tablePage(row: number, col: number, sheet = sheetIndex.value) {
  table.value = await call("table", {
    job_id: job.value.id,
    file_id: selected.value,
    row,
    col,
    sheet,
  });
  sheetIndex.value = sheet;
}
async function start(retry?: string[]) {
  await run(async () => {
    preview.value = null;
    showPreview.value = false;
    const options = { ...imageOptions.value };
    if (showOcr.value && selected.value) {
      options[selected.value] = {
        ...(options[selected.value] || {}),
        corrections: ocrEdits.value,
      };
      showOcr.value = false;
    }
    job.value = await call("start_job", {
      job_id: job.value.id,
      year: year.value,
      rules: rules.value,
      source_id: sourceId.value,
      retry_ids: retry,
      options,
    });
    checked.value = [];
  });
}
async function poll() {
  if (!running.value || polling) return;
  polling = true;
  try {
    const previous = job.value.status;
    job.value = await call("get_job", { job_id: job.value.id });
    if (previous !== job.value.status && !running.value) {
      await loadFile();
      await refreshJobs();
    }
  } catch (e: any) {
    notify(e.message, true);
  } finally {
    polling = false;
  }
}
function operation() {
  return {
    type: mode.value,
    source_id: sourceId.value || undefined,
    source_name: sourceName.value,
    coverage: mode.value === "update" ? [from.value, to.value] : undefined,
    mappings: Object.fromEntries(
      Object.entries(mappings.value).filter(([, v]) => v),
    ),
    cancel_ids: cancellations.value,
    correction_choices: corrections.value,
  };
}
async function makePreview() {
  await run(async () => {
    preview.value = await call("preview_change", {
      workspace_id: props.workspace.id,
      expected_version: props.workspace.version,
      job_id: job.value.id,
      operation: operation(),
    });
    showPreview.value = preview.value.summary.unresolved.length === 0;
    if (!showPreview.value) notify("请在下方处理新旧对应和取消项，再重新预览");
  });
}
async function commit() {
  await run(async () => {
    const value = await call("commit_change", {
      preview_id: preview.value.preview_id,
      expected_version: preview.value.base_version,
    });
    showPreview.value = false;
    preview.value = null;
    job.value = await call("get_job", { job_id: job.value.id });
    emit("refresh");
    await refreshJobs();
    notify(value.warning || "安排已保存到本机日历");
  });
}
async function saveDraft(values: any) {
  await run(async () => {
    job.value = await call("edit_draft", {
      job_id: job.value.id,
      edits: [{ index: editIndex.value, values }],
    });
    editing.value = null;
    preview.value = null;
    checked.value = [];
    notify("修正已保留在草稿中，确认导入后加入日历");
  });
}
async function showEvidence(entry: any) {
  await run(async () => {
    const source = entry.sources?.[0];
    if (!source) return;
    const file = job.value.files.find(
      (f: any) => f.filename === source.filename,
    );
    if (!file) return;
    selected.value = file.id;
    await loadFile();
    if (source.evidence?.image)
      evidenceImage.value = await call("evidence", {
        id: source.evidence.image,
      });
    const refs = [
      source.name_cell,
      ...Object.values(source.evidence || {}).flatMap(
        (v: any) => String(v).match(/[A-Z]+\d+/g) || [],
      ),
    ];
    locate.value = refs;
    const match = String(source.name_cell).match(/([A-Z]+)(\d+)/);
    if (match && table.value) {
      let col = 0;
      for (const c of match[1]) col = col * 26 + c.charCodeAt(0) - 64;
      const si = table.value.sheets.findIndex(
        (s: any) => s.name === source.sheet,
      );
      await tablePage(
        Math.floor((Number(match[2]) - 1) / 50) * 50,
        Math.floor((col - 1) / 20) * 20,
        Math.max(0, si),
      );
    }
  });
}
async function mapCell(cell: any) {
  if (!mappingOpen.value) return;
  if (mapField.value === "header") {
    await run(async () => {
      const value = await call("table", {
        job_id: job.value.id,
        file_id: selected.value,
        sheet: sheetIndex.value,
        header_row: cell.row,
      });
      headerRow.value = cell.row;
      mapHeaders.value = value.headers;
    });
  } else {
    mapValues.value[mapField.value] =
      (mapLayout.value === "names_columns" && mapField.value === "name") ||
      (mapLayout.value === "names_rows" && mapField.value === "date")
        ? cell.row
        : cell.col;
  }
}
async function saveMapping() {
  await run(async () => {
    if (!mapHeaders.value.length) throw Error("请先点击表头行");
    const mapping = { ...mapValues.value };
    const config = {
      ...rules.value,
      template: {
        layout: mapLayout.value,
        sheet: table.value.sheet,
        header_row: headerRow.value,
        headers: mapHeaders.value,
        mapping,
      },
    };
    const t = await call("save_template", {
      name: mapName.value || sourceName.value || "我的表格模板",
      rules: config,
      description: "本机校对的表格布局",
    });
    templates.value = await call("templates");
    templateId.value = t.id;
    localRules.value = config;
    mappingOpen.value = false;
    notify("模板已保存，请重新识别以应用布局");
  });
}
function previewBatch() {
  if (!checked.value.length) {
    notify("请先勾选草稿", true);
    return;
  }
  batchPreview.value = checked.value.map((index) => {
    const e = entries.value[index],
      values: any = {};
    if (batchDate.value) values.date = batchDate.value;
    if (batchPlace.value) values.location = batchPlace.value;
    if (batchCategory.value) values.category = batchCategory.value;
    if (batchStart.value) {
      values.start = batchStart.value;
      values.all_day = false;
      values.end = batchEnd.value || null;
      values.precision = batchEnd.value ? "interval" : "point";
      values.end_date = batchEnd.value ? batchDate.value || e.date : null;
    }
    return { index, values, before: e, after: { ...e, ...values } };
  });
}
async function applyBatch() {
  await run(async () => {
    job.value = await call("edit_draft", {
      job_id: job.value.id,
      edits: batchPreview.value.map(({ index, values }) => ({ index, values })),
    });
    batch.value = false;
    batchPreview.value = [];
    checked.value = [];
    preview.value = null;
  });
}
watch(
  [batchDate, batchPlace, batchCategory, batchStart, batchEnd, checked],
  () => {
    batchPreview.value = [];
  },
  { deep: true },
);
watch(
  () => props.jobId,
  (id) => {
    if (id && id !== job.value?.id) resume(id);
  },
  { immediate: true },
);
watch(
  () => props.workspace.id,
  () => {
    job.value = null;
    refreshJobs();
  },
  { immediate: true },
);
watch(sourceId, () => {
  localRules.value = null;
});
watch([mode, sourceId, from, to], () => {
  preview.value = null;
  mappings.value = {};
  cancellations.value = [];
  corrections.value = {};
});
timer = setInterval(poll, 900);
onUnmounted(() => {
  if (timer) clearInterval(timer);
});
defineExpose({ accept, resume });
</script>

<template>
  <section class="page-stack">
    <div class="page-heading">
      <div>
        <p class="eyebrow">属于你的安排，清楚地放在一起</p>
        <h1>导入工作台</h1>
        <p class="muted">把表格交给星程，只看属于你的安排。</p>
      </div>
      <span class="badge soft">本机处理 · 无需上传</span>
    </div>
    <div
      v-if="!job || ['committed', 'discarded'].includes(job.status)"
      class="welcome-grid"
    >
      <div class="drop-card">
        <div class="document-illustration">
          <span>✦</span><i></i><i></i><i></i>
        </div>
        <h2>把分散的安排，带进日历</h2>
        <p>拖入排班表、课表或清晰截图<br />核对后再保存，每条安排都有依据。</p>
        <div class="button-row">
          <button
            class="primary"
            @click="choose('select_files')"
            :disabled="busy"
          >
            选择文件</button
          ><button
            class="secondary"
            @click="choose('paste_image')"
            :disabled="busy"
          >
            粘贴截图
          </button>
        </div>
        <small>XLSX / XLS / CSV / PNG / JPEG · 每批最多 10 份</small>
      </div>
      <aside class="card start-guide">
        <span class="kicker">开始只需要三步</span>
        <ol>
          <li>
            <b>选择你的文件</b>
            <p>表格和截图可以一起整理</p>
          </li>
          <li>
            <b>对照原文核对</b>
            <p>不确定的日期和班次会标出来</p>
          </li>
          <li>
            <b>保存并导出日历</b>
            <p>下次有新版，再清楚地更新</p>
          </li>
        </ol>
        <button class="text-button" @click="choose('sample')">
          用“星辰奕歌”示例试一次 →
        </button>
      </aside>
    </div>
    <template v-else
      ><div class="card import-config">
        <div class="form-grid four">
          <label
            >导入方式<select v-model="mode" :disabled="running">
              <option value="append">追加安排</option>
              <option value="update">更新已有来源</option>
            </select></label
          ><label
            >来源<select v-model="sourceId" :disabled="running">
              <option value="">建立新来源</option>
              <option v-for="s in workspace.sources" :value="s.id" :key="s.id">
                {{ s.name }}
              </option>
            </select></label
          ><label v-if="!sourceId"
            >来源名称<input
              v-model="sourceName"
              :disabled="running"
              maxlength="100" /></label
          ><label
            >缺省年份<input
              v-model.number="year"
              type="number"
              min="1900"
              max="2199"
              :disabled="running" /></label
          ><label
            >可复用模板<select
              v-model="templateId"
              :disabled="running"
              @change="localRules = null"
            >
              <option value="">
                {{ sourceId ? "使用来源规则" : "自动识别布局" }}
              </option>
              <option v-for="t in templates" :key="t.id" :value="t.id">
                {{ t.name }}
              </option>
            </select></label
          ><label v-if="mode === 'update'"
            >覆盖开始日期<input v-model="from" type="date" /></label
          ><label v-if="mode === 'update'"
            >覆盖结束日期<input v-model="to" type="date"
          /></label>
        </div>
        <div class="toolbar">
          <button class="primary" @click="start()" :disabled="busy || running">
            {{ job.report ? "重新识别全部" : "开始识别" }}</button
          ><button
            v-if="running"
            class="secondary"
            @click="
              run(async () => {
                job = await call('cancel_job', { job_id: job.id });
              })
            "
          >
            取消识别</button
          ><span v-if="running" class="processing">正在处理文件，请稍候…</span
          ><span v-else class="muted"
            >重新识别会重建当前草稿；正式日历保持原样。</span
          ><button
            class="text-button push-right"
            @click="
              run(async () => {
                await call('discard_job', { job_id: job.id });
                job = null;
                await refreshJobs();
              })
            "
            :disabled="busy"
          >
            丢弃本次导入
          </button>
        </div>
      </div>
      <div class="file-tabs">
        <button
          v-for="file in job.files"
          :key="file.id"
          :class="{ selected: file.id === selected }"
          @click="
            run(async () => {
              selected = file.id;
              sheetIndex = 0;
              await loadFile();
            })
          "
        >
          <span class="file-type">{{ file.suffix.slice(1).toUpperCase() }}</span
          ><span class="truncate">{{ file.filename }}</span
          ><span class="badge" :class="{ warning: file.status === 'error' }">{{
            statusLabel[file.status]
          }}</span>
        </button>
      </div>
      <div v-if="currentFile?.error" class="notice warning">
        {{ currentFile.error }}
        <button @click="start([currentFile.id])" :disabled="running">
          重试此文件
        </button>
      </div>
      <div class="review-grid">
        <section class="card evidence-panel">
          <header class="panel-heading">
            <h2>原文与依据</h2>
            <button
              v-if="table"
              class="text-button"
              @click="mappingOpen = !mappingOpen"
            >
              {{ mappingOpen ? "关闭布局校正" : "校正表格布局" }}
            </button>
          </header>
          <p v-if="evidenceImage" class="muted">本条安排的局部依据</p>
          <img
            v-if="evidenceImage"
            :src="evidenceImage"
            class="ocr-overview"
          /><template v-if="table"
            ><div v-if="table.template_matches?.length" class="notice">
              <span>表头匹配的模板，请核对后选择：</span
              ><button
                v-for="t in table.template_matches"
                :key="t.id"
                class="text-button"
                :title="t.reason"
                @click="
                  templateId = t.id;
                  localRules = null;
                "
              >
                {{ t.name }}
              </button>
            </div>
            <div class="toolbar compact">
              <select
                :value="sheetIndex"
                @change="
                  run(() =>
                    tablePage(
                      0,
                      0,
                      Number(($event.target as HTMLSelectElement).value),
                    ),
                  )
                "
              >
                <option v-for="(sheet, i) in table.sheets" :value="i" :key="i">
                  {{ sheet.name }}
                </option></select
              ><span class="muted"
                >{{ table.row + 1 }}–{{
                  Math.min(table.row + 50, table.sheets[sheetIndex].height)
                }}
                行</span
              >
            </div>
            <div v-if="mappingOpen" class="mapping-editor">
              <label
                >布局<select v-model="mapLayout">
                  <option value="records">逐行明细表</option>
                  <option value="names_rows">姓名在行，日期在列</option>
                  <option value="names_columns">姓名在列，日期在行</option>
                </select></label
              ><label
                >点击单元格指定<select v-model="mapField">
                  <option value="header">表头行</option>
                  <option value="name">姓名区域</option>
                  <option value="date">日期区域</option>
                  <option value="title">事项列</option>
                  <option value="time">时间列</option>
                </select></label
              >
              <p class="muted">
                表头：第 {{ headerRow + 1 }} 行 · 姓名轴
                {{ mapValues.name + 1 }} · 日期轴 {{ mapValues.date + 1 }}
              </p>
              <input v-model="mapName" placeholder="模板名称" /><button
                class="primary small"
                @click="saveMapping"
              >
                保存模板
              </button>
            </div>
            <div class="table-scroll">
              <table class="source-table">
                <tbody>
                  <tr v-for="(line, i) in table.cells" :key="i">
                    <th>{{ table.row + i + 1 }}</th>
                    <td
                      v-for="cell in line"
                      :key="cell.col"
                      :class="{
                        highlight: locate.includes(cell.coordinate),
                        pickable: mappingOpen,
                      }"
                      @click="mapCell(cell)"
                      :title="cell.coordinate + ' · ' + cell.text"
                    >
                      <span class="cell-coordinate">{{ cell.coordinate }}</span
                      >{{ cell.text || " " }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="pagination">
              <button
                @click="
                  run(() => tablePage(Math.max(0, table.row - 50), table.col))
                "
                :disabled="!table.row"
              >
                ↑ 上 50 行</button
              ><button
                @click="run(() => tablePage(table.row + 50, table.col))"
                :disabled="table.row + 50 >= table.sheets[sheetIndex].height"
              >
                ↓ 下 50 行</button
              ><button
                @click="
                  run(() => tablePage(table.row, Math.max(0, table.col - 20)))
                "
                :disabled="!table.col"
              >
                ←</button
              ><button
                @click="run(() => tablePage(table.row, table.col + 20))"
                :disabled="table.col + 20 >= table.sheets[sheetIndex].width"
              >
                →
              </button>
            </div></template
          >
          <template v-else-if="image"
            ><CropImage
              :src="image"
              :initial="imageOptions[selected] || currentFile.options"
              @change="imageOptions[selected] = $event"
            />
            <div v-if="ocr.blocks?.length" class="toolbar">
              <span class="muted"
                >{{ ocr.blocks.length }} 处文字 ·
                {{ ocr.reliable ? "布局已还原" : "布局待确认" }}</span
              ><button class="secondary small" @click="showOcr = true">
                核对识别文字
              </button>
            </div></template
          >
          <div v-else class="empty small-empty">
            {{
              job.files.length
                ? "选择文件查看原文"
                : "课程由个人规则生成，可在右侧核对实际日期。"
            }}
          </div>
        </section>
        <section class="card draft-panel">
          <header class="panel-heading">
            <h2>
              你的安排 <span class="count">{{ entries.length }}</span>
            </h2>
            <button
              class="text-button"
              @click="batch = true"
              :disabled="!checked.length"
            >
              批量修正 {{ checked.length || "" }}
            </button>
          </header>
          <p v-if="!job.report" class="empty">
            {{
              running
                ? "识别完成后，安排会出现在这里。"
                : "完成裁剪和规则选择后，点击“开始识别”。"
            }}
          </p>
          <template v-else
            ><p v-if="!entries.length" class="notice warning">
              没有提取出本人的安排。请检查姓名是否与原文完全一致，或校正表格布局后重新识别。
            </p>
            <div class="draft-summary">
              <label class="check"
                ><input
                  type="checkbox"
                  :checked="
                    checked.length === entries.length && entries.length > 0
                  "
                  @change="
                    checked =
                      checked.length === entries.length
                        ? []
                        : entries.map((_, i) => i)
                  "
                />选择全部</label
              ><span
                >{{ job.report.events.length }} 项已提取 ·
                {{ job.report.pending.length }} 项待确认</span
              >
            </div>
            <div class="draft-list">
              <article
                v-for="(entry, i) in entries.slice(page * 50, (page + 1) * 50)"
                :key="page * 50 + i"
                class="event-row"
              >
                <input
                  v-model="checked"
                  type="checkbox"
                  :value="page * 50 + i"
                  :aria-label="'选择 ' + entry.title"
                />
                <div class="event-body" @click="showEvidence(entry)">
                  <div class="event-date">
                    {{ entry.date || "日期待确认" }}
                    <span
                      v-if="entry.status === 'pending'"
                      class="badge warning"
                      >待确认</span
                    >
                  </div>
                  <h3>{{ entry.title }}</h3>
                  <p>
                    {{ entry.all_day ? "全天" : entry.start || "时间未注明"
                    }}{{ entry.end ? " — " + entry.end : "" }}
                    <span v-if="entry.end_date && entry.end_date !== entry.date"
                      >（次日）</span
                    >
                  </p>
                  <small>{{ entry.location || "地点未注明" }}</small>
                  <p
                    v-for="warning in entry.warnings"
                    :key="warning"
                    class="field-warning"
                  >
                    {{ warning }}
                  </p>
                </div>
                <button
                  class="text-button"
                  @click="
                    editIndex = page * 50 + i;
                    editing = entry;
                  "
                >
                  修正
                </button>
              </article>
            </div>
            <div class="pagination" v-if="entries.length > 50">
              <button @click="page--" :disabled="page === 0">上一页</button
              ><span>{{ page + 1 }} / {{ Math.ceil(entries.length / 50) }}</span
              ><button
                @click="page++"
                :disabled="(page + 1) * 50 >= entries.length"
              >
                下一页
              </button>
            </div>
            <p
              v-for="warning in job.report.warnings"
              :key="warning"
              class="notice warning"
            >
              {{ warning }}
            </p>
            <div class="button-row panel-footer">
              <button
                class="secondary"
                @click="run(() => call('export_json', { job_id: job.id }))"
              >
                导出提取报告</button
              ><button
                class="primary"
                @click="makePreview"
                :disabled="busy || running"
              >
                预览并加入日历
              </button>
            </div></template
          >
        </section>
      </div>
      <section
        v-if="preview && preview.summary.unresolved.length"
        class="card update-matching"
      >
        <h2>核对新版与旧安排</h2>
        <p class="muted">
          只有你明确选定的旧安排会作为变更对应；完全相同的记录已自动对应。
        </p>
        <input
          v-model="oldSearch"
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
        <button class="primary" @click="makePreview">重新预览</button>
      </section>
    </template>
    <section class="card recent-imports">
      <header class="panel-heading">
        <h2>导入记录</h2>
        <span class="muted">未完成的任务可以继续核对</span>
      </header>
      <div v-if="!jobs.length" class="empty small-empty">
        还没有导入记录，从上方选择第一份文件。
      </div>
      <button
        v-for="item in jobs.slice(0, 15)"
        :key="item.id"
        class="history-row"
        @click="resume(item.id)"
      >
        <span class="file-glyph">▤</span
        ><span class="truncate">{{
          item.filenames.join("、") || "个人课程规则"
        }}</span
        ><small>{{ item.created_at.slice(0, 10) }}</small
        ><span class="badge">{{ statusLabel[item.status] }}</span>
      </button>
    </section>
    <Modal v-if="editing" title="修正安排" @close="editing = null"
      ><EventForm :event="editing" @save="saveDraft" @cancel="editing = null"
    /></Modal>
    <Modal v-if="batch" title="批量补全草稿" wide @close="batch = false"
      ><div class="form-grid">
        <label>日期<input v-model="batchDate" type="date" /></label
        ><label>地点<input v-model="batchPlace" /></label
        ><label>开始<input v-model="batchStart" type="time" /></label
        ><label>结束（同日）<input v-model="batchEnd" type="time" /></label
        ><label
          >分类<select v-model="batchCategory">
            <option value="">保留原分类</option>
            <option>工作</option>
            <option>学习</option>
            <option>培训</option>
            <option>考试</option>
            <option>休息</option>
          </select></label
        >
      </div>
      <p class="muted">空白字段保留原值。跨夜安排请逐项修改。</p>
      <button class="secondary" @click="previewBatch">
        查看 {{ checked.length }} 项修改预览
      </button>
      <div class="change-list">
        <article v-for="item in batchPreview.slice(0, 50)" :key="item.index">
          <div>
            <b>{{ item.before.title }}</b>
            <p>
              {{ item.before.date }} {{ item.before.start }}
              {{ item.before.location }} → {{ item.after.date }}
              {{ item.after.start }} {{ item.after.location }}
            </p>
          </div>
        </article>
      </div>
      <template #footer
        ><button class="secondary" @click="batch = false">取消</button
        ><button
          class="primary"
          :disabled="!batchPreview.length || busy"
          @click="applyBatch"
        >
          确认修改草稿
        </button></template
      ></Modal
    >
    <Modal
      v-if="showOcr"
      title="对照图片，核对识别文字"
      wide
      @close="showOcr = false"
      ><p class="muted">
        分数表示文字识别分数。修改姓名或文字后重新提取，不会自动替换为相似姓名。
      </p>
      <img
        v-if="ocr.preview_image"
        :src="ocr.preview_image"
        class="ocr-overview"
      />
      <div class="ocr-words">
        <label v-for="block in ocr.blocks" :key="block.id"
          ><small
            >{{ block.cell || block.id }} ·
            {{ Math.round(block.score * 100) }} 分</small
          ><input v-model="ocrEdits[block.id]" maxlength="1000" /><small
            >原文：{{ block.original_text }}</small
          ></label
        >
      </div>
      <template #footer
        ><button class="secondary" @click="showOcr = false">返回</button
        ><button
          class="primary"
          @click="start([selected])"
          :disabled="busy || running"
        >
          按修正文字重新提取
        </button></template
      ></Modal
    >
    <ChangePreview
      v-if="showPreview && preview"
      :preview="preview"
      :busy="busy"
      @close="showPreview = false"
      @commit="commit"
    />
  </section>
</template>
