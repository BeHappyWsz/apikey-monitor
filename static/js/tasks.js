import { taskProgress } from "./state.js";
import { $, toast } from "./utils.js";

export function createTaskController({ api, load, openModal, closeModal, onTaskDone }) {
  let lastTask = null;

  async function startTask(task) {
    if (!task?.task_id) return;
    lastTask = task;
    openTask(task);
    for (;;) {
      await new Promise((resolve) => setTimeout(resolve, 700));
      task = await api("GET", `/api/tasks/${task.task_id}`);
      lastTask = task;
      openTask(task);
      if (taskProgress(task).terminal) {
        const total = Number(task.total || 0);
        const processed = Number(task.completed || 0);
        const failed = Number(task.failed || 0);
        const skipped = Number(task.skipped || 0);
        const ok = Math.max(0, processed - failed - skipped);
        toast(`???? ? ?? ${ok} ? ?? ${failed} ? ?? ${skipped} ? ? ${total}`, 4800);
        await load();
        return;
      }
    }
  }

  function openTask(task) {
    const progress = taskProgress(task);
    $("#task-title").textContent = task.kind === "check" ? "??????" : "????";
    const failed = Number(task.failed || 0);
    const skipped = Number(task.skipped || 0);
    const total = Number(task.total || 0);
    const processed = Number(task.completed || 0);
    if (progress.terminal) {
      const ok = Math.max(0, processed - failed - skipped);
      $("#task-message").textContent = `??? ? ?? ${ok} ? ?? ${failed} ? ?? ${skipped} ? ? ${total}`;
    } else {
      $("#task-message").textContent = `${progress.label}??? ${failed}??? ${skipped}`;
    }
    $("#task-progress-bar").style.width = `${progress.percent}%`;
    const foot = $("#task-foot");
    if (foot) foot.hidden = !progress.terminal;
    const problemsBtn = $("#btn-task-problems");
    if (problemsBtn) {
      problemsBtn.hidden = failed <= 0 && !progress.terminal;
      // Always offer "?????" after terminal so user can review non-up keys
      if (progress.terminal) problemsBtn.hidden = false;
    }
    openModal("modal-task", !progress.terminal);
  }

  $("#btn-task-problems")?.addEventListener("click", () => {
    closeModal?.("modal-task");
    onTaskDone?.({ filter: "problem", task: lastTask });
  });

  return { startTask };
}
