import { taskProgress } from "./state.js";
import { $, toast } from "./utils.js";

export function createTaskController({ api, load, openModal }) {
  async function startTask(task) {
    if (!task?.task_id) return;
    openTask(task);
    for (;;) {
      await new Promise((resolve) => setTimeout(resolve, 700));
      task = await api("GET", `/api/tasks/${task.task_id}`);
      openTask(task);
      if (taskProgress(task).terminal) {
        toast(task.status === "completed" ? "批量检测完成" : "批量检测已结束，部分项目失败");
        await load();
        return;
      }
    }
  }

  function openTask(task) {
    const progress = taskProgress(task);
    $("#task-title").textContent = task.kind === "check" ? "批量检测进度" : "任务进度";
    $("#task-message").textContent = `${progress.label}，失败 ${task.failed || 0}，跳过 ${task.skipped || 0}`;
    $("#task-progress-bar").style.width = `${progress.percent}%`;
    openModal("modal-task", !progress.terminal);
  }

  return { startTask };
}
