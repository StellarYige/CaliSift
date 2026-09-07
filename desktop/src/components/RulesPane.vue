<script setup lang="ts">
import { ref, watch, nextTick } from "vue";
import { call } from "../bridge";
import { useActions } from "../actions";
import ChangePreview from "./ChangePreview.vue";
import Modal from "./Modal.vue";
const props = defineProps<{ workspace: any; sourceId?: string }>(),
  emit = defineEmits(["refresh", "course"]);
const { run, busy, notify } = useActions();
const source = ref(props.sourceId || ""),
  name = ref(""),
  description = ref(""),
  shifts = ref<any[]>([]),
  shiftName = ref(""),
  aliases = ref(""),
  start = ref("08:00"),
  end = ref("16:00"),
  nextDay = ref(false),
  template = ref<any>(null),
  preview = ref<any>(null),
  templates = ref<any[]>([]),
  sharing = ref<any>(null),
  shareChecked = ref(false);
const monday = ref(""),
  weeks = ref(20),
  periods = ref("08:00-08:45\n08:55-09:40\n10:00-10:45\n10:55-11:40"),
  courseTitle = ref(""),
  weekday = ref(1),
  periodFrom = ref(1),
  periodTo = ref(2),
  weekFrom = ref(1),
  weekTo = ref(16),
  parity = ref("all"),
  specificWeeks = ref(""),
  location = ref("");
function clone(value: any) {
  return JSON.parse(JSON.stringify(value));
}
async function loadTemplate(item: any) {
  source.value = "";
  await nextTick();
  name.value = item.name;
  description.value = item.description;
  shifts.value = clone(item.rules.shifts || []);
  template.value = clone(item.rules.template || null);
  monday.value = item.rules.semester?.monday || "";
  weeks.value = item.rules.semester?.weeks || 20;
  if (item.rules.semester)
    periods.value = item.rules.semester.periods
      .map((p: any) => p.start + "-" + p.end)
      .join("\n");
}
watch(
  [source, name, shifts, monday, weeks, periods, template],
  () => {
    preview.value = null;
  },
  { deep: true },
);
async function refresh() {
  templates.value = await call("templates");
}
function load() {
  const s = props.workspace.sources.find((s: any) => s.id === source.value);
  name.value = s?.name || "";
  shifts.value = clone(s?.rules?.shifts || []);
  template.value = clone(s?.rules?.template || null);
  monday.value = "";
  weeks.value = 20;
  if (s?.rules?.semester) {
    const sem = s.rules.semester;
    monday.value = sem.monday;
    weeks.value = sem.weeks;
    periods.value = sem.periods
      .map((p: any) => p.start + "-" + p.end)
      .join("\n");
  }
}
function semester() {
  return {
    monday: monday.value,
    weeks: weeks.value,
    periods: periods.value
      .split("\n")
      .filter((s) => s.trim())
      .map((s) => {
        const [start, end] = s.trim().split(/\s*[-—–]\s*/);
        return { start, end };
      }),
  };
}
function config() {
  return {
    ...(shifts.value.length ? { shifts: shifts.value } : {}),
    ...(monday.value ? { semester: semester() } : {}),
    ...(template.value ? { template: template.value } : {}),
  };
}
function addShift() {
  if (!shiftName.value.trim() || !aliases.value.trim()) {
    notify("请填写班次名称和符号", true);
    return;
  }
  shifts.value.push({
    name: shiftName.value.trim(),
    aliases: aliases.value.split(/[、,，\s]+/).filter(Boolean),
    start: start.value,
    end: end.value,
    next_day: nextDay.value,
  });
  shiftName.value = "";
  aliases.value = "";
}
async function sourcePreview() {
  await run(async () => {
    preview.value = await call("preview_change", {
      workspace_id: props.workspace.id,
      expected_version: props.workspace.version,
      operation: {
        type: "source_config",
        source_id: source.value,
        name: name.value,
        rules: config(),
        apply: true,
      },
    });
  });
}
async function saveTemplate() {
  await run(async () => {
    await call("save_template", {
      name: name.value,
      rules: config(),
      description: description.value,
    });
    await refresh();
    notify("规则模板已保存，可在导入时复用");
  });
}
async function expand() {
  await run(async () => {
    if (!monday.value) throw Error("请先设置第一教学周的周一");
    const course: any = {
      title: courseTitle.value,
      weekday: weekday.value,
      periods: Array.from(
        { length: periodTo.value - periodFrom.value + 1 },
        (_, i) => i + periodFrom.value,
      ),
      week_from: weekFrom.value,
      week_to: weekTo.value,
      parity: parity.value,
      location: location.value,
    };
    if (specificWeeks.value.trim())
      course.weeks = specificWeeks.value
        .split(/[、,，\s]+/)
        .filter(Boolean)
        .map(Number);
    const job = await call("course_draft", {
      workspace_id: props.workspace.id,
      course,
      semester: semester(),
    });
    emit("course", job.id);
  });
}
watch(source, load, { immediate: true });
watch(() => props.workspace.version, load);
refresh();
</script>
<template>
  <section class="page-stack">
    <div class="page-heading">
      <div>
        <p class="eyebrow">设置一次，相同安排重复使用</p>
        <h1>规则模板</h1>
        <p class="muted">原表写明的时间优先，规则用于补全缺失字段。</p>
      </div>
      <button
        class="secondary"
        @click="
          run(async () => {
            if (await call('import_template')) {
              await refresh();
              notify('模板已导入');
            }
          })
        "
      >
        导入模板
      </button>
    </div>
    <div class="card">
      <div class="form-grid">
        <label
          >绑定来源<select v-model="source">
            <option value="">建立独立规则模板</option>
            <option v-for="s in workspace.sources" :key="s.id" :value="s.id">
              {{ s.name }}
            </option>
          </select></label
        ><label
          >来源 / 模板名称<input
            v-model="name"
            placeholder="例如：单位月度排班"
            maxlength="100" /></label
        ><label class="span-2"
          >适用说明<input
            v-model="description"
            placeholder="说明适用的布局和规则，不包含个人信息"
        /></label>
      </div>
    </div>
    <div class="two-columns">
      <section class="card">
        <header class="panel-heading">
          <h2>班次时间</h2>
          <span class="muted">只应用于选定来源</span>
        </header>
        <div v-for="(shift, i) in shifts" :key="i" class="shift-row">
          <div>
            <b>{{ shift.name }}</b
            ><small>{{ shift.aliases.join(" / ") }}</small>
          </div>
          <span
            >{{ shift.start }}–{{ shift.end
            }}{{ shift.next_day ? " 次日" : "" }}</span
          ><button class="text-button" @click="shifts.splice(i, 1)">
            移除
          </button>
        </div>
        <div v-if="!shifts.length" class="empty small-empty">
          添加“早班”“夜班”等符号对应的实际时间。
        </div>
        <div class="form-grid">
          <label>名称<input v-model="shiftName" placeholder="早班" /></label
          ><label
            >符号与别名<input v-model="aliases" placeholder="早, 早班" /></label
          ><label>开始<input v-model="start" type="time" /></label
          ><label>结束<input v-model="end" type="time" /></label
          ><label class="check"
            ><input v-model="nextDay" type="checkbox" />次日结束</label
          ><button class="secondary" @click="addShift">添加班次</button>
        </div>
      </section>
      <section class="card">
        <header class="panel-heading"><h2>学期与节次</h2></header>
        <div class="form-grid">
          <label>第一教学周的周一<input v-model="monday" type="date" /></label
          ><label
            >学期周数<input
              v-model.number="weeks"
              type="number"
              min="1"
              max="60" /></label
          ><label class="span-2"
            >每行一个节次（开始–结束）<textarea
              v-model="periods"
              rows="7"
              spellcheck="false"
            />
          </label>
        </div>
        <p class="muted">
          不自动推断节假日停课。临时调课可在对应的单次安排中修改。
        </p>
        <p v-if="template" class="notice">
          已绑定表格布局：{{ template.layout }}，表头第
          {{ template.header_row + 1 }} 行。可在导入工作台重新校正。
        </p>
      </section>
    </div>
    <div class="button-row">
      <button
        v-if="source"
        class="primary"
        @click="sourcePreview"
        :disabled="busy"
      >
        预览对已有安排的影响</button
      ><button class="secondary" @click="saveTemplate" :disabled="busy">
        保存为可复用模板
      </button>
    </div>
    <section class="card">
      <header class="panel-heading">
        <h2>建立学期课程</h2>
        <span class="muted">先展开为实际日期，再核对保存</span>
      </header>
      <div class="form-grid four">
        <label
          >课程名称<input v-model="courseTitle" placeholder="课程名称" /></label
        ><label
          >星期<select v-model.number="weekday">
            <option
              v-for="(label, i) in ['一', '二', '三', '四', '五', '六', '日']"
              :key="i"
              :value="i + 1"
            >
              星期{{ label }}
            </option>
          </select></label
        ><label
          >开始节次<input
            v-model.number="periodFrom"
            type="number"
            min="1"
            max="30" /></label
        ><label
          >结束节次<input
            v-model.number="periodTo"
            type="number"
            min="1"
            max="30" /></label
        ><label
          >开始周<input
            v-model.number="weekFrom"
            type="number"
            min="1"
            max="60" /></label
        ><label
          >结束周<input
            v-model.number="weekTo"
            type="number"
            min="1"
            max="60" /></label
        ><label
          >单双周<select v-model="parity">
            <option value="all">全部周</option>
            <option value="odd">单周</option>
            <option value="even">双周</option>
          </select></label
        ><label
          >指定周次（可选）<input
            v-model="specificWeeks"
            placeholder="1,3,7,9" /></label
        ><label class="span-2">地点<input v-model="location" /></label>
      </div>
      <button class="primary" @click="expand" :disabled="busy">
        展开日期并核对
      </button>
    </section>
    <section class="card">
      <header class="panel-heading"><h2>已保存模板</h2></header>
      <div v-if="!templates.length" class="empty small-empty">还没有模板。</div>
      <article v-for="item in templates" :key="item.id" class="template-row">
        <div>
          <h3>{{ item.name }}</h3>
          <p class="muted">
            {{ item.description || "本机规则模板" }} ·
            {{ item.rules.shifts?.length || 0 }} 个班次
          </p>
        </div>
        <button class="text-button" @click="loadTemplate(item)">载入编辑</button
        ><button
          class="secondary small"
          @click="
            sharing = item;
            shareChecked = false;
          "
        >
          导出分享
        </button>
      </article>
    </section>
    <Modal v-if="sharing" title="检查共享模板" wide @close="sharing = null"
      ><p>分享前检查表头和说明，确保没有姓名、私人事项或个人文件路径。</p>
      <pre>{{
        JSON.stringify(
          {
            name: sharing.name,
            description: sharing.description,
            rules: sharing.rules,
          },
          null,
          2,
        )
      }}</pre>
      <label class="check"
        ><input
          v-model="shareChecked"
          type="checkbox"
        />我已检查，这份模板可以分享</label
      ><template #footer
        ><button class="secondary" @click="sharing = null">取消</button
        ><button
          class="primary"
          :disabled="!shareChecked"
          @click="
            run(async () => {
              if (
                await call('export_template', {
                  template_id: sharing.id,
                  reviewed: true,
                })
              )
                sharing = null;
            })
          "
        >
          保存模板文件
        </button></template
      ></Modal
    >
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
          notify('来源规则已更新');
        })
      "
    />
  </section>
</template>
