<script setup lang="ts">
import { ref, watch } from "vue";
import { call } from "../bridge";
import { useActions } from "../actions";
import Modal from "./Modal.vue";
import PreferencesPane from "./PreferencesPane.vue";
const props = defineProps<{ workspace: any; capabilities: any }>(),
  emit = defineEmits(["refresh", "workspace"]);
const { run, busy, notify } = useActions();
const newName = ref(""),
  restore = ref<any>(null),
  replace = ref(false),
  jobs = ref<any[]>([]),
  discard = ref<any>(null);
async function refresh() {
  jobs.value = await call("list_jobs", { workspace_id: props.workspace.id });
}
watch(
  () => props.workspace.version,
  () => {
    refresh();
  },
  { immediate: true },
);
</script>
<template>
  <section class="page-stack">
    <div class="page-heading">
      <div>
        <p class="eyebrow">数据留在本机，由你掌握</p>
        <h1>设置</h1>
        <p class="muted">
          CaliSift {{ capabilities.version }} · {{ capabilities.timezone }}
        </p>
      </div>
    </div>
    <div class="two-columns">
      <section class="card">
        <header class="panel-heading"><h2>个人工作区</h2></header>
        <p>
          当前：<b>{{ workspace.name }}</b> ·
          {{ workspace.active_count }} 条当前安排
        </p>
        <p class="muted">不同姓名使用独立工作区，切换不会清空原安排。</p>
        <div class="button-row">
          <input
            v-model="newName"
            placeholder="新工作区的完整姓名"
            maxlength="80"
          /><button
            class="secondary"
            @click="
              run(async () => {
                const w = await call('create_workspace', { name: newName });
                newName = '';
                emit('workspace', w.id);
              })
            "
            :disabled="busy || !newName.trim()"
          >
            建立工作区
          </button>
        </div>
        <p class="muted path-label">数据目录：{{ capabilities.data_path }}</p>
      </section>
      <section class="card">
        <header class="panel-heading"><h2>备份与恢复</h2></header>
        <p>备份包含已保存安排、个人修正、规则、导出状态和必要图片证据。</p>
        <p class="muted">
          不包含模型或未完成任务的整份原文件。旧小程序请先导出 JSON
          备份，再在这里导入。
        </p>
        <div class="button-row">
          <button
            class="primary"
            @click="
              run(async () => {
                if (await call('backup', { workspace_id: workspace.id }))
                  notify('完整工作区备份已保存');
              })
            "
          >
            备份当前工作区</button
          ><button
            class="secondary"
            @click="
              run(async () => {
                restore = await call('prepare_restore');
                replace = false;
              })
            "
          >
            恢复 / 迁移备份
          </button>
        </div>
      </section>
    </div>
    <PreferencesPane :workspace-id="workspace.id" @refresh="emit('refresh')" />
    <section class="card">
      <header class="panel-heading">
        <h2>图片识别</h2>
        <span
          class="badge"
          :class="capabilities.ocr.ready ? 'soft' : 'warning'"
          >{{ capabilities.ocr.ready ? "本地模型已就绪" : "模型未就绪" }}</span
        >
      </header>
      <p>
        清晰打印体表格和截图，在这台电脑上识别。首次安装完整包即可离线使用。
      </p>
      <p v-if="!capabilities.ocr.ready" class="notice warning">
        {{ capabilities.ocr.message }}
      </p>
      <details>
        <summary>模型与处理说明</summary>
        <p>
          {{ capabilities.ocr.model }}。单图最多 1200 万像素，90
          秒超时。手写、模糊或无法可靠还原的布局需要重新整理或人工核对。
        </p>
      </details>
      <div class="button-row">
        <button
          class="secondary"
          @click="
            run(async () => {
              if (await call('model_repair')) {
                emit('refresh');
                notify('离线模型包已校验并安装');
              }
            })
          "
        >
          从离线模型包修复</button
        ><button class="text-button" @click="run(() => call('open_project'))">
          打开项目与下载说明 ↗
        </button>
      </div>
    </section>
    <section class="card">
      <h2>问题反馈</h2>
      <p>
        复制版本、系统和模型就绪状态，便于反馈；摘要不包含姓名、日程或本机路径。
      </p>
      <button
        class="secondary"
        @click="
          run(async () => {
            await call('copy_diagnostics');
            notify('诊断摘要已复制');
          })
        "
      >
        复制诊断摘要
      </button>
    </section>
    <section class="card">
      <header class="panel-heading"><h2>未完成任务与暂存文件</h2></header>
      <p class="muted">
        为方便恢复核对，未完成任务保留本机原文件副本。确认导入或丢弃任务后清理。
      </p>
      <article
        v-for="j in jobs.filter((j) => j.status !== 'committed')"
        :key="j.id"
        class="history-row"
      >
        <span class="truncate">{{ j.filenames.join("、") || "课程草稿" }}</span
        ><small>{{ (j.size / 1024 / 1024).toFixed(1) }} MiB</small
        ><button class="text-button" @click="discard = j">丢弃并清理</button>
      </article>
      <p v-if="jobs.every((j) => j.status === 'committed')" class="muted">
        没有未完成任务。
      </p>
    </section>
    <Modal v-if="restore" title="核对备份后恢复" @close="restore = null"
      ><h3>{{ restore.name }}</h3>
      <p>
        {{ restore.events }} 条安排 · {{ restore.sources }} 个来源 ·
        {{ restore.evidence }} 份图片证据
      </p>
      <p>默认恢复为独立工作区，保留当前数据。</p>
      <label class="check"
        ><input type="checkbox" v-model="replace" />替换当前“{{
          workspace.name
        }}”工作区，并先创建恢复点</label
      ><template #footer
        ><button class="secondary" @click="restore = null">取消</button
        ><button
          class="primary"
          :disabled="busy"
          @click="
            run(async () => {
              const w = await call('restore_backup', {
                token: restore.token,
                replace_workspace_id: replace ? workspace.id : null,
                expected_version: replace ? workspace.version : null,
              });
              restore = null;
              emit('workspace', w.id);
              notify('备份已恢复');
            })
          "
        >
          确认恢复
        </button></template
      ></Modal
    >
    <Modal v-if="discard" title="丢弃未完成任务" @close="discard = null"
      ><p>将删除本次未保存草稿和临时原文件，已保存日历保持原样。</p>
      <p>{{ discard.filenames.join("、") }}</p>
      <template #footer
        ><button class="secondary" @click="discard = null">保留任务</button
        ><button
          class="primary"
          @click="
            run(async () => {
              await call('discard_job', { job_id: discard.id });
              discard = null;
              await refresh();
            })
          "
        >
          确认丢弃
        </button></template
      ></Modal
    >
  </section>
</template>
