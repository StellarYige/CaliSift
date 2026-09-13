<script setup lang="ts">
import { ref, watch, nextTick } from "vue";
type Cell = { row: number; col: number; coordinate: string; text: string };
const props = defineProps<{
  table: {
    row: number;
    col: number;
    cells: Cell[][];
    sheets: { height: number; width: number }[];
  };
  sheetIndex: number;
  locate: string[];
  mappingOpen: boolean;
}>();
const emit = defineEmits<{
  pick: [cell: Cell];
  page: [row: number, col: number];
}>();
const container = ref<HTMLElement | null>(null);
watch(
  [() => props.table, () => props.locate],
  async () => {
    await nextTick();
    const target = container.value?.querySelector<HTMLElement>(
      `[data-coordinate="${props.locate[0] || ""}"]`,
    );
    if (target && container.value) {
      // Scroll the source pane itself without moving the whole workbench.
      const box = container.value.getBoundingClientRect(),
        cell = target.getBoundingClientRect();
      const rowHeader =
        target.parentElement?.querySelector("th")?.getBoundingClientRect()
          .width || 0;
      const left = box.left + rowHeader + 8;
      if (cell.top < box.top || cell.bottom > box.bottom)
        container.value.scrollTop += cell.top - box.top - 8;
      if (cell.left < left || cell.right > box.right)
        container.value.scrollLeft += cell.left - left;
    }
  },
  { immediate: true },
);
</script>
<template>
  <div class="table-scroll" ref="container">
    <table class="source-table">
      <tbody>
        <tr v-for="(line, i) in table.cells" :key="i">
          <th>{{ table.row + i + 1 }}</th>
          <td
            v-for="cell in line"
            :key="cell.col"
            :data-coordinate="cell.coordinate"
            :class="{
              highlight: locate.includes(cell.coordinate),
              pickable: mappingOpen,
            }"
            @click="emit('pick', cell)"
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
      @click="emit('page', Math.max(0, table.row - 50), table.col)"
      :disabled="!table.row"
    >
      ↑ 上 50 行</button
    ><button
      @click="emit('page', table.row + 50, table.col)"
      :disabled="table.row + 50 >= table.sheets[sheetIndex]!.height"
    >
      ↓ 下 50 行</button
    ><button
      @click="emit('page', table.row, Math.max(0, table.col - 20))"
      :disabled="!table.col"
    >
      ←</button
    ><button
      @click="emit('page', table.row, table.col + 20)"
      :disabled="table.col + 20 >= table.sheets[sheetIndex]!.width"
    >
      →
    </button>
  </div>
</template>
