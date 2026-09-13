<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import { call } from "../client";
import { useActions } from "../actions";
const props = defineProps<{ workspace: any }>();
const { run, busy, notify } = useActions();
const profiles = ref<any[]>([]),
  exports = ref<any[]>([]),
  profileId = ref(""),
  profileName = ref("我的日历"),
  filename = ref("CaliSift-日程.ics"),
  preview = ref<any>(null);
const options = reactive({
  from: "",
  to: "",
  category: "",
  source_id: "",
  alarm: 15,
});
let previewSequence = 0;
async function refresh() {
  profiles.value = await call("profiles", { workspace_id: props.workspace.id });
  exports.value = await call("exports", { workspace_id: props.workspace.id });
}
function selectProfile() {
  const p = profiles.value.find((p) => p.id === profileId.value);
  if (p) {
    profileName.value = p.name;
    filename.value = p.filename || "CaliSift-日程.ics";
    Object.assign(
      options,
      { from: "", to: "", category: "", source_id: "", alarm: 0 },
      p.options,
    );
  }
}
async function check() {
  const sequence = ++previewSequence;
  preview.value = null;
  await run(async () => {
    const value = await call("export_preview", {
      workspace_id: props.workspace.id,
      options: { ...options },
    });
    if (sequence === previewSequence) preview.value = value;
  });
}
async function save() {
  await run(async () => {
    const result = await call("export_file", {
      workspace_id: props.workspace.id,
      expected_version: preview.value.version,
      options: { ...options },
      filename: filename.value,
      profile_id: profileId.value,
    });
    if (result) {
      await refresh();
      notify(
        "已请求下载 ICS 安排快照，请在浏览器下载列表确认。请导入专用日历；外部日历尚未更新。",
      );
    }
  });
}
function invalidatePreview() {
  previewSequence++;
  preview.value = null;
}
watch(options, invalidatePreview, { deep: true });
watch(
  [() => props.workspace.id, () => props.workspace.version],
  () => {
    invalidatePreview();
    run(refresh);
  },
  { immediate: true },
);
</script>
<template>
  <section class="page-stack">
    <div class="page-heading">
      <div>
        <p class="eyebrow">核对好的安排，带到常用日历里</p>
        <h1>导出与记录</h1>
        <p class="muted">
          保存当前安排的 ICS 快照，提醒由导入后的日历应用处理。
        </p>
      </div>
      <span class="badge soft">安排快照</span>
    </div>
    <p class="notice snapshot-notice">
      ICS 是导出时的安排快照。之后在星程中改期或取消，不会自动传到外部日历；
      不保证重新导入后自动更新或删除旧事项，也可能出现重复项。
    </p>
    <div class="two-columns">
      <section class="card">
        <header class="panel-heading"><h2>导出方案</h2></header>
        <div class="form-grid">
          <label
            >已保存方案<select v-model="profileId" @change="selectProfile">
              <option value="">新建方案</option>
              <option v-for="p in profiles" :key="p.id" :value="p.id">
                {{ p.name }}
              </option>
            </select></label
          ><label>方案名称<input v-model="profileName" maxlength="100" /></label
          ><label>开始日期<input v-model="options.from" type="date" /></label
          ><label>结束日期<input v-model="options.to" type="date" /></label
          ><label
            >来源<select v-model="options.source_id">
              <option value="">全部来源</option>
              <option v-for="s in workspace.sources" :value="s.id" :key="s.id">
                {{ s.name }}
              </option>
            </select></label
          ><label
            >分类<select v-model="options.category">
              <option value="">全部分类</option>
              <option
                v-for="category in workspace.settings.categories"
                :key="category.name"
              >
                {{ category.name }}
              </option>
            </select></label
          ><label
            >提醒<select v-model.number="options.alarm">
              <option :value="0">不提醒</option>
              <option :value="15">提前 15 分钟</option>
              <option :value="30">提前 30 分钟</option>
              <option :value="60">提前 1 小时</option>
              <option :value="1440">提前 1 天</option>
            </select></label
          ><label>文件名<input v-model="filename" /></label>
        </div>
        <div class="button-row">
          <button
            class="secondary"
            @click="
              run(async () => {
                const p = await call('save_profile', {
                  workspace_id: workspace.id,
                  name: profileName,
                  options: { ...options },
                  filename,
                  profile_id: profileId || undefined,
                  expected_revision: profiles.find((p) => p.id === profileId)
                    ?.revision,
                });
                await refresh();
                profileId = p.id;
                notify('导出方案已保存');
              })
            "
          >
            保存方案</button
          ><button class="primary" @click="check" :disabled="busy">
            查看导出预览
          </button>
        </div>
      </section>
      <aside class="card export-help">
        <span class="kicker">导入到你的日历</span>
        <h2>用专用日历核对每一版</h2>
        <ol>
          <li>选择日期范围，核对本次包含和未包含的安排，保存 ICS 文件。</li>
          <li>
            在支持 ICS 导入的日历应用中新建空的专用日历，例如“星程安排 ·
            9月13日版”，再将文件导入其中。
          </li>
          <li>
            有新版时，保留旧版备份，将新版导入另一个空的专用日历。核对数量、日期、跨夜结束时间和提醒。
          </li>
          <li>
            核对无误后，停用旧专用日历的显示和提醒，避免重复提醒；需要删除时只处理确认可丢弃的旧专用日历。
          </li>
        </ol>
        <p class="notice">
          不要删除混有其他个人事项的日历。仅隐藏日历未必会停用提醒，请检查目标日历的提醒设置。
        </p>
        <details>
          <summary>兼容性与更新说明</summary>
          <p>
            项目历史验证记录：Windows 上的 Thunderbird 155.0
            的导入器能读入中文、跨夜、全天和提醒字段。
            重复导入不会自动更新或删除已有安排。建议将 CaliSift
            安排放在专用日历中；更新前保留备份，并在新的专用日历核对新版。
          </p>
          <p>
            iOS、Android 和 Apple
            日历尚未真机验证。不要清理包含其他个人事项的日历；提醒通知是否弹出取决于目标日历和系统设置。
          </p>
        </details>
      </aside>
    </div>
    <section v-if="preview" class="card">
      <header class="panel-heading">
        <h2>本次可导出 {{ preview.count }} 项</h2>
        <button
          class="primary"
          :disabled="busy || preview.blocked || !preview.count"
          @click="save"
        >
          保存 ICS 文件
        </button>
      </header>
      <p class="notice snapshot-notice">
        本次保存的是 ICS
        安排快照。重新导入不保证覆盖改期或删除旧事项；请按专用日历步骤核对新版。
      </p>
      <p v-if="preview.blocked" class="notice warning">
        部分安排没有时间。请在“安排预览”中补全，或明确设为全天后再导出。
      </p>
      <p v-else class="muted">
        仅包含已确认、未隐藏、未归档且未取消的安排。时区：Asia/Shanghai。
      </p>
      <details v-if="preview.excluded.length" open>
        <summary>{{ preview.excluded.length }} 项未包含</summary>
        <div class="excluded-list">
          <p v-for="e in preview.excluded" :key="e.id">
            <span>{{ e.date }} {{ e.title }}</span
            ><span class="badge">{{ e.reason }}</span>
          </p>
        </div>
      </details>
    </section>
    <section class="card">
      <header class="panel-heading">
        <h2>导出记录</h2>
        <span class="muted">记录的是文件生成结果</span>
      </header>
      <p class="muted">
        “不再包含”只表示新文件中没有这些安排，不代表外部日历已删除它们。
      </p>
      <div v-if="!exports.length" class="empty small-empty">
        还没有导出文件。
      </div>
      <article v-for="record in exports" :key="record.id" class="export-row">
        <span class="file-type">ICS</span>
        <div>
          <h3>{{ record.filename }}</h3>
          <p>
            {{ record.count }} 项安排 ·
            {{ record.created_at.slice(0, 16).replace("T", " ") }} UTC
          </p>
          <small class="muted"
            >较上次：新增 {{ record.changes.added }} · 变化
            {{ record.changes.changed }} · 不再包含
            {{ record.changes.removed }}</small
          >
        </div>
        <span class="badge soft">已生成文件</span>
      </article>
    </section>
  </section>
</template>
