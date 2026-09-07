<script setup lang="ts">
import { reactive } from "vue";
const props = defineProps<{ event: any }>();
const emit = defineEmits(["save", "cancel"]);
const value = reactive({
  ...props.event,
  notesText: (props.event.notes || []).join("\n"),
  next_day: !!props.event.end_date && props.event.end_date !== props.event.date,
});
function submit() {
  let ending = null;
  if (value.end && !value.all_day) {
    const d = new Date(value.date + "T00:00:00Z");
    if (value.next_day) d.setUTCDate(d.getUTCDate() + 1);
    ending = d.toISOString().slice(0, 10);
  }
  emit("save", {
    date: value.date || null,
    title: value.title,
    location: value.location || "",
    shift: value.shift || "",
    category: value.category || "其他",
    notes: value.notesText.split("\n").filter(Boolean),
    all_day: !!value.all_day,
    start: value.all_day ? null : value.start || null,
    end: value.all_day ? null : value.end || null,
    end_date: ending,
    precision:
      value.all_day || !value.start ? "date" : value.end ? "interval" : "point",
    status: value.status || "confirmed",
  });
}
</script>
<template>
  <form @submit.prevent="submit" class="form-grid">
    <label class="span-2"
      >事项<input
        v-model="value.title"
        required
        maxlength="2000"
        autofocus /></label
    ><label
      >日期<input
        v-model="value.date"
        type="date"
        :required="value.status !== 'pending'" /></label
    ><label
      >分类<select v-model="value.category">
        <option>工作</option>
        <option>学习</option>
        <option>培训</option>
        <option>考试</option>
        <option>休息</option>
        <option>其他</option>
      </select></label
    ><label
      >开始时间<input
        v-model="value.start"
        type="time"
        :disabled="value.all_day" /></label
    ><label
      >结束时间<input
        v-model="value.end"
        type="time"
        :disabled="value.all_day" /></label
    ><label class="check"
      ><input
        v-model="value.next_day"
        type="checkbox"
        :disabled="value.all_day"
      />次日结束</label
    ><label class="check"
      ><input v-model="value.all_day" type="checkbox" />明确设为全天</label
    ><label class="span-2"
      >地点<input v-model="value.location" maxlength="2000" /></label
    ><label>班次 / 符号<input v-model="value.shift" maxlength="1000" /></label
    ><label
      >核对状态<select v-model="value.status">
        <option value="confirmed">已核对</option>
        <option value="pending">待确认</option>
      </select></label
    ><label class="span-2"
      >备注<textarea v-model="value.notesText" rows="3" />
    </label>
    <div class="span-2 form-footer">
      <button type="button" class="secondary" @click="emit('cancel')">
        取消</button
      ><button class="primary" type="submit">保存修正</button>
    </div>
  </form>
</template>
