<script setup lang="ts">
import { computed, ref } from "vue";
import Modal from "./Modal.vue";
const props = defineProps<{ preview: any; busy?: boolean }>();
const emit = defineEmits(["close", "commit"]);
const page = ref(0);
const changes = computed(() => [
  ...props.preview.summary.added.map((x: any) => ({ kind: "新增", value: x })),
  ...props.preview.summary.changed.map((x: any) => ({
    kind: "修改",
    value: x.after,
    before: x.before,
  })),
  ...props.preview.summary.cancelled.map((x: any) => ({
    kind: "取消",
    value: x,
  })),
]);
</script>
<template>
  <Modal title="确认这次变化" wide @close="emit('close')"
    ><div class="stats">
      <div>
        <strong>{{ preview.summary.added.length }}</strong
        ><span>新增</span>
      </div>
      <div>
        <strong>{{ preview.summary.changed.length }}</strong
        ><span>修改</span>
      </div>
      <div>
        <strong>{{ preview.summary.cancelled.length }}</strong
        ><span>取消</span>
      </div>
      <div>
        <strong>{{ preview.summary.duplicates }}</strong
        ><span>重复</span>
      </div>
    </div>
    <p
      v-for="message in preview.summary.warnings"
      :key="message"
      class="notice"
    >
      {{ message }}
    </p>
    <div v-if="preview.summary.unresolved.length" class="notice warning">
      还有
      {{ preview.summary.unresolved.length }}
      项需要对应旧安排或选择个人修正处理方式，请返回完成核对。
    </div>
    <div class="change-list">
      <article
        v-for="(change, i) in changes.slice(page * 50, (page + 1) * 50)"
        :key="i"
      >
        <span class="badge">{{ change.kind }}</span>
        <div>
          <b
            >{{ change.value.date || "日期待确认" }} ·
            {{ change.value.title }}</b
          >
          <p v-if="change.before" class="muted">
            原：{{ change.before.date }} {{ change.before.start }}–{{
              change.before.end
            }}
            {{ change.before.location }}
          </p>
          <p>
            {{ change.value.start || "时间未注明"
            }}{{ change.value.end ? "–" + change.value.end : "" }}
            {{ change.value.location }}
          </p>
        </div>
      </article>
    </div>
    <div v-if="changes.length > 50" class="pagination">
      <button @click="page--" :disabled="page === 0">上一页</button
      ><span>{{ page + 1 }} / {{ Math.ceil(changes.length / 50) }}</span
      ><button @click="page++" :disabled="(page + 1) * 50 >= changes.length">
        下一页
      </button>
    </div>
    <p class="muted">
      确认后保存在这台电脑。图片只长期保留必要的局部证据；整份临时原文件会清理。
    </p>
    <template #footer
      ><button class="secondary" @click="emit('close')">返回核对</button
      ><button
        class="primary"
        :disabled="busy || preview.summary.unresolved.length > 0"
        @click="emit('commit')"
      >
        确认保存
      </button></template
    ></Modal
  >
</template>
