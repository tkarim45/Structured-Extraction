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
