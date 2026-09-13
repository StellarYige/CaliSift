<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
defineProps<{ title: string; wide?: boolean }>();
const emit = defineEmits(["close"]);
const panel = ref<HTMLElement>();
const previous = document.activeElement as HTMLElement | null;
function keyboard(e: KeyboardEvent) {
  if (e.key === "Escape") emit("close");
  if (e.key === "Tab" && panel.value) {
    const all = Array.from(
      panel.value.querySelectorAll<HTMLElement>(
        'button,input,select,textarea,[tabindex="0"]',
      ),
    ).filter((x) => !x.hasAttribute("disabled"));
    const first = all[0],
      last = all[all.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last?.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first?.focus();
    }
  }
}
onMounted(() => {
  panel.value?.focus();
  document.addEventListener("keydown", keyboard);
});
onUnmounted(() => {
  document.removeEventListener("keydown", keyboard);
  previous?.focus();
});
</script>
<template>
  <Teleport to="body"
    ><div class="modal-backdrop" @click.self="emit('close')">
      <section
        ref="panel"
        tabindex="-1"
        class="modal"
        :class="{ wide }"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
      >
        <header>
          <h2>{{ title }}</h2>
          <button class="icon-button" @click="emit('close')" aria-label="关闭">
            ×
          </button>
        </header>
        <div class="modal-body"><slot /></div>
        <footer v-if="$slots.footer"><slot name="footer" /></footer>
      </section></div
  ></Teleport>
</template>
