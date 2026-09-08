<script setup lang="ts">
import { ref, watch } from "vue";
import { call } from "../bridge";
import { useActions } from "../actions";
import type { Preferences, PreferenceSnapshot } from "../types";
const props = defineProps<{ workspaceId: string }>();
const emit = defineEmits(["refresh"]);
const { run, busy, notify } = useActions();
const snapshot = ref<PreferenceSnapshot>();
const value = ref<Preferences>();
const categoryName = ref("");
async function load() {
  snapshot.value = await call<PreferenceSnapshot>("get_preferences", {
    workspace_id: props.workspaceId,
  });
  value.value = structuredClone(snapshot.value.values);
}
async function save() {
  await run(async () => {
    await call("save_preferences", {
      workspace_id: props.workspaceId,
      expected_revision: snapshot.value!.revision,
      values: JSON.parse(JSON.stringify(value.value)),
    });
    await load();
    emit("refresh");
    notify("偏好已保存，正在核对的日历预览仍然有效");
  });
}
function addCategory() {
  const name = categoryName.value.trim();
  if (!name || value.value!.categories.some((c) => c.name === name))
    return notify("请填写不重复的分类名称", true);
  value.value!.categories.push({ name, color: "#8876c6", active: true });
  categoryName.value = "";
}
watch(
  () => props.workspaceId,
  () => run(load),
  { immediate: true },
);
</script>
<template>
  <section class="card" v-if="value">
    <header class="panel-heading">
      <h2>外观与使用习惯</h2>
      <button class="text-button" @click="run(load)">重新读取设置</button>
    </header>
    <div class="form-grid four">
      <label
        >主题<select v-model="value.theme">
          <option value="system">跟随系统</option>
          <option value="light">浅色</option>
          <option value="dark">深色</option>
        </select></label
      >
      <label
        >字号<select v-model.number="value.font_size">
          <option :value="14">标准</option>
          <option :value="17">大字号</option>
          <option :value="20">特大字号</option>
        </select></label
      >
      <label
        >间距<select v-model="value.density">
          <option value="comfortable">舒适</option>
          <option value="compact">紧凑</option>
        </select></label
      >
      <label
        >每周开始<select v-model.number="value.week_start">
          <option :value="1">周一</option>
          <option :value="0">周日</option>
        </select></label
      >
      <label
        >配置起点<select v-model="value.scenario">
          <option value="general">通用</option>
          <option value="work">工作优先</option>
          <option value="study">学习优先</option>
        </select></label
      >
      <label class="check"
        ><input
          type="checkbox"
          v-model="value.hide_rest"
        />查看时隐藏休息安排</label
      >
    </div>
    <p class="muted">
      工作与学习可以同时保存。配置起点只调整规则页面默认展开的内容。
    </p>
    <h3>分类与颜色</h3>
    <div class="color-settings">
      <label v-for="category in value.categories" :key="category.name"
        >{{ category.name }}<input type="color" v-model="category.color" /><span
          class="check"
          ><input type="checkbox" v-model="category.active" />启用</span
        ></label
      >
    </div>
    <div class="button-row">
      <input
        v-model="categoryName"
        maxlength="40"
        placeholder="新增分类"
        @keydown.enter.prevent="addCategory"
      /><button
        class="secondary"
        @click="addCategory"
        :disabled="value.categories.length >= 60"
      >
        添加分类
      </button>
    </div>
    <p class="muted">停用分类后，已有安排仍保留原分类与颜色。</p>
    <button class="primary" @click="save" :disabled="busy">保存偏好</button>
  </section>
</template>
