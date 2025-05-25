document.addEventListener("DOMContentLoaded", () => {
  const saveButtons = document.querySelectorAll(".save-btn");

  saveButtons.forEach((btn) => {
    btn.addEventListener("click", async () => {
      const rowIndex = btn.dataset.rowIndex;
      const roleInput = btn.parentElement.querySelector(".role-input");
      const newRole = roleInput.value.trim();
      const filename = window.location.pathname.split("/").pop();

      if (!newRole) {
        showError("Role Assigned To cannot be empty");
        return;
      }

      try {
        const response = await fetch(`/api/update_role/${filename}`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            row_index: parseInt(rowIndex),
            role_assigned_to: newRole,
          }),
        });

        const data = await response.json();
        if (response.ok) {
          showSuccess("Role updated successfully");
          btn.textContent = "Saved";
          btn.disabled = true;
          setTimeout(() => {
            btn.textContent = "Save";
            btn.disabled = false;
          }, 2000);
        } else {
          showError(`Error: ${data.error}`);
        }
      } catch (error) {
        showError(`Error updating role: ${error.message}`);
        console.error("Error updating role:", error);
      }
    });
  });

  // Add save logic for Marked as Completed
  document.querySelectorAll(".save-marked-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const rowIndex = btn.dataset.rowIndex;
      const markedInput = btn.parentElement.querySelector(".marked-completed-input");
      const marked_completed = markedInput.value.trim();
      const filename = window.location.pathname.split("/").pop();
      try {
        const response = await fetch(`/api/update_work_status/${filename}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ row_index: parseInt(rowIndex), marked_completed }),
        });
        const data = await response.json();
        if (response.ok) {
          showSuccess("Marked as Completed updated successfully");
          btn.textContent = "Saved";
          btn.disabled = true;
          setTimeout(() => {
            btn.textContent = "Save";
            btn.disabled = false;
          }, 2000);
        } else {
          showError(`Error: ${data.error}`);
        }
      } catch (error) {
        showError(`Error updating Marked as Completed: ${error.message}`);
        console.error("Error updating Marked as Completed:", error);
      }
    });
  });

  document.querySelectorAll(".mark-completed-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const rowIndex = btn.dataset.rowIndex;
      const filename = window.location.pathname.split("/").pop();
      try {
        const response = await fetch(`/api/update_work_status/${filename}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ row_index: parseInt(rowIndex), marked_completed: "Yes" }),
        });
        const data = await response.json();
        if (response.ok) {
          // Replace button with 'Completed'
          btn.parentElement.innerHTML = "Completed";
          showSuccess("Marked as Completed!");
        } else {
          showError(`Error: ${data.error}`);
        }
      } catch (error) {
        showError(`Error updating Marked as Completed: ${error.message}`);
        console.error("Error updating Marked as Completed:", error);
      }
    });
  });

  // Toast notifications
  function showSuccess(message) {
    Toastify({
      text: message,
      duration: 3000,
      style: { background: "#059669" },
      position: "top-right",
    }).showToast();
  }

  function showError(message) {
    Toastify({
      text: message,
      duration: 5000,
      style: { background: "#dc2626" },
      position: "top-right",
    }).showToast();
  }
});
