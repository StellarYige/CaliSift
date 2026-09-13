import { createApp } from "vue";
import App from "./App.vue";
import "./style.css";
import { registerOffline } from "./offline";
createApp(App).mount("#app");
void registerOffline();
