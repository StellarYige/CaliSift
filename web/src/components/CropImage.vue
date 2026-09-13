<script setup lang="ts">
import { ref, watch, computed } from "vue";
const props = defineProps<{ src: string; initial?: any }>();
const emit = defineEmits(["change"]);
const rotation = ref(0),
  canvas = ref<HTMLCanvasElement>(),
  crop = ref([0, 0, 1, 1]),
  origin = ref<number[] | null>(null);
const cropStyle = computed(() => ({
  left: crop.value[0] * 100 + "%",
  top: crop.value[1] * 100 + "%",
  width: (crop.value[2] - crop.value[0]) * 100 + "%",
  height: (crop.value[3] - crop.value[1]) * 100 + "%",
}));
async function draw() {
  const image = new Image();
  image.src = props.src;
  await image.decode();
  const target = canvas.value;
  if (!target) return;
  const swap = rotation.value % 180 !== 0;
  const width = swap ? image.height : image.width,
    height = swap ? image.width : image.height;
  const scale = Math.min(1, 1000 / width);
  target.width = width * scale;
  target.height = height * scale;
  const ctx = target.getContext("2d")!;
  ctx.translate(target.width / 2, target.height / 2);
  ctx.rotate((rotation.value * Math.PI) / 180);
  ctx.drawImage(
    image,
    (-image.width * scale) / 2,
    (-image.height * scale) / 2,
    image.width * scale,
    image.height * scale,
  );
}
function update() {
  emit("change", { rotation: rotation.value, crop: crop.value });
}
function reset() {
  crop.value = [0, 0, 1, 1];
  update();
}
function point(e: PointerEvent) {
  const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
  return [
    Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)),
    Math.max(0, Math.min(1, (e.clientY - r.top) / r.height)),
  ];
}
function start(e: PointerEvent) {
  origin.value = point(e);
  (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
}
function move(e: PointerEvent) {
  if (!origin.value) return;
  const p = point(e);
  crop.value = [
    Math.min(p[0], origin.value[0]),
    Math.min(p[1], origin.value[1]),
    Math.max(p[0], origin.value[0]),
    Math.max(p[1], origin.value[1]),
  ];
}
function finish() {
  if (!origin.value) return;
  origin.value = null;
  if (
    crop.value[2] - crop.value[0] < 0.02 ||
    crop.value[3] - crop.value[1] < 0.02
  )
    reset();
  else update();
}
watch(
  () => props.src,
  () => {
    rotation.value = props.initial?.rotation || 0;
    crop.value = props.initial?.crop || [0, 0, 1, 1];
    draw();
  },
  { immediate: true, flush: "post" },
);
function rotate() {
  rotation.value = (rotation.value + 90) % 360;
  reset();
  draw();
}
</script>
<template>
  <div class="toolbar">
    <button class="secondary small" @click="rotate">↻ 旋转 90°</button
    ><button class="text-button" @click="reset">保留整张</button
    ><span class="muted">拖动框选，保留表头和姓名</span>
  </div>
  <div
    class="crop-stage"
    @pointerdown="start"
    @pointermove="move"
    @pointerup="finish"
    @pointercancel="finish"
  >
    <canvas ref="canvas" />
    <div class="crop-outline" :style="cropStyle" />
  </div>
</template>
