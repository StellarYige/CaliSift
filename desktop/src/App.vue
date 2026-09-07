<script setup lang="ts">
import { ref, provide, nextTick, watch } from "vue";
import { call, whenReady } from "./bridge";
import ImportPane from "./components/ImportPane.vue";
import EventsPane from "./components/EventsPane.vue";
import SourcesPane from "./components/SourcesPane.vue";
import RulesPane from "./components/RulesPane.vue";
import ExportPane from "./components/ExportPane.vue";
import SettingsPane from "./components/SettingsPane.vue";
const capabilities = ref<any>(null),
  workspace = ref<any>(null),
  page = ref("import"),
  name = ref(""),
  loading = ref(true),
  toast = ref(""),
  error = ref(false),
  jobId = ref(""),
  sourceId = ref(""),
  importPane = ref<InstanceType<typeof ImportPane>>();
let toastTimer: ReturnType<typeof setTimeout> | undefined;
function notify(message: string, isError = false) {
  toast.value = message;
  error.value = isError;
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (toast.value = ""), isError ? 15000 : 6000);
}
provide("notify", notify);
const nav = [
  { id: "import", icon: "⇣", label: "导入工作台" },
  { id: "sources", icon: "▤", label: "来源与历史" },
  { id: "events", icon: "▦", label: "安排预览" },
  { id: "rules", icon: "⌘", label: "规则模板" },
  { id: "export", icon: "↗", label: "导出与记录" },
  { id: "settings", icon: "⚙", label: "设置" },
];
async function refresh(id?: string) {
  try {
    capabilities.value = await call("capabilities");
    const active =
      id || workspace.value?.id || capabilities.value.workspaces[0]?.id;
    if (active) {
      workspace.value = await call("workspace", { workspace_id: active });
      window.calisiftWorkspace = active;
    }
  } catch (e: any) {
    notify(e.message, true);
  } finally {
    loading.value = false;
  }
}
async function selectWorkspace(id: string) {
  jobId.value = "";
  sourceId.value = "";
  await refresh(id);
  page.value = "import";
}
async function create() {
  try {
    const result = await call("create_workspace", { name: name.value });
    await refresh(result.id);
  } catch (e: any) {
    notify(e.message, true);
  }
}
async function sample() {
  name.value = "星辰奕歌";
  await create();
  if (workspace.value) {
    await nextTick();
    const job = await call("sample", { workspace_id: workspace.value.id });
    await importPane.value?.accept(job);
  }
}
async function showCourse(id: string) {
  jobId.value = id;
  page.value = "import";
  await nextTick();
  await importPane.value?.resume(id);
}
window.addEventListener("calisift-drop", async (event: Event) => {
  const data = (event as CustomEvent).detail;
  if (data.error) return notify(data.error, true);
  page.value = "import";
  await nextTick();
  await importPane.value?.accept(data.job);
});
watch(
  () => workspace.value?.settings.large_text,
  (large) =>
    (document.documentElement.style.fontSize = large ? "17px" : "14px"),
);
whenReady(() => refresh());
setTimeout(() => {
  if (!window.pywebview) {
    loading.value = false;
    notify("请通过 CaliSift 桌面程序打开，浏览器页面没有连接本机服务。", true);
  }
}, 4000);
</script>
<template>
  <div class="app-shell" :class="{ large: workspace?.settings.large_text }">
    <aside class="sidebar">
      <a class="brand" href="#" @click.prevent="page = 'import'"
        ><svg viewBox="0 0 40 40" aria-hidden="true">
          <path
            d="M20 2L24.6 15.4L38 20L24.6 24.6L20 38L15.4 24.6L2 20L15.4 15.4Z"
            fill="currentColor"
          /></svg
        ><span>CaliSift<small>星程</small></span></a
      >
      <div v-if="workspace" class="workspace-switch">
        <span class="avatar">{{ workspace.name.slice(0, 1) }}</span
        ><select
          :value="workspace.id"
          aria-label="切换工作区"
          @change="selectWorkspace(($event.target as HTMLSelectElement).value)"
        >
          <option
            v-for="w in capabilities.workspaces"
            :key="w.id"
            :value="w.id"
          >
            {{ w.name }}
          </option>
        </select>
      </div>
      <nav aria-label="主导航">
        <button
          v-for="item in nav"
          :key="item.id"
          :class="{ active: page === item.id }"
          :disabled="!workspace"
          @click="page = item.id"
        >
          <span>{{ item.icon }}</span
          >{{ item.label }}
        </button>
      </nav>
      <div class="sidebar-bottom">
        <span class="local-dot"></span>安排保存在这台电脑<small
          >核对、积累，安心导出。</small
        ><span class="version">{{
          capabilities?.version || "0.3.0-alpha.1"
        }}</span>
      </div>
    </aside>
    <main>
      <div class="topbar">
        <span>个人日程整理工具</span
        ><span>{{
          workspace ? workspace.name + "的工作区" : "欢迎使用星程"
        }}</span>
      </div>
      <div v-if="loading" class="startup">
        <span class="empty-star">✦</span>
        <p>正在打开本机工作区…</p>
      </div>
      <section v-else-if="!workspace" class="onboarding">
        <div class="hero-star">✦</div>
        <p class="eyebrow">CaliSift · 星程</p>
        <h1>把表格交给星程，<br />只看属于你的安排。</h1>
        <p>
          排班、课程、培训、考试，一起整理。<br />在本机识别，对照原文核对，再带到你的日历。
        </p>
        <form @submit.prevent="create">
          <label
            >你的完整姓名<input
              v-model="name"
              placeholder="例如：星辰奕歌"
              maxlength="80"
              required
              autofocus /></label
          ><button class="primary" type="submit">建立个人工作区 →</button>
        </form>
        <button class="text-button" @click="sample">先用示例体验</button>
        <div class="onboarding-notes">
          <span>✓ 本机处理</span><span>✓ 无需账号</span
          ><span>✓ 核对后保存</span>
        </div>
      </section>
      <template v-else
        ><ImportPane
          v-if="page === 'import'"
          ref="importPane"
          :key="workspace.id"
          :workspace="workspace"
          :job-id="jobId"
          @job="jobId = $event"
          @refresh="refresh()" /><SourcesPane
          v-else-if="page === 'sources'"
          :workspace="workspace"
          @rules="
            sourceId = $event;
            page = 'rules';
          "
          @import="page = 'import'"
          @refresh="refresh()" /><EventsPane
          v-else-if="page === 'events'"
          :key="workspace.id"
          :workspace="workspace"
          @refresh="refresh()" /><RulesPane
          v-else-if="page === 'rules'"
          :key="workspace.id"
          :workspace="workspace"
          :source-id="sourceId"
          @refresh="refresh()"
          @course="showCourse" /><ExportPane
          v-else-if="page === 'export'"
          :key="workspace.id"
          :workspace="workspace" /><SettingsPane
          v-else-if="page === 'settings'"
          :key="workspace.id"
          :workspace="workspace"
          :capabilities="capabilities"
          @refresh="refresh()"
          @workspace="selectWorkspace"
      /></template>
    </main>
    <div v-if="toast" class="toast" :class="{ error }" role="alert">
      <span>{{ error ? "!" : "✓" }}</span
      >{{ toast }}<button @click="toast = ''" aria-label="关闭提示">×</button>
    </div>
  </div>
</template>
