<script setup lang="ts">
import { offline, offlineTask, checkUpdate } from "../offline";
</script>
<template>
  <section class="card">
    <header class="panel-heading">
      <h2>准备离线使用</h2>
      <span class="badge" :class="offline.ready ? 'soft' : 'warning'">{{
        offline.ready ? "离线就绪" : "尚未就绪"
      }}</span>
    </header>
    <p>
      应用、Python/WASM 和图片模型均来自本站。资源全部下载并通过 SHA-256
      校验后，断网也可处理表格和图片。
    </p>
    <p role="status">
      {{ offline.message }} · {{ (offline.loaded / 1048576).toFixed(1) }} /
      {{ (offline.total / 1048576).toFixed(1) }} MiB
    </p>
    <progress
      :value="offline.loaded"
      :max="offline.total || 1"
      aria-label="离线资源准备进度"
    ></progress>
    <div class="button-row">
      <button class="primary" :disabled="offline.busy" @click="offlineTask()">
        {{ offline.busy ? "正在校验资源…" : "准备 / 修复离线资源" }}</button
      ><button
        class="secondary"
        :disabled="offline.busy"
        @click="offlineTask('CHECK')"
      >
        重新校验</button
      ><button class="text-button" @click="checkUpdate">检查更新</button>
    </div>
    <p v-if="offline.update" class="notice">
      新版已下载。请先保存当前核对工作，关闭本站的所有标签页，再重新打开以使用新版。个人数据库会保留。
    </p>
    <p class="muted">
      浏览器可能回收站点存储，请定期下载备份。离线就绪只代表本站资源完整，不表示已备份个人数据。
    </p>
  </section>
</template>
