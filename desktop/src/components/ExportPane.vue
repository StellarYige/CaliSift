<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import { call } from "../bridge";
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
  await run(async () => {
    preview.value = await call("export_preview", {
      workspace_id: props.workspace.id,
      options: { ...options },
    });
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
      notify("ICS 文件已保存，可按导入说明加入系统日历");
    }
  });
}
watch(options, () => (preview.value = null), { deep: true });
watch(
  () => props.workspace.version,
  () => {
    preview.value = null;
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
        <p class="muted">生成标准 ICS 文件，提醒由导入后的日历应用处理。</p>
      </div>
      <span class="badge soft">静态日历文件</span>
    </div>
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
              <option>工作</option>
              <option>学习</option>
              <option>培训</option>
              <option>考试</option>
              <option>休息</option>
              <option>其他</option>
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
        <h2>让提醒回到你熟悉的地方</h2>
        <ol>
          <li>选择日期范围，检查可导出的安排。</li>
          <li>保存 ICS 文件，通过你常用的方式传到手机或电脑。</li>
          <li>在支持导入 ICS 的日历中，导入到一个专用日历。</li>
        </ol>
        <p class="notice">
          新版可能需要重新导入或替换专用日历。文件导出不等于外部日历已同步。
        </p>
        <details>
          <summary>兼容性与更新说明</summary>
          <p>
            本版本的 iOS、Android
            和桌面日历真实导入兼容性仍待逐个平台验证，不能保证重复导入会自动更新或删除旧安排。
          </p>
          <p>
            先保留原日历备份，再按目标日历的操作说明导入；不要清理包含其他个人事项的日历。提醒是否生效也取决于日历设置。
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
        <span class="badge soft">已生成文件</span
        ><button
          class="text-button"
          @click="run(() => call('open_export', { export_id: record.id }))"
        >
          打开文件夹
        </button>
      </article>
    </section>
  </section>
</template>
